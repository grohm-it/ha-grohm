"""Pausa/ripresa della ricarica (changeDeviceStatus)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    STATUS_CHARGING,
    STATUS_PAUSED,
    STATUS_WAITING,
    pause_resume_target,
)
from .coordinator import GrohmConfigEntry
from .entity import GrohmEntity, add_entities_for_new_devices

_CONTROLLABLE = (STATUS_CHARGING, STATUS_PAUSED, STATUS_WAITING)


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
            GrohmChargingSwitch(coordinator, device_id, "charging_switch")
        ],
    )


class GrohmChargingSwitch(GrohmEntity, SwitchEntity):
    """Acceso = in carica. Spegnere mette in pausa, accendere riprende.

    Utilizzabile solo con un'auto collegata (stato In carica / In pausa /
    In attesa), come il pulsante pausa/riprendi dell'app.
    """

    _attr_translation_key = "charging"

    @property
    def available(self) -> bool:
        return super().available and self.session.get("status") in _CONTROLLABLE

    @property
    def is_on(self) -> bool:
        return self.session.get("status") == STATUS_CHARGING

    async def _send(self, wanted_on: bool) -> None:
        status = self.session.get("status")
        if (status == STATUS_CHARGING) == wanted_on:
            return  # già nello stato richiesto
        target = pause_resume_target(status)
        if target is None:
            return
        await self.coordinator.async_command(
            self.coordinator.api.change_status(self.device_id, target)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(False)
