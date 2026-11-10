"""Sensors of Grohm chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from grohm import ChargerStatus, ChargingSession, Device

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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GrohmConfigEntry, GrohmCoordinator
from .entity import GrohmEntity, async_add_device_entities

PARALLEL_UPDATES = 0

type StateType = str | int | float | datetime | None


def _from_session(
    getter: Callable[[ChargingSession], StateType],
) -> Callable[[Device], StateType]:
    """Read a value from the current session, None without a session."""
    return lambda device: getter(device.session) if device.session else None


@dataclass(frozen=True, kw_only=True)
class GrohmSensorEntityDescription(SensorEntityDescription):
    """Describes a Grohm sensor."""

    value_fn: Callable[[Device], StateType]
    exists_fn: Callable[[Device], bool] = lambda _: True
    available_when_offline: bool = False


SENSORS: tuple[GrohmSensorEntityDescription, ...] = (
    GrohmSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.lower() for status in ChargerStatus],
        value_fn=lambda device: device.status.lower() if device.status else None,
    ),
    GrohmSensorEntityDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=_from_session(lambda session: session.power),
    ),
    GrohmSensorEntityDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_from_session(lambda session: session.energy_wh),
    ),
    GrohmSensorEntityDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        available_when_offline=True,
        value_fn=lambda device: device.total_energy_kwh,
    ),
    GrohmSensorEntityDescription(
        key="car_current",
        translation_key="car_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_from_session(lambda session: session.car_current),
    ),
    GrohmSensorEntityDescription(
        key="max_current",
        translation_key="max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_from_session(lambda session: session.max_current),
    ),
    GrohmSensorEntityDescription(
        key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=0,
        value_fn=_from_session(lambda session: session.voltage),
    ),
    GrohmSensorEntityDescription(
        key="charge_duration",
        translation_key="charge_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=_from_session(lambda session: session.charge_seconds),
    ),
    GrohmSensorEntityDescription(
        key="session_start",
        translation_key="session_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=_from_session(lambda session: session.created_at),
    ),
    GrohmSensorEntityDescription(
        key="charging_phases",
        translation_key="charging_phases",
        value_fn=lambda device: device.charging_phases,
        exists_fn=lambda device: device.three_phase,
    ),
    GrohmSensorEntityDescription(
        key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_from_session(lambda session: session.wifi_dbm),
    ),
    GrohmSensorEntityDescription(
        key="nominal_power",
        translation_key="nominal_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        available_when_offline=True,
        value_fn=lambda device: device.nominal_power_kw,
    ),
    GrohmSensorEntityDescription(
        key="energy_price",
        translation_key="energy_price",
        native_unit_of_measurement="EUR/kWh",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        available_when_offline=True,
        value_fn=lambda device: device.energy_price,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrohmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: (
            GrohmSensor(coordinator, device.id, description)
            for description in SENSORS
            if description.exists_fn(device)
        ),
    )


class GrohmSensor(GrohmEntity, SensorEntity):
    """A sensor of a charger."""

    entity_description: GrohmSensorEntityDescription

    def __init__(
        self,
        coordinator: GrohmCoordinator,
        device_id: str,
        description: GrohmSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self.available_when_offline = description.available_when_offline

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        device = self.device
        return self.entity_description.value_fn(device) if device else None
