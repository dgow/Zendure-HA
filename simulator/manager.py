"""
Standalone ZendureManager power distribution engine.

Faithfully recreates the core algorithm from manager.py:421-640
without any Home Assistant dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .const import DeviceState, ManagerMode, ManagerState, SmartMode
from .fusegroup import FuseGroup
from .models import SimDevice

_HYSTERESIS_THRESHOLD = 300

_LOGGER = logging.getLogger(__name__)


class SimManager:
    """
    Standalone ZendureManager power distribution engine.

    Handles P1 meter input, device classification, and weighted
    charge/discharge distribution.
    """

    def __init__(
        self,
        devices: list[SimDevice],
        mode: ManagerMode = ManagerMode.MATCHING,
    ) -> None:
        self.devices = devices
        self.operation = mode

        # Partition lists (rebuilt each cycle)
        self.charge: list[SimDevice] = []
        self.charge_limit = 0
        self.charge_optimal = 0
        self.charge_weight = 0

        self.discharge: list[SimDevice] = []
        self.discharge_bypass = 0
        self.discharge_produced = 0
        self.discharge_limit = 0
        self.discharge_optimal = 0
        self.discharge_weight = 0

        self.idle: list[SimDevice] = []
        self.idle_lvlmax = 0
        self.idle_lvlmin = 0

        self.produced = 0
        self.pwr_low = 0

        # Hysteresis state
        self.charge_time = datetime.max
        self.charge_last = datetime.min

        # Manual power setpoint
        self.manual_power = 0

        # Aggregate sensors
        self.power = 0
        self.available_kwh = 0.0
        self.global_soc = 0.0
        self.operation_state = ManagerState.OFF

        # Fuse group setup: each device gets its own group
        for d in devices:
            d.fuse_grp = FuseGroup(d.name, d.discharge_limit, d.charge_limit, [d])

    def power_changed(self, p1: int, sim_time: datetime) -> None:
        """Core power distribution — mirrors manager.py:421-511."""
        available_kwh = 0.0
        setpoint = p1
        power = 0
        total_stored_kwh = 0.0
        online_kwh = 0.0

        # Reset partitions
        self.charge = []
        self.charge_limit = 0
        self.charge_optimal = 0
        self.charge_weight = 0

        self.discharge = []
        self.discharge_bypass = 0
        self.discharge_produced = 0
        self.discharge_limit = 0
        self.discharge_optimal = 0
        self.discharge_weight = 0

        self.idle = []
        self.idle_lvlmax = 0
        self.idle_lvlmin = 0
        self.produced = 0

        # Classify each device
        for d in self.devices:
            if d.power_get():
                # Calculate power production
                d.pwr_produced = min(
                    0,
                    d.batteryOutput.asInt
                    + d.homeInput.asInt
                    - d.batteryInput.asInt
                    - d.homeOutput.asInt,
                )
                self.produced -= d.pwr_produced

                # home = -homeInput + max(0, offgrid)
                home = -d.homeInput.asInt + max(0, d.pwr_offgrid)
                if home < 0:
                    # Charging — device is consuming grid power
                    self.charge.append(d)
                    self.charge_limit += d.fuse_grp.charge_limit(d)
                    self.charge_optimal += d.charge_optimal
                    self.charge_weight += d.pwr_max * (100 - d.electricLevel.asInt)
                    setpoint -= min(d.homeInput.asInt, d.batteryInput.asInt)
                elif (home := d.homeOutput.asInt) > 0:
                    # Discharging — device is feeding the home
                    self.discharge.append(d)
                    if d.state == DeviceState.SOCFULL and d.exports_bypass:
                        self.discharge_bypass += min(-d.pwr_produced, home)
                    self.discharge_limit += d.fuse_grp.discharge_limit(d)
                    self.discharge_optimal += d.discharge_optimal
                    self.discharge_produced -= d.pwr_produced
                    self.discharge_weight += d.pwr_max * d.electricLevel.asInt
                    setpoint += home
                else:
                    # Idle
                    self.idle.append(d)
                    self.idle_lvlmax = max(self.idle_lvlmax, d.electricLevel.asInt)
                    self.idle_lvlmin = min(
                        self.idle_lvlmin,
                        d.electricLevel.asInt
                        if d.state != DeviceState.SOCFULL
                        else 100,
                    )

                available_kwh += d.actualKwh
                power += d.pwr_offgrid + home + d.pwr_produced
                total_stored_kwh += d.electricLevel.asNumber / 100 * d.kWh
                online_kwh += d.kWh

        # Update aggregate sensors
        self.power = power
        self.available_kwh = available_kwh
        self.global_soc = (total_stored_kwh / online_kwh * 100) if online_kwh > 0 else 0

        # Remove non-dispatchable bypass production
        setpoint -= self.discharge_bypass

        _LOGGER.debug(
            "P1 => p1:%d setpoint:%dW charge:%d discharge:%d idle:%d produced:%d",
            p1,
            setpoint,
            len(self.charge),
            len(self.discharge),
            len(self.idle),
            self.produced,
        )

        # Mode dispatch
        match self.operation:
            case ManagerMode.MATCHING:
                if setpoint < 0:
                    self._power_charge(setpoint, sim_time)
                else:
                    self._power_discharge(setpoint)

            case ManagerMode.MATCHING_DISCHARGE:
                self._power_discharge(max(0, setpoint))

            case ManagerMode.MATCHING_CHARGE | ManagerMode.STORE_SOLAR:
                if (
                    setpoint > 0
                    and self.produced > SmartMode.POWER_START
                    and self.operation == ManagerMode.MATCHING_CHARGE
                ):
                    self._power_discharge(min(self.produced, setpoint))
                else:
                    self._power_charge(min(0, setpoint), sim_time)

            case ManagerMode.MANUAL:
                if self.manual_power > 0:
                    self._power_discharge(self.manual_power)
                else:
                    self._power_charge(self.manual_power, sim_time)

            case ManagerMode.OFF:
                self.operation_state = ManagerState.OFF

    def _power_charge(self, setpoint: int, sim_time: datetime) -> None:
        """Charge devices — mirrors manager.py:513-577."""
        _LOGGER.debug("Charge => setpoint %dW", setpoint)

        # Stop discharging devices
        for d in self.discharge:
            if d.byPass.asInt > 0:
                continue
            d.power_discharge(0 if d.pwr_offgrid == 0 else -10)

        # Prevent hysteresis
        if self.charge_time > sim_time:
            if self.charge_time == datetime.max:
                self.charge_time = sim_time + timedelta(
                    seconds=2
                    if (sim_time - self.charge_last).total_seconds()
                    > _HYSTERESIS_THRESHOLD
                    else 60
                )
                self.charge_last = self.charge_time
                self.pwr_low = 0
            setpoint = 0

        self.operation_state = (
            ManagerState.CHARGE if setpoint < 0 else ManagerState.IDLE
        )

        # Distribute charge power
        dev_start = (
            min(0, setpoint - self.charge_optimal * 2)
            if setpoint < -SmartMode.POWER_START
            else 0
        )
        limit = self.charge_limit
        setpoint = max(limit, setpoint)

        for i, d in enumerate(
            sorted(self.charge, key=lambda d: d.electricLevel.asInt, reverse=True)
        ):
            device_weight = d.pwr_max * (100 - d.electricLevel.asInt)
            if self.charge_weight != 0:
                pwr = int(setpoint * device_weight / self.charge_weight)
            else:
                pwr = 0
            self.charge_weight -= device_weight

            # Adjust limit
            limit -= d.pwr_max
            pwr = max(pwr, setpoint, d.pwr_max)
            if limit > setpoint - pwr:
                pwr = max(setpoint - limit, setpoint, d.pwr_max)

            # Optimal working range
            if len(self.charge) > 1 and i == 0:
                self.pwr_low = (
                    0
                    if (delta := d.charge_start * 1.5 - pwr) >= 0
                    else self.pwr_low + int(-delta)
                )
                pwr = 0 if self.pwr_low < d.charge_optimal else pwr

            actual = d.power_charge(pwr)
            setpoint -= actual
            dev_start += (
                -1 if pwr != 0 and d.electricLevel.asInt > self.idle_lvlmin + 3 else 0
            )

        # Start idle devices if needed
        if dev_start < 0 and len(self.idle) > 0:
            self.idle.sort(key=lambda d: d.electricLevel.asInt, reverse=False)
            for d in self.idle:
                start_pwr = SmartMode.POWER_START
                d.power_charge(
                    -start_pwr - max(0, d.pwr_offgrid)
                    if d.state != DeviceState.SOCFULL
                    else -max(0, d.pwr_offgrid)
                )
                if (dev_start := dev_start - d.charge_optimal * 2) >= 0:
                    break
            self.pwr_low = 0

    def _power_discharge(self, setpoint: int) -> None:
        """Discharge devices — mirrors manager.py:579-640."""
        _LOGGER.debug("Discharge => setpoint %dW", setpoint)
        self.operation_state = (
            ManagerState.DISCHARGE
            if setpoint > 0 and self.discharge
            else ManagerState.IDLE
        )

        # Reset hysteresis
        if self.charge_time != datetime.max:
            self.charge_time = datetime.max
            self.pwr_low = 0

        # Stop charging devices
        for d in self.charge:
            d.power_discharge(0 if max(0, d.pwr_offgrid) == 0 else 10)

        # Distribute discharge power
        dev_start = (
            max(0, setpoint - self.discharge_optimal * 2 - self.discharge_produced)
            if setpoint > SmartMode.POWER_START
            else 0
        )
        solaronly = self.discharge_produced >= setpoint
        limit = self.discharge_produced if solaronly else self.discharge_limit
        setpoint = min(limit, setpoint)

        for i, d in enumerate(
            sorted(self.discharge, key=lambda d: d.electricLevel.asInt, reverse=False)
        ):
            device_weight = d.pwr_max * d.electricLevel.asInt
            if self.discharge_weight != 0:
                pwr = int(setpoint * device_weight / self.discharge_weight)
            elif len(self.discharge) > i:
                pwr = int(setpoint / (len(self.discharge) - i))
            else:
                pwr = 0

            if pwr < -d.pwr_produced and d.state == DeviceState.SOCFULL:
                pwr = -d.pwr_produced
            self.discharge_weight -= device_weight

            # Adjust limit
            limit -= -d.pwr_produced if solaronly else d.pwr_max
            if limit < setpoint - pwr:
                pwr = max(
                    setpoint - limit,
                    0 if d.state != DeviceState.SOCFULL else -d.pwr_produced,
                )
            pwr = min(pwr, setpoint, d.pwr_max)

            # Optimal working range
            if len(self.discharge) > 1 and i == 0 and d.state != DeviceState.SOCFULL:
                self.pwr_low = (
                    0
                    if (delta := d.discharge_start * 1.5 - pwr) <= 0
                    else self.pwr_low + int(delta)
                )
                pwr = 0 if self.pwr_low > d.discharge_optimal else pwr

            actual = d.power_discharge(pwr)
            setpoint -= actual
            dev_start += (
                1 if pwr != 0 and d.electricLevel.asInt + 3 < self.idle_lvlmax else 0
            )

        # Start idle devices if needed
        if dev_start > 0 and len(self.idle) > 0:
            self.idle.sort(key=lambda d: d.electricLevel.asInt, reverse=True)
            for d in self.idle:
                if d.state != DeviceState.SOCEMPTY:
                    d.power_discharge(SmartMode.POWER_START)
                    if (dev_start := dev_start - d.discharge_optimal * 2) <= 0:
                        break
            self.pwr_low = 0
