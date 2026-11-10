"""Tests of setup, entities and commands."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from grohm import GrohmConnectionError
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.grohm.const import DOMAIN

from .conftest import FakeGrohmCloud, device_payload, setup_integration


async def test_private_account(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )
    assert sorted(device.name for device in devices) == ["Carport", "Garage"]
    garage = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "1")})
    assert garage is not None
    assert garage.model == "22 kW charger, three phase"
    assert garage.serial_number == "AA:BB:CC:DD:EE:01"

    assert hass.states.get("sensor.garage_status").state == "charging"
    assert hass.states.get("sensor.garage_power").state == "22.15"
    assert hass.states.get("sensor.garage_session_energy").state == "5.4"
    assert hass.states.get("sensor.garage_total_energy").state == "1234.5"
    assert hass.states.get("sensor.garage_voltage").state == "231.0"
    assert hass.states.get("sensor.garage_charging_phases").state == "3"
    assert hass.states.get("sensor.carport_charging_phases") is None
    assert hass.states.get("sensor.carport_rated_power").state == "7.4"
    assert hass.states.get("binary_sensor.garage_car").state == "on"
    assert hass.states.get("lock.garage").state == "unlocked"
    assert hass.states.get("switch.garage_charging").state == "on"
    # Forced charge is for manager accounts only.
    assert hass.states.get("button.garage_force_charge") is None
    assert hass.states.get("binary_sensor.garage_forced_charge") is None


async def test_lock(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    await hass.services.async_call(
        "lock", "lock", {"entity_id": "lock.garage"}, blocking=True
    )
    assert hass.states.get("lock.garage").state == "locked"
    await hass.services.async_call(
        "lock", "unlock", {"entity_id": "lock.garage"}, blocking=True
    )
    assert hass.states.get("lock.garage").state == "unlocked"


async def test_pause_and_resume(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    entity_id = "switch.garage_charging"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    assert cloud.operations[-2] == (
        "ChangeDeviceStatus",
        {"deviceId": "1", "status": "PAUSED"},
    )
    assert hass.states.get(entity_id).state == "off"
    assert hass.states.get("sensor.garage_power").state == "0.0"

    # Turning off again does nothing.
    count = len(cloud.operations)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    assert len(cloud.operations) == count

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert cloud.operations[-2] == (
        "ChangeDeviceStatus",
        {"deviceId": "1", "status": "RUNNING"},
    )
    assert hass.states.get(entity_id).state == "on"


async def test_switch_unavailable_without_car(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.devices["1"]["currentSession"]["status"] = "READY"
    cloud.devices["2"]["currentSession"] = None
    await setup_integration(hass, config_entry)
    assert hass.states.get("switch.garage_charging").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.carport_charging").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.garage_car").state == "off"
    assert hass.states.get("sensor.carport_status").state == "unknown"


async def test_manager_account(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.account_type = "1"
    cloud.devices["3"]["currentSession"]["status"] = "READY"
    await setup_integration(hass, config_entry)

    # The chargers of all networks and outside them; no network devices.
    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )
    assert sorted(device.name for device in devices) == ["Carport", "Garage", "Parking"]

    assert hass.states.get("button.garage_force_charge").state == STATE_UNAVAILABLE
    assert hass.states.get("button.parking_force_charge").state == "unknown"
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.parking_force_charge"}, blocking=True
    )
    assert cloud.devices["3"]["forceCharge"] is True
    assert hass.states.get("binary_sensor.parking_forced_charge").state == "on"
    assert hass.states.get("button.parking_force_charge").state == STATE_UNAVAILABLE


async def test_command_error(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    with (
        patch(
            "custom_components.grohm.coordinator.GrohmClient.set_locked",
            side_effect=GrohmConnectionError("down"),
        ),
        pytest.raises(HomeAssistantError, match="did not accept the command"),
    ):
        await hass.services.async_call(
            "lock", "lock", {"entity_id": "lock.garage"}, blocking=True
        )


async def test_offline_charger(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.devices["1"]["isConnected"] = False
    await setup_integration(hass, config_entry)
    assert hass.states.get("sensor.garage_power").state == STATE_UNAVAILABLE
    assert hass.states.get("lock.garage").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.garage_connectivity").state == "off"
    assert hass.states.get("sensor.garage_total_energy").state == "1234.5"


async def test_installer_account(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.account_type = "2"
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_wrong_password_starts_reauth(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.password = "changed"
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_cloud_down_retries(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    with patch(
        "custom_components.grohm.coordinator.GrohmClient.get_user",
        side_effect=GrohmConnectionError("down"),
    ):
        await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_new_charger_and_expired_session(
    hass: HomeAssistant,
    cloud: FakeGrohmCloud,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, config_entry)
    cloud.devices["4"] = device_payload("4", "Barn")
    cloud.private_ids.append("4")
    cloud.logged_in = False  # the session expired on the server

    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.barn_status").state == "charging"
    assert hass.states.get("sensor.garage_status").state == "charging"


async def test_unload(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    await setup_integration(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert cloud.logged_in is False
