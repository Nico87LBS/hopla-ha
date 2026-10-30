"""Hopla models."""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, List
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
  
)


_LOGGER = logging.getLogger(__name__)


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a Hopla timestamp, returning None for empty or invalid values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _LOGGER.debug("Unable to parse Hopla datetime: %s", value)
        return None

@dataclass
class HoplaMember:
    """Hopla family member model."""
    id: int
    user_id: int
    family_id: int
    role: str
    is_active: bool
    username: str
    display_name: str
    image: Optional[str] = None
    points: int = 0
    points_redeemed: int = 0
    # Away, such as at the other parent's home: the member's tasks wait.
    away: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaMember":
        """Create a HoplaMember from JSON data."""
        return cls(
            id=data["id"],
            user_id=data["userId"],
            # circleId: from a server older than 1.29.0.
            family_id=data["familyId"] if "familyId" in data else data["circleId"],
            role=data["role"],
            is_active=data["isActive"],
            username=data["username"],
            display_name=data["displayName"],
            image=data.get("image"),
            points=data.get("points", 0),
            points_redeemed=data.get("pointsRedeemed", 0),
            away=bool(data.get("away", False)),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt")
        )
    
    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["HoplaMember"]:
        """Create a list of HoplaMembers from JSON data."""
        return [cls.from_json(member) for member in data]

@dataclass
class HoplaReward:
    """Hopla reward catalog item."""
    id: int
    name: str
    points_cost: int
    description: Optional[str] = None
    is_active: bool = True
    # Redemptions allowed per member per calendar period; 0 means no limit.
    quota_count: int = 0
    quota_period: Optional[str] = None
    quota_used: dict[int, int] = field(default_factory=dict)
    quota_resets_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaReward":
        """Create a HoplaReward from JSON data."""
        return cls(
            id=data["id"],
            name=data["name"],
            points_cost=data.get("pointsCost", 0),
            description=data.get("description") or None,
            is_active=data.get("isActive", True),
            quota_count=data.get("quotaCount") or 0,
            quota_period=data.get("quotaPeriod") or None,
            quota_used={int(user): used for user, used in (data.get("quotaUsed") or {}).items()},
            quota_resets_at=_parse_datetime(data.get("quotaResetsAt")),
        )


@dataclass
class HoplaRedemption:
    """A member's request to spend points on a reward."""
    id: int
    reward_id: int
    user_id: int
    reward_name: str
    points_cost: int
    status: int  # 0 pending, 1 approved, 2 rejected
    requested_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaRedemption":
        """Create a HoplaRedemption from JSON data."""
        return cls(
            id=data["id"],
            reward_id=data.get("rewardId"),
            user_id=data.get("userId"),
            reward_name=data.get("rewardName", ""),
            points_cost=data.get("pointsCost", 0),
            status=data.get("status", 0),
            requested_at=_parse_datetime(data.get("requestedAt")),
        )


@dataclass
class HoplaAssignee:
    """Hopla assignee model."""
    user_id: int

