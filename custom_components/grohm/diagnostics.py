"""Diagnostica (dati scaricabili dalla pagina dell'integrazione)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import GrohmConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "serialNumber", "name", "id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GrohmConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    user = coordinator.api.user
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "account_type": user.account_type if user else None,
        "devices": [
            async_redact_data(device, TO_REDACT)
            for device in (coordinator.data or {}).values()
        ],
    }
