"""Coordinator that reads all chargers of an account in one request."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
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
    COMMAND_POLL_INTERVAL,
    COMMAND_TIMEOUT,
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
        self._follow_ups: dict[str, asyncio.Task[None]] = {}

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

    async def async_command(
        self,
        command: Awaitable[None],
        device_id: str,
        done: Callable[[Device], bool],
    ) -> None:
        """Send a command to a charger, then follow it up in the background.

        Returns as soon as the cloud accepts the command. The state is then
        read again every few seconds until `done` is true for the charger,
        or the command times out.
        """
        try:
            await command
        except GrohmError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if task := self._follow_ups.pop(device_id, None):
            task.cancel()
        self._follow_ups[device_id] = self.config_entry.async_create_background_task(
            self.hass,
            self._async_follow_up(device_id, done),
            f"{DOMAIN} command follow-up {device_id}",
        )

    async def _async_follow_up(
        self, device_id: str, done: Callable[[Device], bool]
    ) -> None:
        """Read the state until the charger reports the result of a command."""
        # Ask the charger to report its state more often, like the app does.
        with contextlib.suppress(GrohmError):
            await self.client.notify_viewing(device_id)
        # One more read after the entities stop showing the requested state.
        deadline = self.hass.loop.time() + COMMAND_TIMEOUT + COMMAND_POLL_INTERVAL
        try:
            while self.hass.loop.time() < deadline:
                await asyncio.sleep(COMMAND_POLL_INTERVAL)
                await self.async_refresh()
                if (device := self.data.get(device_id)) is not None and done(device):
                    return
        finally:
            # A newer command on the same charger may have replaced this task.
            if self._follow_ups.get(device_id) is asyncio.current_task():
                del self._follow_ups[device_id]
