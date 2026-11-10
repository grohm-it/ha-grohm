"""The Grohm integration."""

from __future__ import annotations

from grohm import GrohmClient

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .coordinator import GrohmConfigEntry, GrohmCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: GrohmConfigEntry) -> bool:
    """Set up Grohm from a config entry."""
    # The API authenticates with a session cookie: use a session with a
    # cookie jar of its own, not the shared one.
    session = async_create_clientsession(hass)
    client = GrohmClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = GrohmCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GrohmConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.logout()
    return unloaded
