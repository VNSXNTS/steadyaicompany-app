"""Experimentos de validação de oferta: regras de decisão, aprovação e contas em centavos.

Parâmetros padrão dos testes: preço 2000, taxa 10% (200) => CPA de equilíbrio 1800;
teto 5000; limite sem venda 2000; mínimo de 3 vendas para decidir.
"""
import pytest

from app.models.entities import Approval

BASE = {
    "name": "Mapa da Aprovação", "market": "BR", "currency": "BRL", "price_cents": 2000, "fee_bps": 1000,
    "budget_cap_cents": 5000, "max_spend_without_sale_cents": 2000, "min_sales_to_decide": 3,
}


def make(client, **over) -> dict:
    r = client.post("/experiments", json={**BASE, **over})
    assert r.status_code == 201, r.text
    return r.json()


def approve(client, exp_id: int) -> None:
    ap = client.post(f"/experiments/{exp_id}/request-approval").json()
    assert client.post(f"/approvals/{ap['id']}/decide", json={"decision": "approved"}).status_code == 200


def running(client, **over) -> int:
    exp = make(client, **over)
    approve(client, exp["id"])
    return exp["id"]


def spend(client, exp_id, cents):
    return client.post(f"/experiments/{exp_id}/spend", json={"amount_cents": cents})


def sale(client, exp_id, gross=2000, fee=200, refunded=0):
    return client.post(f"/experiments/{exp_id}/sales",
                       json={"gross_cents": gross, "fee_cents": fee, "refunded_cents": refunded})


def get(client, exp_id) -> dict:
    return client.get(f"/experiments/{exp_id}").json()


# ---- criação ----------------------------------------------------------------------------------------
def test_market_and_currency_are_required_with_no_default(client):
    for missing in ("market", "currency"):
        body = {k: v for k, v in BASE.items() if k != missing}
        assert client.post("/experiments", json=body).status_code == 422


def test_stop_limit_cannot_exceed_the_budget_cap(client):
    r = client.post("/experiments", json={**BASE, "max_spend_without_sale_cents": 6000})
    assert r.status_code == 422


def test_new_experiment_has_no_invented_numbers(client):
    m = make(client)["metrics"]
    assert m["roi_percent"] is None and m["cpa_cents"] is None  # sem base: nunca 0 inventado
    assert m["break_even_cpa_cents"] == 1800
    assert m["action"] == "not_started"


def test_break_even_includes_percentage_and_fixed_fees(client):
    m = make(client, fee_bps=500, fee_fixed_cents=50)["metrics"]  # 2000 - (100 + 50)
    assert m["break_even_cpa_cents"] == 1850


def test_fees_that_eat_the_price_are_flagged(client):
    m = make(client, fee_bps=10_000)["metrics"]
    assert m["break_even_cpa_cents"] == 0 and any("Taxas" in w for w in m["warnings"])


# ---- aprovação --------------------------------------------------------------------------------------
def test_request_approval_creates_a_pending_approval_and_blocks_a_second_request(client):
    exp = make(client)
    ap = client.post(f"/experiments/{exp['id']}/request-approval")
    assert ap.status_code == 202
    body = ap.json()
    assert body["action"] == "activate_campaign" and body["status"] == "pending"
    assert "NÃO gasta" in body["consequences"] and body["details"]["budget_cap_cents"] == 5000
    assert get(client, exp["id"])["status"] == "pending_approval"
    assert client.post(f"/experiments/{exp['id']}/request-approval").status_code == 409


def test_experiment_is_only_active_after_the_owner_approves(client):
    exp = make(client)
    ap = client.post(f"/experiments/{exp['id']}/request-approval").json()
    assert get(client, exp["id"])["metrics"]["action"] == "not_started"
    client.post(f"/approvals/{ap['id']}/decide", json={"decision": "approved"})
    g = get(client, exp["id"])
    assert g["status"] == "approved" and g["approved_at"] and g["metrics"]["action"] == "continue"


def test_rejected_and_changes_requested_outcomes(client):
    e1 = make(client)
    a1 = client.post(f"/experiments/{e1['id']}/request-approval").json()
    client.post(f"/approvals/{a1['id']}/decide", json={"decision": "rejected"})
    assert get(client, e1["id"])["status"] == "rejected"
    e2 = make(client)
    a2 = client.post(f"/experiments/{e2['id']}/request-approval").json()
    client.post(f"/approvals/{a2['id']}/decide", json={"decision": "changes_requested"})
    assert get(client, e2["id"])["status"] == "draft"  # pode pedir de novo


def test_unrelated_activate_campaign_approval_does_not_touch_experiments(client, db):
    exp = make(client)
    a = Approval(action="activate_campaign", details={})
    db.add(a)
    db.commit()
    assert client.post(f"/approvals/{a.id}/decide", json={"decision": "approved"}).status_code == 200
    assert get(client, exp["id"])["status"] == "draft"


