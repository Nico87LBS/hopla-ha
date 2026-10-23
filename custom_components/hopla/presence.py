"""Children away, such as at the other parent's home: their tasks wait for them."""


def away_ids(members) -> set[int]:
    """Return the members who are away now."""
    return {member.user_id for member in members if getattr(member, "away", False)}


def waits_for_absent(task, away: set[int]) -> bool:
    """Return True when everyone the task is for now is away (same rule as the server)."""
    members = task.members_now
    return bool(away) and bool(members) and all(user_id in away for user_id in members)


def present_tasks(tasks, members):
    """Return the tasks, without those that wait for a child who is away."""
    away = away_ids(members)
    if not away:
        return tasks
    return [task for task in tasks if not waits_for_absent(task, away)]
