from __future__ import annotations


def execute_approved_actions(actions: list[dict], approved: bool) -> list[dict]:
    """Deterministic execution boundary; callers must pass an approved decision."""
    if not approved:
        return []
    return [{**action, "status": "submitted"} for action in actions]

