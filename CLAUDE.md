# CLAUDE.md

Guidance for Claude Code and other coding agents working in this repository.
`AGENTS.md` points here.

## What This Is

A Home Assistant custom integration (HACS) for the Salus iT500 thermostat
through the Salus cloud API used by the mobile app (Arrayent backend,
`sal-emea-p01-api.arrayent.com`). Config flow from the UI, a polling
`DataUpdateCoordinator`, commands confirmed from a fresh device report.

## Commands

```bash
python -m venv .venv && .venv/Scripts/python -m pip install pytest pytest-asyncio aiohttp   # Windows
python -m pytest -q -p no:homeassistant tests/test_api.py tests/test_model.py   # no HA needed
python -m pytest -q tests/test_init.py    # end-to-end in HA (Linux only, runs in CI)
```

`tests/conftest.py` loads `api.py` and `model.py` under a stub package, so those
tests need no Home Assistant. `tests/test_init.py` needs
`pytest-homeassistant-custom-component`. `tests/fixtures/*.xml` are recorded
responses with the device id, user id and description replaced.

## Layout

| File | Role |
|---|---|
| `api.py` | `SalusClient`: login, token renewal, retries, XML parsing. Session injected. No HA imports |
| `model.py` | Attribute names, `decode()` to `ThermostatState`, mode and setpoint writes. No HA imports |
| `coordinator.py` | Polling, plausibility check, confirmed commands, optional periodic wake |
| `__init__.py` | Entry setup and unload |
| `config_flow.py` | Account login, device pick, reauth, options (poll / wake interval) |
| `entity.py` | Base entity and device info |
| `climate.py`, `sensor.py`, `binary_sensor.py`, `button.py` | Thin entity wrappers |
| `diagnostics.py` | Raw attributes and state, credentials redacted |

## Thermostat Rules (learned on real hardware, do not break)

- **The cloud copy can be hours old.** The battery thermostat reports only when
  a value changes. Never treat an old `updTime` as an error; show it.
- **Refresh mode wakes it.** Writing `F=60` makes the thermostat report every
  attribute within ~3 s (measured). Every command writes `F` first and then
  polls for a report newer than the command. Waking costs battery: never wake on
  every poll; the periodic wake is opt-in.
- **One attribute per write.** The device reports `multiAttributeCapable=false`.
- **Mode flags:** `A89=1` means off regardless of `A92` (manual) or `A88`
  (temporary hold). When leaving off, write the other flags first and `A89=0`
  last. Only write flags whose value differs.
- **Zones:** attribute letter `A` = zone 1, `B` = zone 2 (same numbers). Zone 2
  entities exist only when `S06 == 1` (CH1+CH2). On single-zone units the `B`
  attributes hold placeholders (room 60.0 C, setpoint 0): never show them.
  Zone 1 unique ids keep the plain keys of v0.1; zone 2 uses `zone2_` keys.
- **Boost:** write the setpoint (optional) then `A91` = 1-3 hours; `A91=0`
  cancels. Not yet verified on the live unit: test only with the owner's consent,
  it starts the boiler.
- **Battery:** `S03 == "0"` is OK; anything else is low (same rule as the
  website's `battery_check.php`).
- **32/32 reading** (room and setpoint both 32 °C) means a broken session:
  discard it and log in again.
- **Error codes:** login `403` + `errorCode 101` = bad credentials; zamapi
  `requestFault` `106` = token expired (log in again once), `109` = unknown device.
- Passwords: the API takes the MD5 hex digest. Never log credentials or tokens.

## Conventions

- **No co-author lines in commits.** Sole author is `ZaBug`. Never add
  `Co-Authored-By:` trailers. Use the local repo identity
  (`git config user.name` must be `ZaBug`).
- **English only** for commits, PRs, release notes, tags, code comments, logs
  and docs, even when the conversation is in another language.
- Conventional commit prefixes: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`,
  `test:`. Version bump commits carry `(vX.Y.Z)` in the message.
- **Version sync**: `manifest.json` `version` and `const.py`
  `INTEGRATION_VERSION` must match.
- `manifest.json` `requirements` stays empty; stdlib + HA APIs (aiohttp) only.
- All `.py` and `.json` files are UTF-8 without BOM.
- `strings.json` and `translations/en.json` stay identical.
- No code from the unlicensed salusfy forks; RichyA/pyit500 is MIT.

## Releasing

1. Bump `manifest.json` `version` and `const.py` `INTEGRATION_VERSION` together.
2. Push to `main` and wait for `.github/workflows/validate.yml` (HACS action
   without ignores, hassfest, tests) to pass.
3. Only then create the tag and a full GitHub release (`vX.Y.Z`, English notes).
   The HACS default store requires releases, not just tags.
4. hassfest rules: no `homeassistant` key in `manifest.json`; keys sorted
   `domain`, `name`, then alphabetical; `translations/en.json` present.

## HA Quality Rules

- Entities read only `coordinator.data` and call public coordinator methods.
- Listeners and timers are cancelled on unload (`entry.async_on_unload`).
- Commands raise `HomeAssistantError` when not confirmed; never fail silently.
- Never hardcode `suggested_area` in `DeviceInfo`.
- Type hints: `str | None`, not `Optional[str]`.
