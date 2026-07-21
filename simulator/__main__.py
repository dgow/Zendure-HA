"""
ZendureManager standalone simulator.

Run with: python -m simulator [options]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from .const import ManagerMode
from .manager import SimManager
from .output import DeviceRow, SimRow, format_table, generate_charts, rows_to_csv
from .scenarios import SCENARIOS, Scenario, get_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ZendureManager power distribution simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  sunny        Clear sunny day, 800W solar peak, 300W load
  cloudy       Cloudy day with passing clouds
  evening      Afternoon into evening with load spikes
  multi_device Two devices at different SOC levels
  minimal      Quick 1-hour test

Modes:
  off               No power distribution
  manual            Manual power setpoint
  matching          Full bidirectional grid matching
  matching_discharge Only discharge on grid deficit
  matching_charge   Primarily charge, limited discharge
  store_solar       Only charge from surplus
""",
    )

    parser.add_argument(
        "-s",
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default="sunny",
        help="Predefined scenario (default: sunny)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=[m.name.lower() for m in ManagerMode],
        default="matching",
        help="Manager mode (default: matching)",
    )
    parser.add_argument(
        "--soc",
        type=float,
        default=None,
        help="Override initial battery SOC%% (0-100)",
    )
    parser.add_argument(
        "--device",
        choices=["solarflow800", "solarflow2400", "hub2000", "custom"],
        default=None,
        help="Override device type",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Override simulation duration in hours",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=None,
        help="Override time step in seconds",
    )
    parser.add_argument(
        "--load",
        type=float,
        default=None,
        help="Override household load in watts",
    )
    parser.add_argument(
        "--solar-peak",
        type=float,
        default=None,
        help="Override solar peak watts",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Export results to CSV file",
    )
    parser.add_argument(
        "--charts",
        type=str,
        default=None,
        nargs="?",
        const="simulation.png",
        help="Generate chart image (default: simulation.png)",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available scenarios and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def build_scenario(args: argparse.Namespace) -> Scenario:
    """Build scenario from args, applying overrides."""
    scenario = get_scenario(args.scenario)

    # Apply overrides
    if args.duration is not None:
        scenario.duration_hours = args.duration
    if args.step is not None:
        scenario.step_seconds = args.step
    if args.load is not None:
        scenario.p1.household_load = args.load
    if args.solar_peak is not None:
        scenario.solar.peak_watts = args.solar_peak

    if args.soc is not None:
        for d in scenario.devices:
            d.initial_soc = args.soc
            d.soc = args.soc

    if args.device is not None:
        device_presets = {
            "solarflow800": {
                "kWh": 1.0,
                "charge_limit": -1000,
                "discharge_limit": 800,
                "max_solar": 1200,
            },
            "solarflow2400": {
                "kWh": 2.4,
                "charge_limit": -2400,
                "discharge_limit": 2400,
                "max_solar": 2400,
            },
            "hub2000": {
                "kWh": 2.0,
                "charge_limit": 0,
                "discharge_limit": 1200,
                "max_solar": 2400,
            },
        }
        if args.device in device_presets:
            preset = device_presets[args.device]
            for d in scenario.devices:
                for k, v in preset.items():
                    setattr(d, k, v)

    return scenario


def run_simulation(
    scenario: Scenario, mode: ManagerMode, verbose: bool = False
) -> list[SimRow]:
    """Run the simulation and return results."""
    del verbose  # Reserved for future debug logging
    manager = SimManager(devices=scenario.devices, mode=mode)

    total_steps = int(scenario.duration_hours * 3600 / scenario.step_seconds)
    start_time = datetime(2024, 6, 15, 6, 0)  # A sunny summer day
    rows: list[SimRow] = []

    print(f"\nRunning '{scenario.name}' scenario: {scenario.description}")
    print(
        f"  Duration: {scenario.duration_hours}h"
        f" | Step: {scenario.step_seconds}s | Mode: {mode.name}"
    )
    print(f"  Devices: {', '.join(d.name for d in scenario.devices)}")
    print(
        f"  Solar peak: {scenario.solar.peak_watts}W"
        f" | Household load: {scenario.p1.household_load}W"
    )
    print()

    for step in range(total_steps + 1):
        sim_time = start_time + timedelta(seconds=step * scenario.step_seconds)
        hour_of_day = sim_time.hour + sim_time.minute / 60

        # Get solar production
        solar_w = scenario.solar.production(hour_of_day)

        # Get device contributions to home (from previous state)
        device_contribution = 0
        for d in scenario.devices:
            device_contribution += d.homeOutput.asInt - d.homeInput.asInt

        # Get P1 reading
        p1 = scenario.p1.reading(solar_w, device_contribution)

        # Run manager decision (sets device flows)
        manager.power_changed(p1, sim_time)

        # Record row: SOC at START of step, flows DURING this step
        state_name = (
            manager.operation_state.name
            if hasattr(manager.operation_state, "name")
            else str(manager.operation_state)
        )
        total_charge = sum(d.batteryInput.asInt for d in scenario.devices)
        total_discharge = sum(d.batteryOutput.asInt for d in scenario.devices)

        dev_rows = [
            DeviceRow(
                name=d.name,
                soc=d.soc,
                battery_input=d.batteryInput.asInt,
                battery_output=d.batteryOutput.asInt,
                home_input=d.homeInput.asInt,
                home_output=d.homeOutput.asInt,
            )
            for d in scenario.devices
        ]

        rows.append(
            SimRow(
                time=sim_time,
                p1=p1,
                solar=solar_w,
                charge_power=total_charge,
                discharge_power=total_discharge,
                manager_state=state_name,
                devices=dev_rows,
            )
        )

        # Advance SOC using the flows just set (becomes next step's starting SOC)
        for d in scenario.devices:
            d.advance(scenario.step_seconds)

    return rows


def main() -> None:
    args = parse_args()

    if args.list_scenarios:
        print("Available scenarios:\n")
        for name, factory in SCENARIOS.items():
            s = factory()
            print(f"  {name:15s}  {s.description}")
        print()
        return

    # Set up logging
    if args.verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

    # Build scenario and run
    scenario = build_scenario(args)
    mode = ManagerMode[args.mode.upper()]
    rows = run_simulation(scenario, mode, verbose=args.verbose)

    # Print terminal table
    print(format_table(rows))

    # Export CSV if requested
    if args.csv:
        with Path(args.csv).open("w") as f:
            f.write(rows_to_csv(rows))
        print(f"\nCSV exported to: {args.csv}")

    # Generate charts if requested
    if args.charts is not None:
        path = generate_charts(rows, args.charts)
        if path:
            print(f"Chart saved to: {path}")
        else:
            print("matplotlib not installed. Install with: pip install matplotlib")

    print(f"\nSimulation complete: {len(rows)} steps over {scenario.duration_hours}h")


if __name__ == "__main__":
    main()
