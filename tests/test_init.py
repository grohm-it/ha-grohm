"""Test di config flow, entità e comandi in Home Assistant."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohm.const import DOMAIN


async def _start_flow(hass: HomeAssistant, password: str = "secret"):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: " User@Example.it ", CONF_PASSWORD: password}
    )


async def test_flow_private_ok(hass: HomeAssistant, backend) -> None:
    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.it"
    assert result["result"].unique_id == "42"


async def test_flow_installer_refused(hass: HomeAssistant, backend) -> None:
    backend.account_type = "2"
    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "installer_not_allowed"}
    assert backend.logged_in is False


async def test_flow_invalid_auth(hass: HomeAssistant, backend) -> None:
    result = await _start_flow(hass, password="wrong")
    assert result["errors"] == {"base": "invalid_auth"}


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="42",
        data={CONF_EMAIL: "user@example.it", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_private(hass: HomeAssistant, backend) -> None:
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == ["Box mono", "Garage"]

    assert hass.states.get("sensor.garage_status").state == "charging"
    assert float(hass.states.get("sensor.garage_power").state) == 22.15
    assert float(hass.states.get("sensor.garage_voltage").state) == 231.0
    assert hass.states.get("sensor.garage_charging_phases").state == "3"
    assert hass.states.get("sensor.box_mono_charging_phases") is None
    assert hass.states.get("lock.garage_lock").state == "unlocked"
    assert hass.states.get("switch.garage_charging").state == "on"
    # privato: niente ricarica forzata
    assert hass.states.get("button.garage_force_charge") is None

    await hass.services.async_call(
        "lock", "lock", {"entity_id": "lock.garage_lock"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("lock.garage_lock").state == "locked"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.garage_charging"}, blocking=True
    )
    await hass.async_block_till_done()
    assert backend.calls[-2][0] == "ChangeDeviceStatus" or any(
        op == "ChangeDeviceStatus" and v["status"] == "PAUSED"
        for op, v in backend.calls
    )
    assert hass.states.get("switch.garage_charging").state == "off"
    assert hass.states.get("sensor.garage_power").state == "0.0"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garage_charging"}, blocking=True
    )
    await hass.async_block_till_done()
    assert any(
        op == "ChangeDeviceStatus" and v["status"] == "RUNNING"
        for op, v in backend.calls
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert backend.logged_in is False


async def test_setup_gestore_flat_devices(hass: HomeAssistant, backend) -> None:
    backend.account_type = "1"
    backend.devices["3"]["currentSession"]["status"] = "READY"
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == ["Box mono", "Garage", "Parcheggio"]
    assert hass.states.get("button.parcheggio_force_charge").state != "unavailable"
    assert hass.states.get("button.garage_force_charge").state == "unavailable"

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.parcheggio_force_charge"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert backend.devices["3"]["forceCharge"] is True
    assert (
        hass.states.get("binary_sensor.parcheggio_forced_charge_active").state == "on"
    )


async def test_setup_installer_entry_fails(hass: HomeAssistant, backend) -> None:
    backend.account_type = "2"
    entry = _entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_wrong_password_starts_reauth(hass: HomeAssistant, backend) -> None:
    backend.password = "changed"
    entry = _entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_offline_device(hass: HomeAssistant, backend) -> None:
    backend.devices["1"]["isConnected"] = False
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garage_power").state == "unavailable"
    assert hass.states.get("binary_sensor.garage_connectivity").state == "off"
    assert hass.states.get("sensor.garage_total_energy").state == "1234.5"
