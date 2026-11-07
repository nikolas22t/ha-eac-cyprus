"""Sensors: bill estimate for the current billing period and related figures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EacConfigEntry
from .const import DOMAIN
from .coordinator import EacCoordinator, EacData


@dataclass(frozen=True, kw_only=True)
class EacSensorDescription(SensorEntityDescription):
    """Describes an EAC sensor."""

    value: Callable[[EacData], Any]
    attrs: Callable[[EacData], dict[str, Any]] | None = None


def _bill_attrs(d: EacData) -> dict[str, Any]:
    b = asdict(d.bill)
    return {
        **{k: round(v, 2) for k, v in b.items()},
        "period_start": d.period_start.date().isoformat(),
        "period_end": d.period_end.date().isoformat(),
        "data_until": d.data_until.isoformat() if d.data_until else None,
        "rates_live": d.rates_live,
    }


EUR = "EUR"
KWH = UnitOfEnergy.KILO_WATT_HOUR

SENSORS: tuple[EacSensorDescription, ...] = (
    EacSensorDescription(
        key="bill_so_far", translation_key="bill_so_far", native_unit_of_measurement=EUR,
        device_class=SensorDeviceClass.MONETARY, suggested_display_precision=2,
        value=lambda d: round(d.bill.total, 2), attrs=_bill_attrs,
    ),
    EacSensorDescription(
        key="bill_projected", translation_key="bill_projected", native_unit_of_measurement=EUR,
        device_class=SensorDeviceClass.MONETARY, suggested_display_precision=2,
        value=lambda d: round(d.projected_total, 2),
    ),
    EacSensorDescription(
        key="period_import", translation_key="period_import", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=1,
        value=lambda d: round(d.bill.imported, 2),
    ),
    EacSensorDescription(
        key="period_export", translation_key="period_export", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=1,
        value=lambda d: round(d.bill.exported, 2),
    ),
    EacSensorDescription(
        key="period_billable", translation_key="period_billable", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=1,
        value=lambda d: round(d.bill.net, 2),
    ),
    EacSensorDescription(
        key="credit_in", translation_key="credit_in", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=1,
        value=lambda d: round(d.bill.credit_in, 1),
        attrs=lambda d: {"credit_carried_forward_so_far": round(d.bill.credit_out, 1)},
    ),
    EacSensorDescription(
        key="last_day_import", translation_key="last_day_import", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=2,
        value=lambda d: d.last_day_import, attrs=lambda d: {"date": d.last_day},
    ),
    EacSensorDescription(
        key="last_day_export", translation_key="last_day_export", native_unit_of_measurement=KWH,
        device_class=SensorDeviceClass.ENERGY, suggested_display_precision=2,
        value=lambda d: d.last_day_export, attrs=lambda d: {"date": d.last_day},
    ),
    EacSensorDescription(
        key="import_price", translation_key="import_price", native_unit_of_measurement=f"{EUR}/{KWH}",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=4,
        value=lambda d: round(d.import_price, 6), attrs=lambda d: dict(d.rates),
    ),
    EacSensorDescription(
        key="export_credit", translation_key="export_credit", native_unit_of_measurement=f"{EUR}/{KWH}",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=4,
        value=lambda d: round(d.export_credit, 6),
    ),
    EacSensorDescription(
        key="data_until", translation_key="data_until", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: d.data_until,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EacConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(EacSensor(coordinator, desc) for desc in SENSORS)


class EacSensor(CoordinatorEntity[EacCoordinator], SensorEntity):
    """One EAC figure."""

    _attr_has_entity_name = True
    entity_description: EacSensorDescription

    def __init__(self, coordinator: EacCoordinator, desc: EacSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        sp = coordinator.sp_id
        self._attr_unique_id = f"{sp}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, sp)},
            name=f"EAC {sp}",
            manufacturer="Electricity Authority of Cyprus",
            model=coordinator.config_entry.data.get("address") or "Smart meter",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs
        return fn(self.coordinator.data) if fn else None
