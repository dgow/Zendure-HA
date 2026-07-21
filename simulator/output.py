"""Terminal table and chart output for ZendureManager simulation."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SimRow:
    """One row of simulation output."""

    time: datetime
    p1: int
    solar: float
    charge_power: int = 0
    discharge_power: int = 0
    manager_state: str = "IDLE"
    devices: list[DeviceRow] = field(default_factory=list)


@dataclass
class DeviceRow:
    """Per-device state in one simulation row."""

    name: str
    soc: float
    battery_input: int = 0
    battery_output: int = 0
    home_input: int = 0
    home_output: int = 0


def format_table(rows: list[SimRow]) -> str:
    """Format simulation results as an ASCII table."""
    if not rows:
        return "No data."

    # Header
    header = f"{'Time':>8}  {'P1':>7}  {'Solar':>7}  {'State':>10}"
    dev_headers = ""
    if rows[0].devices:
        for d in rows[0].devices:
            short = d.name[:12]
            dev_headers += f"  {short:>12}"
    dev_headers += f"  {'Charge':>8}  {'Discharge':>10}"

    sep = "-" * len(header + dev_headers)

    lines = [sep, header + dev_headers, sep]

    prev_state = None
    for row in rows:
        time_str = row.time.strftime("%H:%M")
        state_str = row.manager_state.ljust(10)

        dev_soc = ""
        for d in row.devices:
            dev_soc += f"  {d.soc:>10.1f}%"

        charge = row.charge_power
        discharge = row.discharge_power

        line = (
            f"{time_str:>8}  {row.p1:>+7d}  {row.solar:>7.0f}"
            f"  {state_str}{dev_soc}  {charge:>+8d}  {discharge:>+10d}"
        )
        lines.append(line)

        # Blank line on state change
        if prev_state is not None and prev_state != row.manager_state:
            lines.append(sep)
        prev_state = row.manager_state

    lines.append(sep)
    return "\n".join(lines)


def rows_to_csv(rows: list[SimRow]) -> str:
    """Export simulation rows to CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    header = ["time", "p1_watts", "solar_watts", "manager_state"]
    for row in rows:
        for d in row.devices:
            header.extend(
                [f"{d.name}_soc", f"{d.name}_charge_w", f"{d.name}_discharge_w"]
            )
        break  # Only need one device header set
    header.extend(["total_charge_w", "total_discharge_w"])
    writer.writerow(header)

    for row in rows:
        state_name = row.manager_state
        line = [row.time.strftime("%H:%M:%S"), row.p1, f"{row.solar:.0f}", state_name]
        for d in row.devices:
            line.extend([f"{d.soc:.1f}", d.battery_input, d.battery_output])
        line.extend([row.charge_power, row.discharge_power])
        writer.writerow(line)

    return buf.getvalue()


def generate_charts(rows: list[SimRow], output_path: str | None = None) -> str | None:
    """
    Generate matplotlib charts from simulation data.

    Returns the output file path, or None if matplotlib is not available.
    """
    try:
        import matplotlib as mpl

        mpl.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    if not rows:
        return None

    times = [r.time for r in rows]
    p1_values = [r.p1 for r in rows]
    solar_values = [r.solar for r in rows]
    charge_values = [r.charge_power for r in rows]
    discharge_values = [r.discharge_power for r in rows]

    # Collect per-device SOC
    device_socs: dict[str, list[float]] = {}
    for row in rows:
        for d in row.devices:
            device_socs.setdefault(d.name, []).append(d.soc)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    fig.suptitle("ZendureManager Simulation", fontsize=14)

    # Plot 1: P1 meter and solar
    ax1 = axes[0]
    ax1.plot(times, p1_values, label="P1 Grid Power", color="steelblue", linewidth=1.5)
    ax1.plot(
        times, solar_values, label="Solar Production", color="orange", linewidth=1.5
    )
    ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
    ax1.set_ylabel("Power (W)")
    ax1.legend(loc="upper right")
    ax1.set_title("Grid Power (P1) & Solar Production")
    ax1.grid(True, alpha=0.3)

    # Plot 2: Device SOC
    ax2 = axes[1]
    for name, socs in device_socs.items():
        ax2.plot(times, socs, label=f"{name} SOC", linewidth=1.5)
    ax2.set_ylabel("SOC (%)")
    ax2.set_ylim(0, 105)
    ax2.legend(loc="upper right")
    ax2.set_title("Battery State of Charge")
    ax2.grid(True, alpha=0.3)

    # Plot 3: Charge/Discharge power
    ax3 = axes[2]
    ax3.fill_between(
        times, charge_values, 0, alpha=0.4, color="green", label="Charging"
    )
    ax3.fill_between(
        times, discharge_values, 0, alpha=0.4, color="red", label="Discharging"
    )
    ax3.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
    ax3.set_ylabel("Power (W)")
    ax3.set_xlabel("Time")
    ax3.legend(loc="upper right")
    ax3.set_title("Device Power Distribution")
    ax3.grid(True, alpha=0.3)

    # Format x-axis
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.xticks(rotation=45)

    plt.tight_layout()

    if output_path is None:
        output_path = "simulation.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return output_path
