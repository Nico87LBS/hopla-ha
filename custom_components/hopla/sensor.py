"""Hopla sensor platform."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .chore_sensor import async_setup_chore_sensors
from .family_sensor import async_setup_family_sensors

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hopla sensor entities."""
    await async_setup_chore_sensors(hass, config_entry, async_add_entities)
    await async_setup_family_sensors(hass, config_entry, async_add_entities)
