"""Thermostat state decoded from the raw attributes. No Home Assistant imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from .api import Attribute

# Zone attributes are the zone letter plus a number: A = zone 1 (the thermostat
# itself), B = zone 2 (an iT300TX receiver). Temperatures are in 0.01 °C.
ROOM_TEMP = "84"
SETPOINT = "85"
RELAY = "87"
TEMP_HOLD = "88"  # 0 = follow schedule, 1 = temporary hold
OFF = "89"  # 1 = zone off
FROST_ACTIVE = "90"
BOOST_HOURS = "91"  # hours left; writing N > 0 starts a boost, 0 cancels it
MANUAL = "92"  # 1 = manual mode

ATTR_BATTERY = "S03"  # "0" = OK (same rule as the website's battery_check.php)
ATTR_SYSTEM_TYPE = "S06"
ATTR_FROST_TEMP = "S09"
ATTR_FIRMWARE = "S13"
ATTR_ONLINE = "online"
ATTR_RSSI = "rfrssi"
ATTR_DESCRIPTION = "desc"
# Write-only in practice: "Turn On Refresh Mode for X Seconds (Recommend X=60)".
# The gateway wakes the thermostat, which reports every attribute within seconds.
ATTR_REFRESH = "F"

# Zone attributes the thermostat reports together; their newest timestamp is the last report.
REPORT_SUFFIXES = (ROOM_TEMP, SETPOINT, RELAY, OFF, TEMP_HOLD)

# A broken cloud session once reported 32/32 (salusfy issues #9 and #31): never trust it.
BOGUS_TEMP = 32.0

# Boost length accepted by the thermostat (the manual documents 1, 2 or 3 hours).
MIN_BOOST_HOURS = 1
MAX_BOOST_HOURS = 3


class Zone(IntEnum):
    """Heating zone; the value is the zone number shown to users."""

    ONE = 1
    TWO = 2

    @property
    def prefix(self) -> str:
        """Attribute letter of the zone."""
        return "A" if self is Zone.ONE else "B"

    def attr(self, suffix: str) -> str:
        """Attribute name of a zone attribute, e.g. Zone.TWO.attr(SETPOINT) == "B85"."""
        return f"{self.prefix}{suffix}"


class SystemType(IntEnum):
    """S06: what the thermostat controls."""

    CH1 = 0
    CH1_CH2 = 1
    CH1_HOT_WATER = 2


class Mode(StrEnum):
    """Zone operating mode."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"
    TEMP_HOLD = "temp_hold"


@dataclass(frozen=True, slots=True)
class ZoneState:
    """Decoded state of one heating zone."""

    room_temperature: float | None
    setpoint: float | None
    heating: bool
    mode: Mode
    frost_active: bool
    boost_hours: int
    last_report_ms: int

    @property
    def boost_active(self) -> bool:
        """True while a boost is counting down."""
        return self.boost_hours > 0


@dataclass(frozen=True, slots=True)
class ThermostatState:
    """Decoded zones plus system diagnostics."""

    zones: dict[Zone, ZoneState]
    system_type: SystemType | None
    battery_low: bool | None
    online: bool | None
    rssi: int | None
    firmware: str | None
    frost_temperature: float | None
    description: str | None

    @property
    def zone1(self) -> ZoneState:
        """Zone 1 is always present."""
        return self.zones[Zone.ONE]

    @property
    def last_report_ms(self) -> int:
        """Newest report of any zone."""
        return max(zone.last_report_ms for zone in self.zones.values())

    @property
    def plausible(self) -> bool:
        """False for the 32/32 pattern of a broken session."""
        zone = self.zone1
        return not (zone.room_temperature == BOGUS_TEMP and zone.setpoint == BOGUS_TEMP)


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


def decode_mode(attrs: dict[str, Attribute], zone: Zone = Zone.ONE) -> Mode:
    """Consolidated mode from the off / manual / temp hold flags."""
    if _flag(attrs, zone.attr(OFF)):
        return Mode.OFF
    if _flag(attrs, zone.attr(MANUAL)):
        return Mode.MANUAL
    if _flag(attrs, zone.attr(TEMP_HOLD)):
        return Mode.TEMP_HOLD
    return Mode.AUTO


def decode_zone(attrs: dict[str, Attribute], zone: Zone) -> ZoneState:
    """Decode one zone."""
    return ZoneState(
        room_temperature=_centi(attrs, zone.attr(ROOM_TEMP)),
        setpoint=_centi(attrs, zone.attr(SETPOINT)),
        heating=bool(_flag(attrs, zone.attr(RELAY))),
        mode=decode_mode(attrs, zone),
        frost_active=bool(_flag(attrs, zone.attr(FROST_ACTIVE))),
        boost_hours=_int(attrs, zone.attr(BOOST_HOURS)) or 0,
        last_report_ms=max(
            (attrs[zone.attr(s)].updated_ms for s in REPORT_SUFFIXES if zone.attr(s) in attrs),
            default=0,
        ),
    )


def decode(attrs: dict[str, Attribute]) -> ThermostatState:
    """Decode the attributes of an iT500. Zone 2 only exists on CH1+CH2 systems."""
    raw_type = _int(attrs, ATTR_SYSTEM_TYPE)
    try:
        system_type = SystemType(raw_type) if raw_type is not None else None
    except ValueError:
        system_type = None
    zones = {Zone.ONE: decode_zone(attrs, Zone.ONE)}
    if system_type is SystemType.CH1_CH2:
        zones[Zone.TWO] = decode_zone(attrs, Zone.TWO)
    battery = _value(attrs, ATTR_BATTERY)
    return ThermostatState(
        zones=zones,
        system_type=system_type,
        battery_low=None if battery is None else battery != "0",
        online=_flag(attrs, ATTR_ONLINE),
        rssi=_int(attrs, ATTR_RSSI),
        firmware=_value(attrs, ATTR_FIRMWARE),
        frost_temperature=_centi(attrs, ATTR_FROST_TEMP),
        description=_value(attrs, ATTR_DESCRIPTION),
    )


def mode_writes(mode: Mode, zone: Zone = Zone.ONE) -> list[tuple[str, str]]:
    """Attribute writes that select a mode, in a safe order (off flag last when leaving off)."""
    off, manual, hold = zone.attr(OFF), zone.attr(MANUAL), zone.attr(TEMP_HOLD)
    if mode is Mode.OFF:
        return [(off, "1")]
    if mode is Mode.MANUAL:
        return [(manual, "1"), (off, "0")]
    if mode is Mode.TEMP_HOLD:
        return [(manual, "0"), (hold, "1"), (off, "0")]
    return [(manual, "0"), (hold, "0"), (off, "0")]


def setpoint_value(temperature: float) -> str:
    """Setpoint in the API unit (0.01 °C), on the thermostat's 0.1 °C grid."""
    return str(round(temperature * 10) * 10)


def boost_writes(zone: Zone, hours: int, temperature: float | None) -> list[tuple[str, str]]:
    """Writes that start a boost: optional setpoint first, then the hours."""
    if not MIN_BOOST_HOURS <= hours <= MAX_BOOST_HOURS:
        raise ValueError(f"Boost hours must be {MIN_BOOST_HOURS}-{MAX_BOOST_HOURS}")
    writes = []
    if temperature is not None:
        writes.append((zone.attr(SETPOINT), setpoint_value(temperature)))
    writes.append((zone.attr(BOOST_HOURS), str(hours)))
    return writes
