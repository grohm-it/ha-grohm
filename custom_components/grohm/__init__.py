"""Integrazione Home Assistant per le wallbox Grohm."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.util.ssl import get_default_context

from .api import GrohmApi, create_session
from .coordinator import GrohmConfigEntry, GrohmCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: GrohmConfigEntry) -> bool:
    """Login, prima lettura e creazione delle entità."""
    # Sessione HTTP dedicata: il cookie di sessione Grohm non deve finire
    # nel cookie jar condiviso di Home Assistant.
    session = create_session(get_default_context())
    api = GrohmApi(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    entry.async_on_unload(session.close)
    coordinator = GrohmCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GrohmConfigEntry) -> bool:
    """Scarica le piattaforme e chiude la sessione Grohm."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.logout()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: GrohmConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
