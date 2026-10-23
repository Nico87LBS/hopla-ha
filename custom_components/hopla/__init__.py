"""The Hopla integration."""
import logging
from datetime import timedelta
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from .const import (DOMAIN, CONF_URL, CONF_TOKEN, CONF_SHOW_DUE_IN, LIVE_REFRESH_INTERVAL, OFFLINE_REFRESH_INTERVAL,
                    CONF_PARENT_USERS, CONF_PARENT_PIN_HASH, CONF_PARENT_PIN_SALT)
from .api import HoplaApiClient
from .frontend import async_setup_frontend
from .completion_history import async_completed_occurrences
from .approval import ApprovalTracker, STATUS_PENDING_APPROVAL, pending_approvals, member_name
from .games import GamesTracker, PointsLedgerTracker, games_today, ledger_entries, presets as points_presets
from .realtime import RealtimeListener
from .reminders import ReminderScheduler
from .parental import (ParentGuard, ParentModeError, RewardRequestTracker, pending_rewards,
                       PARENT_MODE_DURATION)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.TODO, Platform.SENSOR, Platform.CALENDAR, Platform.BINARY_SENSOR]

EVENT_TASK_COMPLETED = "hopla_task_completed"

SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_CREATE_TASK = "create_task"
SERVICE_UPDATE_TASK = "update_task"
SERVICE_DELETE_TASK = "delete_task"
SERVICE_SKIP_TASK = "skip_task"
SERVICE_COMPLETE_ASSIGNED_TASK = "complete_assigned_task"
SERVICE_POSTPONE_TASK = "postpone_task"
SERVICE_APPROVE_TASK = "approve_task"
SERVICE_REJECT_TASK = "reject_task"
SERVICE_REDEEM_REWARD = "redeem_reward"
SERVICE_APPROVE_REWARD = "approve_reward"
SERVICE_REJECT_REWARD = "reject_reward"
SERVICE_UNLOCK_PARENT_MODE = "unlock_parent_mode"
SERVICE_LOCK_PARENT_MODE = "lock_parent_mode"
SERVICE_ADJUST_POINTS = "adjust_points"
SERVICE_CATCH_UP_SLOT = "catch_up_slot"
SERVICES = [SERVICE_COMPLETE_TASK, SERVICE_CREATE_TASK, SERVICE_UPDATE_TASK, SERVICE_DELETE_TASK, SERVICE_SKIP_TASK,
            SERVICE_COMPLETE_ASSIGNED_TASK, SERVICE_POSTPONE_TASK, SERVICE_APPROVE_TASK, SERVICE_REJECT_TASK,
            SERVICE_REDEEM_REWARD, SERVICE_APPROVE_REWARD, SERVICE_REJECT_REWARD,
            SERVICE_UNLOCK_PARENT_MODE, SERVICE_LOCK_PARENT_MODE, SERVICE_ADJUST_POINTS, SERVICE_CATCH_UP_SLOT]

COMPLETE_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.Coerce(int),
    vol.Optional("completed_by"): vol.Coerce(int),
    vol.Optional("config_entry_id"): cv.string,
})

CREATE_TASK_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Optional("description"): cv.string,
    vol.Optional("due_date"): cv.string,
    vol.Optional("created_by"): vol.Coerce(int),
    vol.Optional("config_entry_id"): cv.string,
})

UPDATE_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.Coerce(int),
    vol.Optional("name"): cv.string,
    vol.Optional("description"): cv.string,
    vol.Optional("due_date"): cv.string,
    vol.Optional("force_unarchive", default=False): cv.boolean,
    vol.Optional("assigned_to"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1))),
    vol.Optional("config_entry_id"): cv.string,
})

DELETE_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.Coerce(int),
    vol.Optional("config_entry_id"): cv.string,
})

SKIP_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.Coerce(int),
    vol.Optional("completed_by"): vol.Coerce(int),
    vol.Optional("config_entry_id"): cv.string,
})

ASSIGNED_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("config_entry_id"): cv.string,
    # For a task for everyone together: which of them did it.
    vol.Optional("completed_by"): vol.All(vol.Coerce(int), vol.Range(min=1)),
})
POSTPONE_TASK_SCHEMA = ASSIGNED_TASK_SCHEMA

APPROVE_TASK_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    # For a task done several times a day: the slot of today, from 0.
    vol.Optional("slot"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional("config_entry_id"): cv.string,
})

CATCH_UP_SLOT_SCHEMA = vol.Schema({
    vol.Required("task_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Required("slot"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional("completed_by"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("config_entry_id"): cv.string,
})

REJECT_TASK_SCHEMA = APPROVE_TASK_SCHEMA.extend({
    vol.Optional("note"): cv.string,
})

REDEEM_REWARD_SCHEMA = vol.Schema({
    vol.Required("reward_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("user_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("config_entry_id"): cv.string,
})

REWARD_REQUEST_SCHEMA = vol.Schema({
    vol.Required("redemption_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("config_entry_id"): cv.string,
})

UNLOCK_PARENT_MODE_SCHEMA = vol.Schema({
    vol.Required("pin"): cv.string,
    vol.Optional("config_entry_id"): cv.string,
})

LOCK_PARENT_MODE_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
})

MAX_ADJUSTMENT = 1000

# Either an amount (positive for a bonus, negative for a penalty) or a preset.
ADJUST_POINTS_SCHEMA = vol.All(vol.Schema({
    vol.Required("user_id"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Exclusive("points", "amount"): vol.All(vol.Coerce(int), vol.Range(min=-MAX_ADJUSTMENT, max=MAX_ADJUSTMENT),
                                               vol.NotIn([0])),
    vol.Exclusive("preset_id", "amount"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("reason"): vol.All(cv.string, vol.Length(max=200)),
    vol.Optional("config_entry_id"): cv.string,
}), cv.has_at_least_one_key("points", "preset_id"))


def _parent_error(err: ParentModeError) -> ServiceValidationError:
    """Explain in the user's language why a parent action was refused."""
    placeholders = {"attempts_left": str(err.details.get("attempts_left", "")), "minutes": ""}
    if until := err.details.get("until"):
        placeholders["minutes"] = str(max(1, round((until - dt_util.utcnow()).total_seconds() / 60)))
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=err.reason,
                                  translation_placeholders=placeholders)


def require_parent(config: dict, call: ServiceCall) -> None:
    """Refuse a parent action from anyone else, such as the family tablet."""
    try:
        config["parental"].require_parent(call.context.user_id)
    except ParentModeError as err:
        raise _parent_error(err) from err

@callback
def _remove_thing_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the entities of Hopla objects (things), which no longer exist."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (entity.unique_id or "").startswith("hopla_thing_"):
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hopla from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    _remove_thing_entities(hass, entry)
    await async_setup_frontend(hass)

    session = async_get_clientsession(hass)
    client = HoplaApiClient(
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        session,
    )

    # Updated in place so entities holding this list see points and photos change.
    circle_members = []
    approvals = ApprovalTracker(hass.bus.async_fire)
    reminders = ReminderScheduler(
        lambda when, action: async_track_point_in_utc_time(hass, callback(action), when),
        hass.bus.async_fire,
    )
    entry.async_on_unload(reminders.cancel_all)
    reward_requests = RewardRequestTracker(hass.bus.async_fire)
    ledger = PointsLedgerTracker(hass.bus.async_fire)
    games = GamesTracker(hass.bus.async_fire)

    @callback
    def parent_mode_changed() -> None:
        # Entities read parent mode from the guard; tell them to write their state.
        coordinator.async_update_listeners()

    parental = ParentGuard(entry.data.get(CONF_PARENT_USERS, []), entry.data.get(CONF_PARENT_PIN_HASH),
                           entry.data.get(CONF_PARENT_PIN_SALT), on_change=parent_mode_changed)
    entry.async_on_unload(parental.lock)

    async def async_update_tasks():
        tasks = await client.async_get_tasks()
        history = await client.async_get_task_history(days=7)
        coordinator.completed_tasks = await async_completed_occurrences(client, tasks, history)
        try:
            circle_members[:] = await client.async_get_circle_members()
        except Exception as err:
            _LOGGER.warning("Failed to refresh circle members: %s", err)
        try:
            coordinator.rewards = await client.async_get_rewards()
        except Exception as err:
            _LOGGER.debug("Failed to refresh rewards: %s", err)
        if coordinator.rewards is not None:
            try:
                coordinator.pending_rewards = pending_rewards(
                    await client.async_get_redemptions("pending"), circle_members)
                reward_requests.update(coordinator.pending_rewards, entry.entry_id)
            except Exception as err:
                _LOGGER.debug("Failed to refresh reward requests: %s", err)
        try:
            coordinator.points_presets = points_presets(await client.async_get_points_presets())
        except Exception as err:
            _LOGGER.debug("Failed to refresh points presets: %s", err)
        if coordinator.points_presets is not None:
            try:
                coordinator.points_history = ledger_entries(await client.async_get_points_history(), circle_members)
                ledger.update(coordinator.points_history, entry.entry_id)
            except Exception as err:
                _LOGGER.debug("Failed to refresh the points history: %s", err)
        try:
            coordinator.games_today = games_today(await client.async_get_games_today())
            games.update(coordinator.games_today, entry.entry_id, circle_members)
        except Exception as err:
            _LOGGER.debug("Failed to refresh today's games: %s", err)
        coordinator.pending_approvals = pending_approvals(tasks, history, circle_members)
        approvals.update(coordinator.pending_approvals, entry.entry_id)
        reminders.update(tasks, circle_members, entry.entry_id)
        return tasks

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_chores",
        update_method=async_update_tasks,
        update_interval=timedelta(seconds=OFFLINE_REFRESH_INTERVAL),
    )
    coordinator.rewards = None
    coordinator.pending_approvals = []
    coordinator.pending_rewards = []
    coordinator.points_presets = None
    coordinator.points_history = []
    coordinator.games_today = None
    await coordinator.async_config_entry_first_refresh()

    @callback
    def live_status_changed(connected: bool) -> None:
        coordinator.update_interval = timedelta(
            seconds=LIVE_REFRESH_INTERVAL if connected else OFFLINE_REFRESH_INTERVAL)

    @callback
    def task_completed(details: dict) -> None:
        hass.bus.async_fire(EVENT_TASK_COMPLETED, {
            **details,
            "completed_by_name": member_name(circle_members, details["completed_by"]),
            "config_entry_id": entry.entry_id,
        })

    listener = RealtimeListener(
        session, entry.data[CONF_URL], entry.data[CONF_TOKEN],
        coordinator.async_request_refresh, live_status_changed, task_completed,
    )
    # Cancelled automatically when the entry unloads.
    entry.async_create_background_task(hass, listener.run(), f"{DOMAIN}_live_updates")

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_URL: entry.data[CONF_URL],
        CONF_TOKEN: entry.data[CONF_TOKEN],
        CONF_SHOW_DUE_IN: entry.data.get(CONF_SHOW_DUE_IN, 7),
        "coordinator": coordinator,
        "client": client,
        "circle_members": circle_members,
        "listener": listener,
        "parental": parental,
    }
    
    # Register services before setting up platforms
    async def complete_task_handler(call: ServiceCall) -> ServiceResponse:
        return await async_complete_task_service(hass, call)
    
    async def create_task_handler(call: ServiceCall) -> None:
        await async_create_task_service(hass, call)
    
    async def update_task_handler(call: ServiceCall) -> None:
        await async_update_task_service(hass, call)
    
    async def delete_task_handler(call: ServiceCall) -> None:
        await async_delete_task_service(hass, call)

    async def skip_task_handler(call: ServiceCall) -> None:
        await async_skip_task_service(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_TASK,
        complete_task_handler,
        schema=COMPLETE_TASK_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_TASK,
        create_task_handler,
        schema=CREATE_TASK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_TASK,
        update_task_handler,
        schema=UPDATE_TASK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_TASK,
        delete_task_handler,
        schema=DELETE_TASK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SKIP_TASK,
        skip_task_handler,
        schema=SKIP_TASK_SCHEMA,
    )
    _LOGGER.debug("Registered services: %s.%s, %s.%s, %s.%s, %s.%s, %s.%s",
                  DOMAIN, SERVICE_COMPLETE_TASK, DOMAIN, SERVICE_CREATE_TASK,
                  DOMAIN, SERVICE_UPDATE_TASK, DOMAIN, SERVICE_DELETE_TASK,
                  DOMAIN, SERVICE_SKIP_TASK)
    
    async def complete_assigned_handler(call: ServiceCall) -> None:
        await async_task_row_action(hass, call, complete=True)

    async def postpone_handler(call: ServiceCall) -> None:
        await async_task_row_action(hass, call, complete=False)

    hass.services.async_register(DOMAIN, SERVICE_COMPLETE_ASSIGNED_TASK,
                                 complete_assigned_handler, schema=ASSIGNED_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_POSTPONE_TASK,
                                 postpone_handler, schema=POSTPONE_TASK_SCHEMA)

    async def approve_handler(call: ServiceCall) -> None:
        await async_resolve_approval_service(hass, call, approve=True)

    async def reject_handler(call: ServiceCall) -> None:
        await async_resolve_approval_service(hass, call, approve=False)

    async def redeem_handler(call: ServiceCall) -> ServiceResponse:
        return await async_redeem_reward_service(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_APPROVE_TASK,
                                 approve_handler, schema=APPROVE_TASK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REJECT_TASK,
                                 reject_handler, schema=REJECT_TASK_SCHEMA)
    async def catch_up_handler(call: ServiceCall) -> None:
        await async_catch_up_slot_service(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_CATCH_UP_SLOT,
                                 catch_up_handler, schema=CATCH_UP_SLOT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REDEEM_REWARD, redeem_handler,
                                 schema=REDEEM_REWARD_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)

    async def approve_reward_handler(call: ServiceCall) -> None:
        await async_resolve_reward_service(hass, call, approve=True)

    async def reject_reward_handler(call: ServiceCall) -> None:
        await async_resolve_reward_service(hass, call, approve=False)

    async def unlock_handler(call: ServiceCall) -> ServiceResponse:
        return await async_unlock_parent_mode_service(hass, call)

    async def lock_handler(call: ServiceCall) -> None:
        config = await _get_config(hass, call)
        config["parental"].lock()

    hass.services.async_register(DOMAIN, SERVICE_APPROVE_REWARD, approve_reward_handler,
                                 schema=REWARD_REQUEST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REJECT_REWARD, reject_reward_handler,
                                 schema=REWARD_REQUEST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNLOCK_PARENT_MODE, unlock_handler,
                                 schema=UNLOCK_PARENT_MODE_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_LOCK_PARENT_MODE, lock_handler,
                                 schema=LOCK_PARENT_MODE_SCHEMA)

    async def adjust_points_handler(call: ServiceCall) -> ServiceResponse:
        return await async_adjust_points_service(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_ADJUST_POINTS, adjust_points_handler,
                                 schema=ADJUST_POINTS_SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.add_update_listener(async_reload_entry)
    
    return True

async def async_complete_task_service(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Handle the complete_task service call.

    A task that requires approval is only submitted: it waits for an admin and
    the response says so with pending_approval.
    """
    task_id = call.data["task_id"]
    completed_by = call.data.get("completed_by")
    config_entry_id = call.data.get("config_entry_id")
    
    entry = await _get_config_entry(hass, config_entry_id)
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found for complete_task")

    # Get API client and coordinator
    config = hass.data[DOMAIN][entry.entry_id]
    client = config["client"]
    coordinator = config["coordinator"]

    try:
        result = await client.async_complete_task(task_id, completed_by)
    except Exception as e:
        _LOGGER.error("Failed to complete task %d: %s", task_id, e)
        raise HomeAssistantError(f"Failed to complete Hopla task {task_id}: {e}") from e

    # A task done several times a day ticks the slot open now; that slot may
    # wait for a parent while the task itself never does.
    pending = result.status == STATUS_PENDING_APPROVAL or any(
        slot.get("state") == "pending" and _slot_open(slot) for slot in result.slots_today or [])
    _LOGGER.info("Task %d %s by user %s", task_id,
                 "submitted for approval" if pending else "completed", completed_by or "default")
    # Refresh now rather than debounced, so a dashboard tap shows its result at once.
    await coordinator.async_refresh()
    return {"task_id": task_id, "pending_approval": pending}


def _slot_open(slot: dict) -> bool:
    """Return True while a slot of today is the one to do now."""
    opens = dt_util.parse_datetime(slot.get("opensAt") or "")
    closes = dt_util.parse_datetime(slot.get("closesAt") or "")
    return opens is not None and closes is not None and opens <= dt_util.now() < closes


async def async_resolve_approval_service(hass: HomeAssistant, call: ServiceCall, *, approve: bool) -> None:
    """Approve or reject a task completion waiting for approval.

    With a slot, only that slot of today of a task done several times a day.
    """
    task_id = call.data["task_id"]
    slot = call.data.get("slot")
    entry = await _get_config_entry(hass, call.data.get("config_entry_id"))
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found")
    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    try:
        if slot is not None:
            note = call.data.get("note")
            await config["client"].async_slot_action(task_id, slot, "approve" if approve else "reject",
                                                     {"note": note} if note and not approve else None)
        elif approve:
            await config["client"].async_approve_task(task_id)
        else:
            await config["client"].async_reject_task(task_id, call.data.get("note"))
    except Exception as err:
        raise HomeAssistantError(str(err)) from err
    finally:
        await config["coordinator"].async_refresh()


async def async_catch_up_slot_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Tick, as a parent, a slot of today that a child did: open now, or missed."""
    entry = await _get_config_entry(hass, call.data.get("config_entry_id"))
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found")
    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    completed_by = call.data.get("completed_by")
    try:
        await config["client"].async_slot_action(call.data["task_id"], call.data["slot"], "catchup",
                                                 {"completedBy": completed_by} if completed_by else None)
    except Exception as err:
        raise HomeAssistantError(str(err)) from err
    finally:
        await config["coordinator"].async_refresh()


async def async_redeem_reward_service(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Spend a member's points on a reward.

    From a parent it is approved at once. From anyone else, such as the family
    tablet, it becomes a request that a parent approves.
    """
    config = await _get_config(hass, call)
    request = not config["parental"].is_parent(call.context.user_id)
    try:
        redemption = await config["client"].async_redeem_reward(
            call.data["reward_id"], call.data.get("user_id"), request=request)
    except Exception as err:
        raise HomeAssistantError(str(err)) from err
    finally:
        await config["coordinator"].async_refresh()
    return {"redemption_id": redemption.id, "approved": redemption.status == 1,
            "pending": redemption.status == 0, "points_cost": redemption.points_cost}


async def async_resolve_reward_service(hass: HomeAssistant, call: ServiceCall, *, approve: bool) -> None:
    """Approve or reject a reward request."""
    config = await _get_config(hass, call)
    require_parent(config, call)
    try:
        await config["client"].async_resolve_redemption(call.data["redemption_id"], approve)
    except Exception as err:
        raise HomeAssistantError(str(err)) from err
    finally:
        await config["coordinator"].async_refresh()


async def async_adjust_points_service(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Give a bonus or a penalty; a penalty never takes the balance below zero."""
    config = await _get_config(hass, call)
    require_parent(config, call)
    try:
        result = await config["client"].async_adjust_points(
            call.data["user_id"], call.data.get("points"), call.data.get("preset_id"), call.data.get("reason"))
    except Exception as err:
        raise HomeAssistantError(str(err)) from err
    finally:
        await config["coordinator"].async_refresh()
    return {key: result.get(key) for key in ("action", "points", "delta", "reason")}


async def async_unlock_parent_mode_service(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    """Open parent mode with the parent code; it closes again by itself."""
    config = await _get_config(hass, call)
    parental = config["parental"]
    try:
        until = parental.unlock(call.data["pin"])
    except ParentModeError as err:
        raise _parent_error(err) from err
    async_call_later(hass, PARENT_MODE_DURATION.total_seconds() + 1, lambda _now: parental.expire())
    return {"unlocked_until": until.isoformat()}


async def _get_config(hass: HomeAssistant, call: ServiceCall) -> dict:
    entry = await _get_config_entry(hass, call.data.get("config_entry_id"))
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found")
    return hass.data[DOMAIN][entry.entry_id]

async def async_create_task_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the create_task service call."""
    name = call.data["name"]
    description = call.data.get("description")
    due_date = call.data.get("due_date")
    created_by = call.data.get("created_by")
    config_entry_id = call.data.get("config_entry_id")
    
    # Find the config entry to use
    entry = await _get_config_entry(hass, config_entry_id)
    if not entry:
        return
    
    # Get API client and coordinator
    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    client = config["client"]
    coordinator = config["coordinator"]

    try:
        result = await client.async_create_task(name, description, due_date, created_by)
        _LOGGER.info("Task '%s' created successfully with ID %d", name, result.id)
        await coordinator.async_request_refresh()

    except Exception as e:
        _LOGGER.error("Failed to create task '%s': %s", name, e)

async def async_update_task_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the update_task service call."""
    task_id = call.data["task_id"]
    name = call.data.get("name")
    description = call.data.get("description")
    due_date = call.data.get("due_date")
    force_unarchive = call.data.get("force_unarchive", False)
    assigned_to = call.data.get("assigned_to")
    config_entry_id = call.data.get("config_entry_id")

    if not any(field in call.data for field in ("name", "description", "due_date", "assigned_to")) and not force_unarchive:
        raise HomeAssistantError("Provide at least one task field to update")
    
    # Find the config entry to use
    entry = await _get_config_entry(hass, config_entry_id)
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found for update_task")
    
    # Get API client and coordinator
    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    client = config["client"]
    coordinator = config["coordinator"]

    try:
        result = None
        if force_unarchive or any(field in call.data for field in ("name", "description", "due_date")):
            result = await client.async_update_task(task_id, name, description, due_date, force_unarchive)
        if "assigned_to" in call.data:
            await client.async_assign_task(task_id, assigned_to)
        _LOGGER.info("Task %d updated successfully", task_id)
        await coordinator.async_request_refresh()

    except Exception as e:
        _LOGGER.error("Failed to update task %d: %s", task_id, e)
        raise HomeAssistantError(f"Failed to update Hopla task {task_id}: {e}") from e

    if result is not None and not result.is_active:
        raise HomeAssistantError(
            f"Hopla task {task_id} was updated but remains archived. "
            "Set force_unarchive to true to reactivate it."
        )

async def async_delete_task_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the delete_task service call."""
    task_id = call.data["task_id"]
    config_entry_id = call.data.get("config_entry_id")
    
    # Find the config entry to use
    entry = await _get_config_entry(hass, config_entry_id)
    if not entry:
        raise HomeAssistantError("No matching Hopla integration found for delete_task")
    
    # Get API client and coordinator
    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    client = config["client"]
    coordinator = config["coordinator"]

    try:
        success = await client.async_delete_task(task_id)
        if success:
            _LOGGER.info("Task %d deleted successfully", task_id)
            await coordinator.async_request_refresh()
        else:
            raise HomeAssistantError(f"Hopla did not delete task {task_id}")

    except Exception as e:
        _LOGGER.error("Failed to delete task %d: %s", task_id, e)
        raise HomeAssistantError(f"Failed to delete Hopla task {task_id}: {e}") from e

async def async_skip_task_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the skip_task service call."""
    task_id = call.data["task_id"]
    completed_by = call.data.get("completed_by")
    config_entry_id = call.data.get("config_entry_id")

    entry = await _get_config_entry(hass, config_entry_id)
    if not entry:
        return

    config = hass.data[DOMAIN][entry.entry_id]
    require_parent(config, call)
    client = config["client"]
    coordinator = config["coordinator"]

    try:
        result = await client.async_skip_task(task_id, completed_by)
        _LOGGER.info("Task %d skipped successfully", task_id)
        await coordinator.async_request_refresh()

    except Exception as e:
        _LOGGER.error("Failed to skip task %d: %s", task_id, e)

async def _get_config_entry(hass: HomeAssistant, config_entry_id: str = None) -> ConfigEntry:
    """Get the config entry to use for the service call."""
    entry = None
    if config_entry_id:
        # Check if it's a config entry ID
        entry = hass.config_entries.async_get_entry(config_entry_id)
        
        # If not found, check if it's an entity ID and extract config entry from it
        if not entry and config_entry_id.startswith("todo."):
            entity_registry = hass.helpers.entity_registry.async_get()
            entity_entry = entity_registry.async_get(config_entry_id)
            if entity_entry:
                entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
        
        if not entry:
            _LOGGER.error("Config entry not found for: %s", config_entry_id)
            return None
    else:
        # Use the first Hopla integration if no specific entry provided
        entries = [entry for entry in hass.config_entries.async_entries(DOMAIN)]
        if not entries:
            _LOGGER.error("No Hopla integration found")
            return None
        entry = entries[0]
    
    if entry.domain != DOMAIN:
        _LOGGER.error("Config entry %s belongs to %s, expected %s", entry.entry_id, entry.domain, DOMAIN)
        return None
    if entry.entry_id not in hass.data.get(DOMAIN, {}):
        _LOGGER.error("Config entry %s is not loaded", entry.entry_id)
        return None

    return entry

async def async_task_row_action(hass: HomeAssistant, call: ServiceCall, *, complete: bool) -> None:
    """Resolve the current server assignment/date before a dashboard action."""
    entry = await _get_config_entry(hass, call.data.get("config_entry_id"))
    if entry is None:
        raise HomeAssistantError("No matching Hopla integration found")
    config = hass.data[DOMAIN][entry.entry_id]
    if not complete:
        require_parent(config, call)
    client = config["client"]
    try:
        tasks = await client.async_get_tasks()
        task = next((task for task in tasks if task.id == call.data["task_id"] and task.is_active), None)
        if task is None:
            raise HomeAssistantError("Task is no longer active or visible; refresh the list")
        if complete:
            # None leaves attribution to Hopla's authenticated API token owner.
            completed_by = task.assigned_to
            if task.together and call.data.get("completed_by") in task.members_now:
                completed_by = call.data["completed_by"]
            await client.async_complete_task(task.id, completed_by=completed_by)
        else:
            if task.frequency_type in ("once", "no_repeat", "trigger", "always"):
                raise HomeAssistantError("This task has no next scheduled occurrence")
            await client.async_reschedule_task(task.id)

    except HomeAssistantError:
        raise
    except Exception as err:
        raise HomeAssistantError(f"Hopla task action failed: {err}") from err
    finally:
        await config["coordinator"].async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove services if this is the last config entry
        if not hass.data[DOMAIN]:
            for service_name in SERVICES:
                if hass.services.has_service(DOMAIN, service_name):
                    hass.services.async_remove(DOMAIN, service_name)
            _LOGGER.debug("Removed services: %s.%s, %s.%s, %s.%s, %s.%s", 
                          DOMAIN, SERVICE_COMPLETE_TASK, DOMAIN, SERVICE_CREATE_TASK, 
                          DOMAIN, SERVICE_UPDATE_TASK, DOMAIN, SERVICE_DELETE_TASK)
    
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
