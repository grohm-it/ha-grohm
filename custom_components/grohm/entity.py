"""Entità base: una wallbox fisica = un dispositivo in Home Assistant."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import nominal_kw
from .const import DOMAIN, MANUFACTURER
from .coordinator import GrohmConfigEntry, GrohmCoordinator


def _model(device: dict[str, Any]) -> str:
    kw = nominal_kw(device)
    phase = "trifase" if device.get("fase") == "tri" else "monofase"
    if kw is None:
        return f"Wallbox {phase}"
    label = f"{kw:.0f}" if abs(kw - round(kw)) < 0.05 else f"{kw:.1f}"
    return f"Wallbox {label} kW {phase}"


class GrohmEntity(CoordinatorEntity[GrohmCoordinator]):
    """Entità legata a una singola wallbox."""

    _attr_has_entity_name = True
    # Se True l'entità resta disponibile anche con la wallbox offline
    # (es. connettività, energia totale).
    _available_when_offline = False

    def __init__(self, coordinator: GrohmCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = self.device
        serial = device.get("serialNumber")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, serial.lower())} if serial else set(),
            manufacturer=MANUFACTURER,
            model=_model(device),
            name=device.get("name") or serial or f"Wallbox {device_id}",
            serial_number=serial,
        )

    @property
    def device(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self.device_id) or {}

    @property
    def session(self) -> dict[str, Any]:
        return self.device.get("currentSession") or {}

    @property
    def online(self) -> bool:
        return self.device.get("isConnected") is not False

    @property
    def available(self) -> bool:
        if not super().available or not self.device:
            return False
        return self._available_when_offline or self.online


def add_entities_for_new_devices(
    coordinator: GrohmCoordinator,
    entry: GrohmConfigEntry,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[str, dict[str, Any]], Iterable[Entity]],
) -> None:
    """Crea le entità per le wallbox presenti e per quelle che compaiono dopo."""
    known: set[str] = set()

    @callback
    def _check() -> None:
        new = [i for i in (coordinator.data or {}) if i not in known]
        if not new:
            return
        entities: list[Entity] = []
        for device_id in new:
            known.add(device_id)
            entities.extend(factory(device_id, coordinator.data[device_id]))
        async_add_entities(entities)

    _check()
    entry.async_on_unload(coordinator.async_add_listener(_check))
