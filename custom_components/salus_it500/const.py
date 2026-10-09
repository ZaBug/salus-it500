"""Constants for the Salus iT500 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "salus_it500"
INTEGRATION_VERSION: Final = "0.1.0"
MANUFACTURER: Final = "Salus"
MODEL: Final = "iT500"

CONF_DEVICE_ID: Final = "device_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_WAKE_INTERVAL: Final = "wake_interval"

# Reading the cloud is cheap (no radio traffic to the thermostat).
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 600

# Periodic refresh mode wakes the battery thermostat; 0 disables it.
DEFAULT_WAKE_INTERVAL: Final = 0
MAX_WAKE_INTERVAL: Final = 1440

# Refresh mode length requested from the gateway (value recommended by the API itself).
REFRESH_SECONDS: Final = 60
# Command confirmation: poll the cloud at these offsets (s) after waking the thermostat.
CONFIRM_POLL_DELAYS: Final = (3, 3, 4, 5, 5, 10)
COMMAND_ATTEMPTS: Final = 2

MIN_TEMP: Final = 5.0
MAX_TEMP: Final = 35.0
TEMP_STEP: Final = 0.1
