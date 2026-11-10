"""Fixtures: a fake Grohm cloud behind the client of the library."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import patch

from grohm import GrohmAuthenticationError, GrohmClient
import pytest

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohm.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


def device_payload(device_id: str, name: str, fase: str = "tri") -> dict[str, Any]:
    """A charger as the GraphQL API returns it."""
    return {
        "id": device_id,
        "name": name,
        "serialNumber": f"AA:BB:CC:DD:EE:0{device_id}",
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


class FakeGrohmCloud:
    """Answers the GraphQL operations of the library."""

    def __init__(self) -> None:
        self.password = "secret"
        self.account_type: str | None = "0"
        self.logged_in = False
        self.operations: list[tuple[str, dict[str, Any]]] = []
        self.devices = {
            "1": device_payload("1", "Garage"),
            "2": device_payload("2", "Carport", fase="mono"),
            "3": device_payload("3", "Parking"),
        }
        self.private_ids = ["1", "2"]
        self.networks = [["1"], ["3"]]
        self.orphan_ids = ["2"]

    def _user(self) -> dict[str, Any]:
        return {
            "id": "42",
            "email": "user@example.com",
            "accountType": self.account_type,
        }

    @staticmethod
    def _page(items: list[Any]) -> dict[str, Any]:
        return {"items": items, "pageInfo": {"hasNextPage": False}}

    async def request(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        variables = variables or {}
        operation = query.split("(")[0].split("{")[0].split()[1]
        self.operations.append((operation, variables))
        if operation == "Login":
            if variables["password"] != self.password:
                return {
                    "login": {
                        "__typename": "LoginError",
                        "message": "Invalid email or password",
                    }
                }
            self.logged_in = True
            return {"login": {"__typename": "LoginSuccess", "user": self._user()}}
        if operation == "Logout":
            self.logged_in = False
            return {"logout": None}
        if operation == "Me":
            return {"me": self._user() if self.logged_in else None}
        if not self.logged_in:
            raise GrohmAuthenticationError("User is not authenticated")
        if operation == "MyDevices":
            return {"myDevices": self._page([{"id": i} for i in self.private_ids])}
        if operation == "MyNetworks":
            return {
                "myNetworks": self._page(
                    [{"devices": [{"id": i} for i in ids]} for ids in self.networks]
                )
            }
        if operation == "DevicesOutOfNet":
            return {"devicesOutOfNet": self._page([{"id": i} for i in self.orphan_ids])}
        if operation == "Devices":
            return {
                f"d{i}": copy.deepcopy(self.devices.get(variables[f"id{i}"]))
                for i in range(len(variables))
            }
        if operation == "EditDevice":
            self.devices[variables["id"]].update(variables["input"])
            return {"editDevice": {"__typename": "EditDeviceSuccess"}}
        if operation == "ChangeDeviceStatus":
            session = self.devices[variables["deviceId"]]["currentSession"]
            session["status"] = {
                "PAUSED": "PAUSED",
                "RUNNING": "CHARGING",
                "RESUMED": "CHARGING",
            }[variables["status"]]
            return {"changeDeviceStatus": {"device": {"id": variables["deviceId"]}}}
        raise AssertionError(f"Unexpected operation {operation}")


@pytest.fixture
def cloud() -> Generator[FakeGrohmCloud]:
    """Replace the transport of the library with the fake cloud."""
    fake = FakeGrohmCloud()

    async def _request(
        self: GrohmClient, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await fake.request(query, variables)

    with (
        patch.object(GrohmClient, "_request", _request),
        patch("custom_components.grohm.coordinator.COMMAND_REFRESH_DELAY", 0),
    ):
        yield fake


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry of a Grohm account."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="42",
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
