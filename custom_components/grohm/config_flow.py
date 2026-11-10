"""Configurazione da interfaccia: login con le credenziali dell'app my-Grohm.

Sono ammessi solo gli account *privato* e *gestore*: gli *installatori*
vengono rifiutati (vedono solo dispositivi di altri e in sola lettura).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.ssl import get_default_context

from .api import (
    ACCOUNT_INSTALLATORE,
    GrohmApi,
    GrohmAuthError,
    GrohmConnectionError,
    GrohmError,
    GrohmUnsupportedAccountError,
    GrohmUser,
    create_session,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


class GrohmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flusso di configurazione Grohm."""

    VERSION = 1

    async def _try_login(
        self, email: str, password: str
    ) -> tuple[GrohmUser | None, dict[str, str]]:
        session = create_session(get_default_context())
        api = GrohmApi(session, email, password)
        try:
            user = await api.login()
        except GrohmUnsupportedAccountError as err:
            reason = (
                "installer_not_allowed"
                if err.account_type == ACCOUNT_INSTALLATORE
                else "account_type_missing"
            )
            return None, {"base": reason}
        except GrohmAuthError:
            return None, {"base": "invalid_auth"}
        except GrohmConnectionError:
            return None, {"base": "cannot_connect"}
        except GrohmError:
            _LOGGER.exception("Errore inatteso durante il login Grohm")
            return None, {"base": "unknown"}
        finally:
            # Il flusso serve solo a verificare: la sessione vera la apre l'integrazione.
            await api.logout()
            await session.close()
        return user, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            user, errors = await self._try_login(email, user_input[CONF_PASSWORD])
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
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            email = entry.data[CONF_EMAIL]
            user, errors = await self._try_login(email, user_input[CONF_PASSWORD])
            if user is not None:
                await self.async_set_unique_id(user.id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): USER_SCHEMA.schema[CONF_PASSWORD]}
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> GrohmOptionsFlow:
        return GrohmOptionsFlow()


class GrohmOptionsFlow(OptionsFlow):
    """Opzioni: intervallo di aggiornamento."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
