"""Test del client e degli helper di dominio (senza Home Assistant)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.grohm import api as grohm


def test_build_devices_query():
    q = grohm.build_devices_query(2)
    assert "$id0: ID!, $id1: ID!" in q
    assert "d1: device(id: $id1) { ...GrohmDevice }" in q
    assert "fragment GrohmDevice on Device" in q


def test_power_zero_when_not_charging():
    assert (
        grohm.power_w({"status": "READY", "energyCar": 1500, "maxCurrentCar": 0}) == 0
    )
    assert (
        grohm.power_w({"status": "CHARGING", "energyCar": 1500, "maxCurrentCar": 0})
        == 0
    )
    assert (
        grohm.power_w({"status": "CHARGING", "energyCar": 7300, "maxCurrentCar": 32})
        == 7300
    )
    assert grohm.power_w({}) is None


def test_voltage_millivolt_string():
    assert grohm.voltage_volts({"voltage": "231500"}) == 231.5
    assert grohm.voltage_volts({"voltage": None}) is None


def test_nominal_kw_snaps_by_phase():
    assert grohm.nominal_kw({"maxPowerKw": 22.2, "fase": "tri"}) == 22
    assert grohm.nominal_kw({"maxPowerKw": 11.1, "fase": "tri"}) == 11
    assert grohm.nominal_kw({"maxPowerKw": 7.36, "fase": "mono"}) == 7.4
    assert grohm.nominal_kw({"maxPowerKw": None}) is None


def test_charging_phases():
    tri = {"fase": "tri"}
    session = {
        "status": "CHARGING",
        "energyCar": 7360,
        "maxCurrentCar": 32,
        "voltage": "230000",
    }
    assert grohm.charging_phases(session, tri) == 1
    session["energyCar"] = 22080
    assert grohm.charging_phases(session, tri) == 3
    assert grohm.charging_phases(session, {"fase": "mono"}) is None


def test_pause_resume_target():
    assert grohm.pause_resume_target("CHARGING") == "PAUSED"
    assert grohm.pause_resume_target("PAUSED") == "RUNNING"
    assert grohm.pause_resume_target("WAITING") == "RESUMED"
    assert grohm.pause_resume_target("READY") is None


def _api():
    session = MagicMock()
    session.cookie_jar = MagicMock()
    session.cookie_jar.__iter__ = lambda self: iter([])
    return grohm.GrohmApi(session, "a@b.it", "secret")


async def test_installer_login_refused(backend):
    backend.account_type = "2"
    api = _api()
    with pytest.raises(grohm.GrohmUnsupportedAccountError):
        await api.login()
    assert api.user is None
    assert backend.logged_in is False  # sessione chiusa subito


async def test_missing_account_type_refused(backend):
    backend.account_type = None
    with pytest.raises(grohm.GrohmUnsupportedAccountError):
        await _api().login()


async def test_private_device_ids(backend):
    api = _api()
    await api.login()
    assert await api.device_ids() == ["1", "2"]


async def test_gestore_device_ids_flatten_networks(backend):
    backend.account_type = "1"
    api = _api()
    await api.login()
    # wallbox di tutte le reti + quelle fuori rete, nessuna "rete" restituita
    assert await api.device_ids() == ["1", "3", "2"]


async def test_relogin_on_expired_session(backend):
    api = _api()
    await api.login()
    backend.logged_in = False  # il server ha invalidato la sessione
    devices = await api.devices(["1"])
    assert devices["1"]["name"] == "Garage"
    assert [op for op, _ in backend.calls].count("Login") == 2


async def test_account_becoming_installer_is_refused(backend):
    api = _api()
    await api.login()
    backend.account_type = "2"
    with pytest.raises(grohm.GrohmUnsupportedAccountError):
        await api.device_ids()
