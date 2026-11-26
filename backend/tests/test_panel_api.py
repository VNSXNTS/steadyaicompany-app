"""Fase 11: rotas de apoio do painel (ferramentas, roteiros, download seguro de arquivos, checklist)."""
import hashlib
from pathlib import Path

import pytest

from app.models.entities import Task, TaskStatus
from app.services import agent_tools, ceo
from app.services.tasks import create_task, run_task


@pytest.fixture(autouse=True)
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "art"))
    return tmp_path / "art"


def build_xlsx_task(db):
    t = create_task(db, "product_creator", "gerar planilha", input={"tool": "steady_payoff_xlsx"})
    run_task(db, t)
    assert t.status == TaskStatus.COMPLETED and t.output["files"]
    return t


# ---- listas ----
def test_agent_tools_lists_every_registered_tool_with_summary(client):
    d = client.get("/agent-tools").json()
    assert len(d) == len(agent_tools.TOOLS) == 11
    assert {"agent_key": "product_creator", "tool": "steady_payoff_xlsx"}.items() <= next(
        x for x in d if x["tool"] == "steady_payoff_xlsx").items()
    assert all(x["summary"] for x in d)


def test_pipelines_describe_steps_and_flag_the_risky_one(client):
    d = {p["key"]: p for p in client.get("/ceo/pipelines").json()}
    assert set(d) == set(ceo.PIPELINES)
    assert d["new_product"]["steps"][-1] == {"agent_key": "growth_strategist", "risky": True}
    assert d["new_product"]["uses_tools"] is False
    assert d["steady_payoff_build"]["uses_tools"] is True
    assert not any(s["risky"] for s in d["steady_payoff_build"]["steps"])  # roteiro de ferramentas nunca é de risco
    assert "sem custo" in d["steady_payoff_build"]["label"]


def test_launch_checklist_exposes_items_and_minimum_angles(client):
    from app.services import experiments
    d = client.get("/experiments/launch-checklist").json()
    assert d["items"] == experiments.LAUNCH_CHECKLIST and d["min_creative_angles"] == experiments.MIN_CREATIVE_ANGLES


# ---- download de arquivo ----
def test_download_returns_the_exact_generated_file(client, db):
    t = build_xlsx_task(db)
    r = client.get(f"/tasks/{t.id}/files/0")
    assert r.status_code == 200
    assert hashlib.sha256(r.content).hexdigest() == t.output["files"][0]["sha256"]
    assert len(r.content) == t.output["files"][0]["bytes"]
    assert "attachment" in r.headers["content-disposition"] and ".xlsx" in r.headers["content-disposition"]
    assert "spreadsheetml" in r.headers["content-type"]


@pytest.mark.parametrize("index", [1, -1, 99])
def test_download_index_out_of_range_is_404(client, db, index):
    t = build_xlsx_task(db)
    assert client.get(f"/tasks/{t.id}/files/{index}").status_code == 404


def test_download_task_without_files_or_missing_is_404(client, db):
    t = create_task(db, "cfo", "resumo", input={"tool": "financial_summary"})
    run_task(db, t)
    assert client.get(f"/tasks/{t.id}/files/0").status_code == 404
    assert client.get("/tasks/9999/files/0").status_code == 404


def test_download_refuses_a_file_changed_after_generation(client, db, artifacts):
    t = build_xlsx_task(db)
    f = artifacts / t.output["files"][0]["path"]
    f.write_bytes(f.read_bytes() + b"x")
    r = client.get(f"/tasks/{t.id}/files/0")
    assert r.status_code == 409 and "SHA-256" in r.json()["detail"]


def test_download_refuses_path_traversal_even_if_the_record_is_tampered(client, db, artifacts, tmp_path):
    outside = tmp_path / "segredo.txt"
    outside.write_text("conteudo fora do armazenamento")
    t = build_xlsx_task(db)
    out = dict(t.output)
    out["files"] = [{"path": "../segredo.txt", "bytes": 1, "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}]
    t.output = out
    db.commit()
    r = client.get(f"/tasks/{t.id}/files/0")
    assert r.status_code == 409 and "fora" in r.json()["detail"] and b"segredo" not in r.content


def test_download_missing_file_is_409(client, db, artifacts):
    t = build_xlsx_task(db)
    (artifacts / t.output["files"][0]["path"]).unlink()
    r = client.get(f"/tasks/{t.id}/files/0")
    assert r.status_code == 409 and "não encontrado" in r.json()["detail"]


def test_new_routes_require_authentication(client, db):
    from fastapi.testclient import TestClient
    from app.main import app
    t = build_xlsx_task(db)
    with TestClient(app) as anon:
        for url in ("/agent-tools", "/ceo/pipelines", f"/tasks/{t.id}/files/0", "/experiments/launch-checklist"):
            assert anon.get(url).status_code == 401, url


def test_resolve_artifact_unit(artifacts):
    artifacts.mkdir(parents=True)
    f = artifacts / "a.txt"
    f.write_text("oi")
    rec = {"path": "a.txt", "bytes": 2, "sha256": hashlib.sha256(b"oi").hexdigest()}
    assert agent_tools.resolve_artifact(rec) == f.resolve()
    for bad in ({**rec, "sha256": "0" * 64}, {**rec, "path": "../a.txt"}, {**rec, "path": ""}, {**rec, "path": "nao.txt"}):
        with pytest.raises(agent_tools.ToolError):
            agent_tools.resolve_artifact(bad)
