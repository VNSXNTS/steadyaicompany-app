"""Fase 7, 3º lote: creative_check, growth_math, refund_followup, content_calendar, product_spec_check."""
from app.models.entities import Sale, TaskStatus
from app.services.tasks import create_task, run_task


def _run(db, agent, tool, **extra):
    t = create_task(db, agent, f"ferramenta {tool}", input={"tool": tool, **extra})
    run_task(db, t)
    return t


# ---- creative_director ----
def test_creative_flags_guarantee_and_missing_disclaimer(db):
    t = _run(db, "creative_director", "creative_check", headline="Guaranteed debt freedom", body="Pay it all off")
    r = t.output["result"]
    assert t.status == TaskStatus.COMPLETED and r["approved"] is False
    assert any("guaranteed" in f for f in r["findings"]) and any("resultados variam" in f for f in r["findings"])


def test_creative_clean_text_passes_and_long_headline_flagged(db):
    ok = _run(db, "creative_director", "creative_check", headline="A simple payoff planner",
              body="Plan your payments. Results vary.")
    assert ok.output["result"]["approved"] is True
    long = _run(db, "creative_director", "creative_check", headline="x" * 91)
    assert any("91 caracteres" in f for f in long.output["result"]["findings"])
    assert "aprovação do proprietário" in ok.output["notes"][0]


def test_creative_requires_headline(db):
    t = _run(db, "creative_director", "creative_check")
    assert t.status == TaskStatus.FAILED and "input.headline" in t.error


# ---- growth_strategist ----
def test_growth_math_exact_numbers(db):
    t = _run(db, "growth_strategist", "growth_math", price_cents=1900, fee_percent=10, fee_fixed_cents=30,
             test_budget_cents=5000)
    r = t.output["result"]
    assert r["net_per_sale_cents"] == 1900 - 190 - 30 == 1680
    assert r["break_even_cpa_cents"] == 1680 and r["sales_to_recover_budget"] == 3  # teto de 5000/1680


def test_growth_math_refuses_when_fees_eat_the_price(db):
    for extra in ({"fee_fixed_cents": 100}, {"fee_fixed_cents": 150}):
        t = _run(db, "growth_strategist", "growth_math", price_cents=100, test_budget_cents=100, **extra)
        assert t.status == TaskStatus.FAILED and "não cobre as taxas" in t.error, extra


def test_growth_math_rejects_bad_input(db):
    for extra in ({"price_cents": 0, "test_budget_cents": 100}, {"price_cents": 100, "test_budget_cents": 100,
                  "fee_percent": 100}, {"price_cents": 100, "test_budget_cents": 100, "fee_fixed_cents": 100},
                  {"price_cents": 19.9, "test_budget_cents": 100}):
        t = _run(db, "growth_strategist", "growth_math", **extra)
        assert t.status == TaskStatus.FAILED, extra


# ---- customer_success ----
def test_refund_followup_lists_only_refunded_and_null_rate_without_sales(db):
    empty = _run(db, "customer_success", "refund_followup").output["result"]
    assert empty["refunded_count"] == 0 and empty["refund_count_rate_percent"] is None
    db.add_all([Sale(gross_cents=1900), Sale(gross_cents=1900, refunded_cents=1900),
                Sale(gross_cents=1900, refunded_cents=500)])
    db.commit()
    t = _run(db, "customer_success", "refund_followup")
    r = t.output["result"]
    assert r["refunded_count"] == 2 and r["total_sales"] == 3 and r["refund_count_rate_percent"] == 66.67
    assert [x["full_refund"] for x in r["refunded_sales"]] == [True, False]
    assert "NÃO são registrados" in t.output["notes"][0]


# ---- social_media ----
def test_content_calendar_dates_and_draft_status(db):
    t = _run(db, "social_media", "content_calendar", topics=["a", "b", "c", "d"], start_date="2026-12-01",
             posts_per_week=3)
    posts = t.output["result"]["posts"]
    assert [p["date"] for p in posts] == ["2026-12-01", "2026-12-03", "2026-12-06", "2026-12-08"]
    assert all(p["status"] == "draft" for p in posts) and "Nada foi publicado" in t.output["notes"][0]


def test_content_calendar_validates(db):
    for extra in ({"topics": [], "start_date": "2026-12-01"}, {"topics": ["a"], "start_date": "01/12/2026"},
                  {"topics": ["a"], "start_date": "2026-12-01", "posts_per_week": 8}, {"topics": [" "], "start_date": "2026-12-01"}):
        assert _run(db, "social_media", "content_calendar", **extra).status == TaskStatus.FAILED, extra


# ---- product_architect ----
def test_spec_check_complete_and_incomplete(db):
    full = {"name": "Steady Payoff", "promise": "A clear payoff plan", "audience": "variable income",
            "price_cents": 1900, "deliverables": ["xlsx"], "refund_policy": "30 days"}
    assert _run(db, "product_architect", "product_spec_check", spec=full).output["result"]["complete"] is True
    bad = _run(db, "product_architect", "product_spec_check", spec={**full, "refund_policy": "", "price_cents": 0,
                                                                  "deliverables": []})
    issues = bad.output["result"]["issues"]
    assert bad.output["result"]["complete"] is False and len(issues) == 3
    assert _run(db, "product_architect", "product_spec_check", spec="x").status == TaskStatus.FAILED


def test_new_tools_are_bound_to_their_agent(db):
    t = _run(db, "cfo", "growth_math", price_cents=100, test_budget_cents=100)
    assert t.status == TaskStatus.FAILED and "não tem a ferramenta" in t.error
