"""Predefined simulation scenarios for ZendureManager testing."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SimDevice, SimP1Meter, SimSolarPanel


@dataclass
class Scenario:
    """A complete simulation scenario configuration."""

    name: str
    description: str
    duration_hours: float
    step_seconds: float
    solar: SimSolarPanel
    p1: SimP1Meter
    devices: list[SimDevice]


def sunny() -> Scenario:
    """Classic sunny day: smooth solar curve, moderate household load."""
    return Scenario(
        name="sunny",
        description=(
            "Clear sunny day with moderate household load (300W)."
            " Solar peaks at 800W around noon."
        ),
        duration_hours=14,
        step_seconds=300,
        solar=SimSolarPanel(peak_watts=800, sunrise_hour=6.0, sunset_hour=20.0),
        p1=SimP1Meter(household_load=300),
        devices=[
            SimDevice(
                name="SolarFlow 800",
                device_id="sf800_001",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                max_solar=1200,
                initial_soc=50,
            ),
        ],
    )


def cloudy() -> Scenario:
    """Cloudy day with intermittent clouds reducing solar output."""
    return Scenario(
        name="cloudy",
        description="Cloudy day with passing clouds. Solar fluctuates 200-600W.",
        duration_hours=14,
        step_seconds=300,
        solar=SimSolarPanel(
            peak_watts=600,
            sunrise_hour=7.0,
            sunset_hour=19.0,
            clouds=[
                (9.0, 10.0, 0.3),  # Heavy cloud 9-10am
                (11.5, 12.5, 0.5),  # Medium cloud midday
                (14.0, 15.0, 0.2),  # Heavy cloud 2-3pm
                (16.0, 17.0, 0.6),  # Light cloud 4-5pm
            ],
        ),
        p1=SimP1Meter(household_load=400),
        devices=[
            SimDevice(
                name="SolarFlow 800",
                device_id="sf800_002",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                max_solar=1200,
                initial_soc=30,
            ),
        ],
    )


def evening() -> Scenario:
    """Evening scenario: solar drops, household load spikes."""
    return Scenario(
        name="evening",
        description=(
            "Afternoon into evening. Solar drops while load spikes."
        ),
        duration_hours=8,
        step_seconds=300,
        solar=SimSolarPanel(
            peak_watts=400,
            sunrise_hour=10.0,
            sunset_hour=20.0,
        ),
        p1=SimP1Meter(household_load=300),
        devices=[
            SimDevice(
                name="SolarFlow 800",
                device_id="sf800_003",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                max_solar=1200,
                initial_soc=85,
            ),
        ],
    )


def multi_device() -> Scenario:
    """Two devices with different SOC levels on the same fuse group."""
    return Scenario(
        name="multi_device",
        description=(
            "Two SolarFlow 800 devices at different SOC levels."
            " Tests weighted distribution."
        ),
        duration_hours=10,
        step_seconds=300,
        solar=SimSolarPanel(peak_watts=800, sunrise_hour=7.0, sunset_hour=19.0),
        p1=SimP1Meter(household_load=500),
        devices=[
            SimDevice(
                name="SF800-Unit1",
                device_id="sf800_a",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                max_solar=1200,
                initial_soc=30,
            ),
            SimDevice(
                name="SF800-Unit2",
                device_id="sf800_b",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                max_solar=1200,
                initial_soc=70,
            ),
        ],
    )


def minimal() -> Scenario:
    """Minimal test: single device, flat solar, quick run."""
    return Scenario(
        name="minimal",
        description="Quick test: 500W constant solar, 200W load, 1 hour.",
        duration_hours=1,
        step_seconds=60,
        solar=SimSolarPanel(peak_watts=500, sunrise_hour=0, sunset_hour=24),
        p1=SimP1Meter(household_load=200),
        devices=[
            SimDevice(
                name="TestDevice",
                device_id="test_001",
                kWh=1.0,
                charge_limit=-1000,
                discharge_limit=800,
                initial_soc=50,
            ),
        ],
    )


SCENARIOS: dict[str, callable] = {
    "sunny": sunny,
    "cloudy": cloudy,
    "evening": evening,
    "multi_device": multi_device,
    "minimal": minimal,
}


def get_scenario(name: str) -> Scenario:
    """Get a scenario by name."""
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"Unknown scenario '{name}'. Available: {available}")
    return SCENARIOS[name]()
