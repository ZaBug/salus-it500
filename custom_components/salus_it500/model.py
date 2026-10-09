"""Thermostat state decoded from the raw attributes. No Home Assistant imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .api import Attribute

# Zone 1 (the thermostat itself). Temperatures are in 0.01 °C.
ATTR_ROOM_TEMP = "A84"
ATTR_SETPOINT = "A85"
ATTR_RELAY = "A87"
ATTR_TEMP_HOLD = "A88"  # 0 = follow schedule, 1 = temporary hold
ATTR_OFF = "A89"  # 1 = zone off
ATTR_FROST_ACTIVE = "A90"
ATTR_BOOST_HOURS = "A91"
ATTR_MANUAL = "A92"  # 1 = manual mode
ATTR_BATTERY = "S03"  # "0" = OK (same rule as the website's battery_check.php)
ATTR_FROST_TEMP = "S09"
ATTR_FIRMWARE = "S13"
ATTR_ONLINE = "online"
ATTR_RSSI = "rfrssi"
ATTR_DESCRIPTION = "desc"
# Write-only in practice: "Turn On Refresh Mode for X Seconds (Recommend X=60)".
# The gateway wakes the thermostat, which reports every attribute within seconds.
ATTR_REFRESH = "F"

# Attributes the thermostat reports together; their newest timestamp is the last report.
REPORT_ATTRS = (ATTR_ROOM_TEMP, ATTR_SETPOINT, ATTR_RELAY, ATTR_OFF, ATTR_TEMP_HOLD)

# A broken cloud session once reported 32/32 (salusfy issues #9 and #31): never trust it.
BOGUS_TEMP = 32.0


class Mode(StrEnum):
    """Zone 1 operating mode."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"
    TEMP_HOLD = "temp_hold"


@dataclass(frozen=True, slots=True)
class ThermostatState:
    """Decoded zone 1 state plus system diagnostics."""

    room_temperature: float | None
    setpoint: float | None
    heating: bool
    mode: Mode
    frost_active: bool
    boost_hours: int
    battery_low: bool | None
    online: bool | None
    rssi: int | None
    firmware: str | None
    frost_temperature: float | None
    description: str | None
    last_report_ms: int

    @property
    def plausible(self) -> bool:
        """False for the 32/32 pattern of a broken session."""
        return not (self.room_temperature == BOGUS_TEMP and self.setpoint == BOGUS_TEMP)


def _value(attrs: dict[str, Attribute], name: str) -> str | None:
    attr = attrs.get(name)
    if attr is None or attr.value == "":
        return None
    return attr.value


def _centi(attrs: dict[str, Attribute], name: str) -> float | None:
    raw = _value(attrs, name)
    if raw is None or not raw.lstrip("-").isdigit():
        return None
    return int(raw) / 100


def _flag(attrs: dict[str, Attribute], name: str) -> bool | None:
    raw = _value(attrs, name)
    return None if raw is None else raw == "1"


def _int(attrs: dict[str, Attribute], name: str) -> int | None:
    raw = _value(attrs, name)
    if raw is None:
        return None
    token = raw.split()[0] if raw.split() else ""
    return int(token) if token.lstrip("-").isdigit() else None


def decode_mode(attrs: dict[str, Attribute]) -> Mode:
    """Consolidated mode from the off / manual / temp hold flags."""
    if _flag(attrs, ATTR_OFF):
        return Mode.OFF
    if _flag(attrs, ATTR_MANUAL):
        return Mode.MANUAL
    if _flag(attrs, ATTR_TEMP_HOLD):
        return Mode.TEMP_HOLD
    return Mode.AUTO


def decode(attrs: dict[str, Attribute]) -> ThermostatState:
    """Decode the attributes of an iT500."""
    battery = _value(attrs, ATTR_BATTERY)
    return ThermostatState(
        room_temperature=_centi(attrs, ATTR_ROOM_TEMP),
        setpoint=_centi(attrs, ATTR_SETPOINT),
        heating=bool(_flag(attrs, ATTR_RELAY)),
        mode=decode_mode(attrs),
        frost_active=bool(_flag(attrs, ATTR_FROST_ACTIVE)),
        boost_hours=_int(attrs, ATTR_BOOST_HOURS) or 0,
        battery_low=None if battery is None else battery != "0",
        online=_flag(attrs, ATTR_ONLINE),
        rssi=_int(attrs, ATTR_RSSI),
        firmware=_value(attrs, ATTR_FIRMWARE),
        frost_temperature=_centi(attrs, ATTR_FROST_TEMP),
        description=_value(attrs, ATTR_DESCRIPTION),
        last_report_ms=max((attrs[n].updated_ms for n in REPORT_ATTRS if n in attrs), default=0),
    )


def mode_writes(mode: Mode) -> list[tuple[str, str]]:
    """Attribute writes that select a mode, in a safe order (off flag last when leaving off)."""
    if mode is Mode.OFF:
        return [(ATTR_OFF, "1")]
    if mode is Mode.MANUAL:
        return [(ATTR_MANUAL, "1"), (ATTR_OFF, "0")]
    if mode is Mode.TEMP_HOLD:
        return [(ATTR_MANUAL, "0"), (ATTR_TEMP_HOLD, "1"), (ATTR_OFF, "0")]
    return [(ATTR_MANUAL, "0"), (ATTR_TEMP_HOLD, "0"), (ATTR_OFF, "0")]


def setpoint_value(temperature: float) -> str:
    """Setpoint in the API unit (0.01 °C), on the thermostat's 0.1 °C grid."""
    return str(round(temperature * 10) * 10)
