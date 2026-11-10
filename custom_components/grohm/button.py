"""Ricarica forzata (solo account gestore, come nell'app)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import STATUS_READY
from .coordinator import GrohmConfigEntry
from .entity import GrohmEntity, add_entities_for_new_devices


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GrohmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if not coordinator.is_gestore:
        return
    add_entities_for_new_devices(
        coordinator,
        entry,
        async_add_entities,
        lambda device_id, _: [
            GrohmForceChargeButton(coordinator, device_id, "force_charge_button")
        ],
    )


class GrohmForceChargeButton(GrohmEntity, ButtonEntity):
    """Avvia una ricarica senza tessera. La wallbox la tiene attiva per 300 s."""

    _attr_translation_key = "force_charge"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.session.get("status") == STATUS_READY
            and self.device.get("forceCharge") is not True
        )

    async def async_press(self) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.force_charge(self.device_id)
        )
