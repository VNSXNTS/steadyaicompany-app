"""Fase 7, 1º lote: ferramentas reais do CFO, Product Creator e Quality Guardian."""
import shutil

import pytest
from openpyxl import load_workbook

from app.models.entities import AuditLog, Sale, TaskStatus
from app.services import agent_tools
from app.services.tasks import create_task, run_task

needs_office = pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")),
                                  reason="LibreOffice ausente")


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


def _make(db, agent, tool, **extra):
    return create_task(db, agent, f"ferramenta {tool}", input={"tool": tool, **extra})


def _build(db):
    t = _make(db, "product_creator", "steady_payoff_xlsx")
    run_task(db, t)
    assert t.status == TaskStatus.COMPLETED, t.error
    return t


def _review(db, product):
    r = _make(db, "quality_guardian", "review_xlsx", product_task_id=product.id)
    run_task(db, r)
    return r


def test_product_creator_generates_traceable_file_with_formulas(db, artifacts):
    t = _build(db)
    rec = t.output["files"][0]
    path = artifacts / rec["path"]
    assert path.is_file() and rec["bytes"] == path.stat().st_size and len(rec["sha256"]) == 64
    wb = load_workbook(path)
    assert wb.sheetnames == ["Start Here", "Debts", "Income", "Plan", "Dashboard"]
    assert wb["Debts"]["F5"].value.startswith("=IF(") and wb["Dashboard"]["B3"].value == "=Debts!B20"
    assert "EXAMPLE" in wb["Debts"]["A2"].value
    assert db.query(AuditLog).filter_by(action="tool_run").count() == 1


@needs_office
def test_quality_guardian_approves_good_workbook_after_real_recalculation(db):
    r = _review(db, _build(db))
    assert r.status == TaskStatus.COMPLETED
    res = r.output["result"]
    assert res["verdict"] == "approved", res["checks"]
    assert all(c["status"] == "pass" for c in res["checks"]) and len(res["checks"]) == 8


@needs_office
def test_quality_guardian_rejects_formula_error(db, artifacts):
    t = _build(db)
    path = artifacts / t.output["files"][0]["path"]
    wb = load_workbook(path)
    wb["Dashboard"]["B3"] = "=1/0"
    wb.save(path)
    t.output = {**t.output, "files": [{**t.output["files"][0], "sha256": agent_tools._sha256(path)}]}  # hash válido
    db.commit()
    res = _review(db, t).output["result"]
    assert res["verdict"] == "rejected"
    failed = {c["name"] for c in res["checks"] if c["status"] == "fail"}
    assert "nenhuma fórmula com erro após recalcular" in failed


@needs_office
def test_quality_guardian_rejects_wrong_numbers_even_without_errors(db, artifacts):
    t = _build(db)
    path = artifacts / t.output["files"][0]["path"]
    wb = load_workbook(path)
    wb["Debts"]["E5"] = "=B5*C5/100"  # juros anual no lugar do mensal: sem erro, mas conta errada
    wb["Dashboard"]["B6"] = "=Debts!E20"
    wb["Dashboard"]["B5"] = "=Debts!C20+1"  # APR médio adulterado
    wb.save(path)
    t.output = {**t.output, "files": [{**t.output["files"][0], "sha256": agent_tools._sha256(path)}]}
    db.commit()
    res = _review(db, t).output["result"]
    assert res["verdict"] == "rejected"
    assert any(c["status"] == "fail" and "esperado" in c["name"] for c in res["checks"])


def test_quality_guardian_detects_tampered_file_by_hash(db, artifacts):
    t = _build(db)
    path = artifacts / t.output["files"][0]["path"]
    wb = load_workbook(path)
    wb["Debts"]["B5"] = 99999
    wb.save(path)  # arquivo mudou depois de registrado
    res = _review(db, t).output["result"]
    assert res["verdict"] == "rejected"
    assert {"SHA-256 confere com o registrado"} <= {c["name"] for c in res["checks"] if c["status"] == "fail"}


def test_without_libreoffice_gaps_are_reported_not_hidden(db, monkeypatch):
    t = _build(db)
    monkeypatch.setattr(agent_tools, "_recalculate", lambda path: None)
    r = _review(db, t)
    res = r.output["result"]
    assert res["verdict"] == "approved_with_gaps"  # nunca "approved" sem ter recalculado
    assert [c["status"] for c in res["checks"]].count("skipped") == 2
    assert "não executada" in r.output["notes"][0]


def test_review_refuses_path_outside_artifacts_and_missing_product(db, artifacts):
    t = _build(db)
    t.output = {**t.output, "files": [{**t.output["files"][0], "path": "../../etc/passwd"}]}
    db.commit()
    r = _review(db, t)
    assert r.status == TaskStatus.FAILED and "fora de ARTIFACTS_DIR" in r.error
    bad = _make(db, "quality_guardian", "review_xlsx", product_task_id=99999)
    run_task(db, bad)
    assert bad.status == TaskStatus.FAILED and "product_task_id" in bad.error


def test_agent_cannot_use_another_agents_tool(db):
    t = _make(db, "market_hunter", "steady_payoff_xlsx")
    run_task(db, t)
    assert t.status == TaskStatus.FAILED and "não tem a ferramenta" in t.error


def test_cfo_summary_has_null_margin_and_roi_without_basis(db):
    t = _make(db, "cfo", "financial_summary")
    run_task(db, t)
    res = t.output["result"]
    assert res["margin_percent"] is None and res["roi_percent"] is None and res["net_revenue_cents"] == 0
    assert any("Margem indisponível" in n for n in t.output["notes"])


def test_cfo_summary_net_revenue_and_profit_are_not_gross(db):
    db.add(Sale(product_id=None, gross_cents=10_000, fee_cents=500, refunded_cents=1_000))
    db.commit()
    t = _make(db, "cfo", "financial_summary")
    run_task(db, t)
    res = t.output["result"]
    assert res["gross_revenue_cents"] == 10_000 and res["net_revenue_cents"] == 8_500
    assert res["profit_cents"] == 8_500 and res["roi_percent"] is None  # sem despesa, ROI continua nulo


def test_tool_tasks_never_touch_the_ai_provider(db, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("provedor de IA chamado por tarefa de ferramenta")

    monkeypatch.setattr("app.services.tasks.get_provider", boom)
    t = _make(db, "cfo", "financial_summary")
    run_task(db, t)
    assert t.status == TaskStatus.COMPLETED


def test_tasks_without_tool_still_use_the_provider(db):
    t = create_task(db, "cfo", "resuma")
    run_task(db, t)
    assert t.output["provider"] == "mock" and "tool" not in t.output
