"""Track tasks waiting for approval and announce changes as Home Assistant events."""

STATUS_PENDING_APPROVAL = 3
HISTORY_PENDING_APPROVAL = 3

EVENT_PENDING_APPROVAL = "hopla_task_pending_approval"
EVENT_APPROVAL_RESOLVED = "hopla_task_approval_resolved"


def member_name(members, user_id):
    """Return a member's display name, or None when unknown."""
    for member in members:
        if member.user_id == user_id:
            return member.display_name or member.username
    return None


def slot_attributes(slots):
    """Today's slots of a task done several times a day, for its attributes."""
    return [{
        "index": slot.get("index"),
        "name": slot.get("name") or "",
        "time": slot.get("time"),
        "at": slot.get("at"),
        "opens_at": slot.get("opensAt"),
        "closes_at": slot.get("closesAt"),
        "state": slot.get("state"),
        "completed_by": slot.get("completedBy"),
    } for slot in slots or []]


def pending_approvals(tasks, history, members):
    """Describe each active task waiting for approval and who completed it.

    The completer comes from the task's pending history entry; it is None when
    that entry is older than the history window.
    """
    completers = {}
    for occurrence in history:
        if occurrence.status == HISTORY_PENDING_APPROVAL and occurrence.chore_id not in completers:
            completers[occurrence.chore_id] = occurrence.completed_by
    pending = []
    for task in tasks:
        if not task.is_active:
            continue
        # A task done several times a day waits for approval slot by slot.
        for slot in getattr(task, "slots_today", None) or []:
            if slot.get("state") != "pending":
                continue
            pending.append({
                "task_id": task.id,
                "task_name": task.name,
                "points": task.points,
                "completed_by": slot.get("completedBy"),
                "completed_by_name": member_name(members, slot.get("completedBy")),
                "slot": slot.get("index"),
                "slot_name": slot.get("name") or slot.get("time"),
            })
        if task.status != STATUS_PENDING_APPROVAL:
            continue
        completed_by = completers.get(task.id)
        pending.append({
            "task_id": task.id,
            "task_name": task.name,
            "points": task.points,
            "completed_by": completed_by,
            "completed_by_name": member_name(members, completed_by),
        })
    return pending


class ApprovalTracker:
    """Fire one event when a task starts waiting for approval and one when it stops.

    The first refresh only records the current state, so a Home Assistant
    restart does not repeat notifications for tasks that were already waiting.
    """

    def __init__(self, fire):
        self._fire = fire
        self._known = None

    def update(self, pending, entry_id):
        # A slot of a task done several times a day waits on its own.
        current = {(item["task_id"], item.get("slot")): item for item in pending}
        if self._known is not None:
            for key, item in current.items():
                if key not in self._known:
                    self._fire(EVENT_PENDING_APPROVAL, {**item, "config_entry_id": entry_id})
            for key, item in self._known.items():
                if key not in current:
                    resolved = {
                        "task_id": item["task_id"],
                        "task_name": item["task_name"],
                        "config_entry_id": entry_id,
                    }
                    if item.get("slot") is not None:
                        resolved["slot"] = item["slot"]
                    self._fire(EVENT_APPROVAL_RESOLVED, resolved)
        self._known = current
