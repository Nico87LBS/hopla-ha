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


EVENT_SURPRISE_TASK = "hopla_surprise_task"
EVENT_BONUS_PERIOD_STARTED = "hopla_bonus_period_started"
EVENT_BONUS_PERIOD_ENDED = "hopla_bonus_period_ended"


def games_today(data):
    """Today's games from Hopla, in the shape the sensors and events use."""
    if not data:
        return None
    surprise = data.get("surprise")
    period = data.get("period")
    rules = data.get("rules") or {}
    return {
        "surprise": {
            "task_id": surprise["choreId"],
            "task_name": surprise.get("name"),
            "points": surprise["points"],
            "day": surprise.get("day"),
        } if surprise else None,
        "bonus_period": {
            "id": period["id"],
            "name": period["name"],
            "multiplier": period["multiplier"],
            "starts_at": period["startsAt"],
            "ends_at": period["endsAt"],
        } if period else None,
        "streaks": {
            item["userId"]: {
                "current": item["current"],
                "best": item["best"],
                "done_today": item.get("doneToday", False),
            } for item in data.get("streaks") or []
        },
        "streak_every": rules.get("streakEvery", 0),
        "streak_bonus": rules.get("streakBonus", 0),
    }


class GamesTracker:
    """Fire events when the surprise task is drawn and when a bonus period starts or ends.

    Like the other trackers, the first refresh only records the current state.
    """

    def __init__(self, fire):
        self._fire = fire
        self._seen = False
        self._surprise = None
        self._period = None

    def update(self, today, entry_id):
        surprise = (today or {}).get("surprise")
        period = (today or {}).get("bonus_period")
        surprise_key = (surprise["day"], surprise["task_id"]) if surprise else None
        if self._seen:
            if surprise_key and surprise_key != self._surprise:
                self._fire(EVENT_SURPRISE_TASK, {**surprise, "config_entry_id": entry_id})
            if self._period and (not period or period["id"] != self._period["id"]):
                self._fire(EVENT_BONUS_PERIOD_ENDED, {**self._period, "config_entry_id": entry_id})
            if period and (not self._period or period["id"] != self._period["id"]):
                self._fire(EVENT_BONUS_PERIOD_STARTED, {**period, "config_entry_id": entry_id})
        self._seen = True
        self._surprise = surprise_key
        self._period = period
