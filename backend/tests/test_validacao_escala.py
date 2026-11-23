"""Fase 16b: preparação de lançamento, evento sazonal e escala só depois de validar.

Reaproveita os helpers de test_experiments (preço 2000, taxa 10%, CPA de equilíbrio 1800, teto 5000,
limite sem venda 2000, mínimo 3 vendas).
"""
from datetime import date, timedelta

import pytest

from app.models.entities import Approval, Experiment
from app.services import experiments as svc
from tests.test_experiments import ANGLES, CHECKLIST, approve, get, make, ready, running, sale, spend


def today() -> date:
    return svc._today()


def plan(client, exp_id, angles=ANGLES, checklist=CHECKLIST):
    return client.put(f"/experiments/{exp_id}/launch-plan", json={"creative_angles": angles, "checklist": checklist})


def validated(client, **over) -> int:
    """Experimento encerrado como VALIDADO (3 vendas, gasto 900 => CPA 300 <= 1800)."""
    eid = running(client, **over)
    spend(client, eid, 900)
    for _ in range(3):
        sale(client, eid)
    r = client.post(f"/experiments/{eid}/close", json={"outcome": "validated"})
    assert r.status_code == 200, r.text
    return eid


SCALE = {"name": "Escala", "budget_cap_cents": 20000, "max_spend_without_sale_cents": 4000, "min_sales_to_decide": 5}


# ---- checklist e ângulos bloqueiam o pedido de aprovação ------------------------------------------------
def test_cannot_request_approval_without_launch_plan_and_no_approval_is_created(client, db):
    exp = make(client)
    r = client.post(f"/experiments/{exp['id']}/request-approval")
    assert r.status_code == 409 and "Checklist pendente" in r.json()["detail"]
    assert db.query(Approval).count() == 0 and get(client, exp["id"])["status"] == "draft"


@pytest.mark.parametrize("item", sorted(svc.LAUNCH_CHECKLIST))
def test_each_checklist_item_is_required(client, item):
    exp = make(client)
    assert plan(client, exp["id"], checklist={**CHECKLIST, item: False}).status_code == 200
    r = client.post(f"/experiments/{exp['id']}/request-approval")
    assert r.status_code == 409 and svc.LAUNCH_CHECKLIST[item] in r.json()["detail"]


def test_three_distinct_angles_with_hooks_are_required(client):
    exp = make(client)
    for angles in (ANGLES[:2], [ANGLES[0], ANGLES[1], {"angle": " DOR ", "hook": "outro"}]):
        plan(client, exp["id"], angles=angles)
        r = client.post(f"/experiments/{exp['id']}/request-approval")
        assert r.status_code == 409 and "ângulos" in r.json()["detail"]
    assert plan(client, exp["id"], angles=ANGLES).status_code == 200
    assert client.post(f"/experiments/{exp['id']}/request-approval").status_code == 202


def test_angle_without_hook_is_rejected_by_the_schema(client):
    exp = make(client)
    assert plan(client, exp["id"], angles=[{"angle": "dor", "hook": ""}]).status_code == 422


def test_unknown_checklist_item_is_rejected(client):
    exp = make(client)
    assert plan(client, exp["id"], checklist={"inventado": True}).status_code == 422


def test_launch_plan_is_frozen_after_approval_is_requested(client):
    exp = make(client)
    ready(client, exp["id"])
    client.post(f"/experiments/{exp['id']}/request-approval")
    assert plan(client, exp["id"], angles=[]).status_code == 409
    assert len(get(client, exp["id"])["creative_angles"]) == 3


def test_blockers_are_listed_in_metrics_only_while_draft(client):
    exp = make(client)
    assert len(get(client, exp["id"])["metrics"]["launch_blockers"]) == 5  # 4 itens + ângulos
    approve(client, exp["id"])
    assert get(client, exp["id"])["metrics"]["launch_blockers"] == []


def test_approval_details_carry_the_launch_plan_for_the_owner_to_review(client):
    exp = make(client, event_name="Prova", event_date=(today() + timedelta(days=30)).isoformat())
    ready(client, exp["id"])
    ap = client.post(f"/experiments/{exp['id']}/request-approval").json()
    d = ap["details"]
    assert d["event_name"] == "Prova" and len(d["creative_angles"]) == 3 and d["stage"] == "validation"


# ---- evento sazonal -----------------------------------------------------------------------------------
def test_event_name_and_date_go_together(client):
    d = (today() + timedelta(days=30)).isoformat()
    for body in ({"event_name": "Prova"}, {"event_date": d}):
        r = client.post("/experiments", json={**{
            "name": "x", "market": "US", "currency": "USD", "price_cents": 2000, "budget_cap_cents": 5000,
            "max_spend_without_sale_cents": 2000, "min_sales_to_decide": 3}, **body})
        assert r.status_code == 422


