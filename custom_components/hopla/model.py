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
class HoplaProject:
    """Hopla project model."""
    id: int
    name: str
    description: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaProject":
        """Create a HoplaProject from JSON data."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
        )

    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["HoplaProject"]:
        """Create a list of HoplaProjects from JSON data."""
        return [cls.from_json(project) for project in data]

@dataclass
class HoplaMember:
    """Hopla circle member model."""
    id: int
    user_id: int
    circle_id: int
    role: str
    is_active: bool
    username: str
    display_name: str
    image: Optional[str] = None
    points: int = 0
    points_redeemed: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_json(cls, data: dict) -> "HoplaMember":
        """Create a HoplaMember from JSON data."""
        return cls(
            id=data["id"],
            user_id=data["userId"],
            circle_id=data["circleId"],
            role=data["role"],
            is_active=data["isActive"],
            username=data["username"],
            display_name=data["displayName"],
            image=data.get("image"),
            points=data.get("points", 0),
            points_redeemed=data.get("pointsRedeemed", 0),
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
    project_id: Optional[int] = None
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

    @property
    def interval_type(self) -> Optional[str]:
        """Return the interval unit, when this task uses interval recurrence."""
        if self.frequency_type != "interval" or not isinstance(self.frequency_metadata, dict):
            return None
        unit = self.frequency_metadata.get("unit")
        return unit if isinstance(unit, str) and unit else None
    
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
            project_id=data.get("projectId"),
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

@dataclass 
class HoplaThing:
    """Hopla thing model."""
    id: int
    name: str
    type: str  # text, number, boolean, action
    state: str
    user_id: int
    circle_id: int
    updated_at: Optional[str] = None
    created_at: Optional[str] = None
    thing_chores: Optional[List] = None
    
    @classmethod
    def from_json(cls, data: dict) -> "HoplaThing":
        """Create a HoplaThing from JSON data."""
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            state=str(data["state"]),
            user_id=data["userID"],
            circle_id=data["circleId"],
            updated_at=data.get("updatedAt"),
            created_at=data.get("createdAt"),
            thing_chores=data.get("thingChores")
        )
    
    @classmethod
    def from_json_list(cls, data: List[dict]) -> List["HoplaThing"]:
        """Create a list of HoplaThings from JSON data."""
        return [cls.from_json(thing) for thing in data]
    
