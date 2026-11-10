"""Sensori binari delle wallbox Grohm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import STATUS_CHARGING
from .coordinator import GrohmConfigEntry, GrohmCoordinator
from .entity import GrohmEntity, add_entities_for_new_devices


@dataclass(frozen=True, kw_only=True)
class GrohmBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any], dict[str, Any]], bool | None]
    available_when_offline: bool = False


BINARY_SENSORS: tuple[GrohmBinaryDescription, ...] = (
    GrohmBinaryDescription(
        key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        available_when_offline=True,
        value_fn=lambda d, s: d.get("isConnected") is True,
    ),
    GrohmBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d, s: s.get("status") == STATUS_CHARGING,
    ),
    GrohmBinaryDescription(
        key="force_charge",
        translation_key="force_charge",
        value_fn=lambda d, s: d.get("forceCharge") is True,
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
        lambda device_id, _: [
            GrohmBinarySensor(coordinator, device_id, desc)
            for desc in BINARY_SENSORS
            # la ricarica forzata è una funzione del solo gestore
            if desc.key != "force_charge" or coordinator.is_gestore
        ],
    )


class GrohmBinarySensor(GrohmEntity, BinarySensorEntity):
    entity_description: GrohmBinaryDescription

    def __init__(
        self,
        coordinator: GrohmCoordinator,
        device_id: str,
        description: GrohmBinaryDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._available_when_offline = description.available_when_offline

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.device, self.session)
