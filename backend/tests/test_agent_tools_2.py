"""Fase 7, 2º lote: Strategy (experiment_review), Sales Manager (sales_report), Competitor Analyst (offer_comparison)."""
import pytest

from app.models.entities import Product, Sale, TaskStatus
from app.services.tasks import create_task, run_task
from tests.test_experiments import running, sale, spend


def _run(db, agent, tool, **extra):
    t = create_task(db, agent, f"ferramenta {tool}", input={"tool": tool, **extra})
    run_task(db, t)
    return t


# ---- strategy / experiment_review ----------------------------------------------------------------
def test_review_low_confidence_and_continue_with_little_evidence(client, db):
    exp = running(client)
    spend(client, exp, 1000)
    sale(client, exp)
    t = _run(db, "strategy", "experiment_review", experiment_id=exp)
    r = t.output["result"]
    assert t.status == TaskStatus.COMPLETED
    assert r["recommendation"] == "continue" and r["confidence"] == "baixa"
    assert r["sales_count"] == 1 and r["cpa_cents"] == 1000 and r["break_even_cpa_cents"] == 1800
    assert any("Amostra pequena" in x for x in r["risks"])
    assert "não garante lucro" in t.output["notes"][0]


def test_review_reuses_stop_rule_and_never_claims_profit(client, db):
    exp = running(client)
    spend(client, exp, 2000)  # limite sem venda
    r = _run(db, "strategy", "experiment_review", experiment_id=exp).output["result"]
    assert r["recommendation"] == "stop" and r["cpa_cents"] is None and r["roi_percent"] is not None


def test_review_validated_candidate_still_medium_or_low_confidence(client, db):
    exp = running(client)
    spend(client, exp, 3000)
    for _ in range(3):
        sale(client, exp)
    r = _run(db, "strategy", "experiment_review", experiment_id=exp).output["result"]
    assert r["recommendation"] == "validated_candidate"
    assert r["confidence"] == "média"  # 3 vendas: acima do mínimo do experimento, abaixo de 30
    assert any("Amostra pequena" in x for x in r["risks"])


def test_review_requires_existing_experiment(db):
    for bad in ({}, {"experiment_id": 9999}, {"experiment_id": "1"}):
        t = _run(db, "strategy", "experiment_review", **bad)
        assert t.status == TaskStatus.FAILED and "experiment_id" in t.error


# ---- sales_manager / sales_report ---------------------------------------------------------------
def test_sales_report_empty_has_no_invented_numbers(db):
    t = _run(db, "sales_manager", "sales_report")
    assert t.output["result"] == {"products": [], "flags": []}
    assert any("Nenhuma venda" in n for n in t.output["notes"])
    assert any("NÃO são calculados" in n for n in t.output["notes"])  # sem funil


def test_sales_report_net_revenue_refund_rate_and_flag(db):
    p = Product(name="Steady Payoff", niche="debt", description="x", price_cents=2000)
    db.add(p)
    db.commit()
    db.add_all([Sale(product_id=p.id, gross_cents=2000, fee_cents=200, refunded_cents=0),
                Sale(product_id=p.id, gross_cents=2000, fee_cents=200, refunded_cents=1000)])
    db.commit()
    r = _run(db, "sales_manager", "sales_report").output["result"]
    row = r["products"][0]
    assert row["product"] == "Steady Payoff" and row["sales_count"] == 2
    assert row["net_revenue_cents"] == 4000 - 400 - 1000
    assert row["refund_rate_percent"] == 25.0
    assert r["flags"] and "Steady Payoff" in r["flags"][0]


def test_sales_report_refund_rate_is_null_without_gross(db):
    db.add(Sale(product_id=None, gross_cents=0, fee_cents=0, refunded_cents=0))
    db.commit()
    row = _run(db, "sales_manager", "sales_report").output["result"]["products"][0]
    assert row["product"] == "sem produto" and row["refund_rate_percent"] is None


# ---- competitor_analyst / offer_comparison -------------------------------------------------------
OFFERS = [{"name": "A", "price_cents": 900, "bonuses": ["x", "y"], "source": "ad library"},
          {"name": "B", "price_cents": 1500, "bonuses": [], "source": "página"},
          {"name": "C", "price_cents": 2700, "source": "página"}]


def test_offer_comparison_stats_and_scope_disclaimer(db):
    t = _run(db, "competitor_analyst", "offer_comparison", offers=OFFERS)
    r = t.output["result"]
    assert (r["min_price_cents"], r["median_price_cents"], r["max_price_cents"]) == (900, 1500, 2700)
    assert r["offers_with_bonuses"] == 1 and r["count"] == 3
    assert "nada foi coletado da internet" in t.output["notes"][0]
    assert len(t.output["notes"]) == 1  # 3 ofertas com fonte: sem alertas extras


def test_offer_comparison_flags_small_sample_and_missing_source(db):
    t = _run(db, "competitor_analyst", "offer_comparison", offers=[{"name": "A", "price_cents": 500}])
    assert any("confiança baixa" in n for n in t.output["notes"])
    assert any("sem fonte" in n for n in t.output["notes"])


@pytest.mark.parametrize("bad", [
    {}, {"offers": []}, {"offers": "x"}, {"offers": [{"price_cents": 1}]},
    {"offers": [{"name": "A", "price_cents": -1}]}, {"offers": [{"name": "A", "price_cents": 9.5}]},
    {"offers": [{"name": "A", "price_cents": True}]}, {"offers": [{"name": "A", "price_cents": 1, "bonuses": "x"}]},
])
def test_offer_comparison_rejects_invalid_input_instead_of_guessing(db, bad):
    t = _run(db, "competitor_analyst", "offer_comparison", **bad)
    assert t.status == TaskStatus.FAILED and t.error
