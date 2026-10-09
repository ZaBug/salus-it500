"""Config flow: Salus account, then the thermostat; options for polling."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DeviceInfo, SalusAuthError, SalusClient, SalusError
from .const import (
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_WAKE_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WAKE_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_WAKE_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .model import ATTR_DESCRIPTION

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


class SalusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, str] = {}
        self._devices: list[DeviceInfo] = []
        self._client: SalusClient | None = None

    async def _async_fetch_devices(self, username: str, password: str) -> list[DeviceInfo]:
        self._client = SalusClient(async_get_clientsession(self.hass), username, password)
        await self._client.login()
        return await self._client.async_get_devices()

    async def _async_title(self, device: DeviceInfo) -> str:
        """The description set in the Salus app (e.g. the location), else the gateway name."""
        if self._client is not None:
            try:
                attributes = await self._client.async_get_attributes(device.device_id)
            except SalusError:
                attributes = {}
            description = attributes.get(ATTR_DESCRIPTION)
            if description is not None and description.value:
                return f"Salus {description.value}"
        return f"Salus {device.name}"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                devices = await self._async_fetch_devices(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except SalusAuthError:
                errors["base"] = "invalid_auth"
            except SalusError:
                errors["base"] = "cannot_connect"
            else:
                if not devices:
                    return self.async_abort(reason="no_devices")
                self._credentials = user_input
                self._devices = devices
                if len(devices) == 1:
                    return await self._async_create(devices[0])
                return await self.async_step_device()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            device = next(d for d in self._devices if d.device_id == user_input[CONF_DEVICE_ID])
            return await self._async_create(device)
        options = [
            selector.SelectOptionDict(value=d.device_id, label=f"{d.name} ({d.device_id})")
            for d in self._devices
        ]
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )}
            ),
        )

    async def _async_create(self, device: DeviceInfo) -> ConfigFlowResult:
        await self.async_set_unique_id(device.device_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=await self._async_title(device),
            data={**self._credentials, CONF_DEVICE_ID: device.device_id},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                devices = await self._async_fetch_devices(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except SalusAuthError:
                errors["base"] = "invalid_auth"
            except SalusError:
                errors["base"] = "cannot_connect"
            else:
                if not any(d.device_id == entry.data[CONF_DEVICE_ID] for d in devices):
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> SalusOptionsFlow:
        return SalusOptionsFlow()


class SalusOptionsFlow(OptionsFlow):
    """Polling and wake intervals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
                        unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_WAKE_INTERVAL,
                    default=options.get(CONF_WAKE_INTERVAL, DEFAULT_WAKE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=MAX_WAKE_INTERVAL, step=1,
                        unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
