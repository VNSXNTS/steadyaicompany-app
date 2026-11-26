"""Ferramentas reais dos agentes (Fase 7, 1º lote): nada aqui chama IA, rede ou gasta dinheiro.

- cfo / financial_summary: números financeiros do banco (centavos; margem e ROI nulos sem base).
- product_creator / steady_payoff_xlsx: gera a planilha Steady Payoff com fórmulas e a registra (caminho + SHA-256).
- quality_guardian / review_xlsx: confere a planilha de verdade (arquivo, hash, fórmulas, erros, valores esperados).
- strategy / experiment_review, sales_manager / sales_report, competitor_analyst / offer_comparison (2º lote):
  só leem dados registrados ou informados na tarefa; dizem o que NÃO sabem.
- 3º lote: creative_director / creative_check, growth_strategist / growth_math, customer_success / refund_followup,
  social_media / content_calendar, product_architect / product_spec_check (também por regras, sem IA).

Uma tarefa só usa ferramenta se pedir explicitamente (`input.tool`); o roteiro do CEO continua como antes.
Todo arquivo gerado fica em ARTIFACTS_DIR e é rastreável pela saída da tarefa (caminho relativo, bytes, sha256).
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

import statistics

from sqlalchemy import func, select

from app.models.entities import Experiment, Product, Sale, Task, TaskStatus
from app.services import experiments, metrics

ERROR_VALUES = ("#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")
FIRST_ROW, LAST_ROW = 5, 19  # linhas de dívidas na aba Debts (15 vagas)

# Dados de EXEMPLO (marcados como tais na planilha). O cliente substitui pelos seus.
EXAMPLE_DEBTS = [("Example card A", 3200.0, 24.99, 96.0), ("Example card B", 1450.0, 19.99, 45.0),
                 ("Example car loan", 8200.0, 7.5, 240.0)]
EXAMPLE_INCOME = [2400.0, 3600.0, 1900.0, 3100.0, 2800.0, 2200.0]
EXAMPLE_ESSENTIALS = 1800.0


class ToolError(Exception):
    pass


def artifacts_dir() -> Path:
    return Path(os.getenv("ARTIFACTS_DIR", "storage/artifacts")).resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_record(path: Path) -> dict:
    return {"path": str(path.relative_to(artifacts_dir())), "bytes": path.stat().st_size, "sha256": _sha256(path)}


# ----------------------------------------------------------------------------------------- CFO
def financial_summary(db: Session, task: Task) -> dict:
    """Resumo financeiro real: receita bruta, taxas, reembolsos, lucro; margem e ROI ficam nulos sem base."""
    d = metrics.dashboard(db)
    keys = ("gross_revenue_cents", "fees_cents", "refunds_cents", "net_revenue_cents", "expenses_cents",
            "profit_cents", "margin_percent", "roi_percent", "sales_count")
    result = {k: d[k] for k in keys}
    notes = ["Receita líquida = bruta − taxas − reembolsos. Lucro = líquida − despesas. Faturamento não é lucro."]
    if result["margin_percent"] is None:
        notes.append("Margem indisponível: não há receita líquida positiva.")
    if result["roi_percent"] is None:
        notes.append("ROI indisponível: não há despesas registradas.")
    if result["sales_count"] == 0:
        notes.append("Nenhuma venda registrada; nada a concluir sobre desempenho.")
    return {"result": result, "notes": notes, "files": []}


# ------------------------------------------------------------------------------ Product Creator
def build_steady_payoff_workbook() -> Workbook:
    wb = Workbook()
    bold = Font(bold=True)
    head = PatternFill("solid", fgColor="DDE7F0")
    note = Font(italic=True, color="9C0006")

    s = wb.active
    s.title = "Start Here"
    lines = [
        "Steady Payoff — Debt Payoff Planner for variable income",
        "",
        "1. Debts tab: list each debt (balance, APR %, minimum payment). Replace the EXAMPLE rows with your own.",
        "2. Income tab: enter your last 6 months of income and your monthly essentials.",
        "3. Plan tab: pick Avalanche (highest APR first) or Snowball (smallest balance first).",
        "4. Dashboard tab: summary of your numbers.",
        "",
        "The extra payment is based on your 3 LOWEST months of income, so the plan holds up in a slow month.",
        "Months-to-payoff is an ESTIMATE for the target debt only; it does not re-allocate money after a debt is paid off.",
        "This tool is an educational calculator, not financial, legal or tax advice. Results are not guaranteed.",
        "Yellow cells are inputs. Everything else is calculated.",
    ]
    for i, text in enumerate(lines, 1):
        s.cell(i, 1, text)
    s["A1"].font = Font(bold=True, size=14)
    s.column_dimensions["A"].width = 110

    d = wb.create_sheet("Debts")
    d["A1"] = "Debts"; d["A1"].font = Font(bold=True, size=14)
    d["A2"] = "EXAMPLE DATA in the yellow cells — replace with your own debts."; d["A2"].font = note
    for col, title in enumerate(["Debt", "Balance ($)", "APR (%)", "Minimum payment ($)", "Monthly interest ($)",
                                 "Months to payoff at minimum", "Total interest at minimum ($)",
                                 "Avalanche rank", "Snowball rank"], 1):
        c = d.cell(4, col, title); c.font = bold; c.fill = head
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for i, (name, bal, apr, mn) in enumerate(EXAMPLE_DEBTS):
        r = FIRST_ROW + i
        d.cell(r, 1, name); d.cell(r, 2, bal); d.cell(r, 3, apr); d.cell(r, 4, mn)
    rng = lambda col: f"${col}${FIRST_ROW}:${col}${LAST_ROW}"  # noqa: E731
    for r in range(FIRST_ROW, LAST_ROW + 1):
        for col in "ABCD":
            d[f"{col}{r}"].fill = yellow
        d[f"E{r}"] = f'=IF(OR(B{r}="",B{r}<=0),"",B{r}*C{r}/100/12)'
        d[f"F{r}"] = (f'=IF(OR(B{r}="",B{r}<=0),"",IF(D{r}<=E{r},"Payment too low",'
                      f'NPER(C{r}/100/12,-D{r},B{r})))')
        d[f"G{r}"] = f'=IF(ISNUMBER(F{r}),D{r}*F{r}-B{r},"")'
        d[f"H{r}"] = (f'=IF(OR(B{r}="",B{r}<=0),"",COUNTIFS({rng("B")},">0",{rng("C")},">"&C{r})'
                      f'+COUNTIFS($B${FIRST_ROW}:B{r},">0",$C${FIRST_ROW}:C{r},C{r}))')
        d[f"I{r}"] = (f'=IF(OR(B{r}="",B{r}<=0),"",COUNTIFS({rng("B")},">0",{rng("B")},"<"&B{r})'
                      f'+COUNTIFS($B${FIRST_ROW}:B{r},">0",$B${FIRST_ROW}:B{r},B{r}))')
    t = LAST_ROW + 1
    d[f"A{t}"] = "Total"; d[f"A{t}"].font = bold
    d[f"B{t}"] = f"=SUM(B{FIRST_ROW}:B{LAST_ROW})"
    d[f"C{t}"] = f'=IF(B{t}>0,SUMPRODUCT(B{FIRST_ROW}:B{LAST_ROW},C{FIRST_ROW}:C{LAST_ROW})/B{t},"")'
    d[f"D{t}"] = f"=SUM(D{FIRST_ROW}:D{LAST_ROW})"
    d[f"E{t}"] = f"=SUM(E{FIRST_ROW}:E{LAST_ROW})"
    for col, w in zip("ABCDEFGHI", (24, 14, 10, 20, 20, 26, 28, 15, 15)):
        d.column_dimensions[col].width = w

    inc = wb.create_sheet("Income")
    inc["A1"] = "Income (variable income friendly)"; inc["A1"].font = Font(bold=True, size=14)
    inc["A2"] = "EXAMPLE DATA in the yellow cells — replace with your own."; inc["A2"].font = note
    inc["A3"] = "Income by month (last 6 months)"; inc["A3"].font = bold
    for i, v in enumerate(EXAMPLE_INCOME):
        inc.cell(4 + i, 1, f"Month {i + 1}"); inc.cell(4 + i, 2, v).fill = yellow
    inc["A12"] = "Monthly essentials (rent, food, utilities…)"; inc["B12"] = EXAMPLE_ESSENTIALS
    inc["B12"].fill = yellow
    inc["A14"] = "Average income"; inc["B14"] = '=IF(COUNT(B4:B9)=0,"",AVERAGE(B4:B9))'
    inc["A15"] = "Lowest month"; inc["B15"] = '=IF(COUNT(B4:B9)=0,"",MIN(B4:B9))'
    inc["A16"] = "Conservative income (avg of 3 lowest months)"
    inc["B16"] = '=IF(COUNT(B4:B9)<3,"",(SMALL(B4:B9,1)+SMALL(B4:B9,2)+SMALL(B4:B9,3))/3)'
    inc["A17"] = "Total minimum payments"; inc["B17"] = f"=Debts!D{t}"
    inc["A18"] = "Extra available for debt (conservative)"
    inc["B18"] = '=IF(OR(B16="",B12=""),"",MAX(0,B16-B12-B17))'
    inc["A18"].font = bold
    inc.column_dimensions["A"].width = 46; inc.column_dimensions["B"].width = 16

    p = wb.create_sheet("Plan")
    p["A1"] = "Plan"; p["A1"].font = Font(bold=True, size=14)
    p["A3"] = "Strategy"; p["B3"] = "Avalanche"; p["B3"].fill = yellow
    dv = DataValidation(type="list", formula1='"Avalanche,Snowball"', allow_blank=False)
    p.add_data_validation(dv); dv.add("B3")
    p["A4"] = "Target debt row (rank 1)"
    p["B4"] = (f'=IFERROR(IF(B3="Avalanche",MATCH(1,Debts!H{FIRST_ROW}:H{LAST_ROW},0),'
               f'MATCH(1,Debts!I{FIRST_ROW}:I{LAST_ROW},0)),"")')
    p["A5"] = "Target debt"; p["B5"] = f'=IF(B4="","",INDEX(Debts!A{FIRST_ROW}:A{LAST_ROW},B4))'
    p["A6"] = "Target debt minimum payment ($)"; p["B6"] = f'=IF(B4="","",INDEX(Debts!D{FIRST_ROW}:D{LAST_ROW},B4))'
    p["A7"] = "Extra available ($)"; p["B7"] = "=Income!B18"
    p["A8"] = "Total payment on target debt ($)"; p["B8"] = '=IF(OR(B6="",B7=""),"",B6+B7)'
    p["A9"] = "Estimated months to pay off target debt"
    p["B9"] = (f'=IF(OR(B4="",B8=""),"",IF(B8<=INDEX(Debts!E{FIRST_ROW}:E{LAST_ROW},B4),"Payment too low",'
               f'NPER(INDEX(Debts!C{FIRST_ROW}:C{LAST_ROW},B4)/100/12,-B8,INDEX(Debts!B{FIRST_ROW}:B{LAST_ROW},B4))))')
    p["A10"] = "Estimate only: does not re-allocate money after a debt is paid off."; p["A10"].font = note
    p["A12"] = "Payoff order"; p["A12"].font = bold
    for n in range(1, 16):
        p.cell(12 + n, 1, n)
        p.cell(12 + n, 2, (f'=IFERROR(INDEX(Debts!A{FIRST_ROW}:A{LAST_ROW},IF($B$3="Avalanche",'
                           f'MATCH(A{12 + n},Debts!H{FIRST_ROW}:H{LAST_ROW},0),'
                           f'MATCH(A{12 + n},Debts!I{FIRST_ROW}:I{LAST_ROW},0))),"")'))
    p.column_dimensions["A"].width = 44; p.column_dimensions["B"].width = 22

    k = wb.create_sheet("Dashboard")
    k["A1"] = "Dashboard"; k["A1"].font = Font(bold=True, size=14)
    rows = [("Total debt ($)", f"=Debts!B{t}"), ("Total minimum payments ($)", f"=Debts!D{t}"),
            ("Weighted average APR (%)", f"=Debts!C{t}"), ("Interest accruing per month ($)", f"=Debts!E{t}"),
            ("Extra available per month ($)", "=Income!B18"), ("Target debt", "=Plan!B5"),
            ("Estimated months to pay off target debt", "=Plan!B9")]
    for i, (label, formula) in enumerate(rows):
        k.cell(3 + i, 1, label); k.cell(3 + i, 2, formula)
    k.column_dimensions["A"].width = 44; k.column_dimensions["B"].width = 18
    return wb


def steady_payoff_xlsx(db: Session, task: Task) -> dict:
    """Gera a planilha Steady Payoff com fórmulas e guarda o arquivo com SHA-256."""
    out = artifacts_dir() / f"task-{task.id}"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "Steady-Payoff-Debt-Planner.xlsx"
    build_steady_payoff_workbook().save(path)
    return {"result": {"note": "Planilha gerada com dados de EXEMPLO identificados; o quality_guardian deve revisá-la."},
            "notes": [], "files": [_file_record(path)]}


# ------------------------------------------------------------------------------ Quality Guardian
def _expected() -> dict:
    """Valores esperados calculados em Python, independentes das fórmulas da planilha."""
    balances = [d[1] for d in EXAMPLE_DEBTS]
    mins = [d[3] for d in EXAMPLE_DEBTS]
    low3 = sum(sorted(EXAMPLE_INCOME)[:3]) / 3
    extra = max(0.0, low3 - EXAMPLE_ESSENTIALS - sum(mins))
    top = max(EXAMPLE_DEBTS, key=lambda d: d[2])  # Avalanche: maior APR
    rate = top[2] / 100 / 12
    pay = top[3] + extra
    import math
    months = math.log(pay / (pay - rate * top[1])) / math.log(1 + rate)
    return {"total_debt": sum(balances), "total_min": sum(mins),
            "weighted_apr": sum(d[1] * d[2] for d in EXAMPLE_DEBTS) / sum(balances),
            "extra": extra, "target": top[0], "months": months}


def _recalculate(path: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    tmp = Path(tempfile.mkdtemp())
    proc = subprocess.run([soffice, "--headless", f"-env:UserInstallation=file://{tmp}/profile",
                           "--convert-to", "xlsx", "--outdir", str(tmp / "out"), str(path)],
                          capture_output=True, timeout=120)
    out = tmp / "out" / path.name
    return out if proc.returncode == 0 and out.exists() else None


def review_xlsx(db: Session, task: Task) -> dict:
    """Revisa a planilha gerada (fórmulas, abas, erros) a partir de product_task_id."""
    ref = (task.input or {}).get("product_task_id")
    product = db.get(Task, ref) if isinstance(ref, int) else None
    if product is None or product.status != TaskStatus.COMPLETED or not (product.output or {}).get("files"):
        raise ToolError("Informe input.product_task_id de uma tarefa concluída que gerou arquivos")
    record = product.output["files"][0]
    root = artifacts_dir()
    path = (root / record["path"]).resolve()
    if root not in path.parents:
        raise ToolError("Caminho fora de ARTIFACTS_DIR recusado")
    checks: list[dict] = []

    def check(name: str, ok: bool | None, detail: str = ""):
        checks.append({"name": name, "status": "skipped" if ok is None else ("pass" if ok else "fail"),
                       "detail": detail})

    check("arquivo existe", path.is_file())
    if not path.is_file():
        return _verdict(checks, record)
    check("SHA-256 confere com o registrado", _sha256(path) == record["sha256"])
    wb = load_workbook(path)
    want = ["Start Here", "Debts", "Income", "Plan", "Dashboard"]
    check("abas esperadas", wb.sheetnames == want, f"encontradas: {wb.sheetnames}")
    formulas = sum(1 for ws in wb for row in ws.iter_rows() for c in row
                   if isinstance(c.value, str) and c.value.startswith("="))
    check("tem fórmulas (não é só texto)", formulas >= 50, f"{formulas} fórmulas")
    text = " ".join(str(c.value) for row in wb["Start Here"].iter_rows() for c in row if c.value)
    check("aviso de que não é aconselhamento financeiro", "not financial" in text)
    check("dados de exemplo identificados", "EXAMPLE" in str(wb["Debts"]["A2"].value))

    recalculated = _recalculate(path)
    if recalculated is None:
        check("recálculo e erros de fórmula", None, "LibreOffice não encontrado: NÃO verificado")
        check("valores calculados batem com o esperado", None, "NÃO verificado (sem recálculo)")
        return _verdict(checks, record)
    ws = load_workbook(recalculated, data_only=True)
    errors = [f"{s.title}!{c.coordinate}={c.value}" for s in ws for row in s.iter_rows() for c in row
              if isinstance(c.value, str) and c.value in ERROR_VALUES]
    check("nenhuma fórmula com erro após recalcular", not errors, ", ".join(errors[:10]))
    exp = _expected()
    k = ws["Dashboard"]
    got = {"total_debt": k["B3"].value, "total_min": k["B4"].value, "weighted_apr": k["B5"].value,
           "extra": k["B7"].value, "target": k["B8"].value, "months": k["B9"].value}
    bad = []
    for key, want_v in exp.items():
        g = got[key]
        ok = (g == want_v) if isinstance(want_v, str) else (isinstance(g, (int, float)) and abs(g - want_v) < 0.01)
        if not ok:
            bad.append(f"{key}: planilha={g!r} esperado={want_v!r}")
    check("valores calculados batem com o esperado (cálculo independente em Python)", not bad, "; ".join(bad))
    return _verdict(checks, record)


def _verdict(checks: list[dict], record: dict) -> dict:
    failed = [c for c in checks if c["status"] == "fail"]
    skipped = [c for c in checks if c["status"] == "skipped"]
    verdict = "rejected" if failed else ("approved_with_gaps" if skipped else "approved")
    notes = [f"{len(skipped)} verificação(ões) não executada(s)"] if skipped else []
    return {"result": {"verdict": verdict, "checks": checks, "reviewed_file": record}, "notes": notes, "files": []}


# ------------------------------------------------------------------------------- 2º lote
MIN_SALES_FOR_CONFIDENCE = 30  # heurística nossa (não é regra estatística): abaixo disso, confiança baixa
HIGH_REFUND_RATE_PERCENT = 10  # heurística nossa para sinalizar atenção, não um padrão de mercado


def experiment_review(db: Session, task: Task) -> dict:
    """Chief Strategy Officer: reaproveita as regras de `experiments` e acrescenta nível de confiança e riscos.
    Não decide nada: gasto e escala continuam exigindo aprovação do proprietário."""
    ref = (task.input or {}).get("experiment_id")
    exp = db.get(Experiment, ref) if isinstance(ref, int) else None
    if exp is None:
        raise ToolError("Informe input.experiment_id de um experimento existente")
    m = experiments.metrics(db, exp)
    sales = m["sales_count"]
    confidence = "baixa" if sales < max(exp.min_sales_to_decide, 1) else (
        "média" if sales < MIN_SALES_FOR_CONFIDENCE else "mais alta")
    risks = list(m["warnings"])
    if sales < MIN_SALES_FOR_CONFIDENCE:
        risks.append(f"Amostra pequena ({sales} venda(s)): o CPA pode mudar bastante com mais dados.")
    if m["refunded_cents"] > 0:
        risks.append("Há reembolsos registrados; o ponto de equilíbrio não os estima.")
    return {"result": {"experiment_id": exp.id, "recommendation": m["action"], "reason": m["reason"],
                       "confidence": confidence, "risks": risks,
                       "cpa_cents": m["cpa_cents"], "break_even_cpa_cents": m["break_even_cpa_cents"],
                       "spend_cents": m["spend_cents"], "sales_count": sales, "profit_cents": m["profit_cents"],
                       "roi_percent": m["roi_percent"]},
            "notes": ["Recomendação por regras sobre dados registrados; não garante lucro. "
                      "Gastar ou escalar exige aprovação do proprietário."], "files": []}


def sales_report(db: Session, task: Task) -> dict:
    """Sales Manager: vendas e reembolsos por produto, só com o que está registrado (sem dados de funil)."""
    rows = db.execute(
        select(Sale.product_id, func.count(Sale.id), func.coalesce(func.sum(Sale.gross_cents), 0),
               func.coalesce(func.sum(Sale.fee_cents), 0), func.coalesce(func.sum(Sale.refunded_cents), 0))
        .group_by(Sale.product_id).order_by(Sale.product_id)
    ).all()
    names = {p.id: p.name for p in db.scalars(select(Product)).all()}
    products, flags = [], []
    for pid, n, gross, fees, refunded in rows:
        refund_rate = round(refunded / gross * 100, 2) if gross > 0 else None
        name = names.get(pid, "sem produto")
        products.append({"product": name, "sales_count": int(n), "gross_cents": int(gross),
                         "net_revenue_cents": int(gross - fees - refunded), "refund_rate_percent": refund_rate})
        if refund_rate is not None and refund_rate > HIGH_REFUND_RATE_PERCENT:
            flags.append(f"{name}: reembolsos de {refund_rate}% da receita bruta (acima de {HIGH_REFUND_RATE_PERCENT}%)")
    notes = ["Conversão e abandono de funil NÃO são calculados: o sistema não recebe visitas nem cliques."]
    if not products:
        notes.append("Nenhuma venda registrada; nada a reportar.")
    return {"result": {"products": products, "flags": flags}, "notes": notes, "files": []}


def offer_comparison(db: Session, task: Task) -> dict:
    """Competitor Analyst: compara APENAS as ofertas informadas em input.offers (não coleta nada da internet)."""
    offers = (task.input or {}).get("offers")
    if not isinstance(offers, list) or not offers:
        raise ToolError("Informe input.offers: lista de {name, price_cents, bonuses?, source?}")
    clean = []
    for o in offers:
        if not isinstance(o, dict) or not str(o.get("name", "")).strip():
            raise ToolError("Cada oferta precisa de name")
        price = o.get("price_cents")
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            raise ToolError(f"price_cents inválido na oferta {o.get('name')!r} (inteiro em centavos, >= 0)")
        bonuses = o.get("bonuses") or []
        if not isinstance(bonuses, list):
            raise ToolError(f"bonuses deve ser lista na oferta {o['name']!r}")
        clean.append({"name": str(o["name"]).strip(), "price_cents": price, "bonus_count": len(bonuses),
                      "source": str(o.get("source", "")).strip()})
    prices = [o["price_cents"] for o in clean]
    notes = ["Baseado somente nas ofertas informadas; nada foi coletado da internet nem verificado."]
    if len(clean) < 3:
        notes.append(f"Apenas {len(clean)} oferta(s): confiança baixa para falar em faixa de mercado.")
    if any(not o["source"] for o in clean):
        notes.append("Há ofertas sem fonte informada; não dá para conferir a origem do dado.")
    return {"result": {"offers": clean, "count": len(clean), "min_price_cents": min(prices),
                       "median_price_cents": int(statistics.median(prices)), "max_price_cents": max(prices),
                       "offers_with_bonuses": sum(1 for o in clean if o["bonus_count"] > 0)},
            "notes": notes, "files": []}


# ------------------------------------------------------------------------------ 3º lote
# Frases que prometem resultado garantido ou simulam prova social. Lista NOSSA (heurística), não é revisão jurídica.
RISKY_PHRASES = ("guaranteed", "guarantee you", "100% sure", "risk-free", "get out of debt in", "overnight",
                 "no effort", "while you sleep", "as seen on", "doctors hate", "testimonial", "real customer")
HEADLINE_MAX = 90  # heurística nossa para título de anúncio


def _text_field(task: Task, name: str) -> str:
    v = (task.input or {}).get(name)
    if not isinstance(v, str) or not v.strip():
        raise ToolError(f"Informe input.{name} (texto)")
    return v.strip()


def creative_check(db: Session, task: Task) -> dict:
    """Creative Director: confere um texto de criativo informado contra regras de honestidade. Não escreve o texto."""
    headline = _text_field(task, "headline")
    body = str((task.input or {}).get("body") or "").strip()
    text = f"{headline} {body}".lower()
    findings = [f"Frase de risco encontrada: {ph!r} (promessa garantida ou prova social suspeita)"
                for ph in RISKY_PHRASES if ph in text]
    if len(headline) > HEADLINE_MAX:
        findings.append(f"Título com {len(headline)} caracteres (limite sugerido: {HEADLINE_MAX})")
    if body and "results vary" not in text and "not typical" not in text:
        findings.append("Sem aviso de que os resultados variam; inclua se o texto fala de resultado financeiro")
    return {"result": {"approved": not findings, "findings": findings, "headline_length": len(headline)},
            "notes": ["Verificação por lista de frases nossa; não substitui revisão das regras da plataforma de "
                      "anúncios nem revisão jurídica. Publicar anúncio exige aprovação do proprietário."],
            "files": []}


def growth_math(db: Session, task: Task) -> dict:
    """Growth Strategist: ponto de equilíbrio por venda e vendas necessárias para um orçamento de teste. Sem previsão."""
    i = task.input or {}
    for k in ("price_cents", "test_budget_cents"):
        if isinstance(i.get(k), bool) or not isinstance(i.get(k), int) or i[k] <= 0:
            raise ToolError(f"Informe input.{k}: inteiro em centavos, maior que zero")
    fee_pct = i.get("fee_percent", 0)
    fee_fixed = i.get("fee_fixed_cents", 0)
    if isinstance(fee_pct, bool) or not isinstance(fee_pct, (int, float)) or not 0 <= fee_pct < 100:
        raise ToolError("fee_percent deve estar entre 0 e 100")
    if isinstance(fee_fixed, bool) or not isinstance(fee_fixed, int) or fee_fixed < 0:
        raise ToolError("fee_fixed_cents deve ser inteiro >= 0")
    net = i["price_cents"] - round(i["price_cents"] * fee_pct / 100) - fee_fixed
    if net <= 0:
        raise ToolError("Preço não cobre as taxas informadas: receita líquida por venda <= 0")
    sales_to_recover = -(-i["test_budget_cents"] // net)  # teto
    return {"result": {"net_per_sale_cents": net, "break_even_cpa_cents": net,
                       "sales_to_recover_budget": sales_to_recover,
                       "test_budget_cents": i["test_budget_cents"]},
            "notes": ["Conta direta sobre os números informados; ignora reembolsos e não prevê conversão nem vendas. "
                      "Gastar o orçamento exige aprovação do proprietário."], "files": []}


def refund_followup(db: Session, task: Task) -> dict:
    """Customer Success: lista vendas com reembolso para acompanhamento. O sistema não guarda dados do cliente."""
    rows = db.execute(select(Sale.id, Sale.product_id, Sale.gross_cents, Sale.refunded_cents)
                      .where(Sale.refunded_cents > 0).order_by(Sale.id)).all()
    total_sales = db.scalar(select(func.count(Sale.id))) or 0
    items = [{"sale_id": r[0], "product_id": r[1], "gross_cents": r[2], "refunded_cents": r[3],
              "full_refund": r[3] >= r[2]} for r in rows]
    return {"result": {"refunded_sales": items, "refunded_count": len(items), "total_sales": int(total_sales),
                       "refund_count_rate_percent": round(len(items) / total_sales * 100, 2) if total_sales else None},
            "notes": ["Motivo do reembolso e dados do cliente NÃO são registrados; não dá para analisar causas. "
                      "Mensagens sensíveis ao cliente exigem aprovação do proprietário."], "files": []}


def content_calendar(db: Session, task: Task) -> dict:
    """Social Media Manager: monta uma grade de rascunhos a partir dos temas informados. Nada é publicado."""
    from datetime import date, timedelta
    i = task.input or {}
    topics = i.get("topics")
    if not isinstance(topics, list) or not topics or any(not isinstance(t, str) or not t.strip() for t in topics):
        raise ToolError("Informe input.topics: lista de textos não vazios")
    try:
        start = date.fromisoformat(str(i.get("start_date")))
    except ValueError:
        raise ToolError("Informe input.start_date no formato AAAA-MM-DD") from None
    per_week = i.get("posts_per_week", 3)
    if isinstance(per_week, bool) or not isinstance(per_week, int) or not 1 <= per_week <= 7:
        raise ToolError("posts_per_week deve ser inteiro de 1 a 7")
    days = [round(k * 7 / per_week) for k in range(per_week)]
    posts = []
    for n, topic in enumerate(topics):
        week, slot = divmod(n, per_week)
        posts.append({"date": (start + timedelta(days=week * 7 + days[slot])).isoformat(),
                      "topic": topic.strip(), "status": "draft"})
    return {"result": {"posts": posts, "count": len(posts)},
            "notes": ["Só datas e temas; o texto de cada post não foi escrito. Nada foi publicado e "
                      "publicar exige aprovação do proprietário."], "files": []}


SPEC_FIELDS = ("name", "promise", "audience", "refund_policy")


def product_spec_check(db: Session, task: Task) -> dict:
    """Product Architect: confere se a especificação de produto informada está completa e coerente."""
    spec = (task.input or {}).get("spec")
    if not isinstance(spec, dict):
        raise ToolError("Informe input.spec: objeto com name, promise, audience, price_cents, deliverables, refund_policy")
    missing = [f for f in SPEC_FIELDS if not str(spec.get(f, "")).strip()]
    issues = [f"Campo ausente ou vazio: {f}" for f in missing]
    price = spec.get("price_cents")
    if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
        issues.append("price_cents deve ser inteiro em centavos, maior que zero")
    deliverables = spec.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables or any(not str(d).strip() for d in deliverables):
        issues.append("deliverables deve listar ao menos 1 entregável não vazio")
    return {"result": {"complete": not issues, "issues": issues},
            "notes": ["Confere só a completude da especificação; não avalia se o produto vende nem se o preço é bom."],
            "files": []}


# ----------------------------------------------------------------------------------- despacho
TOOLS = {
    ("cfo", "financial_summary"): financial_summary,
    ("product_creator", "steady_payoff_xlsx"): steady_payoff_xlsx,
    ("quality_guardian", "review_xlsx"): review_xlsx,
    ("strategy", "experiment_review"): experiment_review,
    ("sales_manager", "sales_report"): sales_report,
    ("competitor_analyst", "offer_comparison"): offer_comparison,
    ("creative_director", "creative_check"): creative_check,
    ("growth_strategist", "growth_math"): growth_math,
    ("customer_success", "refund_followup"): refund_followup,
    ("social_media", "content_calendar"): content_calendar,
    ("product_architect", "product_spec_check"): product_spec_check,
}


def resolve_artifact(record: dict) -> Path:
    """Caminho do arquivo gerado, com tudo conferido ANTES de servir: dentro de ARTIFACTS_DIR, existente e com o
    mesmo SHA-256 registrado na geração. O caminho vem do registro da tarefa, nunca de quem pede o download."""
    base = artifacts_dir()
    path = (base / str(record.get("path", ""))).resolve()
    if base not in path.parents:
        raise ToolError("Caminho fora de ARTIFACTS_DIR recusado")
    if not path.is_file():
        raise ToolError("Arquivo não encontrado no armazenamento")
    if _sha256(path) != record.get("sha256"):
        raise ToolError("O arquivo mudou desde que foi gerado (SHA-256 diferente); download recusado")
    return path


def list_tools() -> list[dict]:
    """Ferramentas disponíveis por agente, com a primeira linha da descrição de cada uma."""
    return [{"agent_key": a, "tool": t, "summary": ((fn.__doc__ or "").strip().splitlines() or [""])[0]}
            for (a, t), fn in sorted(TOOLS.items())]


def run_tool(db: Session, task: Task, agent_key: str, tool: str) -> dict:
    fn = TOOLS.get((agent_key, tool))
    if fn is None:
        raise ToolError(f"O agente {agent_key} não tem a ferramenta {tool!r}")
    return {"tool": tool, **fn(db, task)}
