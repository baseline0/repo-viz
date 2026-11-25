"""Indicator configuration is validated and serializable without file access."""

from __future__ import annotations

import pytest

from repo_viz.indicators.spec import Arc, Indicator, IndicatorConfig, State

COLORS = dict.fromkeys(State, "#000000")


def test_arc_degrees_and_span_limit() -> None:
    arc = Arc(start_deg=315, end_deg=45, step_deg=12, first_deg=320)
    assert arc.degrees(0) == 320
    assert arc.degrees(4) == 368 % 360
    with pytest.raises(ValueError, match="90 degrees"):
        Arc(start_deg=0, end_deg=120, step_deg=12, first_deg=5)


def test_indicator_rejects_unknown_glyph_and_missing_color() -> None:
    with pytest.raises(ValueError, match="glyph"):
        Indicator("x", "X", "logo", 0, COLORS, "m:f")
    partial = dict(COLORS)
    partial.pop(State.NA)
    with pytest.raises(ValueError, match="colors"):
        Indicator("x", "X", "dot", 0, partial, "m:f")


def test_config_filters_by_trigger_and_serializes() -> None:
    render = Indicator("a", "A", "dot", 0, COLORS, "m:a", triggers=frozenset({"render"}))
    change = Indicator("b", "B", "dot", 1, COLORS, "m:b", triggers=frozenset({"change"}))
    disabled = Indicator("c", "C", "dot", 2, COLORS, "m:c", enabled=False)
    config = IndicatorConfig(1, Arc(315, 45, 12, 320), (change, disabled, render))
    assert [item.id for item in config.enabled_for("render")] == ["a"]
    assert [item.id for item in config.enabled_for("change")] == ["b"]
    payload = config.to_dict()
    assert payload["indicators"][0]["colors"]["verified"] == "#000000"
    assert payload["arc"]["first_deg"] == 320


def test_config_rejects_duplicate_ids_and_positions() -> None:
    one = Indicator("a", "A", "dot", 0, COLORS, "m:a")
    two = Indicator("a", "B", "dot", 1, COLORS, "m:b")
    with pytest.raises(ValueError, match="duplicate"):
        IndicatorConfig(1, Arc(315, 45, 12, 320), (one, two))
