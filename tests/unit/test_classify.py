"""Egress, secret and ingress signature tables are explicit and deterministic."""

from __future__ import annotations

from repo_viz.classify import classify_call, is_ingress_decorator
from repo_viz.model import EdgeKind, Track


def test_http_call_is_data_and_security() -> None:
    kind, tracks, tags = classify_call("httpx.get")
    assert kind is EdgeKind.HTTP
    assert tracks == frozenset({Track.DATA, Track.SECURITY})
    assert tags == frozenset({"egress:http"})


def test_secret_source_is_security_only() -> None:
    kind, tracks, tags = classify_call("os.getenv")
    assert kind is EdgeKind.SECRET
    assert tracks == frozenset({Track.SECURITY})
    assert tags == frozenset({"secret"})


def test_exec_sink_adds_control_track() -> None:
    kind, tracks, tags = classify_call("subprocess.run")
    assert kind is EdgeKind.EXEC
    assert Track.CONTROL in tracks
    assert "egress:exec" in tags


def test_unknown_call_is_plain_control() -> None:
    assert classify_call("helper") == (EdgeKind.CALL, frozenset({Track.CONTROL}), frozenset())


def test_decorator_recognizes_framework_entry_points() -> None:
    assert is_ingress_decorator("app.get")
    assert is_ingress_decorator("shared_task")
    assert not is_ingress_decorator("functools.wraps")
