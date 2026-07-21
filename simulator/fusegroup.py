"""
Simplified FuseGroup for the simulator.

Faithfully recreates fusegroup.py without HA dependencies.
The key logic: charge_limit and discharge_limit distribute power
proportionally by SOC across devices sharing a circuit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SimDevice


class FuseGroup:
    """Fuse group that distributes power limits across devices."""

    def __init__(
        self,
        name: str,
        maxpower: int,
        minpower: int,
        devices: list[SimDevice] | None = None,
    ) -> None:
        self.name = name
        self.maxpower = maxpower
        self.minpower = minpower
        self.init_power = True
        self.devices: list[SimDevice] = devices if devices is not None else []

    def charge_limit(self, d: SimDevice) -> int:
        """Return the charge power limit for a device."""
        if self.init_power:
            self.init_power = False
            if len(self.devices) == 1:
                d.pwr_max = max(self.minpower, d.charge_limit)
            else:
                limit = 0
                weight = 0
                for fd in self.devices:
                    if fd.homeInput.asInt > 0:
                        limit += fd.charge_limit
                        weight += (100 - fd.electricLevel.asInt) * fd.charge_limit
                avail = max(self.minpower, limit)
                for fd in self.devices:
                    if fd.homeInput.asInt > 0:
                        fd.pwr_max = (
                            int(
                                avail
                                * ((100 - fd.electricLevel.asInt) * fd.charge_limit)
                                / weight
                            )
                            if weight < 0
                            else fd.charge_start
                        )
                        limit -= fd.charge_limit
                        if limit > avail - fd.pwr_max:
                            fd.pwr_max = max(avail - limit, avail)
                        fd.pwr_max = max(fd.pwr_max, fd.charge_limit)
                        avail -= fd.pwr_max

        return d.pwr_max

    def discharge_limit(self, d: SimDevice) -> int:
        """Return the discharge power limit for a device."""
        if self.init_power:
            self.init_power = False
            if len(self.devices) == 1:
                d.pwr_max = min(self.maxpower, d.discharge_limit)
            else:
                limit = 0
                weight = 0
                for fd in self.devices:
                    if fd.homeOutput.asInt > 0:
                        limit += fd.discharge_limit
                        weight += fd.electricLevel.asInt * fd.discharge_limit
                avail = min(self.maxpower, limit)
                for fd in self.devices:
                    if fd.homeOutput.asInt > 0:
                        fd.pwr_max = (
                            int(
                                avail
                                * (fd.electricLevel.asInt * fd.discharge_limit)
                                / weight
                            )
                            if weight > 0
                            else fd.discharge_start
                        )
                        limit -= fd.discharge_limit
                        if limit < avail - fd.pwr_max:
                            fd.pwr_max = min(avail - limit, avail)
                        fd.pwr_max = min(fd.pwr_max, fd.discharge_limit)
                        avail -= fd.pwr_max

        return d.pwr_max
