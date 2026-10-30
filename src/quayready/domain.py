from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Assessment:
    status: str
    reasons: dict[str, tuple[str, list[str]]]


def assess(
    expected: set[str],
    snapshots: dict[str, dict[str, Any]],
    scanned: set[str],
    now: int,
    cutoff: int,
    order_conflicted: bool = False,
) -> Assessment:
    reasons: dict[str, tuple[str, list[str]]] = {}
    w, d = snapshots.get("WAREHOUSE"), snapshots.get("DOCUMENT")
    if (w and w["hard_hold"]) or (d and d["status"] == "HOLD"):
        reasons["HARD_HOLD"] = ("Warehouse" if w and w["hard_hold"] else "Documents", [])
    if now >= cutoff:
        reasons["CUTOFF_REACHED"] = ("Planner", [])
    if w is None:
        reasons["WAREHOUSE_MISSING"] = ("Warehouse", [])
    if d is None:
        reasons["DOCUMENT_MISSING"] = ("Documents", [])
    if w and w["status"] == "UNKNOWN":
        reasons["WAREHOUSE_UNKNOWN"] = ("Warehouse", [])
    if d and d["status"] in ("UNKNOWN", "MISSING"):
        reasons["DOCUMENT_UNKNOWN" if d["status"] == "UNKNOWN" else "DOCUMENT_UNAVAILABLE"] = (
            "Documents",
            [],
        )
    for kind, s in snapshots.items():
        if now >= s["valid_until_ms"]:
            reasons[kind + "_EXPIRED"] = ("Warehouse" if kind == "WAREHOUSE" else "Documents", [])
    if order_conflicted or any(
        s["conflict_revision_floor"] is not None for s in snapshots.values()
    ):
        reasons["SOURCE_CONFLICT"] = ("Integration", [])
    if w and w["status"] == "KNOWN":
        if expected - scanned:
            reasons["MISSING_PALLET"] = ("Warehouse", sorted(expected - scanned))
        if scanned - expected:
            reasons["UNEXPECTED_PALLET"] = ("Warehouse", sorted(scanned - expected))
    status = (
        "BLOCKED"
        if "HARD_HOLD" in reasons or "CUTOFF_REACHED" in reasons
        else "NEEDS_REVIEW"
        if reasons
        else "ELIGIBLE_FOR_REVIEW"
    )
    return Assessment(status, reasons)
