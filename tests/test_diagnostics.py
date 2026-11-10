"""Tests of the diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohm.diagnostics import async_get_config_entry_diagnostics

from .conftest import FakeGrohmCloud, setup_integration


async def test_diagnostics(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    result = await async_get_config_entry_diagnostics(hass, config_entry)
    assert result["entry"] == {"email": "**REDACTED**", "password": "**REDACTED**"}
    assert result["account_type"] == "0"
    assert len(result["devices"]) == 2
    device = result["devices"][0]
    assert device["serial_number"] == "**REDACTED**"
    assert device["session"]["status"] == "CHARGING"
