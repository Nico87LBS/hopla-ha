"""Hopla parent mode, on while a parent has unlocked the family tablet."""
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the parent mode sensor."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([HoplaParentModeSensor(config["coordinator"], config_entry, config["parental"])])


class HoplaParentModeSensor(CoordinatorEntity, BinarySensorEntity):
    """On while parent mode is open. Cards read who the parents are from it."""

    _attr_has_entity_name = True
    _attr_translation_key = "parent_mode"
    _attr_icon = "mdi:shield-account"

    def __init__(self, coordinator, config_entry: ConfigEntry, parental) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._parental = parental
        self._attr_unique_id = f"hopla_parent_mode_{config_entry.entry_id}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"family_{self._config_entry.entry_id}")},
            "name": "Hopla",
            "manufacturer": "Hopla",
            "model": "Points and rewards",
        }

    @property
    def is_on(self) -> bool:
        return self._parental.unlocked

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        until = self._parental.unlocked_until if self._parental.unlocked else None
        return {
            "hopla_parent_mode": True,
            "config_entry_id": self._config_entry.entry_id,
            "enabled": self._parental.enabled,
            "parent_users": self._parental.parent_users,
            "has_pin": self._parental.has_pin,
            "unlocked_until": until.isoformat() if until else None,
        }
