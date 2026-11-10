"""Coordinator: un'unica richiesta periodica per tutte le wallbox."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GrohmApi, GrohmAuthError, GrohmError, GrohmUnsupportedAccountError
from .const import (
    COMMAND_REFRESH_DELAY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DISCOVERY_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type GrohmConfigEntry = ConfigEntry[GrohmCoordinator]


class GrohmCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Dati: id wallbox → device (con currentSession)."""

    config_entry: GrohmConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: GrohmConfigEntry, api: GrohmApi
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.device_ids: list[str] = []
        self._last_discovery: datetime | None = None

    @property
    def is_gestore(self) -> bool:
        return self.api.user is not None and self.api.user.is_gestore

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            now = dt_util.utcnow()
            if (
                self._last_discovery is None
                or now - self._last_discovery >= DISCOVERY_INTERVAL
            ):
                self.device_ids = await self.api.device_ids()
                self._last_discovery = now
            return await self.api.devices(self.device_ids)
        except GrohmUnsupportedAccountError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="unsupported_account"
            ) from err
        except GrohmAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except GrohmError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_command(self, coro) -> None:
        """Esegue un comando verso la wallbox e rilegge lo stato poco dopo."""
        try:
            await coro
        except GrohmError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await asyncio.sleep(COMMAND_REFRESH_DELAY)
        await self.async_refresh()
