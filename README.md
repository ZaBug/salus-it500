# Salus iT500

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2025.8%2B-blue.svg)](https://www.home-assistant.io/)

Home Assistant integration for the **Salus iT500** internet thermostat, through
the same cloud API the Salus iT500 mobile app uses. Setup from the UI, commands
confirmed by the thermostat, and diagnostics that show how fresh the data is.

> **Status: alpha.** Tested on one iT500 (single heating zone, thermostat
> firmware `11.7`, gateway `1.5.2.0`). Please report what works on yours.

## Why another iT500 integration

The existing `salusfy` components scrape `salus-it500.com`. That site shows the
same data as the app, so the data is not the problem; what was missing:

* **Freshness.** The battery thermostat reports to the gateway only when a value
  changes. On a quiet night the cloud copy can be hours old, and nothing told
  you. This integration exposes the time of the last report.
* **Commands that may never arrive.** The thermostat sleeps; the website
  endpoint accepts a command without saying whether it was applied. Here every
  command first puts the thermostat in *refresh mode* (attribute `F`, which the
  API itself describes as "Turn On Refresh Mode for X Seconds"), then waits for
  a fresh report that contains the new value, and retries once. Measured on the
  test unit: the thermostat reported within **3 seconds** of the refresh request.
* **Errors.** `retCode` of every write is checked, expired tokens are renewed,
  transient errors are retried, and a broken session (the 32 °C / 32 °C reading
  reported in salusfy issues) is discarded instead of shown.

## Entities

| Entity | What it shows |
|---|---|
| `climate.*` | Zone 1 (and `climate.*_zone_2` on two-zone systems). Modes: **Off**, **Heat** (manual setpoint), **Auto** (schedule). Preset **Temporary hold** = schedule paused at a setpoint. Target in 0.1 °C steps |
| `sensor.*_room_temperature`, `_setpoint` | Temperatures as last reported |
| `sensor.*_last_report` | When the thermostat last reported (diagnostic) |
| `sensor.*_boost_remaining`, `binary_sensor.*_boost` | Hours of boost left / boost running |
| `sensor.*_signal_strength` | RF signal between thermostat and gateway (disabled by default) |
| `binary_sensor.*_heating` | Boiler relay on |
| `binary_sensor.*_battery` | Thermostat batteries low |
| `binary_sensor.*_gateway_online` | Gateway connected to the Salus cloud |
| `binary_sensor.*_frost_protection` | Frost protection active |
| `button.*_refresh` | Wake the thermostat so it reports now |

### Zone 2

On systems with a second heating zone (an iT300TX receiver; the thermostat
reports system type `CH1+CH2`), the integration adds `climate.*_zone_2` and zone 2
room temperature, setpoint, boost, heating and frost protection entities. On
single-zone systems nothing is created. **Untested on real hardware**: the zone 2
attributes (`B84`-`B94`) mirror zone 1 and the code is covered by simulated tests
only. Reports from two-zone owners are welcome.

## Boost

`salus_it500.boost` heats a zone for 1-3 hours, optionally at a new setpoint;
the thermostat counts the hours down and returns to its previous program by
itself. `salus_it500.cancel_boost` stops it. Both target a climate entity and
are confirmed by the thermostat like every other command.

```yaml
action: salus_it500.boost
target:
  entity_id: climate.salus_thermostat
data:
  hours: 2
  temperature: 21
```

The iT500 manual documents boost (1, 2 or 3 hours) for hot water; the heating
boost uses the zone attribute `A91` (`B91` for zone 2), which the API describes
as "CH1 Boost Remaining hours".

## Installation

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ZaBug/salus-it500`,
   type **Integration**.
2. Download **Salus iT500**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Salus iT500**.
4. Enter the email and password of the Salus iT500 app. If the account has more
   than one thermostat, pick one (add the integration again for the others).

**Password with special characters?** Salus silently drops them when the
password is created, while the app and the website accept both forms. If the
login fails, try the password without the special characters.

## Options

| Option | Default | Notes |
|---|---|---|
| Cloud polling interval | 60 s | 30–600 s. Reads the cloud copy; does not wake the thermostat, costs no battery |
| Wake the thermostat every | 0 (never) | 0–1440 min. Forces a full report on a schedule. Uses thermostat battery; commands always wake it anyway |

## How it works

* Login: `POST https://sal-emea-p01-api.arrayent.com/acc/applications/SalusService/sessions`
  with the MD5 hash of the password; the answer is a user id and a security token.
* Reading: `getDeviceAttributesWithValues` returns every attribute with the time
  the device last reported it (`updTime`).
* Writing: `setMultiDeviceAttributes2`, one attribute per call (the device reports
  `multiAttributeCapable=false`).

| Attribute | Meaning |
|---|---|
| `A84` / `A85` | Room temperature / setpoint (0.01 °C) |
| `A87` | Relay (heating) |
| `A88` / `A89` / `A92` | Temporary hold / off / manual flags |
| `A90`, `A91` | Frost protection active, boost hours left (write 1-3 to start, 0 to cancel) |
| `B84`-`B94` | Zone 2, same layout as zone 1 |
| `S06` | System type: 0 = CH1, 1 = CH1+CH2, 2 = CH1 + hot water |
| `S03` | Battery: `0` = OK |
| `online`, `rfrssi` | Gateway online, RF signal |
| `F` | Refresh mode for N seconds |

## Known limitations

* Zone 2 is untested on real hardware (see above). Hot water is not exposed.
* Advance, skip and delay are not implemented: the thermostat has no such
  commands, so they would be Home Assistant timers; an automation does the same.
* The API host is the EMEA endpoint used by the app; other regions are untested.

## Credits

* [RichyA/pyit500](https://github.com/RichyA/pyit500) (MIT): the Arrayent API
  and attribute map this client is based on.
* [floringhimie/salusfy](https://github.com/floringhimie/salusfy),
  [matthewturner/salusfy](https://github.com/matthewturner/salusfy) and
  [gonzague/salusfy](https://github.com/gonzague/salusfy): the original Home
  Assistant integrations and the issues reported by their users (broken-session
  readings, battery check, 0.1 °C steps, mode switching).

The client was written for this project; no code was copied from the projects
without a license. This project is not affiliated with Salus Controls.

## License

[MIT](LICENSE)