@dataclass
class HoplaTask:
    """Hopla task model."""
    id: int
    name: str
    next_due_date: Optional[datetime]
    status: int
    priority: int
    labels: Optional[Any]
    is_active: bool
    is_rolling: bool
    frequency_type: str
    frequency: int
    frequency_metadata: Optional[Any]
    assigned_to: Optional[int] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_completed_date: Optional[datetime] = None
    last_completed_by: Optional[int] = None
    duration: Optional[int] = None
    start_time: Optional[datetime] = None
    timer_updated_at: Optional[datetime] = None
    assignee_ids: Optional[List[int]] = None
    points: Optional[int] = None
    notification: bool = False
    # Reminder offsets from the due date: [{"value": -30, "unit": "m"}, ...]
    reminder_templates: Optional[List[dict]] = None
    # For a task done several times a day: today's slots and their state.
    slots_today: Optional[List[dict]] = None
    # "together": the task is for each of its assignees at once.
    assign_strategy: Optional[str] = None
    # The speed bonus open now: {"points", "endsAt", "liveId" when a parent launched it}.
    flash: Optional[dict] = None

    @property
    def together(self) -> bool:
        """Return True when the task is for all its assignees at once."""
        return self.assign_strategy == "together"

    @property
    def members_now(self) -> List[int]:
        """Return who the task is for now: its assignee, or all of them together."""
        if self.together:
            return list(self.assignee_ids or [])
        return [self.assigned_to] if self.assigned_to is not None else []

    @property
    def interval_type(self) -> Optional[str]:
        """Return the interval unit, when this task uses interval recurrence."""
        if self.frequency_type != "interval" or not isinstance(self.frequency_metadata, dict):
            return None
        unit = self.frequency_metadata.get("unit")
        return unit if isinstance(unit, str) and unit else None
    
    @staticmethod
    def reminder_templates_from(metadata: Any) -> List[dict]:
        """Return a task's reminder offsets, ignoring malformed metadata."""
        templates = metadata.get("templates") if isinstance(metadata, dict) else None
        return [template for template in templates or [] if isinstance(template, dict)]

    @classmethod
    def from_json(cls, data: dict) -> "HoplaTask":
        """Create a HoplaTask from JSON data."""
        # Handle assignedTo field - could be in different formats
        assigned_to = None
        if data.get("assignedTo"):
            if isinstance(data["assignedTo"], int):
                assigned_to = data["assignedTo"]
          
        return cls(
            id=data["id"],
            name=data["name"],
            next_due_date=_parse_datetime(data.get("nextDueDate")),
            status=data.get("status", 0),
            priority=data.get("priority", 0),
            labels=data.get("labelsV2") if data.get("labelsV2") is not None else data.get("labels"),
            is_active=data.get("isActive", True),
            is_rolling=data.get("isRolling", False),
            frequency_type=data.get("frequencyType", "once"),
            frequency=data.get("frequency") or 1,
            frequency_metadata=data.get("frequencyMetadata"),
            assigned_to=assigned_to,
            assignee_ids=[assignee["userId"] for assignee in (data.get("assignees") or [])
                          if isinstance(assignee, dict) and isinstance(assignee.get("userId"), int)],
            description=data.get("description"),
            created_at=_parse_datetime(data.get("createdAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            last_completed_date=_parse_datetime(data.get("lastCompletedDate")),
            last_completed_by=data.get("lastCompletedBy"),
            duration=data.get("duration"),
            start_time=_parse_datetime(data.get("startTime")),
            timer_updated_at=_parse_datetime(data.get("timerUpdatedAt")),
            points=data.get("points"),
            notification=bool(data.get("notification")),
            reminder_templates=cls.reminder_templates_from(data.get("notificationMetadata")),
            slots_today=[slot for slot in data.get("slotsToday") or [] if isinstance(slot, dict)],
            assign_strategy=data.get("assignStrategy"),
            flash=data.get("flash") if isinstance(data.get("flash"), dict) else None,
        )
    
    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["HoplaTask"]:
        """Create a list of HoplaTasks from JSON data."""
        return [cls.from_json(task) for task in data]


@dataclass
class HoplaChoreHistory:
    """Hopla chore history model."""
    id: int
    chore_id: int
    performed_at: Optional[datetime]
    completed_by: Optional[int]
    assigned_to: Optional[int]
    due_date: Optional[datetime]
    status: int
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    duration: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    timer_updated_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaChoreHistory":
        """Create a HoplaChoreHistory from JSON data."""
        return cls(
            id=data["id"],
            chore_id=data["choreId"],
            performed_at=_parse_datetime(data.get("performedAt")),
            completed_by=data.get("completedBy"),
            assigned_to=data.get("assignedTo"),
            due_date=_parse_datetime(data.get("dueDate")),
            status=data.get("status", 0),
            notes=data.get("notes"),
            created_at=_parse_datetime(data.get("createdAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            duration=data.get("duration"),
            start_time=_parse_datetime(data.get("startTime")),
            end_time=_parse_datetime(data.get("endTime")),
            timer_updated_at=_parse_datetime(data.get("timerUpdatedAt")),
        )

    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["HoplaChoreHistory"]:
        """Create a list of HoplaChoreHistory objects from JSON data."""
        return [cls.from_json(history) for history in data]
