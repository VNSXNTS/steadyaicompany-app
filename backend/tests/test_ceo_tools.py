"""Fase 7c: o CEO planeja e executa um roteiro de ferramentas reais, sem IA e sem custo."""
import shutil

import pytest

from app.models.entities import Approval, Task, TaskStatus
from app.services import agent_tools, ceo
from app.services.tasks import TaskError

needs_office = pytest.mark.skipif(not (shutil.which("soffice") or shutil.which("libreoffice")),
                                  reason="LibreOffice ausente")


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


class NoAI:
    def __getattr__(self, name):
        raise AssertionError("provedor de IA usado em roteiro de ferramentas")


def test_plan_wires_tool_inputs_and_dependencies(db):
    t = ceo.plan_goal(db, "Steady Payoff", "steady_payoff_build")
    assert [x.agent_key for x in t] == ["product_creator", "quality_guardian", "sales_manager", "cfo"]
    assert t[0].input["tool"] == "steady_payoff_xlsx" and t[0].depends_on == []
    assert t[1].input["tool"] == "review_xlsx" and t[1].input["product_task_id"] == t[0].id  # id real, não "$step"
    assert t[1].depends_on == [t[0].id] and t[2].depends_on == [t[1].id] and t[3].depends_on == [t[1].id]
    assert all(x.action is None for x in t)  # nenhuma etapa de risco


@needs_office
def test_ceo_runs_the_whole_tool_pipeline_without_ai_or_approvals(db):
    tasks = ceo.plan_goal(db, "Steady Payoff", "steady_payoff_build")
    ran = ceo.run_until_blocked(db, NoAI())
    assert len(ran) == 4 and all(db.get(Task, x.id).status == TaskStatus.COMPLETED for x in tasks)
    assert db.query(Approval).count() == 0
    review = db.get(Task, tasks[1].id).output["result"]
    assert review["verdict"] == "approved"
    report = ceo.executive_report(db)
    assert report["quality_rejected_tasks"] == [] and report["quality_gap_tasks"] == []
    assert report["attention_needed"] is False


def test_rejected_review_is_flagged_in_the_executive_report(db, artifacts):
    tasks = ceo.plan_goal(db, "Steady Payoff", "steady_payoff_build")
    ceo.run_next(db)  # gera a planilha
    path = artifacts / db.get(Task, tasks[0].id).output["files"][0]["path"]
    path.write_bytes(path.read_bytes() + b"x")  # adulterada depois de registrada
    ceo.run_until_blocked(db)
    assert db.get(Task, tasks[1].id).output["result"]["verdict"] == "rejected"
    report = ceo.executive_report(db)
    assert report["quality_rejected_tasks"] == [tasks[1].id] and report["attention_needed"] is True


def test_without_libreoffice_the_report_shows_the_gap(db, monkeypatch):
    monkeypatch.setattr(agent_tools, "_recalculate", lambda p: None)
    tasks = ceo.plan_goal(db, "Steady Payoff", "steady_payoff_build")
    ceo.run_until_blocked(db)
    report = ceo.executive_report(db)
    assert report["quality_gap_tasks"] == [tasks[1].id] and report["attention_needed"] is True


def test_unknown_pipeline_and_default_pipeline_are_unchanged(db):
    with pytest.raises(TaskError):
        ceo.plan_goal(db, "x y z", "inexistente")
    t = ceo.plan_goal(db, "debt planner")  # new_product continua com 10 etapas e sem ferramentas
    assert len(t) == 10 and all("tool" not in x.input for x in t) and t[-1].action == "publish_paid_ads"


def test_pipeline_over_api(client):
    r = client.post("/ceo/plan", json={"goal": "Steady Payoff", "pipeline": "steady_payoff_build"})
    assert r.status_code == 201 and len(r.json()) == 4
    assert client.post("/ceo/plan", json={"goal": "Steady Payoff", "pipeline": "nope"}).status_code == 400
