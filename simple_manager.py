#!/usr/bin/env python3
"""
Zendure SolarFlow 800 Pro2 — simple manager.

Reads the P1 meter value (grid import/export) from the command line and sets
the device output power to cover your home demand.

Usage:
  ./simple_manager.py --p1 <watts>
  ./simple_manager.py --p1 450     # Grid importing 450W → device covers it
  ./simple_manager.py --p1 0       # Grid balanced → stop discharging

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


def read_device() -> dict:
    r = requests.get(f"http://{IP}/properties/report", timeout=5)
    return r.json()


def write_properties(props: dict) -> None:
    payload = {"sn": SN, "id": 1, "properties": props}
    requests.post(f"http://{IP}/properties/write", json=payload, timeout=5)


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--p1":
        print(f"Usage: {sys.argv[0]} --p1 <watts>")
        sys.exit(1)

    p1 = int(sys.argv[2])

    before = read_device()
    p = before.get("properties", {})
    print(f"Before  — battery: {p.get('electricLevel', '?')}%  "
          f"solar: {p.get('solarInputPower', '?')}W  "
          f"home: {p.get('outputHomePower', '?')}W  "
          f"outputLimit: {p.get('outputLimit', '?')}W  "
          f"socSet: {p.get('socSet', '?')}")

    if p1 > 0:
        limit = min(p1, 800)
        write_properties({
            "smartMode": 1,
            "acMode": 2,
            "outputLimit": limit,
            "inputLimit": 0,
            "socSet": 400,
        })
        print(f"P1={p1}W → outputLimit={limit}W, socSet=400 (discharging)")
    else:
        write_properties({
            "smartMode": 1,
            "acMode": 2,
            "outputLimit": 0,
            "inputLimit": 0,
            "socSet": 400,
        })
        print(f"P1={p1}W → outputLimit=0, socSet=400 (stopped, solar bypass)")

    time.sleep(3)
    after = read_device()
    p2 = after.get("properties", {})
    print(f"After   — battery: {p2.get('electricLevel', '?')}%  "
          f"solar: {p2.get('solarInputPower', '?')}W  "
          f"home: {p2.get('outputHomePower', '?')}W  "
          f"outputLimit: {p2.get('outputLimit', '?')}W  "
          f"socSet: {p2.get('socSet', '?')}")


if __name__ == "__main__":
    main()
