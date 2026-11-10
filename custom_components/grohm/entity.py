"""Base entity of the Grohm integration: one charger is one device."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from grohm import ChargingSession, Device

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GrohmConfigEntry, GrohmCoordinator


def _model(device: Device) -> str:
    phases = "three phase" if device.three_phase else "single phase"
    if (kw := device.nominal_power_kw) is None:
        return f"Charger, {phases}"
    return f"{kw:g} kW charger, {phases}"


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
