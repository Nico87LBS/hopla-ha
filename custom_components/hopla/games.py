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
EVENT_RANK_UP = "hopla_rank_up"
EVENT_QUEST_COMPLETED = "hopla_quest_completed"
EVENT_CHALLENGE_WON = "hopla_challenge_won"
EVENT_GOAL_REACHED = "hopla_goal_reached"


def _rank(item):
    rank = item.get("rank") or {}
    following = item.get("next")
    return {
        "level": item.get("level", 1),
        "name": rank.get("name"),
        "icon": rank.get("icon"),
        "earned": item.get("earned", 0),
        "min_points": rank.get("minPoints", 0),
        "next_name": following.get("name") if following else None,
        "next_icon": following.get("icon") if following else None,
        "next_points": following.get("minPoints") if following else None,
    }


def _quest(quest):
    return {
        "id": quest["id"],
        "name": quest["name"],
        "kind": quest["kind"],
        "task_id": quest.get("choreId"),
        "period": quest.get("period"),
        "target": quest["target"],
        "progress": quest.get("progress", 0),
        "reward": quest.get("reward", 0),
        "done": bool(quest.get("completedAt")),
        "ends_at": quest.get("endsAt"),
    }


def _challenge(challenge):
    shared = challenge.get("shared", False)
    winners = challenge.get("winners") or []
    return {
        "id": challenge["id"],
        "name": challenge["name"],
        "kind": challenge["kind"],
        "task_id": challenge.get("choreId"),
        "target": challenge["target"],
        "shared": shared,
        "members": challenge.get("members") or [],
        # JSON object keys are strings; member ids are ints everywhere else.
        "progress": {int(user_id): value for user_id, value in (challenge.get("progress") or {}).items()},
        "total": challenge.get("total", 0),
        "reward": challenge.get("reward", 0),
        "reward_text": challenge.get("rewardText") or None,
        "starts_at": challenge.get("startsAt"),
        "ends_at": challenge.get("endsAt"),
        "done": bool(challenge.get("completedAt")) if shared else bool(winners),
        "winners": winners,
    }


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
        "ranks": {item["userId"]: _rank(item) for item in data.get("members") or []},
        "quests": {item["userId"]: [_quest(q) for q in item.get("quests") or []] for item in data.get("members") or []},
        "challenges": [_challenge(c) for c in data.get("challenges") or []],
    }


class GamesTracker:
    """Fire events for the games: the surprise task drawn, a bonus period
    starting or ending, a rank reached, a quest completed, a challenge won and
    a family goal reached.

    Like the other trackers, the first refresh only records the current state.
    """

    def __init__(self, fire):
        self._fire = fire
        self._seen = False
        self._surprise = None
        self._period = None
        self._levels = {}
        self._quests = set()
        self._wins = set()
        self._goals = set()

    def update(self, today, entry_id, members=()):
        today = today or {}
        surprise = today.get("surprise")
        period = today.get("bonus_period")
        surprise_key = (surprise["day"], surprise["task_id"]) if surprise else None
        levels = {user_id: rank["level"] for user_id, rank in (today.get("ranks") or {}).items()}
        quests = {(user_id, quest["id"]) for user_id, items in (today.get("quests") or {}).items()
                  for quest in items if quest["done"]}
        challenges = today.get("challenges") or []
        wins = {(c["id"], user_id) for c in challenges if not c["shared"] for user_id in c["winners"]}
        goals = {c["id"] for c in challenges if c["shared"] and c["done"]}

        def fire(event, data, user_id=None):
            extra = {"user_id": user_id, "user_name": member_name(members, user_id)} if user_id is not None else {}
            self._fire(event, {**data, **extra, "config_entry_id": entry_id})

        if self._seen:
            if surprise_key and surprise_key != self._surprise:
                fire(EVENT_SURPRISE_TASK, surprise)
            if self._period and (not period or period["id"] != self._period["id"]):
                fire(EVENT_BONUS_PERIOD_ENDED, self._period)
            if period and (not self._period or period["id"] != self._period["id"]):
                fire(EVENT_BONUS_PERIOD_STARTED, period)
            for user_id, level in levels.items():
                if user_id in self._levels and level > self._levels[user_id]:
                    fire(EVENT_RANK_UP, today["ranks"][user_id], user_id)
            for user_id, quest_id in sorted(quests - self._quests):
                quest = next(q for q in today["quests"][user_id] if q["id"] == quest_id)
                fire(EVENT_QUEST_COMPLETED, quest, user_id)
            by_id = {c["id"]: c for c in challenges}
            for challenge_id, user_id in sorted(wins - self._wins):
                fire(EVENT_CHALLENGE_WON, by_id[challenge_id], user_id)
            for challenge_id in sorted(goals - self._goals):
                challenge = by_id[challenge_id]
                fire(EVENT_GOAL_REACHED, {**challenge, "member_names": [
                    member_name(members, user_id) for user_id in challenge["members"]]})
        self._seen = True
        self._surprise = surprise_key
        self._period = period
        # A member missing from one refresh keeps their level.
        self._levels.update(levels)
        self._quests |= quests
        self._wins |= wins
        self._goals |= goals
