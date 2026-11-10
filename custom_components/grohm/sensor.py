"""Sensori delle wallbox Grohm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import (
    KNOWN_STATUSES,
    charging_phases,
    is_three_phase,
    nominal_kw,
    power_w,
    voltage_volts,
)
from .coordinator import GrohmConfigEntry, GrohmCoordinator
from .entity import GrohmEntity, add_entities_for_new_devices

Device = dict[str, Any]
Session = dict[str, Any]


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _status(device: Device, session: Session) -> str | None:
    status = session.get("status")
    if status is None:
        return None
    return status.lower() if status in KNOWN_STATUSES else "unknown"


def _wh_to_kwh(device: Device, session: Session) -> float | None:
    wh = _num(session.get("wattHoursCharged"))
    return None if wh is None else round(wh / 1000, 3)


def _timestamp(device: Device, session: Session) -> datetime | None:
    raw = session.get("createdAt")
    if not raw:
        return None
    parsed = dt_util.parse_datetime(str(raw))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


@dataclass(frozen=True, kw_only=True)
class GrohmSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Device, Session], Any]
    available_when_offline: bool = False
    exists_fn: Callable[[Device], bool] = lambda _: True


SENSORS: tuple[GrohmSensorDescription, ...] = (
    GrohmSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[s.lower() for s in KNOWN_STATUSES] + ["unknown"],
        value_fn=_status,
    ),
    GrohmSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=lambda d, s: power_w(s),
    ),
    GrohmSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_wh_to_kwh,
    ),
    GrohmSensorDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        available_when_offline=True,
        value_fn=lambda d, s: _num(d.get("totalKwhCharged")),
    ),
    GrohmSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda d, s: _num(s.get("maxCurrentCar")),
    ),
    GrohmSensorDescription(
        key="max_current",
        translation_key="max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d, s: _num(s.get("maxCurrent")),
    ),
    GrohmSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=0,
        value_fn=lambda d, s: voltage_volts(s),
    ),
    GrohmSensorDescription(
        key="charge_duration",
        translation_key="charge_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda d, s: _num(s.get("chargeSeconds")),
    ),
    GrohmSensorDescription(
        key="session_start",
        translation_key="session_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=_timestamp,
    ),
    GrohmSensorDescription(
        key="charging_phases",
        translation_key="charging_phases",
        value_fn=lambda d, s: charging_phases(s, d),
        exists_fn=is_three_phase,
    ),
    GrohmSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d, s: _num(s.get("wifiPower")),
    ),
    GrohmSensorDescription(
        key="nominal_power",
        translation_key="nominal_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        available_when_offline=True,
        value_fn=lambda d, s: nominal_kw(d),
    ),
    GrohmSensorDescription(
        key="energy_price",
        translation_key="energy_price",
        native_unit_of_measurement="EUR/kWh",
        entity_category=EntityCategory.DIAGNOSTIC,
        available_when_offline=True,
        suggested_display_precision=3,
        value_fn=lambda d, s: _num(d.get("hourCost")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrohmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    add_entities_for_new_devices(
        coordinator,
        entry,
        async_add_entities,
        lambda device_id, device: [
            GrohmSensor(coordinator, device_id, desc)
            for desc in SENSORS
            if desc.exists_fn(device)
        ],
    )


class GrohmSensor(GrohmEntity, SensorEntity):
    entity_description: GrohmSensorDescription

    def __init__(
        self,
        coordinator: GrohmCoordinator,
        device_id: str,
        description: GrohmSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._available_when_offline = description.available_when_offline

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device, self.session)
