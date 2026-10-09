"""Diagnostics: raw attributes and decoded state, credentials redacted."""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SalusConfigEntry
from .model import ThermostatState

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


def _state(state: ThermostatState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    data = {f.name: getattr(state, f.name) for f in fields(state) if f.name != "zones"}
    data["zones"] = {f"zone{zone.value}": asdict(zs) for zone, zs in state.zones.items()}
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SalusConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": _state(coordinator.data),
        "attributes": {
            name: {"value": attr.value, "updated_ms": attr.updated_ms}
            for name, attr in coordinator.attributes.items()
            if not name.startswith("Phone")
        },
    }
