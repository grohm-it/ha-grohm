"""Config flow of the Grohm integration.

Only private and fleet manager accounts are accepted. Installer accounts are
refused: they only have read-only access to the chargers of their customers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiohttp import ClientSession
from grohm import (
    AccountType,
    GrohmAuthenticationError,
    GrohmClient,
    GrohmConnectionError,
    GrohmError,
    User,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN, LOGGER, SUPPORTED_ACCOUNT_TYPES

EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
)
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): EMAIL_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


class GrohmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grohm."""

    VERSION = 1

    _session: ClientSession | None = None

    async def _async_validate(
        self, email: str, password: str
    ) -> tuple[User | None, dict[str, str]]:
        """Log in, check the account type, and log out again."""
        if self._session is None:
            # A session of its own: the API uses a session cookie.
            self._session = async_create_clientsession(self.hass)
        client = GrohmClient(self._session, email, password)
        try:
            user = await client.login()
        except GrohmAuthenticationError:
            return None, {"base": "invalid_auth"}
        except GrohmConnectionError:
            return None, {"base": "cannot_connect"}
        except GrohmError:
            LOGGER.exception("Unexpected error while logging in")
            return None, {"base": "unknown"}
        # The flow only checks the credentials: the entry opens its own session.
        await client.logout()
        if user.account_type is AccountType.INSTALLER:
            return None, {"base": "installer_not_supported"}
        if user.account_type not in SUPPORTED_ACCOUNT_TYPES:
            return None, {"base": "account_type_missing"}
        return user, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the credentials of the Grohm account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            user, errors = await self._async_validate(email, user_input[CONF_PASSWORD])
            if user is not None:
                await self.async_set_unique_id(user.id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email,
                    data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication when the password was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user, errors = await self._async_validate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if user is not None:
                await self.async_set_unique_id(user.id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
