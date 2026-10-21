"""Turn each task's reminder settings from Hopla into Home Assistant events.

The Hopla server sends no notifications. A task's reminders are offsets from
its due date (negative before, 0 at the due time, positive after), and this
module fires one event at each of those moments so automations can notify the
right person.
"""
from datetime import datetime, timedelta, timezone

EVENT_TASK_REMINDER = "hopla_task_reminder"

UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def reminder_kind(offset_minutes: int) -> str:
    """Name a reminder by its position relative to the due date."""
    if offset_minutes < 0:
        return "before"
    if offset_minutes > 0:
        return "after"
    return "due"


def task_reminders(task):
    """Return (fire time, offset in minutes) for each reminder of a task."""
    due = task.next_due_date
    if not task.is_active or not task.notification or due is None:
        return []
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    reminders = []
    for template in task.reminder_templates or []:
        unit = UNITS.get(template.get("unit"))
        value = template.get("value")
        if unit is None or not isinstance(value, (int, float)):
            continue
        offset = timedelta(**{unit: value})
        reminders.append((due + offset, int(offset.total_seconds() // 60)))
    return reminders


class ReminderScheduler:
    """Keep one timer per upcoming reminder, in step with the latest tasks.

    `schedule(when, action)` must return a function that cancels the timer.
    """

    def __init__(self, schedule, fire, now=lambda: datetime.now(timezone.utc)):
        self._schedule = schedule
        self._fire = fire
        self._now = now
        self._timers = {}
        self._payloads = {}

    def update(self, tasks, members, entry_id):
        """Schedule new reminders and cancel those that no longer apply."""
        names = {member.user_id: member.display_name or member.username for member in members}
        now = self._now()
        wanted = {}
        for task in tasks:
            for when, offset in task_reminders(task):
                if when <= now:
                    continue
                key = (task.id, when.isoformat(), offset)
                wanted[key] = (when, self._event_data(task, when, offset, names, entry_id))

        for key in list(self._timers):
            if key not in wanted:
                self._timers.pop(key)()
                self._payloads.pop(key, None)
        for key, (when, data) in wanted.items():
            # A renamed or reassigned task keeps its timer but fires the latest details.
            self._payloads[key] = data
            if key not in self._timers:
                self._timers[key] = self._schedule(when, self._trigger(key))

    def cancel_all(self):
        """Cancel every pending reminder."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()
        self._payloads.clear()

    def _trigger(self, key):
        def action(*_):
            self._timers.pop(key, None)
            data = self._payloads.pop(key, None)
            if data is not None:
                self._fire(EVENT_TASK_REMINDER, data)
        return action

    @staticmethod
    def _event_data(task, when, offset, names, entry_id):
        assignee = task.assigned_to
        return {
            "task_id": task.id,
            "task_name": task.name,
            "due_date": task.next_due_date.isoformat(),
            "reminder_at": when.isoformat(),
            "offset_minutes": offset,
            "kind": reminder_kind(offset),
            "assigned_to": assignee,
            "assigned_to_name": names.get(assignee),
            "assignee_ids": list(task.assignee_ids or []),
            "points": task.points,
            "config_entry_id": entry_id,
        }
