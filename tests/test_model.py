"""Decoding of recorded iT500 attributes."""

from __future__ import annotations

from conftest import api, fixture_text, model

Attribute = api.Attribute
Mode = model.Mode


def test_decode_recorded_device():
    state = model.decode(api.parse_attributes(fixture_text("attributes.xml")))
    assert state.room_temperature == 17.5
    assert state.setpoint == 12.1
    assert state.heating is False
    assert state.mode is Mode.OFF  # A89=1 even though A92 (manual) is also 1
    assert state.battery_low is False
    assert state.online is True
    assert state.rssi == -56
    assert state.firmware == "11.7"
    assert state.frost_temperature == 5.0
    assert state.description == "Home"
    assert state.last_report_ms > 1_700_000_000_000
    assert state.plausible


def _attrs(**values: str) -> dict[str, api.Attribute]:
    return {name: Attribute(value, 1000) for name, value in values.items()}


def test_modes():
    assert model.decode_mode(_attrs(A89="1", A92="0", A88="0")) is Mode.OFF
    assert model.decode_mode(_attrs(A89="0", A92="1", A88="0")) is Mode.MANUAL
    assert model.decode_mode(_attrs(A89="0", A92="0", A88="1")) is Mode.TEMP_HOLD
    assert model.decode_mode(_attrs(A89="0", A92="0", A88="0")) is Mode.AUTO


def test_battery_low_when_not_zero():
    assert model.decode(_attrs(S03="1")).battery_low is True
    assert model.decode(_attrs()).battery_low is None


def test_bogus_32_reading_is_not_plausible():
    assert not model.decode(_attrs(A84="3200", A85="3200")).plausible
    assert model.decode(_attrs(A84="3200", A85="2100")).plausible


def test_last_report_uses_zone_attributes_only():
    attrs = {
        "A84": Attribute("1750", 5000),
        "S03": Attribute("0", 9000),
        "A85": Attribute("1210", 7000),
    }
    assert model.decode(attrs).last_report_ms == 7000


def test_setpoint_value_rounds_to_tenths():
    assert model.setpoint_value(21.0) == "2100"
    assert model.setpoint_value(12.1) == "1210"
    assert model.setpoint_value(20.04) == "2000"


def test_mode_writes_leave_off_last():
    assert model.mode_writes(Mode.OFF) == [("A89", "1")]
    assert model.mode_writes(Mode.MANUAL)[-1] == ("A89", "0")
    assert model.mode_writes(Mode.AUTO) == [("A92", "0"), ("A88", "0"), ("A89", "0")]
