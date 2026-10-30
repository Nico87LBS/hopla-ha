"""API client for Hopla."""
import logging
import asyncio
from datetime import datetime, timezone
import json
from typing import List, Optional
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_TIMEOUT
from .model import HoplaTask, HoplaMember, HoplaChoreHistory, HoplaReward, HoplaRedemption
_LOGGER = logging.getLogger(__name__)

# Before Hopla 1.29.0 the family was called a circle; these keep an older
# server working until it is updated.
LEGACY_FAMILY_PATH = "/eapi/v1/circle"

class HoplaApiClient:
    """API client for Hopla."""

    def __init__(self, base_url: str, token: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._session = session
        # Where the family's routes live; a server older than 1.29.0 has
        # them under their old name, found on the first members call.
        self._family_path = "/eapi/v1/family"

    @property
    def base_url(self) -> str:
        """Hopla's address, as the integration reaches it."""
        return self._base_url

    def _headers(self) -> dict:
        """Return headers for Hopla API requests."""
        return {
            "secretkey": f"{self._token}",
            "Content-Type": "application/json",
        }

    async def async_get_tasks(self) -> List[HoplaTask]:
        """Get tasks from Hopla."""
        headers = self._headers()
        
        try:
            async with self._session.get(
                f"{self._base_url}/eapi/v1/chore",
                headers=headers,
                timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                if not isinstance(data, list) :
                    _LOGGER.error("Unexpected response format from Hopla API")
                    return []
                
                return [HoplaTask.from_json(task) for task in data]
                
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching tasks from Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla response: %s", err)
            return []

    async def async_get_family_members(self) -> List[HoplaMember]:
        """Get the family's members from Hopla."""
        try:
            data = await self._get_members(self._family_path)
            if data is None and self._family_path == "/eapi/v1/family":
                data = await self._get_members(LEGACY_FAMILY_PATH)
                if data is not None:
                    _LOGGER.info("Hopla server older than 1.29.0: using its old family routes")
                    self._family_path = LEGACY_FAMILY_PATH
            if not isinstance(data, list):
                _LOGGER.error("Unexpected response format from Hopla family members API")
                return []
            return [HoplaMember.from_json(member) for member in data]
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching family members from Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla family members response: %s", err)
            return []

    async def _get_members(self, path: str):
        """The members at `path`, or None when the server has no such route
        (a 404, or its web page in place of JSON)."""
        async with self._session.get(
            f"{self._base_url}{path}/members",
            headers=self._headers(),
            timeout=API_TIMEOUT
        ) as response:
            if response.status == 404 or "json" not in response.content_type:
                return None
            response.raise_for_status()
            return await response.json()

    async def async_complete_task(self, choreId: int, completed_by: int = None) -> HoplaTask:
        """Complete a task"""
        headers = self._headers()

        # Add completed_by parameter if provided
        params = {}
        if completed_by:
            params["completedBy"] = completed_by
            _LOGGER.debug("Adding completedBy parameter: %d", completed_by)
        else:
            _LOGGER.debug("No completedBy parameter - using default")

        try:
            async with self._session.post(
                f"{self._base_url}/eapi/v1/chore/{choreId}/complete",
                headers=headers,
                params=params,
                timeout=API_TIMEOUT
            ) as response:
                if response.status == 400:
                    try:
                        reason = (await response.json()).get("error")
                    except (aiohttp.ClientError, ValueError, AttributeError):
                        reason = None
                    if reason:
                        raise ValueError(f"Hopla refused to complete the task: {reason}")
                response.raise_for_status()
                data = await response.json()
                return HoplaTask.from_json(data)

        except aiohttp.ClientError as err:
            _LOGGER.error("Error completing task in Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla complete task response: %s", err)
            raise

    async def _post_action(self, path: str, operation: str, payload: dict | None = None, method: str = "POST") -> dict:
        """POST to an action route, raising Hopla's own error message on 4xx."""
        async with self._session.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers(),
            json=payload or {},
            timeout=API_TIMEOUT,
        ) as response:
            if 400 <= response.status < 500:
                try:
                    reason = (await response.json()).get("error")
                except (aiohttp.ClientError, ValueError, AttributeError):
                    reason = None
                if response.status == 404 and not reason:
                    reason = "this Hopla server does not support it yet"
                raise ValueError(f"Hopla refused to {operation}: {reason or response.status}")
            response.raise_for_status()
            return await response.json()

    async def async_set_member_away(self, user_id: int, away: bool) -> None:
        """Mark a child away (her tasks wait) or back home."""
        await self._post_action(f"{self._family_path}/members/{user_id}/away", "change who is home",
                                {"away": away}, method="PUT")

    async def async_approve_task(self, task_id: int) -> HoplaTask:
        """Approve a completion waiting for approval; its points go to the completer."""
        data = await self._post_action(f"/eapi/v1/chore/{task_id}/approve", "approve the task")
        return HoplaTask.from_json(data["res"])

    async def async_reject_task(self, task_id: int, note: str | None = None) -> None:
        """Reject a completion waiting for approval; the task is due again."""
        await self._post_action(f"/eapi/v1/chore/{task_id}/reject", "reject the task",
                                {"note": note} if note else None)

    async def async_slot_action(self, task_id: int, slot: int, action: str, payload: dict | None = None) -> HoplaTask:
        """Approve, reject or catch up one slot of today of a task done several times a day."""
        operations = {"approve": "approve the slot", "reject": "reject the slot", "catchup": "catch up the slot"}
        data = await self._post_action(f"/eapi/v1/chore/{task_id}/slots/{slot}/{action}", operations[action], payload)
        return HoplaTask.from_json(data["res"])

    async def async_get_rewards(self) -> Optional[List[HoplaReward]]:
        """Get the reward catalog, or None when the server has no rewards API."""
        async with self._session.get(
            f"{self._base_url}/eapi/v1/rewards",
            headers=self._headers(),
            timeout=API_TIMEOUT,
        ) as response:
            if response.status in (403, 404):
                _LOGGER.debug("Hopla rewards API unavailable: HTTP %s", response.status)
                return None
            response.raise_for_status()
            data = await response.json()
            return [HoplaReward.from_json(item) for item in data or []]

    async def async_get_redemptions(self, status: str | None = None) -> List[HoplaRedemption]:
        """Get reward redemptions, optionally only pending, approved or rejected."""
        async with self._session.get(
            f"{self._base_url}/eapi/v1/rewards/redemptions",
            headers=self._headers(),
            params={"status": status} if status else None,
            timeout=API_TIMEOUT,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return [HoplaRedemption.from_json(item) for item in data or []]

    async def async_redeem_reward(self, reward_id: int, user_id: int | None = None,
                                  request: bool = False) -> HoplaRedemption:
        """Spend points on a reward.

        For another member it is approved at once, unless request is set: then
        it waits for a parent like a member's own request.
        """
        payload = {"userId": user_id, "request": request} if user_id else None
        data = await self._post_action(f"/eapi/v1/rewards/{reward_id}/redeem", "redeem the reward", payload)
        return HoplaRedemption.from_json(data["res"])

    async def async_resolve_redemption(self, redemption_id: int, approve: bool) -> None:
        """Approve or reject a pending redemption."""
        action = "approve" if approve else "reject"
        await self._post_action(f"/eapi/v1/rewards/redemptions/{redemption_id}/{action}",
                                f"{action} the redemption")

    async def async_get_points_presets(self) -> Optional[list]:
        """Get the bonus and penalty presets, or None when the server has no points API."""
        async with self._session.get(
            f"{self._base_url}/eapi/v1/points/presets",
            headers=self._headers(),
            timeout=API_TIMEOUT,
        ) as response:
            if response.status in (403, 404):
                _LOGGER.debug("Hopla points API unavailable: HTTP %s", response.status)
                return None
            response.raise_for_status()
            return (await response.json()).get("res") or []

    async def async_get_points_history(self, limit: int = 20, user_id: int | None = None,
                                       before: int | None = None) -> list:
        """Get the newest points ledger rows of the family, or of one member,
        older than the row `before` when paging back."""
        params = {"limit": limit}
        if user_id:
            params["userId"] = user_id
        if before:
            params["before"] = before
        async with self._session.get(
            f"{self._base_url}/eapi/v1/points/history",
            headers=self._headers(),
            params=params,
            timeout=API_TIMEOUT,
        ) as response:
            response.raise_for_status()
            return (await response.json()).get("res") or []

    async def async_get_family_timezone(self) -> Optional[dict]:
        """Get the family's time zone and the server's (home), or None when the
        server does not know it yet."""
        async with self._session.get(
            f"{self._base_url}{self._family_path}/timezone",
            headers=self._headers(),
            timeout=API_TIMEOUT,
        ) as response:
            if response.status in (403, 404):
                _LOGGER.debug("Hopla family time zone unavailable: HTTP %s", response.status)
                return None
            response.raise_for_status()
            return (await response.json()).get("res")

    async def async_set_family_timezone(self, timezone: str) -> Optional[dict]:
        """Move the family to another time zone; its tasks keep their time of day."""
        data = await self._post_action(f"{self._family_path}/timezone", "change the family's time zone",
                                       {"timezone": timezone}, method="PUT")
        return data.get("res")

    async def async_get_games_today(self) -> Optional[dict]:
        """Get today's games: streaks, the surprise task and the bonus period.

        None when the server has no games API.
        """
        async with self._session.get(
            f"{self._base_url}/eapi/v1/games/today",
            headers=self._headers(),
            timeout=API_TIMEOUT,
        ) as response:
            if response.status in (403, 404):
                _LOGGER.debug("Hopla games API unavailable: HTTP %s", response.status)
                return None
            response.raise_for_status()
            return (await response.json()).get("res")

    async def async_adjust_points(self, user_id: int, points: int | None = None, preset_id: int | None = None,
                                  reason: str | None = None) -> dict:
        """Give a bonus (points > 0) or a penalty (points < 0), or apply a preset."""
        payload = {"userId": user_id, "points": points or 0, "reason": reason, "presetId": preset_id}
        data = await self._post_action("/eapi/v1/points/adjust", "change the points", payload)
        return data["res"]

    async def async_new_play_link(self, user_id: int) -> dict:
        """A link good once, for a minute, that opens a member's learning games without signing in."""
        data = await self._post_action("/eapi/v1/learn/play-links", "open the games", {"userId": user_id})
        return data.get("res") or {}

    async def async_start_chrono(self, task_id: int, points: int, minutes: int) -> dict:
        """Start a speed bonus on a task: extra points for doing it in the next minutes."""
        payload = {"choreId": task_id, "points": points, "minutes": minutes}
        data = await self._post_action("/eapi/v1/games/flashes", "start the speed bonus", payload)
        return data["res"]

    async def async_stop_chrono(self, flash_id: int) -> None:
        """End a speed bonus a parent started, before its time."""
        await self._post_action(f"/eapi/v1/games/flashes/{flash_id}", "stop the speed bonus", method="DELETE")

    async def async_create_task(self, name: str, description: str = None, due_date: str = None, created_by: int = None) -> HoplaTask:
        """Create a new task"""
        headers = self._headers()

        payload = {"name": name, "frequencyType": "once", "assignStrategy": "no_assignee"}
        if description:
            payload["description"] = description
        if due_date:
            payload["dueDate"] = due_date
        if created_by:
            payload["createdBy"] = created_by
        _LOGGER.debug("Creating task with payload: %s", json.dumps(payload))
        try:
            async with self._session.post(
                f"{self._base_url}/api/v1/chores/",
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("New task: %s", data)
                return await self.async_get_task_detail(data["res"])  # Fetch full task details after creation

        except aiohttp.ClientError as err:
            _LOGGER.error("Error creating task in Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla create task response: %s", err)
            raise

    async def _raise_for_status(self, response, operation: str) -> None:
        """Expose known server permission errors without echoing proxy responses."""
        if response.status == 403:
            try:
                error_data = await response.json()
            except (aiohttp.ClientError, ValueError):
                error_data = None
            if isinstance(error_data, dict):
                reason = error_data.get("error")
                if reason in (
                    "You can only update your own chores",
                    "You can only delete your own chores",
                    "user does not have permission to edit this chore",
                    "chore has been modified by another user, please refresh and try again",
                    "updatedAt is in the future and cannot be used to edit the chore",
                    "Only the chore creator or a family admin/manager can update this chore",
                    "Only the chore creator or a circle admin/manager can update this chore",
                    "Only the chore creator or a family admin/manager can delete this chore",
                    "Only the chore creator or a circle admin/manager can delete this chore",
                ):
                    raise ValueError(f"Hopla denied the {operation} (403): {reason}")
        response.raise_for_status()

    async def async_update_task(self, task_id: int, name: str = None, description: str = None, due_date: str = None, force_unarchive: bool = False) -> HoplaTask:
        """Update an existing task"""
        headers = self._headers()

        payload = {}
        if name:
            payload["name"] = name
        if description is not None:  # Allow empty string to clear description
            payload["description"] = description
        if due_date:
            payload["dueDate"] = due_date
        if force_unarchive:
            payload["forceUnarchive"] = True

        if not payload:
            raise ValueError("At least one field must be provided for update")

        try:
            async with self._session.put(
                f"{self._base_url}/eapi/v1/chore/{task_id}",
                headers=headers,
                json=payload,
                timeout=API_TIMEOUT
            ) as response:
                await self._raise_for_status(response, "update")
                data = await response.json()
                task = HoplaTask.from_json(data)
                if due_date:
                    requested_date = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    if task.next_due_date is None or (
                        task.next_due_date.date() != requested_date.date()
                        if len(due_date) == 10
                        else task.next_due_date != requested_date
                    ):
                        raise ValueError("Hopla did not apply the requested due date")
                if force_unarchive and not task.is_active:
                    raise ValueError("Hopla did not reactivate the task; update the Hopla server")
                return task

        except aiohttp.ClientError as err:
            _LOGGER.error("Error updating task in Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla update task response: %s", err)
            raise

    async def async_assign_task(self, task_id: int, assigned_to: int | None) -> None:
        """Assign a task to a user, or to Anyone when assigned_to is None."""
        # The assignee endpoint cannot clear assignments. Fetch the full task for
        # the editor API so recurrence, labels, subtasks and triggers are retained.
        async with self._session.get(
            f"{self._base_url}/api/v1/chores/{task_id}",
            headers=self._headers(), timeout=API_TIMEOUT,
        ) as response:
            response.raise_for_status()
            data = await response.json()
        task = data.get("res", data)
        if not isinstance(task, dict) or task.get("id") != task_id:
            raise ValueError("Unable to fetch the current task for reassignment")

        if assigned_to is None or task.get("assignStrategy") == "no_assignee" or not task.get("assignees"):
            payload = dict(task)
            payload["assignedTo"] = assigned_to
            payload["assignStrategy"] = "no_assignee" if assigned_to is None else "keep_last_assigned"
            payload["assignees"] = [] if assigned_to is None else [{"userId": assigned_to}]
            payload["labelsV2"] = [{"id": label["id"]} for label in task.get("labelsV2") or []]
            # Use the fetched updatedAt to retain Hopla's concurrent-edit check.
            if not payload.get("updatedAt"):
                raise ValueError("Task has no update timestamp; refresh before reassigning")
            async with self._session.put(
                f"{self._base_url}/api/v1/chores/",
                headers=self._headers(), json=payload, timeout=API_TIMEOUT,
            ) as response:
                await self._raise_for_status(response, "reassignment")
            return

        payload = {
            "assignee": assigned_to,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with self._session.put(
                f"{self._base_url}/api/v1/chores/{task_id}/assignee",
                headers=self._headers(),
                json=payload,
                timeout=API_TIMEOUT,
            ) as response:
                response.raise_for_status()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error assigning Hopla task %d: %s", task_id, err)
            raise

    async def async_reschedule_task(self, task_id: int) -> HoplaTask:
        """Use Hopla's scheduler to skip to the next occurrence."""
        async with self._session.post(
            f"{self._base_url}/api/v1/chores/{task_id}/skip",
            headers=self._headers(), timeout=API_TIMEOUT,
        ) as response:
            await self._raise_for_status(response, "reschedule")
            data = await response.json()
            return HoplaTask.from_json(data["res"])

    async def async_skip_task(self, choreId: int, completed_by: int = None) -> HoplaTask:
        """Skip a task, advancing to the next scheduled occurrence without recording a completion."""
        headers = self._headers()

        params = {}
        if completed_by:
            params["completedBy"] = completed_by

        try:
            async with self._session.post(
                f"{self._base_url}/eapi/v1/chore/{choreId}/skip",
                headers=headers,
                params=params,
                timeout=API_TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return HoplaTask.from_json(data)

        except aiohttp.ClientError as err:
            _LOGGER.error("Error skipping task in Hopla: %s", err)
            raise
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Hopla skip task response: %s", err)
            raise

    async def async_delete_task(self, task_id: int) -> bool:
        """Delete a task"""
        headers = self._headers()

        try:
            async with self._session.delete(
                f"{self._base_url}/eapi/v1/chore/{task_id}",
                headers=headers,
                timeout=API_TIMEOUT
            ) as response:
                await self._raise_for_status(response, "delete")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error("Error deleting task in Hopla: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Error deleting task: %s", err)
            raise

    async def async_get_task_detail(self, task_id: int) -> Optional[HoplaTask]:
        """Get detailed task timing data when the full API endpoint is available."""
        try:
            async with self._session.get(
                f"{self._base_url}/api/v1/chores/{task_id}/details",
                headers=self._headers(),
                timeout=API_TIMEOUT
            ) as response:
                if response.status in (401, 403, 404):
                    _LOGGER.debug("Hopla task detail endpoint unavailable: HTTP %s", response.status)
                    return None

                response.raise_for_status()
                data = await response.json()
                detail = data.get("res", data) if isinstance(data, dict) else data

                if not isinstance(detail, dict):
                    _LOGGER.debug("Unexpected Hopla task detail response format")
                    return None

                return HoplaTask.from_json(detail)

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Unable to fetch Hopla task detail %d: %s", task_id, err)
            return None
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.debug("Unable to parse Hopla task detail %d: %s", task_id, err)
            return None

    async def async_get_task_history(self, days: int = 30, include_members: bool = True) -> List[HoplaChoreHistory]:
        """Get recent chore history when the full API endpoint is available."""
        params = {
            "limit": max(days, 1),
            "members": "true" if include_members else "false",
        }

        try:
            async with self._session.get(
                f"{self._base_url}/api/v1/chores/history",
                headers=self._headers(),
                params=params,
                timeout=API_TIMEOUT
            ) as response:
                if response.status in (401, 403, 404):
                    _LOGGER.debug("Hopla task history endpoint unavailable: HTTP %s", response.status)
                    return []

                response.raise_for_status()
                data = await response.json()
                history = data.get("res", data) if isinstance(data, dict) else data

                if not isinstance(history, list):
                    _LOGGER.debug("Unexpected Hopla task history response format")
                    return []

                return HoplaChoreHistory.from_json_list(history)

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Unable to fetch Hopla task history: %s", err)
            return []
        except (KeyError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.debug("Unable to parse Hopla task history: %s", err)
            return []
