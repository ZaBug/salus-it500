"""End-to-end in Home Assistant with a simulated Salus cloud (needs Linux + the HA test harness)."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.salus_it500.api import (
    Attribute,
    DeviceInfo,
    SalusAuthError,
    parse_attributes,
)
from custom_components.salus_it500.const import CONF_DEVICE_ID, DOMAIN

from conftest import fixture_text

DEVICE = DeviceInfo(device_id="123456789", name="STA00000000", type_id="1")
CREDENTIALS = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}


class FakeCloud:
    """Simulated Salus account: writes are applied and reported immediately."""

    devices = [DEVICE]
    login_error: Exception | None = None
    apply_writes = True

    def __init__(self, session, username, password) -> None:
        self.attributes = parse_attributes(fixture_text("attributes.xml"))
        self.writes: list[tuple[str, str]] = []
        FakeCloud.last = self

    async def login(self) -> None:
        if FakeCloud.login_error:
            raise FakeCloud.login_error

    def reset_session(self) -> None:
        pass

    async def async_get_devices(self):
        return FakeCloud.devices

    async def async_get_attributes(self, device_id):
        return dict(self.attributes)

    async def async_set_attribute(self, device_id, name, value) -> None:
        self.writes.append((name, str(value)))
        if not FakeCloud.apply_writes:
            return
        now = int(time.time() * 1000)
        if name == "F":
            self.attributes = {n: Attribute(a.value, now) for n, a in self.attributes.items()}
        else:
            self.attributes[name] = Attribute(str(value), now)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_cloud():
    FakeCloud.devices = [DEVICE]
    FakeCloud.login_error = None
    FakeCloud.apply_writes = True
    with (
        patch("custom_components.salus_it500.SalusClient", FakeCloud),
        patch("custom_components.salus_it500.config_flow.SalusClient", FakeCloud),
        patch("custom_components.salus_it500.coordinator.CONFIRM_POLL_DELAYS", (0, 0)),
    ):
        yield FakeCloud


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE.device_id,
        data={**CREDENTIALS, CONF_DEVICE_ID: DEVICE.device_id},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_single_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID] == DEVICE.device_id
    assert result["result"].unique_id == DEVICE.device_id
    assert result["title"] == "Salus Home"  # description from the attributes


async def test_config_flow_invalid_auth(hass: HomeAssistant, fake_cloud) -> None:
    fake_cloud.login_error = SalusAuthError("nope")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_picks_device(hass: HomeAssistant, fake_cloud) -> None:
    other = DeviceInfo(device_id="555", name="Other", type_id="1")
    fake_cloud.devices = [DEVICE, other]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["step_id"] == "device"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_ID: "555"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID] == "555"


async def test_setup_creates_entities(hass: HomeAssistant) -> None:
    await _setup(hass)
    climate = hass.states.get("climate.home")
    assert climate is not None
    assert climate.state == HVACMode.OFF
    assert climate.attributes["current_temperature"] == 17.5
    assert climate.attributes["temperature"] == 12.1
    assert hass.states.get("sensor.home_room_temperature").state == "17.5"
    assert hass.states.get("binary_sensor.home_battery").state == "off"
    assert hass.states.get("binary_sensor.home_heating").state == "off"


async def test_set_temperature_wakes_and_confirms(hass: HomeAssistant, fake_cloud) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": "climate.home", "temperature": 21.5}, blocking=True
    )
    assert fake_cloud.last.writes == [("F", "60"), ("A85", "2150")]
    assert hass.states.get("climate.home").attributes["temperature"] == 21.5


async def test_hvac_heat_leaves_off_mode(hass: HomeAssistant, fake_cloud) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": "climate.home", "hvac_mode": "heat"}, blocking=True
    )
    # Manual flag is already 1 in the recording, so only the off flag changes.
    assert fake_cloud.last.writes == [("F", "60"), ("A89", "0")]
    assert hass.states.get("climate.home").state == HVACMode.HEAT


async def test_unconfirmed_command_is_retried_then_raises(hass: HomeAssistant, fake_cloud) -> None:
    await _setup(hass)
    fake_cloud.apply_writes = False
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": "climate.home", "temperature": 20}, blocking=True
        )
    assert fake_cloud.last.writes == [("F", "60"), ("A85", "2000")] * 2


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED
