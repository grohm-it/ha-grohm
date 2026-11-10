"""Diagnostics of the Grohm integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import GrohmConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "id", "name", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GrohmConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    user = coordinator.client.user
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "account_type": user.account_type if user else None,
        "devices": [
            async_redact_data(asdict(device), TO_REDACT)
            for device in coordinator.data.values()
        ],
    }
