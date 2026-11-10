"""Charging switch of Grohm chargers: off pauses, on resumes."""

from __future__ import annotations

from typing import Any

from grohm import ChargerStatus

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GrohmConfigEntry
from .entity import GrohmEntity, async_add_device_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrohmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the charging switches."""
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: [
            GrohmChargingSwitch(coordinator, device.id, "charging_switch")
        ],
    )


class GrohmChargingSwitch(GrohmEntity, SwitchEntity):
    """On while charging. Only available while a car is connected."""

    _attr_translation_key = "charging"

    @property
    def available(self) -> bool:
        """Available when charging can be paused or resumed."""
        session = self.session
        return (
            super().available
            and session is not None
            and (session.command_to(True) or session.command_to(False)) is not None
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the charger is charging, or about to."""
        session = self.session
        return self._with_optimistic(
            session is not None and session.status is ChargerStatus.CHARGING
        )

    async def _set_charging(self, charging: bool) -> None:
        if self.is_on == charging:
            return  # already in the requested state, or about to be
        session = self.session
        if session is None or (command := session.command_to(charging)) is None:
            # Nothing to send, for example turned on again while a pause is
            # still pending: show the real state.
            self._optimistic = None
            self.async_write_ha_state()
            return
        await self.coordinator.async_command(
            self.coordinator.client.change_status(self.device_id, command),
            self.device_id,
            lambda device: (device.status is ChargerStatus.CHARGING) is charging,
        )
        self._set_optimistic(charging)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume charging."""
        await self._set_charging(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause charging."""
        await self._set_charging(False)
