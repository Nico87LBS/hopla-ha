"""Read the Hopla server's live event stream (Server-Sent Events)."""
import json

EVENT_HEARTBEAT = "heartbeat"
EVENT_CONNECTED = "connection.established"
EVENT_TASK_COMPLETED = "chore.completed"

# Completion history statuses, as sent by the server.
HISTORY_COMPLETED = 1
HISTORY_PENDING_APPROVAL = 3


class SSEParser:
    """Turn stream lines into decoded event payloads."""

    def __init__(self):
        self._data = []

    def feed_line(self, line: str):
        """Return the decoded event once a blank line ends it, otherwise None."""
        line = line.rstrip("\r\n")
        if not line:
            if not self._data:
                return None
            raw = "\n".join(self._data)
            self._data = []
            try:
                event = json.loads(raw)
            except ValueError:
                return None
            return event if isinstance(event, dict) else None
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data.append(value)
        return None


def reconnect_delay(attempt: int, base: float = 5, cap: float = 300) -> float:
    """Seconds to wait before reconnection attempt number `attempt` (from 0)."""
    return min(cap, base * 2 ** min(attempt, 10))


def needs_refresh(event: dict) -> bool:
    """Whether an event means the family's data changed."""
    return event.get("type") not in (EVENT_HEARTBEAT, None)


def completion_details(event: dict):
    """Describe a finished task from a chore.completed event, or None.

    A completion waiting for approval is not finished yet: the approval
    events announce it instead.
    """
    if event.get("type") != EVENT_TASK_COMPLETED:
        return None
    data = event.get("data") or {}
    chore = data.get("chore") or {}
    history = data.get("history") or {}
    if history.get("status", HISTORY_COMPLETED) != HISTORY_COMPLETED or not chore.get("id"):
        return None
    user = data.get("user") or {}
    return {
        "task_id": chore["id"],
        "task_name": chore.get("name"),
        "points": history.get("points", chore.get("points")),
        "completed_by": history.get("completedBy", user.get("id")),
    }
