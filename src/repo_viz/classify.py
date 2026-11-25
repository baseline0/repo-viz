"""Signature tables that turn dotted call names into tracks and security tags.

## Specification Map

- ``EGRESS_SIGNATURES`` — dotted prefixes that move data out of a component.
- ``SECRET_SOURCES`` — dotted prefixes that read credentials or configuration.
- ``INGRESS_DECORATORS`` — decorator suffixes that expose a symbol externally.
- ``classify_call`` — the single classification entry point used by the parser.
"""

from __future__ import annotations

from repo_viz.model import EdgeKind, Track

EGRESS_SIGNATURES: dict[str, tuple[str, ...]] = {
    "http": ("httpx.", "requests.", "urllib.request", "aiohttp.", "urllib3."),
    "db": ("psycopg.", "psycopg2.", "sqlalchemy.", "asyncpg.", "pymongo.", "redis.", "sqlite3."),
    "exec": ("subprocess.", "os.system", "os.popen"),
    "network": ("socket.", "boto3.", "google.cloud."),
}

SECRET_SOURCES: tuple[str, ...] = ("os.environ", "os.getenv", "pydantic_settings.", "keyring.", "dotenv.")

INGRESS_DECORATORS: tuple[str, ...] = (
    ".get",
    ".post",
    ".put",
    ".patch",
    ".delete",
    ".route",
    "shared_task",
    ".websocket",
)


def matches(dotted: str, signatures: tuple[str, ...]) -> bool:
    """Return True when ``dotted`` starts with one of the dotted prefixes."""
    return any(dotted == prefix.rstrip(".") or dotted.startswith(prefix) for prefix in signatures)


def classify_call(dotted: str) -> tuple[EdgeKind, frozenset[Track], frozenset[str]]:
    """Classify a fully qualified call into an edge kind, tracks, and node tags.

    Unknown calls are ordinary control-flow calls. Egress calls are both data and
    security edges; secret reads are security-only. Multiple egress families on one
    call are represented by multiple tags, keeping the signature table explicit.
    """
    tags: set[str] = set()
    kinds: set[EdgeKind] = set()
    for family, prefixes in EGRESS_SIGNATURES.items():
        if matches(dotted, prefixes):
            kinds.add(
                {
                    "http": EdgeKind.HTTP,
                    "db": EdgeKind.DB,
                    "exec": EdgeKind.EXEC,
                    "network": EdgeKind.HTTP,
                }[family]
            )
            tags.add(f"egress:{family}")
    if matches(dotted, SECRET_SOURCES):
        kinds.add(EdgeKind.SECRET)
        tags.add("secret")
    if kinds:
        tracks = {Track.SECURITY}
        if kinds & {EdgeKind.HTTP, EdgeKind.DB, EdgeKind.EVENT}:
            tracks.add(Track.DATA)
        if EdgeKind.EXEC in kinds:
            tracks.add(Track.CONTROL)
        # Keep one deterministic kind when a call matches several families.
        kind = sorted(kinds, key=lambda item: item.value)[0]
        return kind, frozenset(tracks), frozenset(tags)
    return EdgeKind.CALL, frozenset({Track.CONTROL}), frozenset()


def is_ingress_decorator(dotted: str) -> bool:
    """Return True for framework decorators that expose a symbol to callers."""
    return any(dotted == suffix.lstrip(".") or dotted.endswith(suffix) for suffix in INGRESS_DECORATORS)
