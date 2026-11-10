"""Blocco/sblocco della wallbox (editDevice.locked)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import GrohmConfigEntry
from .entity import GrohmEntity, add_entities_for_new_devices


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
        lambda device_id, _: [GrohmLock(coordinator, device_id, "lock")],
    )


class GrohmLock(GrohmEntity, LockEntity):
    """Wallbox bloccata: non eroga finché non viene sbloccata."""

    _attr_translation_key = "lock"

    @property
    def is_locked(self) -> bool | None:
        locked = self.device.get("locked")
        return None if locked is None else locked is True

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.set_locked(self.device_id, True)
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(
            self.coordinator.api.set_locked(self.device_id, False)
        )
