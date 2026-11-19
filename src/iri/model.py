"""Core hourly water-energy model for IRI Engine v0.1.

This is a transparent screening model, not a detailed engineering design tool.
"""
from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd


@dataclass
class SystemConfig:
    pv_capacity_kw: float = 8.0
    pv_derate: float = 0.80
    pv_temp_coefficient_per_c: float = -0.004
    cell_temp_noct_c: float = 45.0
    reference_temp_c: float = 25.0

    battery_capacity_kwh: float = 20.0
    initial_soc: float = 0.80
    min_soc: float = 0.20
    max_soc: float = 0.95
    max_charge_kw: float = 5.0
    max_discharge_kw: float = 5.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95

    pump_flow_m3_per_hour: float = 12.0
    total_dynamic_head_m: float = 30.0
    pump_efficiency: float = 0.65
    water_demand_m3_per_hour: float = 8.0

    reservoir_capacity_m3: float = 80.0
    initial_reservoir_m3: float = 40.0
    grid_available: bool = False
    grid_energy_cost_per_kwh: float = 0.25
    timestep_hours: float = 1.0

    def validate(self) -> None:
        positive = {
            "pv_capacity_kw": self.pv_capacity_kw,
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "pump_flow_m3_per_hour": self.pump_flow_m3_per_hour,
            "total_dynamic_head_m": self.total_dynamic_head_m,
            "pump_efficiency": self.pump_efficiency,
            "reservoir_capacity_m3": self.reservoir_capacity_m3,
            "timestep_hours": self.timestep_hours,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be > 0")
        if not 0 < self.pump_efficiency <= 1:
            raise ValueError("pump_efficiency must be in (0, 1]")
        if not 0 < self.charge_efficiency <= 1 or not 0 < self.discharge_efficiency <= 1:
            raise ValueError("battery efficiencies must be in (0, 1]")
        if not 0 <= self.min_soc <= self.initial_soc <= self.max_soc <= 1:
            raise ValueError("SOC must satisfy 0 <= min < initial <= max <= 1")
        if self.initial_reservoir_m3 < 0 or self.initial_reservoir_m3 > self.reservoir_capacity_m3:
            raise ValueError("initial reservoir volume must be within reservoir bounds")
        if self.pv_derate <= 0:
            raise ValueError("pv_derate must be > 0")


def pv_power_kw(
    rated_kw: float,
    irradiance_w_m2: float,
    ambient_temp_c: float = 25.0,
    derate: float = 0.80,
    temp_coefficient_per_c: float = -0.004,
    noct_c: float = 45.0,
    reference_temp_c: float = 25.0,
) -> float:
    """Approximate PV output in kW using a NOCT-style cell temperature estimate."""
    if rated_kw < 0 or irradiance_w_m2 < 0:
        raise ValueError("rated power and irradiance must be non-negative")
    if irradiance_w_m2 == 0:
        return 0.0
    cell_temp = ambient_temp_c + ((noct_c - 20.0) / 800.0) * irradiance_w_m2
    temperature_factor = 1.0 + temp_coefficient_per_c * (cell_temp - reference_temp_c)
    return max(0.0, rated_kw * (irradiance_w_m2 / 1000.0) * derate * temperature_factor)


def pump_power_kw(
    flow_m3_per_hour: float,
    head_m: float,
    efficiency: float,
    water_density_kg_m3: float = 1000.0,
    gravity_m_s2: float = 9.80665,
) -> float:
    """Hydraulic pump input power in kW at the specified duty point."""
    if flow_m3_per_hour < 0 or head_m < 0:
        raise ValueError("flow and head must be non-negative")
    if not 0 < efficiency <= 1:
        raise ValueError("efficiency must be in (0, 1]")
    flow_m3_s = flow_m3_per_hour / 3600.0
    return water_density_kg_m3 * gravity_m_s2 * flow_m3_s * head_m / efficiency / 1000.0


def simulate_system(
    weather: pd.DataFrame,
    config: SystemConfig,
    demand_m3_per_hour: Iterable[float] | None = None,
    pump_available: Iterable[bool] | None = None,
) -> pd.DataFrame:
    """Simulate hourly system operation.

    Required weather columns: irradiance_w_m2 and ambient_temp_c.
    Dispatch priority: PV -> battery -> grid (if enabled). Pump flow is
    proportionally curtailed when available electrical power is insufficient.
    """
    config.validate()
    required = {"irradiance_w_m2", "ambient_temp_c"}
    missing = required.difference(weather.columns)
    if missing:
        raise ValueError(f"weather missing columns: {sorted(missing)}")
    n = len(weather)
    if n == 0:
        raise ValueError("weather must contain at least one timestep")

    demand = (
        np.full(n, config.water_demand_m3_per_hour, dtype=float)
        if demand_m3_per_hour is None
        else np.asarray(list(demand_m3_per_hour), dtype=float)
    )
    available = (
        np.ones(n, dtype=bool)
        if pump_available is None
        else np.asarray(list(pump_available), dtype=bool)
    )
    if len(demand) != n or len(available) != n:
        raise ValueError("demand and pump_available must match weather length")
    if np.any(demand < 0):
        raise ValueError("water demand cannot be negative")

    dt = config.timestep_hours
    soc = config.initial_soc
    reservoir = config.initial_reservoir_m3
    pump_kw_rated = pump_power_kw(
        config.pump_flow_m3_per_hour,
        config.total_dynamic_head_m,
        config.pump_efficiency,
    )

    rows = []
    for i, (_, wx) in enumerate(weather.iterrows()):
        pv_kw = pv_power_kw(
            config.pv_capacity_kw,
            float(wx["irradiance_w_m2"]),
            float(wx["ambient_temp_c"]),
            config.pv_derate,
            config.pv_temp_coefficient_per_c,
            config.cell_temp_noct_c,
            config.reference_temp_c,
        )
        target_pump_kw = pump_kw_rated if available[i] else 0.0
        pv_to_pump = min(pv_kw, target_pump_kw)
        remaining_pump_kw = max(0.0, target_pump_kw - pv_to_pump)

        battery_available_kw = min(
            config.max_discharge_kw,
            max(0.0, (soc - config.min_soc) * config.battery_capacity_kwh
                * config.discharge_efficiency / dt),
        )
        battery_to_pump = min(remaining_pump_kw, battery_available_kw)
        remaining_pump_kw -= battery_to_pump
        grid_to_pump = remaining_pump_kw if config.grid_available else 0.0
        supplied_kw = pv_to_pump + battery_to_pump + grid_to_pump
        pump_fraction = min(1.0, supplied_kw / pump_kw_rated) if pump_kw_rated > 0 else 0.0
        if not available[i]:
            pump_fraction = 0.0

        battery_energy_out = battery_to_pump * dt / config.discharge_efficiency
        soc -= battery_energy_out / config.battery_capacity_kwh
        soc = max(config.min_soc, soc)

        pv_surplus_kw = max(0.0, pv_kw - pv_to_pump)
        charge_headroom_kw = max(
            0.0,
            (config.max_soc - soc) * config.battery_capacity_kwh
            / (config.charge_efficiency * dt),
        )
        charge_kw = min(pv_surplus_kw, config.max_charge_kw, charge_headroom_kw)
        soc += charge_kw * dt * config.charge_efficiency / config.battery_capacity_kwh
        soc = min(config.max_soc, max(config.min_soc, soc))

        water_produced = config.pump_flow_m3_per_hour * pump_fraction * dt
        reservoir_before = reservoir
        available_water = reservoir + water_produced
        water_delivered = min(float(demand[i]), available_water)
        unmet_water = max(0.0, float(demand[i]) - water_delivered)
        reservoir = min(
            config.reservoir_capacity_m3,
            max(0.0, available_water - water_delivered),
        )
        overflow = max(0.0, available_water - water_delivered - config.reservoir_capacity_m3)

        grid_energy = grid_to_pump * dt
        rows.append({
            "timestep": i,
            "irradiance_w_m2": float(wx["irradiance_w_m2"]),
            "ambient_temp_c": float(wx["ambient_temp_c"]),
            "pv_generation_kw": pv_kw,
            "pump_available": bool(available[i]),
            "pump_power_required_kw": target_pump_kw,
            "pv_to_pump_kw": pv_to_pump,
            "battery_to_pump_kw": battery_to_pump,
            "grid_to_pump_kw": grid_to_pump,
            "battery_charge_kw": charge_kw,
            "battery_soc": soc,
            "pump_fraction": pump_fraction,
            "water_produced_m3": water_produced,
            "water_demand_m3": float(demand[i]),
            "water_delivered_m3": water_delivered,
            "unmet_water_m3": unmet_water,
            "reservoir_before_m3": reservoir_before,
            "reservoir_after_m3": reservoir,
            "reservoir_overflow_m3": overflow,
            "grid_energy_kwh": grid_energy,
            "grid_cost": grid_energy * config.grid_energy_cost_per_kwh,
        })
    return pd.DataFrame(rows)


def summarise_results(results: pd.DataFrame) -> dict:
    demand = float(results["water_demand_m3"].sum())
    unmet = float(results["unmet_water_m3"].sum())
    delivered = float(results["water_delivered_m3"].sum())
    return {
        "total_demand_m3": demand,
        "total_delivered_m3": delivered,
        "total_unmet_m3": unmet,
        "demand_satisfaction_ratio": (delivered / demand) if demand else 1.0,
        "total_pv_generation_kwh": float(results["pv_generation_kw"].sum()),
        "total_grid_energy_kwh": float(results["grid_energy_kwh"].sum()),
        "total_grid_cost": float(results["grid_cost"].sum()),
        "minimum_battery_soc": float(results["battery_soc"].min()),
        "minimum_reservoir_m3": float(results["reservoir_after_m3"].min()),
        "maximum_reservoir_m3": float(results["reservoir_after_m3"].max()),
        "pump_unavailable_hours": int((~results["pump_available"]).sum()),
    }
