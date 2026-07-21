"""Simulated devices, solar panels, and P1 meter for ZendureManager simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .const import DeviceState, SmartMode


class SimSensor:
    """Lightweight sensor that mimics ZendureSensor.asInt / .asNumber."""

    def __init__(self, value: float = 0, factor: float = 1) -> None:
        self._value: float = value
        self.factor = factor

    @property
    def asInt(self) -> int:
        return int(self._value / self.factor) if self.factor != 1 else int(self._value)

    @property
    def asNumber(self) -> float:
        return self._value / self.factor if self.factor != 1 else self._value

    def update(self, value: float) -> None:
        self._value = value


@dataclass
class SimDevice:
    """
    Simulated Zendure power station.

    Tracks SOC, charge/discharge behavior, and power state.
    Interface matches the properties the manager reads from real devices.
    """

    name: str
    device_id: str
    kWh: float = 1.0
    charge_limit: int = -1200
    discharge_limit: int = 1200
    max_solar: int = -1200
    initial_soc: float = 50.0
    min_soc: float = 0
    soc_set: float = 100.0

    # Internal state
    soc: float = field(init=False)
    online: bool = True
    exports_bypass: bool = False
    by_pass: int = 0

    # Current power flows (watts)
    _home_input: float = field(default=0, init=False)
    _home_output: float = field(default=0, init=False)
    _battery_input: float = field(default=0, init=False)
    _battery_output: float = field(default=0, init=False)
    _solar_input: float = field(default=0, init=False)

    # Derived thresholds
    charge_optimal: int = field(init=False)
    discharge_optimal: int = field(init=False)
    charge_start: int = field(init=False)
    discharge_start: int = field(init=False)

    # Power distribution state (set by manager/fusegroup each cycle)
    pwr_max: int = field(default=0, init=False)
    pwr_produced: int = field(default=0, init=False)

    # Fuse group (set externally)
    fuse_grp: object = None

    # Simulation tracking
    aggr_charge_kwh: float = field(default=0, init=False)
    aggr_discharge_kwh: float = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Initialize derived thresholds from device limits."""
        self.soc = self.initial_soc
        self.charge_optimal = max(1, abs(self.charge_limit) // 4)
        self.discharge_optimal = max(1, self.discharge_limit // 4)
        self.charge_start = max(1, abs(self.charge_limit) // 10)
        self.discharge_start = max(1, self.discharge_limit // 10)
        self.pwr_max = self.discharge_limit

    # --- Sensor-like properties the manager reads ---

    @property
    def electricLevel(self) -> SimSensor:
        return SimSensor(self.soc)

    @property
    def homeInput(self) -> SimSensor:
        return SimSensor(self._home_input)

    @property
    def homeOutput(self) -> SimSensor:
        return SimSensor(self._home_output)

    @property
    def batteryInput(self) -> SimSensor:
        return SimSensor(self._battery_input)

    @property
    def batteryOutput(self) -> SimSensor:
        return SimSensor(self._battery_output)

    @property
    def solarInput(self) -> SimSensor:
        return SimSensor(self._solar_input)

    @property
    def byPass(self) -> SimSensor:
        return SimSensor(self.by_pass)

    @property
    def pwr_offgrid(self) -> int:
        return 0

    @property
    def actualKwh(self) -> float:
        return max(0, (self.soc - self.min_soc) / 100 * self.kWh)

    # --- State determination (mirrors device.py:620-636) ---

    @property
    def state(self) -> DeviceState:
        if not self.online or self.kWh <= 0:
            return DeviceState.OFFLINE
        if self.soc >= self.soc_set:
            return DeviceState.SOCFULL
        if self.soc <= self.min_soc:
            return DeviceState.SOCEMPTY
        return DeviceState.INACTIVE

    # --- Power commands (mirrors device.py:642-661) ---

    def power_get(self) -> bool:
        return self.online

    def power_charge(self, pwr: int) -> int:
        """Charge the device. Returns actual power set (negative = charging)."""
        if not self.online:
            return 0
        pwr = max(self.charge_limit, min(0, pwr))
        if (
            abs(pwr) < SmartMode.POWER_TOLERANCE
            and abs(self._battery_input) < SmartMode.POWER_TOLERANCE
        ):
            return 0

        # Simulate charging: convert power to SOC increase
        # pwr is negative (charging), so energy added = -pwr * dt / 3600
        # We simulate per-step, dt is handled in the simulation loop
        self._battery_input = abs(pwr)
        self._battery_output = 0
        self._home_input = abs(pwr)
        self._home_output = 0
        return pwr

    def power_discharge(self, pwr: int) -> int:
        """Discharge the device. Returns actual power set (positive = discharging)."""
        if not self.online:
            return 0
        pwr = max(0, min(self.discharge_limit, pwr))
        if (
            pwr < SmartMode.POWER_TOLERANCE
            and self._battery_output < SmartMode.POWER_TOLERANCE
        ):
            return 0

        self._battery_output = pwr
        self._battery_input = 0
        self._home_output = pwr
        self._home_input = 0
        return pwr

    def power_off(self) -> None:
        self._home_input = 0
        self._home_output = 0
        self._battery_input = 0
        self._battery_output = 0

    def advance(self, step_seconds: float) -> None:
        """Advance SOC based on current power flows and step duration."""
        # battery flows are in watts, step_seconds is duration
        # kWh is in kilowatt-hours, so multiply by 1000 to get watt-hours
        battery_capacity_wh = self.kWh * 1000

        # Charge energy: battery_input * dt hours
        charge_wh = self._battery_input * (step_seconds / 3600)
        self.soc = min(100, self.soc + (charge_wh / battery_capacity_wh) * 100)
        self.aggr_charge_kwh += charge_wh / 1000

        # Discharge energy: battery_output * dt hours
        discharge_wh = self._battery_output * (step_seconds / 3600)
        self.soc = max(0, self.soc - (discharge_wh / battery_capacity_wh) * 100)
        self.aggr_discharge_kwh += discharge_wh / 1000

    def reset_flows(self) -> None:
        self._home_input = 0
        self._home_output = 0
        self._battery_input = 0
        self._battery_output = 0


@dataclass
class SimSolarPanel:
    """Simulates a solar panel array with a bell-curve production pattern."""

    peak_watts: float = 800
    sunrise_hour: float = 6.0
    sunset_hour: float = 20.0
    clouds: list[tuple[float, float, float]] = field(default_factory=list)

    def production(self, hour_of_day: float) -> float:
        """Return solar production in watts for the given hour (0-24)."""
        if hour_of_day < self.sunrise_hour or hour_of_day > self.sunset_hour:
            return 0
        midday = (self.sunrise_hour + self.sunset_hour) / 2
        span = (self.sunset_hour - self.sunrise_hour) / 2
        x = (hour_of_day - midday) / span
        base = max(0, self.peak_watts * (1 - x**2))
        # Apply cloud遮挡
        for start, end, factor in self.clouds:
            if start <= hour_of_day <= end:
                base *= factor
        return base


@dataclass
class SimP1Meter:
    """
    Simulates P1 smart meter readings.

    The P1 meter reports net grid power:
      positive = grid import (home consuming more than producing)
      negative = grid export (home producing more than consuming)
    """

    household_load: float = 300.0  # Base household consumption in watts

    def reading(self, solar_watts: float, device_contribution: float = 0) -> int:
        """
        Compute P1 reading: load - solar - device discharge.

        Args:
            solar_watts: Current solar production.
            device_contribution: Net device output to home
                (positive = discharging to home).

        Returns:
            Net grid power in watts (positive = import).

        """
        return int(
            self.household_load - solar_watts - device_contribution
        )
