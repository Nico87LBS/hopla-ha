"""Keep parent actions for parents, even on a tablet the whole family uses.

Parents are Home Assistant users chosen in the integration options. Anyone
else, such as a shared "Tablette" account, can complete tasks and ask for
rewards, while approving, editing and spending points need a parent. On the
tablet, a parent opens parent mode for two minutes with a four-digit code.
"""
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
import hmac
import re
import secrets

PARENT_MODE_DURATION = timedelta(minutes=2)
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT = timedelta(minutes=5)
# Four digits can never resist a search on a stolen hash; the attempt limit
# protects the code. Hashing only keeps it out of plain sight, and stays fast
# enough to run in the event loop.
PIN_ITERATIONS = 10_000

EVENT_REWARD_REQUESTED = "hopla_reward_requested"
EVENT_REWARD_REQUEST_RESOLVED = "hopla_reward_request_resolved"

REDEMPTION_PENDING = 0


def valid_pin(pin) -> bool:
    """A parent code is exactly four digits."""
    return isinstance(pin, str) and re.fullmatch(r"\d{4}", pin) is not None


def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hash, salt) for storing a code without the code itself."""
    salt = salt or secrets.token_hex(16)
    digest = pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PIN_ITERATIONS)
    return digest.hex(), salt


class ParentModeError(Exception):
    """The action needs a parent, or the code was refused."""

    def __init__(self, reason: str, **details):
        super().__init__(reason)
        self.reason = reason
        self.details = details


class ParentGuard:
    """Decide who may run parent actions, and hold parent mode open for a while."""

    def __init__(self, parent_users=(), pin_hash=None, pin_salt=None,
                 now=lambda: datetime.now(timezone.utc), on_change=None):
        self.parent_users = list(parent_users or [])
        self._pin_hash = pin_hash
        self._pin_salt = pin_salt
        self._now = now
        self._on_change = on_change
        self.unlocked_until = None
        self._failures = 0
        self._locked_out_until = None

    @property
    def enabled(self) -> bool:
        """With no parent chosen, everyone keeps full access as before."""
        return bool(self.parent_users)

    @property
    def has_pin(self) -> bool:
        return bool(self._pin_hash and self._pin_salt)

    @property
    def unlocked(self) -> bool:
        return self.unlocked_until is not None and self._now() < self.unlocked_until

    def is_parent(self, user_id) -> bool:
        """Automations run without a user and count as parents: parents wrote them."""
        return (not self.enabled or user_id is None or user_id in self.parent_users
                or self.unlocked)

    def require_parent(self, user_id) -> None:
        if not self.is_parent(user_id):
            raise ParentModeError("parent_required")

    def unlock(self, pin) -> datetime:
        """Open parent mode with the code, or raise after a wrong one."""
        now = self._now()
        if self._locked_out_until and now < self._locked_out_until:
            raise ParentModeError("pin_locked", until=self._locked_out_until)
        if not self.has_pin:
            raise ParentModeError("pin_not_set")
        expected = self._pin_hash
        actual = hash_pin(pin, self._pin_salt)[0] if valid_pin(pin) else ""
        if not hmac.compare_digest(actual, expected):
            self._failures += 1
            if self._failures >= MAX_PIN_ATTEMPTS:
                self._failures = 0
                self._locked_out_until = now + PIN_LOCKOUT
                raise ParentModeError("pin_locked", until=self._locked_out_until)
            raise ParentModeError("pin_wrong", attempts_left=MAX_PIN_ATTEMPTS - self._failures)
        self._failures = 0
        self._locked_out_until = None
        self.unlocked_until = now + PARENT_MODE_DURATION
        self._changed()
        return self.unlocked_until

    def lock(self) -> None:
        if self.unlocked_until is not None:
            self.unlocked_until = None
            self._changed()

    def expire(self) -> None:
        """Close parent mode once its time is up; called by a timer."""
        if self.unlocked_until is not None and not self.unlocked:
            self.unlocked_until = None
            self._changed()

    def _changed(self):
        if self._on_change is not None:
            self._on_change()


def pending_rewards(redemptions, members):
    """Describe each reward request waiting for a parent."""
    names = {member.user_id: member.display_name or member.username for member in members}
    return [{
        "redemption_id": r.id,
        "reward_id": r.reward_id,
        "reward_name": r.reward_name,
        "points_cost": r.points_cost,
        "user_id": r.user_id,
        "user_name": names.get(r.user_id),
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
    } for r in redemptions if r.status == REDEMPTION_PENDING]


class RewardRequestTracker:
    """Fire an event when a reward request appears and one when it is answered.

    Like approvals, the first refresh only records what is already waiting.
    """

    def __init__(self, fire):
        self._fire = fire
        self._known = None

    def update(self, pending, entry_id):
        current = {item["redemption_id"]: item for item in pending}
        if self._known is not None:
            for key, item in current.items():
                if key not in self._known:
                    self._fire(EVENT_REWARD_REQUESTED, {**item, "config_entry_id": entry_id})
            for key, item in self._known.items():
                if key not in current:
                    self._fire(EVENT_REWARD_REQUEST_RESOLVED, {
                        "redemption_id": key,
                        "reward_name": item["reward_name"],
                        "user_id": item["user_id"],
                        "config_entry_id": entry_id,
                    })
        self._known = current
