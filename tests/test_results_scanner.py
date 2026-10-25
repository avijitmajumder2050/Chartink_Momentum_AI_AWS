"""Results Scanner tests — saved screener.in pages (tests/fixtures/
results_scanner/) and fake HTTP sessions only; never live calls."""
import os
import time

import pytest

from connectors import results_scanner as rs

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "results_scanner")
Q = "2026-09"


def page(symbol):
    with open(os.path.join(FIXTURES, f"{symbol}.html"), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def store():
    return {s: rs.parse_company_page(page(s)) for s in ("COFORGE", "HCLTECH", "HDFCBANK", "IDEA")}


# ---------------------------------------------------------------- parsing

@pytest.mark.parametrize("text,expected", [
    ("1,192.67", 1192.67), ("12%", 12.0), ("-3.5", -3.5), ("—", None), ("-", None), ("", None), (None, None), ("abc", None),
])
def test_to_number(text, expected):
    assert rs.to_number(text) == expected


def test_quarter_helpers():
    assert rs.quarter_key("Sep 2026") == "2026-09"
    assert rs.quarter_key("TTM") is None
    assert rs.shift_quarter("2026-03", 1) == "2025-12"
    assert rs.shift_quarter("2026-09", 4) == "2025-09"
    assert rs.quarter_label("2026-09") == "Sep '26"
    assert rs.expected_quarter(__import__("datetime").date(2026, 10, 25)) == "2026-09"
    assert rs.expected_quarter(__import__("datetime").date(2027, 2, 1)) == "2026-12"


def test_parse_company_page(store):
    coforge = store["COFORGE"]
    assert coforge["name"] == "Coforge Ltd"
    assert "IT - Software" in coforge["industry"]
    q = coforge["quarters"][Q]
    assert q["sales"] == 6171.0 and q["net_profit"] == 605.0 and q["eps"] == 13.27
    assert q["opm"] == pytest.approx(1223 / 6171 * 100)  # recomputed unrounded


def test_bank_rows_use_aliases(store):
    q = store["HDFCBANK"]["quarters"][Q]
    assert q["sales"] == 95132.0  # "Revenue" row
    assert q["ebitda"] == -5565.0  # "Financing Profit" row


# ---------------------------------------------------------------- metrics

def test_pct_rules():
    assert rs.pct(110, 100) == pytest.approx(10)
    assert rs.pct(10, 0) is None
    assert rs.pct(10, -5) is None
    assert rs.pct(None, 5) is None


def test_coforge_metrics(store):
    m = rs.company_metrics(store["COFORGE"], Q)
    assert m["sales_qoq"] == pytest.approx(11.63, abs=0.01)
    assert m["ebitda_qoq"] == pytest.approx(15.60, abs=0.01)
    assert m["opm_qoq"] == pytest.approx(3.55, abs=0.01)  # relative, unrounded
    assert m["profit_qoq"] == pytest.approx(13.72, abs=0.01)


def test_not_reported_is_none(store):
    assert rs.company_metrics(store["IDEA"], Q) is None


def test_negative_base_is_null(store):
    m = rs.company_metrics(store["HDFCBANK"], Q)
    assert m["ebitda_qoq"] is None and m["opm_qoq"] is None


# ------------------------------------------------------------------ flags

def test_financial_flag(store):
    m = rs.company_metrics(store["HDFCBANK"], Q)
    assert "financial" in rs.flags_for("HDFCBANK", store["HDFCBANK"], m, Q)
    m = rs.company_metrics(store["COFORGE"], Q)
    assert rs.flags_for("COFORGE", store["COFORGE"], m, Q) == []


def synthetic(cur, prev, ago):
    return {"name": "Acme Ltd", "industry": ["Chemicals"], "quarters": {Q: cur, "2026-06": prev, "2025-09": ago}}


def row(sales, ebitda, np_, eps):
    return {"sales": sales, "ebitda": ebitda, "opm": ebitda / sales * 100, "net_profit": np_, "eps": eps}


def test_small_base_extreme_and_yoy_flags():
    e = synthetic(row(100, 20, 10, 1), row(90, 15, 0.4, 0.04), row(100, 20, 12, 1.2))
    m = rs.company_metrics(e, Q)
    flags = rs.flags_for("ACME", e, m, Q)
    assert {"small_base", "extreme_move", "yoy_decline"} <= set(flags)


# --------------------------------------------------------------- criteria

def test_nested_and_or():
    m = {"sales_qoq": 5, "profit_qoq": 20, "eps_qoq": None}
    crit = {"op": "AND", "rules": [
        {"field": "sales_qoq", "operator": ">", "value": 2},
        {"op": "OR", "rules": [{"field": "eps_qoq", "operator": ">", "value": 1}, {"field": "profit_qoq", "operator": "between", "value": [10, 30]}]},
    ]}
    assert rs.evaluate(crit, m)
    crit["rules"][1]["rules"][1]["value"] = [25, 30]
    assert not rs.evaluate(crit, m)


def test_missing_value_fails_every_operator():
    for op, value in ((">", -100), ("<", 100), (">=", 0), ("<=", 0), ("between", [-1e9, 1e9])):
        assert not rs.evaluate({"op": "AND", "rules": [{"field": "eps_qoq", "operator": op, "value": value}]}, {"eps_qoq": None})


def test_qoq_momentum_preset(store):
    result = rs.scan(rs.PRESETS["qoq_momentum"]["criteria"], Q, store=store)
    symbols = [r["symbol"] for r in result["rows"]]
    assert "COFORGE" in symbols
    assert "HDFCBANK" not in symbols  # EBITDA/OPM base <= 0 -> null -> fails
    assert result["total_reported"] == 3  # IDEA hasn't reported Sep '26
    # screener's Operating Profit for HCL grew 8.28% QoQ (Trendlyne's
    # EBITDA: 6.6%), so on this source HCL passes EBITDA QoQ > 8.
    hcl = rs.company_metrics(store["HCLTECH"], Q)
    assert hcl["ebitda_qoq"] == pytest.approx(8.28, abs=0.01)


def test_exclude_financials(store):
    result = rs.scan({"op": "AND", "rules": [{"field": "sales_qoq", "operator": ">", "value": 0}]}, Q, store=store, exclude_financials=True)
    assert "HDFCBANK" not in [r["symbol"] for r in result["rows"]]
    assert result["total_reported"] == 2


def test_zero_matches_reports_most_eliminating_rule(store):
    crit = {"op": "AND", "rules": [{"field": "sales_qoq", "operator": ">", "value": 1000}, {"field": "profit_qoq", "operator": ">", "value": 0}]}
    result = rs.scan(crit, Q, store=store)
    assert result["matched"] == 0
    assert result["eliminated_most"] == {"rule": "Sales QoQ % > 1000", "count": 3, "condition": crit["rules"][0]}


# ------------------------------------------------------- fetching (fakes)

class FakeResp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class FakeSession:
    def __init__(self, responses, robots="User-agent: *\nDisallow: /user/\n"):
        self.headers, self.calls = {}, []
        self.responses, self.robots = responses, robots

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResp(200, self.robots)
        return self.responses[url].pop(0)


NO_WAIT = rs.RateLimiter(0)


def test_fetch_falls_back_to_standalone(monkeypatch):
    empty = "<html><section id='quarters'><table></table></section></html>"
    base = "https://www.screener.in/company/ACME/"
    session = FakeSession({base + "consolidated/": [FakeResp(200, empty)], base: [FakeResp(200, page("COFORGE"))]})
    parsed = rs.ScreenerCompanyPages(session=session, limiter=NO_WAIT).fetch("ACME")
    assert parsed["basis"] == "standalone" and Q in parsed["quarters"]


def test_fetch_retries_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(rs.time, "sleep", lambda s: sleeps.append(s))
    url = "https://www.screener.in/company/COFORGE/consolidated/"
    session = FakeSession({url: [FakeResp(429), FakeResp(200, page("COFORGE"))]})
    parsed = rs.ScreenerCompanyPages(session=session, limiter=NO_WAIT).fetch("COFORGE")
    assert parsed["basis"] == "consolidated"
    assert sleeps == [10]  # 2**1 * 5 after a 429


def test_robots_disallow_blocks_fetch():
    session = FakeSession({}, robots="User-agent: *\nDisallow: /company/\n")
    with pytest.raises(PermissionError):
        rs.ScreenerCompanyPages(session=session, limiter=NO_WAIT).fetch("COFORGE")
    assert all(u.endswith("/robots.txt") for u in session.calls)


def test_rate_limiter_spacing():
    limiter = rs.RateLimiter(0.05)
    start = time.monotonic()
    for _ in range(3):
        limiter.wait()
    assert time.monotonic() - start >= 0.1


def test_refresh_skips_already_reported(tmp_path, monkeypatch, store):
    monkeypatch.setattr(rs, "STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setattr(rs, "expected_quarter", lambda today=None: Q)
    rs.save_store({"COFORGE": {**store["COFORGE"], "fetched_at": time.time()}}, rs.STORE_PATH)

    class Source:
        def __init__(self):
            self.fetched = []

        def fetch(self, symbol):
            self.fetched.append(symbol)
            return store[symbol]

    src = Source()
    result = rs.refresh_store(source=src, universe=[("COFORGE", 1.0), ("HCLTECH", 2.0)])
    assert src.fetched == ["HCLTECH"] and result["fetched"] == 1
    saved = rs.load_store(rs.STORE_PATH)
    assert saved["HCLTECH"]["market_cap"] == 2.0 and Q in saved["HCLTECH"]["first_seen"]


# ------------------------------------------------------------- endpoints

@pytest.fixture()
def client(monkeypatch, store, tmp_path):
    import app
    monkeypatch.setattr(rs, "load_store", lambda path=None: store)
    monkeypatch.setattr(app.cache, "CACHE_DIR", str(tmp_path))
    user = {"email": "u@example.com", "role": "user"}
    monkeypatch.setattr(app, "_current_user", lambda: user)
    plan = {"plan": "free"}
    monkeypatch.setattr(app.subscription_connector, "get_subscription", lambda email: plan)
    c = app.app.test_client()
    c.plan = plan
    return c


def test_meta_endpoint(client):
    d = client.get("/api/results-scanner/meta").get_json()
    assert d["source"] == "screener" and len(d["presets"]) == 3
    sep = next(q for q in d["quarters"] if q["key"] == Q)
    assert sep["reported"] == 3 and sep["label"] == "Sep '26"


def test_free_user_can_run_preset_not_custom(client):
    preset = rs.PRESETS["qoq_momentum"]["criteria"]
    r = client.post("/api/results-scanner", json={"quarter": Q, "criteria": preset})
    assert r.status_code == 200 and "COFORGE" in [x["symbol"] for x in r.get_json()["rows"]]
    custom = {"op": "AND", "rules": [{"field": "sales_qoq", "operator": ">", "value": 1}]}
    r = client.post("/api/results-scanner", json={"quarter": Q, "criteria": custom})
    assert r.status_code == 403 and r.get_json()["code"] == "PRO_REQUIRED"
    client.plan["plan"] = "pro"
    assert client.post("/api/results-scanner", json={"quarter": Q, "criteria": custom}).status_code == 200


def test_bad_requests(client):
    ok = rs.PRESETS["qoq_10_10"]["criteria"]
    assert client.post("/api/results-scanner", json={"quarter": Q, "criteria": {"op": "XOR", "rules": []}}).status_code == 400
    assert client.post("/api/results-scanner", json={"quarter": "2026-08", "criteria": ok}).status_code == 400
    assert client.post("/api/results-scanner", json={"quarter": Q, "criteria": ok, "source": "trendlyne"}).status_code == 400
    bad = {"op": "AND", "rules": [{"field": "nope", "operator": ">", "value": 1}]}
    assert client.post("/api/results-scanner", json={"quarter": Q, "criteria": bad}).status_code == 400


def test_filters_min_cap_and_negative_base(client, store):
    client.plan["plan"] = "pro"
    crit = {"op": "AND", "rules": [{"field": "ebitda_qoq", "operator": ">", "value": -1000}]}
    on = client.post("/api/results-scanner", json={"quarter": Q, "criteria": crit}).get_json()
    off = client.post("/api/results-scanner", json={"quarter": Q, "criteria": crit, "exclude_negative_base": False}).get_json()
    assert "HDFCBANK" not in [r["symbol"] for r in on["rows"]]
    assert "HDFCBANK" in [r["symbol"] for r in off["rows"]]  # negative base measured off |base|
    capped = client.post("/api/results-scanner", json={"quarter": Q, "criteria": crit, "min_market_cap": 1}).get_json()
    assert capped["total_reported"] == 0  # fixtures carry no market cap


def test_report_cards(store):
    result = rs.scan(rs.PRESETS["qoq_momentum"]["criteria"], Q, store=store)
    cards = {c["symbol"]: c for c in result["reported"]}
    assert set(cards) == {"COFORGE", "HCLTECH", "HDFCBANK"}  # every reporter, matched or not
    coforge = cards["COFORGE"]
    assert coforge["matched"] and coforge["passed"] == coforge["total"] == 5 and not coforge["excluded"]
    sales = next(c for c in coforge["checks"] if c["field"] == "sales_qoq")
    assert sales["now"] == 6171.0 and sales["base"] == 5528.0 and sales["pass"]
    sales_line = next(m for m in coforge["metrics"] if m["key"] == "sales")
    assert (sales_line["now"], sales_line["prev"]) == (6171.0, 5528.0)
    assert sales_line["qoq"] == pytest.approx(11.63, abs=0.01) and sales_line["yoy"] == pytest.approx(53.66, abs=0.01)
    assert sales_line["ago"] == pytest.approx(6171 / 1.5366, rel=0.001)
    bank = cards["HDFCBANK"]
    assert bank["excluded"] and not bank["matched"]  # EBITDA/OPM base <= 0
    assert result["reported"][-1]["symbol"] == "HDFCBANK"  # not-comparable sorted last
