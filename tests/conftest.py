"""Fixture: backend GraphQL Grohm finto, al posto della rete."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.grohm.api import GrohmAuthError


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _device(dev_id: str, name: str, serial: str, fase: str = "tri", **extra) -> dict:
    device = {
        "id": dev_id,
        "name": name,
        "serialNumber": serial,
        "isConnected": True,
        "locked": False,
        "fase": fase,
        "forceCharge": False,
        "hourCost": 0.25,
        "maxPowerKw": 22.2 if fase == "tri" else 7.36,
        "totalKwhCharged": 1234.5,
        "currentSession": {
            "status": "CHARGING",
            "voltage": "231000",
            "maxCurrent": 32,
            "maxCurrentCar": 32,
            "wattHoursCharged": 5400,
            "energyCar": 22150,
            "chargeSeconds": 900,
            "wifiPower": -61,
            "createdAt": "2026-11-10T08:00:00+00:00",
        },
    }
    device.update(extra)
    return device


class FakeBackend:
    """Risponde alle operazioni GraphQL usate dall'integrazione."""

    def __init__(self) -> None:
        self.password = "secret"
        self.account_type: str | None = "0"
        self.logged_in = False
        self.calls: list[tuple[str, dict]] = []
        self.devices = {
            "1": _device("1", "Garage", "AA:BB:CC:DD:EE:01"),
            "2": _device("2", "Box mono", "AA:BB:CC:DD:EE:02", fase="mono"),
            "3": _device("3", "Parcheggio", "AA:BB:CC:DD:EE:03"),
        }
        self.private_ids = ["1", "2"]
        self.network_ids = [["1"], ["3"]]  # due reti del gestore
        self.orphan_ids = ["2"]

    def op_name(self, query: str) -> str:
        head = query.strip().split("(")[0].split("{")[0]
        return head.split()[1] if len(head.split()) > 1 else head

    async def post(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        variables = variables or {}
        op = self.op_name(query)
        self.calls.append((op, variables))
        if op == "Login":
            if variables["password"] != self.password:
                return {
                    "login": {
                        "__typename": "LoginError",
                        "message": "Credenziali errate",
                    }
                }
            self.logged_in = True
            return {
                "login": {
                    "__typename": "LoginSuccess",
                    "user": {
                        "id": "42",
                        "email": variables["email"],
                        "accountType": self.account_type,
                    },
                }
            }
        if op == "Logout":
            self.logged_in = False
            return {"logout": True}
        if not self.logged_in:
            if op == "Me":
                return {"me": None}
            raise GrohmAuthError("not authenticated")
        if op == "Me":
            return {
                "me": {"id": "42", "email": "a@b.it", "accountType": self.account_type}
            }
        page = lambda ids: {  # noqa: E731
            "items": [{"id": i} for i in ids],
            "pageInfo": {"hasNextPage": False, "nextPage": None},
        }
        if op == "MyDevices":
            return {"myDevices": page(self.private_ids)}
        if op == "MyNetworksDevices":
            return {
                "myNetworks": {
                    "items": [
                        {"devices": [{"id": i} for i in ids]}
                        for ids in self.network_ids
                    ],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        if op == "DevicesOutOfNet":
            return {"devicesOutOfNet": page(self.orphan_ids)}
        if op == "Devices":
            return {
                f"d{i}": copy.deepcopy(self.devices.get(variables[f"id{i}"]))
                for i in range(len(variables))
            }
        if op == "EditDevice":
            dev = self.devices[variables["id"]]
            dev.update(variables["input"])
            return {
                "editDevice": {
                    "__typename": "EditDeviceSuccess",
                    "device": {"id": dev["id"]},
                }
            }
        if op == "ChangeDeviceStatus":
            dev = self.devices[variables["deviceId"]]
            new = {"PAUSED": "PAUSED", "RUNNING": "CHARGING", "RESUMED": "CHARGING"}[
                variables["status"]
            ]
            dev["currentSession"]["status"] = new
            return {"changeDeviceStatus": {"device": {"id": dev["id"]}}}
        raise AssertionError(f"Operazione inattesa: {op}")


@pytest.fixture
def backend():
    fake = FakeBackend()

    async def _post(self, query, variables=None):
        return await fake.post(query, variables)

    with (
        patch("custom_components.grohm.api.GrohmApi._post", _post),
        patch("custom_components.grohm.coordinator.COMMAND_REFRESH_DELAY", 0),
    ):
        yield fake
