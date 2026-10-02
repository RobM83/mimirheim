"""Integration tests: render the household view against the fixture dump pair.

The household view is the layperson-facing report. These tests confirm that
``build_household_html`` produces a well-formed, self-contained HTML document
from a real dump pair, that it does NOT depend on Plotly, and that the numbers
it embeds agree with the shared ``metrics`` module (the single source of truth).

They mirror ``test_render_against_fixture.py`` and assert only through the
public ``build_household_html`` seam, never against internals.
"""
from __future__ import annotations

import copy
import json
import re

from reporter.household import build_household_html
from reporter.metrics import compute_economic_metrics, compute_schedule_metrics


def _embedded_payload(html: str) -> dict:
    """Extract the JSON data payload the page embeds for its client script."""
    m = re.search(
        r'<script id="household-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert m, "household page must embed a household-data JSON script block"
    return json.loads(m.group(1))


def test_household_produces_self_contained_html(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """Returns a complete, non-empty HTML document that does not need Plotly."""
    result = build_household_html(fixture_inp, fixture_out)
    assert isinstance(result, str)
    assert len(result) > 1000
    assert "<!DOCTYPE html>" in result
    assert "</html>" in result
    assert "plotly" not in result.lower()


def test_household_saving_matches_economic_metrics(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """Embedded savings equals the shared economic-metrics value, not a re-derivation."""
    result = build_household_html(fixture_inp, fixture_out)
    d = _embedded_payload(result)
    eco = compute_economic_metrics(fixture_out)
    assert d["summary"]["saving"] == round(max(0.0, eco.saving_eur), 4)
    assert d["summary"]["naive"] == eco.naive_cost_eur


def test_household_totals_match_schedule_metrics(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """Day-in-numbers totals equal the shared schedule-metrics values."""
    result = build_household_html(fixture_inp, fixture_out)
    d = _embedded_payload(result)
    m = compute_schedule_metrics(fixture_out["schedule"])
    assert d["summary"]["import"] == m.grid_import_kwh
    assert d["summary"]["pv"] == m.pv_total_kwh
    assert d["summary"]["load"] == m.load_total_kwh
    assert d["summary"]["self"] == m.self_sufficiency_pct


def test_household_series_align_with_schedule(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """Every per-step array has one entry per schedule step, aligned by timestamp."""
    result = build_household_html(fixture_inp, fixture_out)
    d = _embedded_payload(result)
    schedule = fixture_out["schedule"]
    n = len(schedule)
    for key in ("t", "price", "exp", "pv", "load", "imp", "expo"):
        assert len(d[key]) == n, f"{key} length {len(d[key])} != {n} steps"
    assert d["t"][0] == schedule[0]["t"]
    assert d["t"][-1] == schedule[-1]["t"]


def test_household_pv_and_load_signs(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """PV and load series are non-negative (metrics sign conventions applied)."""
    d = _embedded_payload(build_household_html(fixture_inp, fixture_out))
    assert all(v >= 0 for v in d["pv"])
    assert all(v >= 0 for v in d["load"])


def test_household_empty_schedule_renders(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """An empty schedule renders a valid page rather than raising."""
    out = copy.deepcopy(fixture_out)
    out["schedule"] = []
    result = build_household_html(fixture_inp, out)
    assert "<!DOCTYPE html>" in result
    assert "</html>" in result


def test_household_no_pv_no_battery_renders(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """A schedule with no PV and no battery devices still renders a valid page."""
    out = copy.deepcopy(fixture_out)
    for step in out["schedule"]:
        step["devices"] = {
            name: dev
            for name, dev in step.get("devices", {}).items()
            if dev.get("type") not in ("pv", "battery")
        }
    result = build_household_html(fixture_inp, out)
    assert "<!DOCTYPE html>" in result
    d = _embedded_payload(result)
    assert all(v == 0 for v in d["pv"])


def test_household_zero_naive_cost_renders(
    fixture_inp: dict, fixture_out: dict
) -> None:
    """Zero naive cost does not divide-by-zero; page renders with 0% saving."""
    out = copy.deepcopy(fixture_out)
    out["naive_cost_eur"] = 0.0
    out["optimised_cost_eur"] = 0.0
    out["soc_credit_eur"] = 0.0
    result = build_household_html(fixture_inp, out)
    d = _embedded_payload(result)
    assert d["summary"]["saving"] == 0.0
