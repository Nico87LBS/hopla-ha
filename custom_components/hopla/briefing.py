"""Morning briefing: the tasks of the day that nothing else announces.

A task with no moment, no deadline and no reminder never triggers
`hopla_task_reminder` nor `hopla_time_notice`. Once a day, at a time the
family chooses, this module lists those tasks so an automation can say them
on a speaker, for instance "Elena, aujourd'hui : ranger ta chambre".
Each task is listed for its own person; a task for nobody is listed apart.
"""
from datetime import datetime, timezone

EVENT_DAILY_BRIEFING = "hopla_daily_briefing"

# Value of the people filter that stands for the tasks of nobody.
NOBODY = "none"
STATUS_PENDING_APPROVAL = 3


def parse_time(value):
    """Read "07:30" as (7, 30); anything else means the briefing is off."""
    try:
        hour, minute = str(value or "").strip().split(":")[:2]
        hour, minute = int(hour), int(minute)
    except ValueError:
        return None
    return (hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None


def parse_members(values):
    """Normalise the people filter: user ids as text, plus NOBODY. Empty keeps everybody."""
    return {str(value) for value in values or [] if str(value)}


def has_hour(task):
    """Whether something already announces this task during the day."""
    metadata = task.frequency_metadata if isinstance(task.frequency_metadata, dict) else {}
    if task.slots_today or metadata.get("slots") or task.deadline is not None:
        return True
    return bool(task.notification and task.reminder_templates)


def _day(moment, tz):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz).date()


def briefing_tasks(tasks, names, today, tz, members_filter=()):
    """Return the briefing: every open task of the day without an hour, by person."""
    wanted = parse_members(members_filter)
    listed = []
    for task in tasks:
        if not task.is_active or task.next_due_date is None or task.status == STATUS_PENDING_APPROVAL:
            continue
        due = _day(task.next_due_date, tz)
        if due > today or has_hour(task):
            continue
        ids = [user_id for user_id in task.members_now if user_id is not None]
        if wanted:
            keep = [user_id for user_id in ids if str(user_id) in wanted]
            if not keep and not (not ids and NOBODY in wanted):
                continue
            ids = keep
        listed.append({"task_id": task.id, "name": task.name, "points": task.points or 0,
                       "member_ids": ids, "member_names": [names.get(user_id) for user_id in ids],
                       "late": due < today})
    by_member = {}
    for item in listed:
        for user_id, name in zip(item["member_ids"], item["member_names"]):
            entry = by_member.setdefault(user_id, {"user_id": user_id, "name": name, "tasks": []})
            entry["tasks"].append(item["name"])
    members = [{**entry, "count": len(entry["tasks"])} for entry in by_member.values()]
    return {"count": len(listed), "tasks": listed, "members": members,
            "unassigned": [item["name"] for item in listed if not item["member_ids"]]}
