# AGENTS.md

## Project

Home Assistant custom integration (HACS-compatible) for Zendure portable power stations and solar micro-inverters. Communicates via MQTT (cloud/local) and HTTP (zenSdk devices). Controls charging/discharging across multiple devices using a P1 smart meter for grid-power balancing.

## Development

```bash
# First-time setup
./scripts/setup        # installs deps + HACS + ensures HA config

# Run dev server
./scripts/develop      # starts HA with debug, sets PYTHONPATH for custom_components

# Lint (no type checker configured)
./scripts/lint         # ruff format . && ruff check . --fix
```

**No tests exist.** No test framework or test commands are configured.

**No type checker.** Only ruff linting is used.

## Linting

Ruff with `select = ["ALL"]` in `.ruff.toml` (py312 target). This is very strict. Many rules are explicitly ignored — check `.ruff.toml` before assuming a lint error is unintentional.

```bash
ruff format .
ruff check . --fix
```

CI only runs HACS validation and hassfest — no lint/typecheck/test in CI.

## Structure

```
custom_components/zendure_ha/
├── __init__.py       # HA integration entry, platforms setup
├── api.py            # Zendure cloud API + MQTT broker setup
├── config_flow.py    # UI config flow (token, MQTT, options)
├── const.py          # Constants, enums (ManagerMode, DeviceState, SmartMode)
├── device.py         # Device hierarchy: ZendureDevice, ZendureLegacy (MQTT), ZendureZenSdk (HTTP)
├── entity.py         # Base HA entity classes, property→entity mapping (~70 properties)
├── fusegroup.py      # Circuit fuse rating enforcement (800W–3600W)
├── manager.py        # ZendureManager: power distribution coordinator, P1 meter handling
├── migration.py      # Config/entity migration between versions
├── sensors/          # sensor.py, binary_sensor.py, number.py, select.py, switch.py, button.py
├── devices/          # Per-model implementations (ace1500, solarflow800, hub2000, etc.)
└── translations/     # en, de, fr, nl, pl
```

## Architecture

- **ZendureManager** (`manager.py`): Central coordinator. Polls devices, tracks P1 meter (grid power), distributes charge/discharge across devices. Modes: OFF, MANUAL, MATCHING, MATCHING_DISCHARGE, MATCHING_CHARGE, STORE_SOLAR.
- **FuseGroup** (`fusegroup.py`): Enforces shared circuit fuse limits across co-located devices.
- **Device hierarchy** (`device.py`): `ZendureDevice` base → `ZendureLegacy` (older, MQTT-only) and `ZendureZenSdk` (newer, local HTTP API). Child batteries: `ZendureBattery`.
- **Per-model files** (`devices/`): Override charge/discharge methods and model-specific behavior. New device models need a new file here + a mapping entry in `api.py`.

## Conventions

- HA dependency: `>=2026.4.3` (manifest.json), `>=2025.4.0` (hacs.json)
- MQTT dependency: `paho-mqtt==2.1.0`
- BLE dependency: `bleak-retry-connector>=3.9.0`
- Single config entry enforced (`single_config_entry: true`)
- 6 HA platforms: binary_sensor, button, number, select, sensor, switch
- Config entry version: 1.0 (minor_version 8)
