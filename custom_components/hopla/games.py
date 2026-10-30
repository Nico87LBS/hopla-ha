"""Bonuses, penalties and the points ledger kept by Hopla."""
from datetime import datetime, timedelta

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


def history_page(rows, members, limit, tasks=(), rewards=()):
    """One page of a member's ledger for the cards, newest first.

    `rows` holds up to one row more than `limit`, which only tells whether
    older rows remain. Each entry gets a name to show: the reason Hopla wrote,
    else the task or reward it is about.
    """
    task_names = {task.id: task.name for task in tasks or []}
    reward_names = {reward.id: reward.name for reward in rewards or []}
    entries = ledger_entries((rows or [])[:limit], members)
    for entry in entries:
        entry["name"] = (entry["reason"] or task_names.get(entry["task_id"])
                         or reward_names.get(entry["reward_id"]) or "")
    return {"entries": entries, "more": len(rows or []) > limit}


def presets(rows):
    """Ready-made bonuses (points > 0) and penalties (points < 0)."""
    return [{"id": row["id"], "name": row["name"], "points": row["points"]} for row in rows or []]


class PointsLedgerTracker:
    """Fire an event for each new ledger row: task, undo, redeem, game, bonus or penalty.

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
        "image": rank.get("image") or None,
        "earned": item.get("earned", 0),
        "min_points": rank.get("minPoints", 0),
        "next_name": following.get("name") if following else None,
        "next_icon": following.get("icon") if following else None,
        "next_image": (following.get("image") or None) if following else None,
        "next_points": following.get("minPoints") if following else None,
        "stars": item.get("stars", 0),
        "round_points": item.get("points", item.get("earned", 0)),
        "star_at": item.get("starAt") or None,
    }


def chrono_attributes(flash):
    """The speed bonus open on a task, for its sensor: extra points until ends_at.

    live_id is set when a parent started it on the spot, None for the task's own.
    """
    if not isinstance(flash, dict) or not flash.get("endsAt"):
        return None
    return {"points": flash.get("points", 0), "ends_at": flash["endsAt"], "live_id": flash.get("liveId") or None}


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
        # A member who was away has a lower target in a challenge that isn't shared.
        "targets": {int(user_id): value for user_id, value in (challenge.get("targets") or {}).items()},
        "days_away": {int(user_id): value for user_id, value in (challenge.get("daysAway") or {}).items()},
        "total": challenge.get("total", 0),
        "reward": challenge.get("reward", 0),
        "reward_text": challenge.get("rewardText") or None,
        "starts_at": challenge.get("startsAt"),
        "ends_at": challenge.get("endsAt"),
        "done": bool(challenge.get("completedAt")) if shared else bool(winners),
        "winners": winners,
    }


def _routine(routine):
    """A routine, its tasks (each child's copy included) and where each
    member stands today."""
    return {
        "id": routine["id"],
        "name": routine.get("name"),
        "bonus": routine.get("bonus", 0),
        "task_ids": routine.get("taskIds") or [],
        "members": [{
            "user_id": item["userId"],
            "current": item.get("current"),
            "step": item.get("step", 0),
            "done": item.get("done", 0),
            "total": item.get("total", 0),
            "finished": item.get("finished", False),
        } for item in routine.get("members") or []],
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
            "task_ids": surprise.get("choreIds") or [surprise["choreId"]],
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
        # Every rank of the circle, lowest first, for the card's rank details.
        "rank_ladder": [{
            "name": rank.get("name"),
            "icon": rank.get("icon"),
            "image": rank.get("image") or None,
            "min_points": rank.get("minPoints", 0),
        } for rank in sorted(data.get("ranks") or [], key=lambda rank: rank.get("minPoints", 0))],
        "quests": {item["userId"]: [_quest(q) for q in item.get("quests") or []] for item in data.get("members") or []},
        "challenges": [_challenge(c) for c in data.get("challenges") or []],
        # Whether the parents stand on the podium with the children.
        "parents_on_podium": data.get("parentsOnPodium", False),
        # What the family earns: hops, points, stars, carrots, coins or tokens.
        "currency": data.get("currency") or "hops",
        # When the games change on their own: midnight, a bonus period edge.
        "next_change_at": data.get("nextChangeAt"),
        # Tasks chained in order: each child sees the step to do now.
        "routines": [_routine(r) for r in data.get("routines") or []],
    }


class NextChangeRefresh:
    """Refresh right after the games change on their own (midnight, a bonus
    period starting or ending): no task changes then, so no live event comes.

    schedule(when, action) runs action at when and returns a cancel callback.
    """

    def __init__(self, schedule, refresh):
        self._schedule = schedule
        self._refresh = refresh
        self._when = None
        self._cancel = None

    def update(self, today):
        when = _parse_time((today or {}).get("next_change_at"))
        if when == self._when:
            return
        self.cancel()
        self._when = when
        if when is not None:
            # A second late, so Hopla's clock is past the change too.
            self._cancel = self._schedule(when + timedelta(seconds=1), self._fire)

    def _fire(self, *_args):
        self._cancel = None
        self._when = None
        self._refresh()

    def cancel(self):
        if self._cancel:
            self._cancel()
        self._cancel = None
        self._when = None


def _parse_time(value):
    if not value:
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Go's zero time means Hopla is too old to say.
    return when if when.year > 1 and when.tzinfo else None


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
        # A prestige star restarts the ranks, so a level is compared with its stars.
        levels = {user_id: (rank.get("stars", 0), rank["level"])
                  for user_id, rank in (today.get("ranks") or {}).items()}
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
                    new_star = level[0] > self._levels[user_id][0]
                    fire(EVENT_RANK_UP, {**today["ranks"][user_id], "new_star": new_star}, user_id)
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