def test_event_in_the_past_blocks_the_approval_request(client):
    exp = make(client, event_name="Prova", event_date=(today() - timedelta(days=1)).isoformat())
    ready(client, exp["id"])
    r = client.post(f"/experiments/{exp['id']}/request-approval")
    assert r.status_code == 409 and "já passou" in r.json()["detail"]


def test_days_to_event_and_urgency_warning(client):
    soon = make(client, event_name="Prova", event_date=(today() + timedelta(days=3)).isoformat())["metrics"]
    assert soon["days_to_event"] == 3 and any("3 dia(s)" in w for w in soon["warnings"])
    far = make(client, event_name="Prova", event_date=(today() + timedelta(days=30)).isoformat())["metrics"]
    assert far["days_to_event"] == 30 and not any("evento sazonal" in w for w in far["warnings"])
    none = make(client)["metrics"]
    assert none["days_to_event"] is None


def _event_passed(db, exp_id):
    e = db.get(Experiment, exp_id)
    e.event_date = today() - timedelta(days=1)
    db.commit()


def test_event_passed_without_enough_evidence_means_stop(client, db):
    eid = running(client, event_name="Prova", event_date=(today() + timedelta(days=5)).isoformat())
    spend(client, eid, 300)
    sale(client, eid)  # 1 de 3 vendas
    assert get(client, eid)["metrics"]["action"] == "continue"
    _event_passed(db, eid)
    m = get(client, eid)["metrics"]
    assert m["action"] == "stop" and "já passou" in m["reason"]


def test_event_passed_does_not_erase_real_evidence(client, db):
    eid = running(client, event_name="Prova", event_date=(today() + timedelta(days=5)).isoformat())
    spend(client, eid, 900)
    for _ in range(3):
        sale(client, eid)
    _event_passed(db, eid)
    assert get(client, eid)["metrics"]["action"] == "validated_candidate"


def test_experiment_without_event_never_stops_for_date(client):
    eid = running(client)
    assert get(client, eid)["metrics"]["action"] == "continue"


# ---- escala só depois de validar -----------------------------------------------------------------------
def test_cannot_scale_an_experiment_that_is_not_validated(client):
    draft = make(client)["id"]
    approved = running(client)
    killed = running(client)
    client.post(f"/experiments/{killed}/close", json={"outcome": "killed"})
    for eid in (draft, approved, killed):
        r = client.post(f"/experiments/{eid}/scale", json=SCALE)
        assert r.status_code == 409 and "VALIDADO" in r.json()["detail"], eid


def test_scale_of_a_validated_experiment_inherits_economics_and_starts_as_draft(client):
    pid = validated(client, event_name="Prova", event_date=(today() + timedelta(days=30)).isoformat())
    r = client.post(f"/experiments/{pid}/scale", json=SCALE)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["stage"] == "scale" and c["parent_experiment_id"] == pid and c["status"] == "draft"
    assert (c["price_cents"], c["fee_bps"], c["market"], c["currency"]) == (2000, 1000, "BR", "BRL")
    assert c["event_name"] == "Prova" and len(c["creative_angles"]) == 3
    assert c["launch_checklist"] == {}  # nova campanha, nova atestação
    assert c["budget_cap_cents"] == 20000 and c["metrics"]["action"] == "not_started"
    assert c["metrics"]["spend_cents"] == 0 and c["metrics"]["cpa_cents"] is None  # não herda o gasto da validação


def test_scale_needs_its_own_checklist_and_its_own_approval(client):
    pid = validated(client)
    cid = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    assert client.post(f"/experiments/{cid}/request-approval").status_code == 409  # checklist vazio
    assert spend(client, cid, 100).status_code == 201  # registrar é possível, mas...
    assert "sem aprovação" in " ".join(get(client, cid)["metrics"]["warnings"])  # ...fica sinalizado
    ready(client, cid)
    ap = client.post(f"/experiments/{cid}/request-approval").json()
    assert ap["action"] == "activate_campaign" and ap["details"]["stage"] == "scale"
    assert ap["details"]["parent_experiment_id"] == pid and ap["details"]["budget_cap_cents"] == 20000
    assert get(client, cid)["status"] == "pending_approval"