def test_spend_before_approval_is_recorded_but_flagged(client):
    exp = make(client)
    assert spend(client, exp["id"], 300).status_code == 201  # o fato aconteceu: registra, mas avisa
    m = get(client, exp["id"])["metrics"]
    assert m["spend_cents"] == 300 and any("sem aprovação" in w for w in m["warnings"])
    assert m["action"] == "not_started"


# ---- regras de decisão ------------------------------------------------------------------------------
def test_continue_while_evidence_is_insufficient(client):
    i = running(client)
    spend(client, i, 1000)
    sale(client, i)
    m = get(client, i)["metrics"]
    assert m["action"] == "continue" and "1 de 3" in m["reason"]


def test_stop_when_spend_limit_reached_with_zero_sales(client):
    i = running(client)
    spend(client, i, 1999)
    assert get(client, i)["metrics"]["action"] == "continue"
    spend(client, i, 1)
    m = get(client, i)["metrics"]
    assert m["action"] == "stop" and "sem nenhuma venda" in m["reason"]


def test_stop_when_budget_cap_is_reached(client):
    i = running(client)
    spend(client, i, 2000)
    sale(client, i)  # tem venda, então a regra "sem venda" não vale
    spend(client, i, 3000)
    m = get(client, i)["metrics"]
    assert m["action"] == "stop" and "Teto" in m["reason"]


def test_spending_over_the_cap_is_flagged(client):
    i = running(client)
    spend(client, i, 5200)
    assert any("passou do teto" in w for w in get(client, i)["metrics"]["warnings"])


def test_validated_candidate_when_cpa_within_break_even_with_enough_sales(client):
    i = running(client)
    for _ in range(3):
        spend(client, i, 1500)
        sale(client, i)
    m = get(client, i)["metrics"]
    # 3 vendas: bruto 6000, taxas 600, líquida 5400; gasto 4500; lucro 900; ROI 20%; CPA 1500 <= 1800
    assert (m["net_revenue_cents"], m["spend_cents"], m["profit_cents"]) == (5400, 4500, 900)
    assert m["roi_percent"] == 20.0 and m["cpa_cents"] == 1500
    assert m["action"] == "validated_candidate" and "não é garantia" in m["reason"]


def test_stop_when_cpa_above_break_even_even_with_enough_sales(client):
    i = running(client, budget_cap_cents=20_000, max_spend_without_sale_cents=2000)
    for _ in range(3):
        spend(client, i, 2000)  # CPA 2000 > 1800
        sale(client, i)
    m = get(client, i)["metrics"]
    assert m["action"] == "stop" and "acima do ponto de equilíbrio" in m["reason"]
    assert m["profit_cents"] == 5400 - 6000  # prejuízo real, não escondido


def test_refunds_reduce_net_revenue_and_roi_needs_spend(client):
    i = running(client)
    sale(client, i, gross=2000, fee=200, refunded=2000 - 200)  # reembolso total
    m = get(client, i)["metrics"]
    assert m["net_revenue_cents"] == 0
    assert m["roi_percent"] is None  # sem gasto não há base para ROI


# ---- encerramento -----------------------------------------------------------------------------------
def test_cannot_mark_validated_without_meeting_the_rules(client):
    i = running(client)
    spend(client, i, 1000)
    sale(client, i)
    r = client.post(f"/experiments/{i}/close", json={"outcome": "validated"})
    assert r.status_code == 409 and "validada" in r.json()["detail"]
    assert get(client, i)["status"] == "approved"


def test_validated_close_works_when_rules_are_met_and_freezes_the_records(client):
    i = running(client)
    for _ in range(3):
        spend(client, i, 1500)
        sale(client, i)
    r = client.post(f"/experiments/{i}/close", json={"outcome": "validated", "note": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["outcome"] == "validated"
    assert spend(client, i, 100).status_code == 409 and sale(client, i).status_code == 409


def test_owner_can_kill_any_time_but_only_an_approved_experiment_can_close(client):
    draft = make(client)
    assert client.post(f"/experiments/{draft['id']}/close", json={"outcome": "killed"}).status_code == 409
    i = running(client)
    r = client.post(f"/experiments/{i}/close", json={"outcome": "killed", "note": "não converte"})
    assert r.status_code == 200 and r.json()["outcome"] == "killed"


# ---- integração e segurança -------------------------------------------------------------------------
def test_experiment_money_feeds_the_global_financials_without_double_counting(client):
    i = running(client)
    spend(client, i, 1500)
    sale(client, i)
    d = client.get("/dashboard").json()
    assert d["expenses_cents"] == 1500 and d["gross_revenue_cents"] == 2000 and d["sales_count"] == 1


def test_invalid_sale_amounts_are_rejected(client):
    i = running(client)
    assert sale(client, i, gross=2000, fee=1500, refunded=600).status_code == 400
    assert get(client, i)["metrics"]["sales_count"] == 0


def test_experiments_require_authentication(client):
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    assert anon.get("/experiments").status_code == 401
    assert anon.post("/experiments", json=BASE).status_code == 401


def test_unknown_experiment_and_product_return_404(client):
    assert client.get("/experiments/999").status_code == 404
    assert client.post("/experiments", json={**BASE, "product_id": 999}).status_code == 404
