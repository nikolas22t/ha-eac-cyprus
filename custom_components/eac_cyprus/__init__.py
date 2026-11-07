"""EAC Cyprus: smart-meter readings and bill estimate from the EAC DSO portal."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EacCoordinator

PLATFORMS = [Platform.SENSOR]

type EacConfigEntry = ConfigEntry[EacCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EacConfigEntry) -> bool:
    """Set up EAC Cyprus from a config entry."""
    coordinator = EacCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: EacConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EacConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
