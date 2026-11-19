"""EAC Cyprus: smart-meter readings, bill estimate and dashboard cards from the EAC DSO portal."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, DOMAIN
from .coordinator import EacCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type EacConfigEntry = ConfigEntry[EacCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the Lovelace card and register the actions."""
    card = Path(__file__).parent / "frontend" / "eac-cyprus-card.js"
    version = (Path(__file__).parent / "manifest.json").stat().st_mtime_ns
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), True)])
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={version}")

    def _entries() -> list[EacConfigEntry]:
        return [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]

    async def import_full_history(call: ServiceCall) -> ServiceResponse:
        result = {}
        for entry in _entries():
            result[entry.runtime_data.sp_id] = await entry.runtime_data.async_import_full_history()
        msg = "\n".join(f"- **{sp}**: {r.get('hours', 0)} hours from {r.get('from', '–')}" for sp, r in result.items())
        await hass.services.async_call(
            "persistent_notification", "create",
            {"title": "EAC Cyprus", "message": f"Full history imported:\n{msg}", "notification_id": "eac_cyprus_history"},
        )
        return result

    async def refresh(call: ServiceCall) -> None:
        for entry in _entries():
            await entry.runtime_data.async_request_refresh()

    hass.services.async_register(DOMAIN, "import_full_history", import_full_history,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "refresh", refresh)
    return True


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
