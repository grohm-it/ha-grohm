"""Tests of the config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

from grohm import GrohmConnectionError, GrohmError
import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.grohm.const import DOMAIN

from .conftest import FakeGrohmCloud

USER_INPUT = {CONF_EMAIL: " User@Example.com ", CONF_PASSWORD: "secret"}


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[None]:
    """Do not set up the entries the flows create."""
    with patch("custom_components.grohm.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant, cloud: FakeGrohmCloud) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {CONF_EMAIL: "user@example.com", CONF_PASSWORD: "secret"}
    assert result["result"].unique_id == "42"
    # The flow only checks the credentials, and logs out again.
    assert [op for op, _ in cloud.operations] == ["Login", "Logout"]


@pytest.mark.parametrize(
    ("account_type", "error"),
    [("2", "installer_not_supported"), (None, "account_type_missing")],
)
async def test_unsupported_accounts(
    hass: HomeAssistant, cloud: FakeGrohmCloud, account_type: str | None, error: str
) -> None:
    cloud.account_type = account_type
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert cloud.logged_in is False

    # The user can recover with another account.
    cloud.account_type = "1"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (None, "invalid_auth"),
        (GrohmConnectionError("down"), "cannot_connect"),
        (GrohmError("boom"), "unknown"),
    ],
)
async def test_errors(
    hass: HomeAssistant,
    cloud: FakeGrohmCloud,
    side_effect: Exception | None,
    error: str,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    if side_effect is None:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_PASSWORD: "wrong"}
        )
    else:
        with patch(
            "custom_components.grohm.config_flow.GrohmClient.login",
            side_effect=side_effect,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], USER_INPUT
            )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, cloud: FakeGrohmCloud, config_entry: MockConfigEntry
) -> None:
    cloud.password = "new"
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new"


async def test_reauth_wrong_account(hass: HomeAssistant, cloud: FakeGrohmCloud) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="other",
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
