#!/usr/bin/env python3
"""
Zendure SolarFlow 800 Pro2 — simple manager.

Reads the P1 meter value (grid import/export) from the command line and sets
the device output power to cover your home demand.

Usage:
  ./simple_manager.py --p1 <watts>    # Manual P1 value
  ./simple_manager.py --p1 450        # Grid importing 450W → device covers it
  ./simple_manager.py --p1 0          # Grid balanced → stop discharging
  ./simple_manager.py --shelly        # Read Shelly + outputHomePower, set output to match

Reference:
  outputLimit : RW  W      0-800     Output/discharge power limit (1x)
  inputLimit  : RW  W      0-1000    AC charge power limit (1x)
  acMode      : RW  int    1-2       1=charge(input), 2=discharge(output)
  smartMode   : RW  int    0-1       Flash persistence: 1 = don't save
  socSet      : RW  0.1%   0-1000    Target SoC (10x scaling: 400 = 40.0%)
  minSoc      : RW  0.1%   0-1000    Min SoC (10x scaling)

  Scaling rule: percentages use 10x (1000 = 100.0%), power uses 1x (800 = 800W).
"""

import sys
import time

import requests

IP = "192.168.77.111"
SN = "EOD1NLN9P125626"
SHELLY_IP = "192.168.55.10"


def read_device() -> dict:
    r = requests.get(f"http://{IP}/properties/report", timeout=5)
    return r.json()


def write_properties(props: dict) -> None:
    payload = {"sn": SN, "id": 1, "properties": props}
    requests.post(f"http://{IP}/properties/write", json=payload, timeout=5)


def get_p1_shelly() -> int:
    r = requests.get(f"http://{SHELLY_IP}/rpc/EM.GetStatus?id=0", timeout=5)
    return int(r.json()["total_act_power"])


def show(level, solar, home, out, label=""):
    print(f"  {label}Bat {level:3d}%  Solar {solar:4d}W  Home {home:4d}W  Limit {out:4d}W")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--shelly":
        shelly_p1 = get_p1_shelly()
        device = read_device()
        home_out = device.get("properties", {}).get("outputHomePower", 0)
        p1 = shelly_p1 + home_out
        print(f"\n>> Grid (Shelly): {shelly_p1:+d}W  |  Device output: {home_out:+d}W  =  Demand: {p1:+d}W\n")
    elif len(sys.argv) == 3 and sys.argv[1] == "--p1":
        p1 = int(sys.argv[2])
        print(f"\n>> Manual P1: {p1:+d}W\n")
    else:
        print(f"Usage: {sys.argv[0]} --p1 <watts>")
        print(f"       {sys.argv[0]} --shelly")
        sys.exit(1)

    before = read_device()
    p = before.get("properties", {})
    show(p.get("electricLevel", 0), p.get("solarInputPower", 0), p.get("outputHomePower", 0), p.get("outputLimit", 0), ">> ")

    p1 = min(p1, 850)

    if p1 > 0:
        write_properties({
            "smartMode": 1,
            "acMode": 2,
            "outputLimit": p1,
            "inputLimit": 0,
            "socSet": 940,
        })
        print(f"\n>> Discharge: outputLimit = {p1}W\n")
    else:
        write_properties({
            "smartMode": 1,
            "acMode": 2,
            "outputLimit": 0,
            "inputLimit": 0,
            "socSet": 400,
        })
        print("\n>> Stopped: outputLimit = 0\n")

    time.sleep(3)
    after = read_device()
    p2 = after.get("properties", {})
    show(p2.get("electricLevel", 0), p2.get("solarInputPower", 0), p2.get("outputHomePower", 0), p2.get("outputLimit", 0), "")


if __name__ == "__main__":
    main()
