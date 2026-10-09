"""Polling coordinator and confirmed commands for one iT500."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Attribute, SalusAuthError, SalusClient, SalusError
from .const import (
    COMMAND_ATTEMPTS,
    CONF_SCAN_INTERVAL,
    CONF_WAKE_INTERVAL,
    CONFIRM_POLL_DELAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WAKE_INTERVAL,
    DOMAIN,
    REFRESH_SECONDS,
)
from .model import ATTR_REFRESH, ATTR_SETPOINT, Mode, ThermostatState, decode, mode_writes, setpoint_value

_LOGGER = logging.getLogger(__name__)

# Tolerance for clock skew between Home Assistant and the Salus servers.
CLOCK_SKEW_MS = 2000


def _now_ms() -> int:
    return int(time.time() * 1000) - CLOCK_SKEW_MS


type SalusConfigEntry = ConfigEntry[SalusCoordinator]


class SalusCoordinator(DataUpdateCoordinator[ThermostatState]):
    """Reads the cloud copy of the thermostat state and runs confirmed commands."""

    config_entry: SalusConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SalusConfigEntry,
        client: SalusClient,
        device_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.device_id = device_id
        self.attributes: dict[str, Attribute] = {}
        self._command_lock = asyncio.Lock()

    async def _async_update_data(self) -> ThermostatState:
        try:
            attributes = await self.client.async_get_attributes(self.device_id)
        except SalusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SalusError as err:
            raise UpdateFailed(str(err)) from err
        state = decode(attributes)
        if not state.plausible:
            # Keep the last good state; the next poll logs in again.
            self.client.reset_session()
            raise UpdateFailed("Implausible 32/32 reading, session reset")
        self.attributes = attributes
        return state

    def start_wake_timer(self) -> None:
        """Wake the thermostat periodically if the user enabled it."""
        minutes = self.config_entry.options.get(CONF_WAKE_INTERVAL, DEFAULT_WAKE_INTERVAL)
        if not minutes:
            return

        async def _wake(_now) -> None:
            try:
                await self.async_wake()
            except HomeAssistantError as err:
                _LOGGER.debug("Periodic wake failed: %s", err)

        self.config_entry.async_on_unload(
            async_track_time_interval(self.hass, _wake, timedelta(minutes=minutes))
        )

    async def _set(self, name: str, value: str) -> None:
        try:
            await self.client.async_set_attribute(self.device_id, name, value)
        except SalusAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"Salus rejected the credentials: {err}") from err
        except SalusError as err:
            raise HomeAssistantError(f"Salus command {name}={value} failed: {err}") from err

    async def _poll_until(self, check, since_ms: int) -> bool:
        """Poll the cloud until a fresh report satisfies check()."""
        for delay in CONFIRM_POLL_DELAYS:
            await asyncio.sleep(delay)
            try:
                attributes = await self.client.async_get_attributes(self.device_id)
            except SalusError as err:
                _LOGGER.debug("Confirmation poll failed: %s", err)
                continue
            state = decode(attributes)
            if not state.plausible:
                continue
            self.attributes = attributes
            self.async_set_updated_data(state)
            if state.last_report_ms >= since_ms and check(attributes):
                return True
        return False

    async def async_wake(self) -> None:
        """Refresh mode: the thermostat reports every attribute within a few seconds."""
        async with self._command_lock:
            since_ms = _now_ms()
            await self._set(ATTR_REFRESH, str(REFRESH_SECONDS))
            await self._poll_until(lambda _attrs: True, since_ms)

    async def _async_command(self, writes: list[tuple[str, str]]) -> None:
        """Wake the thermostat, write, and confirm from a fresh report; retry once."""
        async with self._command_lock:
            for attempt in range(1, COMMAND_ATTEMPTS + 1):
                pending = [(n, v) for n, v in writes if self._current(n) != v]
                if not pending:
                    return
                since_ms = _now_ms()
                await self._set(ATTR_REFRESH, str(REFRESH_SECONDS))
                for name, value in pending:
                    await self._set(name, value)

                def _applied(attrs: dict[str, Attribute], pending=pending) -> bool:
                    return all(attrs.get(n) is not None and attrs[n].value == v for n, v in pending)

                if await self._poll_until(_applied, since_ms):
                    return
                _LOGGER.warning(
                    "Thermostat did not confirm %s (attempt %d/%d)", pending, attempt, COMMAND_ATTEMPTS
                )
            raise HomeAssistantError(
                "The thermostat did not confirm the change; it may apply later when it wakes up"
            )

    def _current(self, name: str) -> str | None:
        attr = self.attributes.get(name)
        return None if attr is None else attr.value

    async def async_set_temperature(self, temperature: float) -> None:
        """Set the zone 1 setpoint."""
        await self._async_command([(ATTR_SETPOINT, setpoint_value(temperature))])

    async def async_set_mode(self, mode: Mode) -> None:
        """Select off / manual / auto / temporary hold."""
        await self._async_command(mode_writes(mode))
