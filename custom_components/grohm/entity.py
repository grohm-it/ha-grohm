"""Base entity of the Grohm integration: one charger is one device."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from grohm import ChargingSession, Device

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COMMAND_TIMEOUT, DOMAIN
from .coordinator import GrohmConfigEntry, GrohmCoordinator


def _model(device: Device) -> str:
    # Single phase chargers are always 7.4 kW. Three phase chargers are 11 or
    # 22 kW, and the API cannot tell which.
    return (
        "Three phase charger" if device.three_phase else "Single phase charger, 7.4 kW"
    )


class GrohmEntity(CoordinatorEntity[GrohmCoordinator]):
    """An entity of one charger."""

    _attr_has_entity_name = True
    # Entities that stay available while the charger is offline, like the
    # connectivity sensor or the total energy.
    available_when_offline = False

    def __init__(self, coordinator: GrohmCoordinator, device_id: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.data[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections=(
                {(CONNECTION_NETWORK_MAC, device.serial_number.lower())}
                if device.serial_number
                else set()
            ),
            manufacturer="Grohm",
            model=_model(device),
            name=device.name or device.serial_number,
            serial_number=device.serial_number or None,
        )

    _optimistic: Any = None
    _optimistic_until = 0.0

    def _set_optimistic(self, value: Any) -> None:
        """Show `value` until the charger reports it, or the command times out."""
        self._optimistic = value
        self._optimistic_until = self.hass.loop.time() + COMMAND_TIMEOUT
        self.async_write_ha_state()

    def _with_optimistic(self, actual: Any) -> Any:
        """Return the requested state while a command is pending, else `actual`."""
        if self._optimistic is None:
            return actual
        if (
            actual == self._optimistic
            or self.hass.loop.time() >= self._optimistic_until
        ):
            self._optimistic = None
            return actual
        return self._optimistic

    @property
    def device(self) -> Device | None:
        """The charger, or None when it is gone."""
        return self.coordinator.data.get(self.device_id)

    @property
    def session(self) -> ChargingSession | None:
        """The current session of the charger."""
        return self.device.session if self.device else None

    @property
    def available(self) -> bool:
        """Whether the entity is available."""
        device = self.device
        if not super().available or device is None:
            return False
        return self.available_when_offline or device.is_connected


def async_add_device_entities(
    entry: GrohmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[GrohmCoordinator, Device], Iterable[Entity]],
) -> None:
    """Add entities for every charger, also for chargers added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new = [device_id for device_id in coordinator.data if device_id not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            entity
            for device_id in new
            for entity in factory(coordinator, coordinator.data[device_id])
        )

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))
