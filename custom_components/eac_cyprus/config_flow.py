"""Config flow: e-mail + password, then pick the supply (service point)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import EacAuthError, EacClient, EacError, ServicePoint
from .const import (
    CONF_BILLING_DAY,
    CONF_BILLING_MONTHS,
    CONF_FIXED_FEES,
    CONF_SERVICE_POINT,
    CONF_TARIFF,
    DEFAULT_BILLING_DAY,
    DEFAULT_BILLING_MONTHS,
    DEFAULT_FIXED_FEES,
    DEFAULT_TARIFF,
    DOMAIN,
)

USER_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


def billing_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Billing options (shared by setup and options flow)."""
    return vol.Schema(
        {
            vol.Required(CONF_BILLING_DAY, default=defaults.get(CONF_BILLING_DAY, DEFAULT_BILLING_DAY)): NumberSelector(
                NumberSelectorConfig(min=1, max=28, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_BILLING_MONTHS, default=defaults.get(CONF_BILLING_MONTHS, DEFAULT_BILLING_MONTHS)
            ): SelectSelector(SelectSelectorConfig(options=["odd", "even"], translation_key="billing_months")),
            vol.Required(CONF_TARIFF, default=defaults.get(CONF_TARIFF, DEFAULT_TARIFF)): SelectSelector(
                SelectSelectorConfig(options=["01", "02", "08"], translation_key="tariff")
            ),
            vol.Required(CONF_FIXED_FEES, default=defaults.get(CONF_FIXED_FEES, DEFAULT_FIXED_FEES)): NumberSelector(
                NumberSelectorConfig(min=0, max=100, step=0.01, mode=NumberSelectorMode.BOX, unit_of_measurement="€")
            ),
        }
    )


async def _login(hass, email: str, password: str) -> list[ServicePoint]:
    client = EacClient(async_get_clientsession(hass), email, password)
    await client.login()
    return await client.service_points()


class EacConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EAC Cyprus."""

    VERSION = 1

    def __init__(self) -> None:
        self._creds: dict[str, str] = {}
        self._points: list[ServicePoint] = []
        self._sp: ServicePoint | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._points = await _login(self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except EacAuthError:
                errors["base"] = "invalid_auth"
            except EacError:
                errors["base"] = "cannot_connect"
            else:
                if not self._points:
                    errors["base"] = "no_service_points"
                else:
                    self._creds = user_input
                    if len(self._points) == 1:
                        self._sp = self._points[0]
                        return await self.async_step_billing()
                    return await self.async_step_service_point()
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_service_point(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._sp = next(p for p in self._points if p.id == user_input[CONF_SERVICE_POINT])
            return await self.async_step_billing()
        options = {p.id: f"{p.id} – {p.address}" for p in self._points}
        return self.async_show_form(
            step_id="service_point", data_schema=vol.Schema({vol.Required(CONF_SERVICE_POINT): vol.In(options)})
        )

    async def async_step_billing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._sp
        await self.async_set_unique_id(self._sp.id)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title=f"EAC {self._sp.id}",
                data={**self._creds, CONF_SERVICE_POINT: self._sp.id, "address": self._sp.address},
                options=user_input,
            )
        return self.async_show_form(
            step_id="billing",
            data_schema=billing_schema({}),
            description_placeholders={"address": self._sp.address},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _login(self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            except EacAuthError:
                errors["base"] = "invalid_auth"
            except EacError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EacOptionsFlow()


class EacOptionsFlow(OptionsFlow):
    """Change billing options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=billing_schema(self.config_entry.options))
