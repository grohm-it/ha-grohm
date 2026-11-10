"""Lock of Grohm chargers: a locked charger does not charge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    """Set up the locks."""
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: [GrohmLock(coordinator, device.id, "lock")],
    )


class GrohmLock(GrohmEntity, LockEntity):
    """Locks and unlocks a charger."""

    _attr_name = None
    _attr_translation_key = "charger"

    @property
    def is_locked(self) -> bool | None:
        """Return whether the charger is locked."""
        return self.device.locked if self.device else None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the charger."""
        await self.coordinator.async_command(
            self.coordinator.client.set_locked(self.device_id, True)
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the charger."""
        await self.coordinator.async_command(
            self.coordinator.client.set_locked(self.device_id, False)
        )
