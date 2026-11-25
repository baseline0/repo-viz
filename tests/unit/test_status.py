"""Status-slot rules and descendant roll-up are deterministic."""

from __future__ import annotations

from repo_viz.model import Metrics, Node, NodeKind, StatusState
from repo_viz.status import rollup_status, status_for


def test_secret_tag_is_a_security_violation() -> None:
    strip = status_for(frozenset({"secret"}), 3, True)
    assert strip.security is StatusState.VIOLATION


def test_complexity_thresholds_drive_efficiency_slot() -> None:
    assert status_for(frozenset(), 16, True).efficiency is StatusState.VIOLATION
    assert status_for(frozenset(), 12, True).efficiency is StatusState.PARTIAL
    assert status_for(frozenset(), 4, True).efficiency is StatusState.VERIFIED
    assert status_for(frozenset(), 0, False).efficiency is StatusState.NOT_APPLICABLE


def test_tags_bubble_from_symbol_to_membrane() -> None:
    members = (
        Node(id=".", label="repo", kind=NodeKind.MEMBRANE),
        Node(id="pkg", label="pkg", kind=NodeKind.MEMBRANE, parent=".", lod_rank=1),
        Node(
            id="pkg/mod.py::f",
            label="f",
            kind=NodeKind.SYMBOL,
            parent="pkg",
            lod_rank=3,
            tags=frozenset({"secret", "untyped"}),
            metrics=Metrics(complexity=11),
        ),
    )
    rolled = {node.id: node for node in rollup_status(members)}
    assert "secret" in rolled["pkg"].tags
    assert rolled["pkg"].status.security is StatusState.VIOLATION
    assert rolled["pkg"].status.efficiency is StatusState.PARTIAL
    assert rolled["pkg"].status.hygiene is StatusState.PARTIAL
