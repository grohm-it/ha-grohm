"""Binary sensors of Grohm chargers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from grohm import ChargerStatus, Device

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GrohmConfigEntry, GrohmCoordinator
from .entity import GrohmEntity, async_add_device_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GrohmBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Grohm binary sensor."""

    value_fn: Callable[[Device], bool | None]
    available_when_offline: bool = False
    managers_only: bool = False


BINARY_SENSORS: tuple[GrohmBinarySensorEntityDescription, ...] = (
    GrohmBinarySensorEntityDescription(
        key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        available_when_offline=True,
        value_fn=lambda device: device.is_connected,
    ),
    GrohmBinarySensorEntityDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda device: device.status is ChargerStatus.CHARGING,
    ),
    GrohmBinarySensorEntityDescription(
        key="car_connected",
        translation_key="car_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda device: (
            device.session.car_connected if device.session else None
        ),
    ),
    GrohmBinarySensorEntityDescription(
        key="force_charge",
        translation_key="force_charge",
        managers_only=True,
        value_fn=lambda device: device.force_charge,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrohmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: (
            GrohmBinarySensor(coordinator, device.id, description)
            for description in BINARY_SENSORS
            if coordinator.is_manager or not description.managers_only
        ),
    )


class GrohmBinarySensor(GrohmEntity, BinarySensorEntity):
    """A binary sensor of a charger."""

    entity_description: GrohmBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: GrohmCoordinator,
        device_id: str,
        description: GrohmBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self.available_when_offline = description.available_when_offline

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        device = self.device
        return self.entity_description.value_fn(device) if device else None
