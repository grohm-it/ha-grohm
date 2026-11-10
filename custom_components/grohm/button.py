"""Forced charge button, for fleet manager accounts like in the app."""

from __future__ import annotations

from grohm import ChargerStatus

from homeassistant.components.button import ButtonEntity
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
    """Set up the forced charge buttons."""
    if not entry.runtime_data.is_manager:
        return
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: [
            GrohmForceChargeButton(coordinator, device.id, "force_charge_button")
        ],
    )


class GrohmForceChargeButton(GrohmEntity, ButtonEntity):
    """Starts charging without an RFID card. Lasts 300 seconds."""

    _attr_translation_key = "force_charge"

    @property
    def available(self) -> bool:
        """Available while the charger is ready and not forced already."""
        device = self.device
        return (
            super().available
            and device is not None
            and device.status is ChargerStatus.READY
            and not device.force_charge
        )

    async def async_press(self) -> None:
        """Start a forced charge."""
        await self.coordinator.async_command(
            self.coordinator.client.force_charge(self.device_id)
        )
