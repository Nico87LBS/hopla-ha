"""Bonuses, penalties and the points ledger kept by Hopla."""
EVENT_POINTS_CHANGED = "hopla_points_changed"

# How many ledger rows the sensor shows, newest first.
RECENT_LIMIT = 10


def member_name(members, user_id):
    """Return a member's display name, or None when unknown."""
    for member in members:
        if member.user_id == user_id:
            return member.display_name or member.username
    return None


def ledger_entries(rows, members):
    """Ledger rows from Hopla, with the member names automations want."""
    return [{
        "id": row["id"],
        "user_id": row["userId"],
        "user_name": member_name(members, row["userId"]),
        "action": row["action"],
        "points": row["points"],
        "delta": row["delta"],
        "reason": row.get("reason"),
        "task_id": row.get("choreId"),
        "reward_id": row.get("rewardId"),
        "created_by": row.get("createdBy"),
        "created_by_name": member_name(members, row.get("createdBy")),
        "created_at": row.get("createdAt"),
    } for row in rows or []]


def presets(rows):
    """Ready-made bonuses (points > 0) and penalties (points < 0)."""
    return [{"id": row["id"], "name": row["name"], "points": row["points"]} for row in rows or []]


class PointsLedgerTracker:
    """Fire an event for each new ledger row: task, undo, redeem, bonus or penalty.

    Like approvals, the first refresh only records where the ledger stands.
    """

    def __init__(self, fire):
        self._fire = fire
        self._last_id = None

    def update(self, entries, entry_id):
        newest = max((entry["id"] for entry in entries), default=0)
        if self._last_id is not None:
            for entry in sorted(entries, key=lambda item: item["id"]):
                if entry["id"] > self._last_id:
                    self._fire(EVENT_POINTS_CHANGED, {**entry, "config_entry_id": entry_id})
        self._last_id = max(newest, self._last_id or 0)