def test_scale_cap_must_exceed_the_validation_cap(client):
    pid = validated(client)
    for cap in (5000, 4000):
        r = client.post(f"/experiments/{pid}/scale", json={**SCALE, "budget_cap_cents": cap,
                                                           "max_spend_without_sale_cents": 1000})
        assert r.status_code == 409 and "maior" in r.json()["detail"]


def test_scale_stop_limit_cannot_exceed_its_cap(client):
    pid = validated(client)
    r = client.post(f"/experiments/{pid}/scale", json={**SCALE, "max_spend_without_sale_cents": 30000})
    assert r.status_code == 409


def test_only_one_open_scale_per_validated_experiment(client):
    pid = validated(client)
    first = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    r = client.post(f"/experiments/{pid}/scale", json=SCALE)
    assert r.status_code == 409 and f"#{first}" in r.json()["detail"]


def test_a_rejected_scale_can_be_replaced(client):
    pid = validated(client)
    cid = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    ready(client, cid)
    ap = client.post(f"/experiments/{cid}/request-approval").json()
    client.post(f"/approvals/{ap['id']}/decide", json={"decision": "rejected"})
    assert client.post(f"/experiments/{pid}/scale", json=SCALE).status_code == 201


def test_scale_cannot_be_scaled_again_and_unknown_parent_is_404(client):
    pid = validated(client)
    cid = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    ready(client, cid)
    ap = client.post(f"/experiments/{cid}/request-approval").json()
    client.post(f"/approvals/{ap['id']}/decide", json={"decision": "approved"})
    spend(client, cid, 2000)
    for _ in range(5):
        sale(client, cid)
    assert client.post(f"/experiments/{cid}/close", json={"outcome": "validated"}).status_code == 200
    r = client.post(f"/experiments/{cid}/scale", json={**SCALE, "budget_cap_cents": 99999})
    assert r.status_code == 409 and "não de outra escala" in r.json()["detail"]
    assert client.post("/experiments/9999/scale", json=SCALE).status_code == 404


def test_scale_money_feeds_the_global_dashboard_once(client):
    pid = validated(client)
    before = client.get("/dashboard").json()
    cid = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    ready(client, cid)
    ap = client.post(f"/experiments/{cid}/request-approval").json()
    client.post(f"/approvals/{ap['id']}/decide", json={"decision": "approved"})
    spend(client, cid, 700)
    sale(client, cid)
    after = client.get("/dashboard").json()
    # o painel global soma a escala exatamente uma vez: +700 de gasto, +1 venda de 2000 bruto
    assert after["expenses_cents"] - before["expenses_cents"] == 700
    assert after["sales_count"] - before["sales_count"] == 1
    assert after["gross_revenue_cents"] - before["gross_revenue_cents"] == 2000
    m = get(client, cid)["metrics"]
    assert m["spend_cents"] == 700 and m["sales_count"] == 1  # só o que foi registrado na escala


# ---- M1: revalidação no momento de aprovar --------------------------------------------------------------
def _audit_actions(db):
    from app.models.entities import AuditLog
    db.expire_all()
    return [a for a in db.query(AuditLog).all()]


def _pending(client, **over):
    exp = make(client, **over)
    ready(client, exp["id"])
    ap = client.post(f"/experiments/{exp['id']}/request-approval").json()
    return exp["id"], ap["id"]


def test_m1_event_passed_before_approval_blocks_it_and_keeps_everything_pending(client, db):
    eid, aid = _pending(client, event_name="Prova", event_date=(today() + timedelta(days=2)).isoformat())
    _event_passed(db, eid)
    r = client.post(f"/approvals/{aid}/decide", json={"decision": "approved"})
    assert r.status_code == 400 and "Aprovação bloqueada" in r.json()["detail"] and "STOP" in r.json()["detail"]
    g = get(client, eid)
    assert g["status"] == "pending_approval" and g["approved_at"] is None and g["metrics"]["action"] == "not_started"
    assert next(a for a in client.get("/approvals").json() if a["id"] == aid)["status"] == "pending"
    blocked = [a for a in _audit_actions(db) if a.action == "experiment_approval_blocked"]
    assert len(blocked) == 1 and blocked[0].detail["experiment_id"] == eid
    assert any("STOP" in x for x in blocked[0].detail["reasons"])


def test_m1_blocked_approval_can_still_be_rejected_or_sent_back_for_changes(client, db):
    for decision, status in (("rejected", "rejected"), ("changes_requested", "draft")):
        eid, aid = _pending(client, event_name="Prova", event_date=(today() + timedelta(days=2)).isoformat())
        _event_passed(db, eid)
        assert client.post(f"/approvals/{aid}/decide", json={"decision": decision}).status_code == 200
        assert get(client, eid)["status"] == status


