"""Announce when a routine, a moment of a task or a task starts or ends.

Hopla knows the hours of a routine (it opens and closes), of each moment of a
task done several times a day, and the deadline of a task. This module fires
`hopla_time_notice` a few minutes before each of those edges and right at the
edge, so an automation can say, for instance, "la routine du matin se termine
dans 5 minutes" or "le brossage des dents est dépassé" on a speaker.

Nothing fires for hours already past when the integration starts, and an
edge that no longer applies (a routine all its members finished, a moment
that was ticked) is cancelled.
"""
from datetime import datetime, timedelta, timezone

EVENT_TIME_NOTICE = "hopla_time_notice"

DEFAULT_MINUTES_BEFORE = "10,5"
# Moments of a task are announced while they can still be done.
_OPEN_STATES = ("upcoming", "open")


def parse_minutes(value):
    """Read "10, 5" as [10, 5]: minutes before an edge, largest first."""
    minutes = set()
    for part in str(value or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            minutes.add(int(part))
    return sorted(minutes, reverse=True)


def _parse(value):
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _names(ids, names):
    return [names.get(user_id) for user_id in ids]


def notice_edges(tasks, today, names):
    """Return {key: (edge, time, data)} for each start and end to announce."""
    edges = {}

    def add(key, edge, when, data):
        when = _parse(when)
        if when is not None:
            edges[(*key, edge)] = (edge, when, data)

    for routine in (today or {}).get("routines") or []:
        members = [m for m in routine.get("members") or [] if m.get("total", 0) > 0]
        if not routine.get("opens_at") and not routine.get("closes_at"):
            continue
        todo = [m for m in members if not m.get("finished")]
        ids = [m["user_id"] for m in todo]
        data = {"item_type": "routine", "item_id": routine["id"], "item_name": routine.get("name"),
                "member_ids": ids, "member_names": _names(ids, names)}
        if routine.get("window") == "upcoming":
            add(("routine", routine["id"]), "start", routine.get("opens_at"), data)
        # A routine everyone finished has nothing left to announce.
        if routine.get("window") != "over" and (todo or not members):
            add(("routine", routine["id"]), "end", routine.get("closes_at"), data)

    for task in tasks:
        if not task.is_active:
            continue
        ids = list(task.members_now)
        base = {"item_id": task.id, "item_name": task.name, "points": task.points,
                "member_ids": ids, "member_names": _names(ids, names)}
        for slot in task.slots_today or []:
            if slot.get("state") not in _OPEN_STATES:
                continue
            data = {**base, "item_type": "moment", "slot_id": slot.get("slotId") or "",
                    "slot_name": slot.get("name") or slot.get("time") or ""}
            key = ("moment", task.id, slot.get("slotId") or slot.get("index"))
            if slot.get("state") == "upcoming":
                add(key, "start", slot.get("opensAt"), data)
            add(key, "end", slot.get("closesAt"), data)
        deadline = task.deadline
        if deadline is not None:
            data = {**base, "item_type": "task"}
            add(("task", task.id), "start", task.next_due_date, data)
            add(("task", task.id), "end", deadline, data)
    return edges


class NoticeScheduler:
    """Keep one timer per announcement, in step with the latest data.

    `schedule(when, action)` must return a function that cancels the timer.
    """

    def __init__(self, schedule, fire, now=lambda: datetime.now(timezone.utc)):
        self._schedule = schedule
        self._fire = fire
        self._now = now
        self._timers = {}
        self._payloads = {}

    def update(self, tasks, today, members, entry_id, minutes_before=None):
        names = {member.user_id: member.display_name or member.username for member in members}
        offsets = parse_minutes(DEFAULT_MINUTES_BEFORE if minutes_before is None else minutes_before)
        now = self._now()
        wanted = {}
        for key, (edge, when, data) in notice_edges(tasks, today, names).items():
            for offset in [*offsets, 0]:
                fire_at = when - timedelta(minutes=offset)
                if fire_at <= now:
                    continue
                payload = {**data, "edge": edge, "kind": "before" if offset else "now",
                           "offset_minutes": offset, "at": when.isoformat(), "config_entry_id": entry_id}
                wanted[(key, offset)] = (fire_at, payload)

        for timer in list(self._timers):
            if timer not in wanted or self._timers[timer][0] != wanted[timer][0]:
                self._timers.pop(timer)[1]()
                self._payloads.pop(timer, None)
        for timer, (fire_at, payload) in wanted.items():
            # A renamed or reassigned item keeps its timer but says the latest details.
            self._payloads[timer] = payload
            if timer not in self._timers:
                self._timers[timer] = (fire_at, self._schedule(fire_at, self._trigger(timer)))

    def cancel_all(self):
        for _, cancel in self._timers.values():
            cancel()
        self._timers.clear()
        self._payloads.clear()

    def _trigger(self, timer):
        def action(*_):
            self._timers.pop(timer, None)
            payload = self._payloads.pop(timer, None)
            if payload is not None:
                self._fire(EVENT_TIME_NOTICE, payload)
        return action
