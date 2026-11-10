"""Coordinator that reads all chargers of an account in one request."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime

from grohm import (
    AccountType,
    Device,
    GrohmAuthenticationError,
    GrohmClient,
    GrohmError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    COMMAND_REFRESH_DELAY,
    DISCOVERY_INTERVAL,
    DOMAIN,
    LOGGER,
    SCAN_INTERVAL,
    SUPPORTED_ACCOUNT_TYPES,
)

type GrohmConfigEntry = ConfigEntry[GrohmCoordinator]


class GrohmCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Charger ID to charger, for every charger of the account."""

    config_entry: GrohmConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: GrohmConfigEntry, client: GrohmClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.device_ids: list[str] = []
        self._last_discovery: datetime | None = None

    @property
    def is_manager(self) -> bool:
        """Whether the account is a fleet manager account."""
        user = self.client.user
        return user is not None and user.account_type is AccountType.MANAGER

    async def _async_update_data(self) -> dict[str, Device]:
        """Fetch the state of all chargers."""
        try:
            now = dt_util.utcnow()
            if (
                self._last_discovery is None
                or now - self._last_discovery >= DISCOVERY_INTERVAL
            ):
                # Also renews the session, and checks the account type.
                user = await self.client.get_user()
                if user.account_type not in SUPPORTED_ACCOUNT_TYPES:
                    raise ConfigEntryError(
                        translation_domain=DOMAIN,
                        translation_key="unsupported_account",
                    )
                self.device_ids = await self.client.get_device_ids()
                self._last_discovery = now
            return await self.client.get_devices(self.device_ids)
        except GrohmAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except GrohmError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_command(self, command: Awaitable[None]) -> None:
        """Send a command to a charger, then read the new state."""
        try:
            await command
        except GrohmError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await asyncio.sleep(COMMAND_REFRESH_DELAY)
        await self.async_refresh()