def test_m1_spend_already_at_the_cap_before_approval_means_stop_and_blocks(client):
    eid, aid = _pending(client)
    assert spend(client, eid, 5000).status_code == 201  # fato já ocorrido: aceito, mas sinalizado
    r = client.post(f"/approvals/{aid}/decide", json={"decision": "approved"})
    assert r.status_code == 400 and "Teto de orçamento" in r.json()["detail"]
    assert get(client, eid)["status"] == "pending_approval"


def test_m1_plan_no_longer_valid_at_approval_time_blocks_it(client, db):
    eid, aid = _pending(client)
    e = db.get(Experiment, eid)
    e.launch_checklist = {**e.launch_checklist, "checkout_tested": False}  # adulterado fora da API
    db.commit()
    r = client.post(f"/approvals/{aid}/decide", json={"decision": "approved"})
    assert r.status_code == 400 and "Checklist pendente" in r.json()["detail"]
    assert get(client, eid)["status"] == "pending_approval"


def test_m1_valid_approval_still_works_and_is_audited_as_revalidated(client, db):
    eid, aid = _pending(client, event_name="Prova", event_date=(today() + timedelta(days=30)).isoformat())
    assert client.post(f"/approvals/{aid}/decide", json={"decision": "approved"}).status_code == 200
    g = get(client, eid)
    assert g["status"] == "approved" and g["approved_at"]
    ok = [a for a in _audit_actions(db) if a.action == "experiment_approval_revalidated"]
    assert len(ok) == 1 and ok[0].detail == {"approval_id": aid, "experiment_id": eid}
    assert not [a for a in _audit_actions(db) if a.action == "experiment_approval_blocked"]


def test_m1_scale_approval_is_revalidated_too(client, db):
    pid = validated(client, event_name="Prova", event_date=(today() + timedelta(days=30)).isoformat())
    cid = client.post(f"/experiments/{pid}/scale", json=SCALE).json()["id"]
    ready(client, cid)
    aid = client.post(f"/experiments/{cid}/request-approval").json()["id"]
    _event_passed(db, cid)
    assert client.post(f"/approvals/{aid}/decide", json={"decision": "approved"}).status_code == 400
    assert get(client, cid)["status"] == "pending_approval"


def test_m1_unrelated_activate_campaign_approval_is_not_revalidated(client, db):
    a = Approval(action="activate_campaign", details={})
    db.add(a)
    db.commit()
    assert client.post(f"/approvals/{a.id}/decide", json={"decision": "approved"}).status_code == 200


# ---- L1: checklist estritamente booleano ----------------------------------------------------------------
@pytest.mark.parametrize("bad", ["yes", "true", "1", 1, 0, None, "", "sim"])
def test_l1_checklist_rejects_anything_that_is_not_a_real_boolean(client, bad):
    exp = make(client)
    r = plan(client, exp["id"], checklist={**CHECKLIST, "checkout_tested": bad})
    assert r.status_code == 422, bad
    assert get(client, exp["id"])["launch_checklist"] == {}  # nada foi gravado


def test_l1_real_booleans_are_accepted_and_false_still_blocks(client):
    exp = make(client)
    r = plan(client, exp["id"], checklist={**CHECKLIST, "refund_policy_published": False})
    assert r.status_code == 200 and r.json()["launch_checklist"]["refund_policy_published"] is False
    assert client.post(f"/experiments/{exp['id']}/request-approval").status_code == 409


# ---- L2: ângulo e gancho sem espaços sobrando ------------------------------------------------------------
@pytest.mark.parametrize("field", ["angle", "hook"])
@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
def test_l2_blank_or_whitespace_only_fields_are_rejected(client, field, blank):
    exp = make(client)
    angles = [{"angle": "a", "hook": "x"}, {"angle": "b", "hook": "y"}, {"angle": "c", "hook": "z", field: blank}]
    assert plan(client, exp["id"], angles=angles).status_code == 422
    assert get(client, exp["id"])["creative_angles"] == []


def test_l2_values_are_stored_stripped_and_padded_duplicates_count_once(client):
    exp = make(client)
    r = plan(client, exp["id"], angles=[{"angle": "  dor  ", "hook": "  gancho 1 "},
                                        {"angle": "urgência", "hook": "g2"}, {"angle": "dor", "hook": "g3"}])
    assert r.status_code == 200
    assert r.json()["creative_angles"][0] == {"angle": "dor", "hook": "gancho 1"}
    assert client.post(f"/experiments/{exp['id']}/request-approval").status_code == 409  # 2 distintos
