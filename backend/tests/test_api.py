from fastapi.testclient import TestClient

from app.main import app


def test_health_is_public(client):
    with TestClient(app) as anon:
        assert anon.get("/health").status_code == 200


def test_endpoints_require_key(client):
    with TestClient(app) as anon:
        assert anon.get("/agents").status_code == 401
        assert anon.get("/agents", headers={"X-API-Key": "errada"}).status_code == 401
        assert anon.get("/dashboard").status_code == 401


def test_fail_closed_without_server_key(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    monkeypatch.setenv("OWNER_EMAIL", "")
    monkeypatch.setenv("OWNER_PASSWORD", "")
    assert client.get("/agents").status_code == 503


def test_agents_and_pause(client):
    assert len(client.get("/agents").json()) == 13
    r = client.post("/agents/cfo/pause")
    assert r.json()["status"] == "paused"
    assert client.post("/agents/cfo/explodir").status_code == 404
    assert client.post("/agents/nao_existe/pause").status_code == 404


def test_task_flow_and_risk_via_api(client):
    r = client.post("/tasks", json={"agent_key": "growth_strategist",
                                    "description": "Ativar campanha", "action": "activate_campaign"})
    assert r.status_code == 201
    assert r.json()["status"] == "awaiting_approval"
    assert r.json()["requires_approval"] is True
    task_id = r.json()["id"]
    assert client.post(f"/tasks/{task_id}/run").status_code == 400  # bloqueado

    approvals = client.get("/approvals").json()
    assert len(approvals) == 1 and approvals[0]["consequences"]
    ok = client.post(f"/approvals/{approvals[0]['id']}/decide", json={"decision": "approved"})
    assert ok.status_code == 200
    done = client.post(f"/tasks/{task_id}/run")
    assert done.json()["status"] == "completed"
    logs = client.get(f"/tasks/{task_id}/logs").json()
    assert [x["event"] for x in logs][:2] == ["created", "awaiting_approval"]


def test_validation_errors(client):
    assert client.post("/tasks", json={"agent_key": "cfo", "description": "x"}).status_code == 422
    assert client.post("/tasks", json={"agent_key": "zzz", "description": "abcdef"}).status_code == 400
    assert client.post("/approvals/999/decide", json={"decision": "approved"}).status_code == 400
    assert client.post("/expenses", json={"category": "luxo", "amount_cents": 5}).status_code == 422


def test_ceo_endpoints(client):
    tasks = client.post("/ceo/plan", json={"goal": "debt planner"}).json()
    assert len(tasks) == 10
    ran = client.post("/ceo/run-all").json()
    assert len(ran) == 9
    report = client.get("/ceo/report").json()
    assert report["pending_approvals"] == 1


def test_publish_product_requires_approval(client):
    pid = client.post("/products", json={"name": "Steady Payoff", "price_cents": 900}).json()["id"]
    appr = client.post(f"/products/{pid}/publish").json()
    products = client.get("/products").json()
    assert products[0]["status"] == "in_review"
    client.post(f"/approvals/{appr['id']}/decide", json={"decision": "approved"})
    assert client.get("/products").json()[0]["status"] == "published"


def test_dashboard_empty_is_zero_not_fake(client):
    d = client.get("/dashboard").json()
    assert d["agents_active"] == 13
    assert d["gross_revenue_cents"] == 0 and d["profit_cents"] == 0
    assert d["margin_percent"] is None and d["roi_percent"] is None
    assert d["recent_activity"] == []


def test_dashboard_money_math(client):
    # bruto 10000, taxa 500, reembolso 1000 => líquido 8500; despesas 3000 => lucro 5500
    client.post("/sales", json={"gross_cents": 10000, "fee_cents": 500, "refunded_cents": 1000})
    client.post("/expenses", json={"category": "ads", "amount_cents": 3000})
    d = client.get("/dashboard").json()
    assert d["gross_revenue_cents"] == 10000
    assert d["net_revenue_cents"] == 8500
    assert d["expenses_cents"] == 3000
    assert d["profit_cents"] == 5500  # faturamento != lucro
    assert d["margin_percent"] == round(5500 / 8500 * 100, 2)
    assert d["roi_percent"] == round(5500 / 3000 * 100, 2)


def test_sale_validation(client):
    assert client.post("/sales", json={"gross_cents": 100, "fee_cents": 80,
                                       "refunded_cents": 50}).status_code == 400
