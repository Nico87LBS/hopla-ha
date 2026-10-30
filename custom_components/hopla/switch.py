"""One switch per child: on while she is home, off while she is away and her tasks wait."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .model import HoplaMember

PARENT_ROLES = ("admin", "manager")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a home switch for each child, including those who join later."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = config["coordinator"]
    members: list[HoplaMember] = config["family_members"]
    known: set[int] = set()

    @callback
    def _add_new_switches() -> None:
        new = [HoplaHomeSwitch(coordinator, config_entry, member) for member in members
               if member.is_active and member.role not in PARENT_ROLES and member.user_id not in known]
        known.update(switch.user_id for switch in new)
        if new:
            async_add_entities(new)

    _add_new_switches()
    config_entry.async_on_unload(coordinator.async_add_listener(_add_new_switches))


class HoplaHomeSwitch(CoordinatorEntity, SwitchEntity):
    """On while the child is home. Turned off, her tasks, streak and quests wait for her."""

    _attr_has_entity_name = True
    _attr_translation_key = "member_home"

    def __init__(self, coordinator, config_entry: ConfigEntry, member: HoplaMember) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self.user_id = member.user_id
        self._attr_unique_id = f"hopla_home_{config_entry.entry_id}_{member.user_id}"
        self._attr_translation_placeholders = {"name": member.display_name or member.username}

    @property
    def _member(self) -> HoplaMember | None:
        members = self.hass.data[DOMAIN][self._config_entry.entry_id]["family_members"]
        return next((m for m in members if m.user_id == self.user_id), None)

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"family_{self._config_entry.entry_id}")},
            "name": "Hopla",
            "manufacturer": "Hopla",
            "model": "Points and rewards",
        }

    @property
    def available(self) -> bool:
        return self._member is not None and super().available

    @property
    def is_on(self) -> bool | None:
        member = self._member
        return None if member is None else not member.away

    @property
    def icon(self) -> str:
        return "mdi:home-account" if self.is_on is not False else "mdi:bag-suitcase"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"hopla_member_id": self.user_id}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_away(False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_away(True)

    async def _set_away(self, away: bool) -> None:
        client = self.hass.data[DOMAIN][self._config_entry.entry_id]["client"]
        try:
            await client.async_set_member_away(self.user_id, away)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
