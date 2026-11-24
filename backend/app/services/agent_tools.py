"""Ferramentas reais dos agentes (Fase 7, 1º lote): nada aqui chama IA, rede ou gasta dinheiro.

- cfo / financial_summary: números financeiros do banco (centavos; margem e ROI nulos sem base).
- product_creator / steady_payoff_xlsx: gera a planilha Steady Payoff com fórmulas e a registra (caminho + SHA-256).
- quality_guardian / review_xlsx: confere a planilha de verdade (arquivo, hash, fórmulas, erros, valores esperados).

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

from app.models.entities import Task, TaskStatus
from app.services import metrics

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


# ----------------------------------------------------------------------------------- despacho
TOOLS = {
    ("cfo", "financial_summary"): financial_summary,
    ("product_creator", "steady_payoff_xlsx"): steady_payoff_xlsx,
    ("quality_guardian", "review_xlsx"): review_xlsx,
}


def run_tool(db: Session, task: Task, agent_key: str, tool: str) -> dict:
    fn = TOOLS.get((agent_key, tool))
    if fn is None:
        raise ToolError(f"O agente {agent_key} não tem a ferramenta {tool!r}")
    return {"tool": tool, **fn(db, task)}
