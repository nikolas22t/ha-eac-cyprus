"""Data-stale problem sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EacConfigEntry
from .coordinator import EacCoordinator
from .sensor import device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: EacConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the binary sensor."""
    async_add_entities([EacStaleSensor(entry.runtime_data)])


class EacStaleSensor(CoordinatorEntity[EacCoordinator], BinarySensorEntity):
    """On when the newest EAC reading is older than the configured threshold."""

    _attr_has_entity_name = True
    _attr_translation_key = "data_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EacCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.sp_id}_data_stale"
        self._attr_device_info = device_info(coordinator)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.stale
