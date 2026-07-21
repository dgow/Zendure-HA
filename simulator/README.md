# ZendureManager Simulator

Standalone simulator for the ZendureManager power distribution algorithm. Simulates P1 smart meter readings, solar production, and battery device behavior without requiring Home Assistant.

## Prerequisites

- Python 3.12+
- `matplotlib` (optional, for chart generation)

```bash
pip install matplotlib  # optional
```

## Quick Start

```bash
# Run with default scenario (sunny day, matching mode)
python -m simulator

# Or use the script wrapper
./scripts/simulate
```

## Usage

```bash
python -m simulator [OPTIONS]
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-s`, `--scenario` | `sunny` | Predefined scenario name |
| `-m`, `--mode` | `matching` | Manager mode |
| `--soc` | (scenario) | Override initial battery SOC% (0-100) |
| `--device` | (scenario) | Override device type |
| `--duration` | (scenario) | Override duration in hours |
| `--step` | (scenario) | Override time step in seconds |
| `--load` | (scenario) | Override household load in watts |
| `--solar-peak` | (scenario) | Override solar peak watts |
| `--csv FILE` | none | Export results to CSV |
| `--charts [FILE]` | none | Generate chart image (default: simulation.png) |
| `--list-scenarios` | none | List all scenarios and exit |
| `-v`, `--verbose` | off | Enable debug logging |

### Modes

| Mode | Description |
|------|-------------|
| `off` | No power distribution, devices powered off |
| `manual` | Use manual power setpoint |
| `matching` | Full bidirectional grid matching |
| `matching_discharge` | Only discharge when grid has deficit |
| `matching_charge` | Primarily charge, limited discharge of produced power |
| `store_solar` | Only charge from surplus, never discharge to grid |

## Scenarios

### `sunny`
Clear sunny day with smooth solar curve. Solar peaks at 800W around noon, household load is 300W. Single SolarFlow 800 device starting at 50% SOC.

```bash
python -m simulator -s sunny
```

### `cloudy`
Cloudy day with intermittent clouds reducing solar output. Load is 400W, device starts at 30% SOC.

```bash
python -m simulator -s cloudy
```

### `evening`
Afternoon into evening. Solar drops while household load spikes (simulating dishwasher/oven). Device starts at 85% SOC.

```bash
python -m simulator -s evening
```

### `multi_device`
Two SolarFlow 800 devices at different SOC levels (30% and 70%). Tests weighted power distribution across devices.

```bash
python -m simulator -s multi_device
```

### `minimal`
Quick 1-hour test with constant 500W solar and 200W load. Good for debugging.

```bash
python -m simulator -s minimal
```

## Examples

```bash
# Sunny day with 90% initial SOC
python -m simulator -s sunny --soc 90

# Cloudy day, store solar mode
python -m simulator -s cloudy -m store_solar

# Multi-device scenario with 2400W solar peak
python -m simulator -s multi_device --solar-peak 2400

# Generate charts
python -m simulator -s sunny --charts output.png

# Export to CSV
python -m simulator -s sunny --csv results.csv

# Verbose debug output
python -m simulator -s minimal -v

# Custom duration and step size
python -m simulator -s sunny --duration 6 --step 60
```

## Output

### Terminal Table

```
----------------------------------------------------------------------------------------------------
    Time       P1    Solar       State    SF800-Unit1    SF800-Unit2     Charge   Discharge
----------------------------------------------------------------------------------------------------
    06:00     +300        0  CHARGE              50.0%          70.0%       -300          0
    06:05     +300        0  CHARGE              50.1%          70.1%       -300          0
    08:00     -200      400  CHARGE              55.0%          75.0%       -600          0
    12:00     -500      800  IDLE                92.0%          98.0%         0          0
    18:00     +500       50  DISCHARGE           88.0%          94.0%         0         500
----------------------------------------------------------------------------------------------------
```

### Charts

With `--charts`, generates a 3-panel PNG:
1. **Grid Power (P1) & Solar Production** — shows the P1 meter reading and solar curve
2. **Battery State of Charge** — SOC% over time for each device
3. **Device Power Distribution** — charge/discharge power over time

## Architecture

The simulator recreates the core power distribution algorithm from `custom_components/zendure_ha/manager.py:421-640` without Home Assistant dependencies:

- **SimDevice** — lightweight device model with the same interface the manager expects
- **SimManager** — standalone power distribution engine with weighted charge/discharge
- **SimSolarPanel** — generates bell-curve solar production with cloud遮挡
- **SimP1Meter** — computes net grid power from load, solar, and device contributions

The algorithm faithfully reproduces:
- Device classification (charge/discharge/idle)
- Weighted power distribution by SOC
- Hysteresis prevention (2-60s delay between charge/discharge switches)
- Idle device startup at POWER_START (50W)
- Fuse group limits
- Optimal working range checks

## Adding Custom Scenarios

Edit `simulator/scenarios.py` to add new scenarios:

```python
def my_scenario() -> Scenario:
    return Scenario(
        name="my_scenario",
        description="Description of the scenario",
        duration_hours=8,
        step_seconds=300,
        solar=SimSolarPanel(peak_watts=1000, sunrise_hour=6, sunset_hour=20),
        p1=SimP1Meter(household_load=400),
        devices=[
            SimDevice(
                name="My Device",
                device_id="my_device_001",
                kWh=2.0,
                charge_limit=-2400,
                discharge_limit=2400,
                initial_soc=60,
            ),
        ],
    )
```

Then register it in the `SCENARIOS` dict at the bottom of the file.
