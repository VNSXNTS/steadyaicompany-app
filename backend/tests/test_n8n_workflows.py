"""Fase 10: os workflows do n8n em workflows/n8n são válidos, seguros e só chamam rotas que EXISTEM no backend.

Isto é verificação estática. A importação e a execução reais foram feitas no n8n 2.35.7 (ver PROJECT_STATUS.md);
este teste só impede que um workflow quebre ou vaze segredo sem ninguém notar.
"""
import json
import re
from pathlib import Path

import pytest

from app.main import app

DIR = Path(__file__).resolve().parents[2] / "workflows" / "n8n"
STEADY = ["relatorio-diario", "aprovacoes-pendentes", "criativos-enfileirar", "ofertas-para-comparacao"]
ALL = sorted(DIR.glob("*.json"))
SECRET_PATTERNS = [r"sk-ant-", r"apify_api_", r"AIza[0-9A-Za-z_-]{20,}", r"xox[bp]-", r"Bearer\s+[A-Za-z0-9._-]{20,}",
                   r"N8N_WEBHOOK_SECRET\s*=", r"ghp_[A-Za-z0-9]{20,}"]


def load(name):
    return json.loads((DIR / f"{name}.json").read_text())


def http_nodes(wf):
    return [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]


def app_paths():
    return set(app.openapi()["paths"])  # rotas reais do backend (app.routes agrupa em _IncludedRouter)


def normalize(url: str) -> str:
    path = url.split("}}", 1)[1] if "}}" in url else url  # tira "={{ base_url }}"
    return re.sub(r"\{\{.*?\}\}", "{x}", path)


def test_all_expected_files_exist():
    assert {p.stem for p in ALL} >= set(STEADY)


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_no_secret_in_any_workflow(path):
    text = path.read_text()
    for pat in SECRET_PATTERNS:
        assert not re.search(pat, text), f"{path.name}: possível segredo ({pat})"


@pytest.mark.parametrize("name", STEADY)
def test_structure_and_connections_are_valid(name):
    wf = load(name)
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)) and len({n["id"] for n in wf["nodes"]}) == len(names)
    for n in wf["nodes"]:
        assert {"id", "name", "type", "typeVersion", "position", "parameters"} <= set(n)
    for src, outs in wf["connections"].items():
        assert src in names
        for branch in outs["main"]:
            for c in branch:
                assert c["node"] in names
    assert wf["active"] is False  # nunca importa ligado: o proprietário ativa depois de configurar
    triggers = [n for n in wf["nodes"] if n["type"].endswith("Trigger")]
    assert any(n["type"] == "n8n-nodes-base.manualTrigger" for n in triggers)  # sempre testável à mão
    # todo nó (fora gatilhos) é alcançável a partir de algum gatilho
    reach, stack = set(), [t["name"] for t in triggers]
    while stack:
        cur = stack.pop()
        if cur in reach:
            continue
        reach.add(cur)
        stack += [c["node"] for br in wf["connections"].get(cur, {}).get("main", []) for c in br]
    assert reach == set(names)


@pytest.mark.parametrize("name", STEADY)
def test_http_nodes_use_header_auth_credential_and_existing_webhook_routes(name):
    paths = app_paths()
    for n in http_nodes(load(name)):
        p = n["parameters"]
        assert p["authentication"] == "genericCredentialType" and p["genericAuthType"] == "httpHeaderAuth"
        assert n["credentials"]["httpHeaderAuth"]["name"] == "Steady Webhook"
        assert "value" not in json.dumps(n["credentials"])  # a credencial é referenciada, nunca embutida
        route = normalize(p["url"])
        assert route.startswith("/webhooks/n8n/"), route
        assert route.replace("{x}", "{task_id}") in paths, f"rota inexistente no backend: {route}"
        assert n.get("retryOnFail") is True


@pytest.mark.parametrize("name", STEADY)
def test_base_url_is_a_placeholder_never_a_real_host(name):
    cfg = next(n for n in load(name)["nodes"] if n["name"] == "Config")
    base = next(a["value"] for a in cfg["parameters"]["assignments"]["assignments"] if a["name"] == "base_url")
    assert base == "https://SEU-BACKEND-AQUI"


@pytest.mark.parametrize("name", ["criativos-enfileirar", "ofertas-para-comparacao"])
def test_post_has_idempotency_key_tied_to_the_execution_and_no_action(name):
    posts = [n for n in http_nodes(load(name)) if n["parameters"]["method"] == "POST"]
    assert len(posts) == 1
    p = posts[0]["parameters"]
    header = {h["name"]: h["value"] for h in p["headerParameters"]["parameters"]}
    assert "$execution.id" in header["Idempotency-Key"]  # estável entre as tentativas do mesmo envio
    assert "action" not in p["jsonBody"].replace("description", "")  # nunca pede ação de risco
    assert "tool:" in p["jsonBody"]


@pytest.mark.parametrize("name", STEADY)
def test_no_workflow_can_decide_approvals_or_run_the_queue(name):
    text = (DIR / f"{name}.json").read_text()
    for bad in ("/decide", "/run", "/approvals/", "/ceo/", "X-API-Key", "ADMIN_API_KEY"):
        assert bad not in text.replace("/webhooks/n8n/approvals/pending", ""), bad


@pytest.mark.parametrize("name", ["relatorio-diario", "aprovacoes-pendentes"])
def test_notification_workflows_have_disabled_email_and_scheduled_trigger(name):
    wf = load(name)
    emails = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.emailSend"]
    assert len(emails) == 1 and emails[0]["disabled"] is True  # nada é enviado até o proprietário configurar e ativar
    assert any(n["type"] == "n8n-nodes-base.scheduleTrigger" for n in wf["nodes"])


@pytest.mark.parametrize("name,field", [("criativos-enfileirar", "headline"), ("ofertas-para-comparacao", "offers_json")])
def test_templates_ship_empty_so_no_invented_data_is_ever_sent(name, field):
    cfg = next(n for n in load(name)["nodes"] if n["name"] == "Config")
    value = next(a["value"] for a in cfg["parameters"]["assignments"]["assignments"] if a["name"] == field)
    assert value in ("", "[]")
    guard = next(n for n in load(name)["nodes"] if n["type"] == "n8n-nodes-base.code")
    assert "throw new Error" in guard["parameters"]["jsCode"]  # vazio falha com mensagem clara em vez de enfileirar
