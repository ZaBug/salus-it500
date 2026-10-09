"""Diagnostics: raw attributes and decoded state, credentials redacted."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SalusConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SalusConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": asdict(coordinator.data) if coordinator.data else None,
        "attributes": {
            name: {"value": attr.value, "updated_ms": attr.updated_ms}
            for name, attr in coordinator.attributes.items()
            if not name.startswith("Phone")
        },
    }
