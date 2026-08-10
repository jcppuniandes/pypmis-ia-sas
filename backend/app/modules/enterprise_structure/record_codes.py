"""Deterministic, visible hierarchy codes for enterprise workspaces."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol


class HierarchyRecord(Protocol):
    external_key: str
    parent_external_key: str | None
    sort_order: int | None
    name: str


def format_segment(sequence: int) -> str:
    """Keep two-digit segments through 99 and extend without rewriting older codes."""
    if sequence < 1:
        raise ValueError("Hierarchy sequence must be positive")
    return f"{sequence:02d}"


def next_record_code(parent_record_code: str | None, sibling_codes: Iterable[str]) -> str:
    sequences: list[int] = []
    for code in sibling_codes:
        segment = str(code).rsplit(".", 1)[-1]
        if segment.isdigit():
            sequences.append(int(segment))
    suffix = format_segment(max(sequences, default=0) + 1)
    return f"{parent_record_code}.{suffix}" if parent_record_code else suffix


def plan_record_codes(nodes: Iterable[HierarchyRecord]) -> dict[str, str]:
    """Preview codes from input hierarchy without touching persistence."""
    rows = list(nodes)
    children: dict[str | None, list[HierarchyRecord]] = defaultdict(list)
    for node in rows:
        children[node.parent_external_key].append(node)

    planned: dict[str, str] = {}

    def assign(parent_key: str | None, prefix: str | None) -> None:
        siblings = sorted(
            children.get(parent_key, []),
            key=lambda item: (item.sort_order or 0, item.name.casefold(), item.external_key),
        )
        for index, node in enumerate(siblings, start=1):
            record_code = f"{prefix}.{format_segment(index)}" if prefix else format_segment(index)
            planned[node.external_key] = record_code
            assign(node.external_key, record_code)

    assign(None, None)
    return planned
