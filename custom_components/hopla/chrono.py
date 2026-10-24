"""Turn speed bonuses (chrono) into Home Assistant events.

A speed bonus gives extra points for a task done before `ends_at`. A parent
can start one on the spot, and a task can carry its own, open for some minutes
after its due time. This module fires `hopla_chrono_started` when one starts
(when the parent starts it, or at the task's due time) and
`hopla_chrono_ended` when its time is up, so automations can announce them.
A speed bonus that goes away early, because the task was done or a parent
stopped it, ends without an event.
"""
from datetime import datetime, timezone

EVENT_CHRONO_STARTED = "hopla_chrono_started"
EVENT_CHRONO_ENDED = "hopla_chrono_ended"


def _parse(value):
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def running_chronos(tasks, names):
    """Return {key: (starts_at, ends_at, data)} for each speed bonus on the tasks.

    One a parent started covers the copies of a task, so it counts once for all
    of them, with every child it is for. starts_at is None when it started on
    the spot, else the task's due time.
    """
    chronos = {}
    for task in tasks:
        flash = task.flash if isinstance(task.flash, dict) else None
        ends = _parse(flash.get("endsAt")) if flash else None
        if ends is None:
            continue
        live_id = flash.get("liveId") or None
        key = ("live", live_id) if live_id else ("task", task.id, ends.isoformat())
        ids = list(task.assignee_ids or []) or ([task.assigned_to] if task.assigned_to else [])
        if key in chronos:
            data = chronos[key][2]
            for user_id in ids:
                if user_id not in data["assignee_ids"]:
                    data["assignee_ids"].append(user_id)
                    data["assignee_names"].append(names.get(user_id))
            continue
        starts = None if live_id else _parse(task.next_due_date)
        chronos[key] = (starts, ends, {
            "task_id": task.id,
            "task_name": task.name,
            "points": flash.get("points", 0),
            "task_points": task.points,
            "ends_at": ends.isoformat(),
            "launched": bool(live_id),
            "assigned_to": task.assigned_to,
            "assigned_to_name": names.get(task.assigned_to),
            "assignee_ids": list(ids),
            "assignee_names": [names.get(user_id) for user_id in ids],
        })
    return chronos


class ChronoTracker:
    """Keep a timer for the start and the end of each speed bonus.

    Like approvals, the first refresh fires nothing for the speed bonuses
    already running. `schedule(when, action)` must return a function that
    cancels the timer.
    """

    def __init__(self, schedule, fire, now=lambda: datetime.now(timezone.utc)):
        self._schedule = schedule
        self._fire = fire
        self._now = now
        self._known = None
        self._timers = {}
        self._payloads = {}

    def update(self, tasks, members, entry_id):
        names = {member.user_id: member.display_name or member.username for member in members}
        now = self._now()
        chronos = running_chronos(tasks, names)
        wanted = {}
        for key, (starts, ends, data) in chronos.items():
            data = {**data, "config_entry_id": entry_id}
            if starts is None or starts <= now:
                if self._known is not None and key not in self._known:
                    self._fire(EVENT_CHRONO_STARTED, {**data, "minutes_left": _minutes_left(ends, now)})
            else:
                wanted[(key, "start")] = (starts, EVENT_CHRONO_STARTED, data, ends)
            if ends > now:
                wanted[(key, "end")] = (ends, EVENT_CHRONO_ENDED, data, ends)
        self._known = set(chronos)

        for timer in list(self._timers):
            if timer not in wanted:
                self._timers.pop(timer)()
                self._payloads.pop(timer, None)
        for timer, (when, event, data, ends) in wanted.items():
            self._payloads[timer] = (event, data, ends)
            if timer not in self._timers:
                self._timers[timer] = self._schedule(when, self._trigger(timer))

    def cancel_all(self):
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()
        self._payloads.clear()

    def _trigger(self, timer):
        def action(*_):
            self._timers.pop(timer, None)
            payload = self._payloads.pop(timer, None)
            if payload is None:
                return
            event, data, ends = payload
            if event == EVENT_CHRONO_STARTED:
                data = {**data, "minutes_left": _minutes_left(ends, self._now())}
            self._fire(event, data)
        return action


def _minutes_left(ends, now):
    seconds = (ends - now).total_seconds()
    return max(0, int(-(-seconds // 60)))
