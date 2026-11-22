"""Core hourly water-energy model for IRI Engine.

This is a transparent screening model, not a detailed engineering design tool.
"""
from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd

from .pump import PumpSystem, legacy_pump

DISPATCH_POLICIES = {"rated", "reservoir_aware"}


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

    # v0.2 dispatch controls (defaults reproduce v0.1)
    dispatch_policy: str = "rated"
    battery_pumping_below_level: float = 1.0  # battery may drive the pump only below this reservoir fraction

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
            raise ValueError("SOC must satisfy 0 <= min <= initial <= max <= 1")
        if self.initial_reservoir_m3 < 0 or self.initial_reservoir_m3 > self.reservoir_capacity_m3:
            raise ValueError("initial reservoir volume must be within reservoir bounds")
        if self.pv_derate <= 0:
            raise ValueError("pv_derate must be > 0")
        if self.dispatch_policy not in DISPATCH_POLICIES:
            raise ValueError(f"dispatch_policy must be one of {sorted(DISPATCH_POLICIES)}")
        if not 0 <= self.battery_pumping_below_level <= 1:
            raise ValueError("battery_pumping_below_level must be in [0, 1]")


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
    pump: PumpSystem | None = None,
) -> pd.DataFrame:
    """Simulate hourly system operation.

    Required weather columns: irradiance_w_m2 (plane-of-array) and ambient_temp_c.
    Dispatch priority: PV -> battery -> grid (if enabled).

    ``pump`` maps electrical power to delivered flow. If omitted, the v0.1
    behaviour is reproduced (ideal positive-displacement pump at fixed head,
    flow proportional to power). Use a centrifugal ``PumpSystem`` with
    borehole drawdown for realistic part-load behaviour.

    ``config.dispatch_policy``:
      - "rated": request full flow whenever the pump is available (v0.1).
      - "reservoir_aware": request only the flow that fits the reservoir
        headroom plus this hour's demand, and use the battery only when the
        reservoir is below ``battery_pumping_below_level``.
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

    if pump is None:
        pump = legacy_pump(config.pump_flow_m3_per_hour, config.total_dynamic_head_m,
                           config.pump_efficiency)

    dt = config.timestep_hours
    cap_kwh = config.battery_capacity_kwh
    res_cap = config.reservoir_capacity_m3
    soc = config.initial_soc
    reservoir = config.initial_reservoir_m3
    irr = weather["irradiance_w_m2"].to_numpy(dtype=float)
    tamb = weather["ambient_temp_c"].to_numpy(dtype=float)
    q_max = pump.max_flow
    q_min = pump.min_flow if pump.kind == "centrifugal" else 0.0

    cols = {k: np.zeros(n) for k in (
        "pv_generation_kw", "pump_power_required_kw", "pv_to_pump_kw", "battery_to_pump_kw",
        "grid_to_pump_kw", "battery_charge_kw", "pv_curtailed_kw", "battery_soc",
        "pump_fraction", "pump_head_m", "water_produced_m3", "water_delivered_m3",
        "unmet_water_m3", "reservoir_before_m3", "reservoir_after_m3",
        "reservoir_overflow_m3", "grid_energy_kwh")}

    for i in range(n):
        pv_kw = pv_power_kw(config.pv_capacity_kw, irr[i], tamb[i], config.pv_derate,
                            config.pv_temp_coefficient_per_c, config.cell_temp_noct_c,
                            config.reference_temp_c)

        # ---- flow request
        if not available[i]:
            q_target = 0.0
        elif config.dispatch_policy == "rated":
            q_target = q_max
        else:
            headroom = max(0.0, res_cap - reservoir) / dt + demand[i]
            q_target = min(q_max, headroom)
            if q_target < q_min:
                q_target = 0.0
        p_target = pump.power_for_flow(q_target)

        # ---- power allocation
        pv_to_pump = min(pv_kw, p_target)
        remaining = p_target - pv_to_pump
        battery_allowed = (config.dispatch_policy == "rated"
                           or reservoir < config.battery_pumping_below_level * res_cap)
        battery_available_kw = min(
            config.max_discharge_kw,
            max(0.0, (soc - config.min_soc) * cap_kwh * config.discharge_efficiency / dt),
        ) if battery_allowed else 0.0
        battery_to_pump = min(remaining, battery_available_kw)
        remaining -= battery_to_pump
        grid_to_pump = remaining if config.grid_available else 0.0
        supplied = pv_to_pump + battery_to_pump + grid_to_pump

        q = min(q_target, pump.flow_for_power(supplied))
        if q <= 0.0:  # below minimum drive power: nothing runs, nothing is drawn
            pv_to_pump = battery_to_pump = grid_to_pump = 0.0
        else:  # draw only the power the operating point needs (pro rata across sources)
            used = pump.power_for_flow(q)
            scale = used / supplied if supplied > 0 else 0.0
            pv_to_pump *= scale
            battery_to_pump *= scale
            grid_to_pump *= scale

        soc -= battery_to_pump * dt / config.discharge_efficiency / cap_kwh
        pv_surplus = max(0.0, pv_kw - pv_to_pump)
        charge_headroom_kw = max(0.0, (config.max_soc - soc) * cap_kwh
                                 / (config.charge_efficiency * dt))
        charge_kw = min(pv_surplus, config.max_charge_kw, charge_headroom_kw)
        soc += charge_kw * dt * config.charge_efficiency / cap_kwh

        # ---- water balance
        produced = q * dt
        before = reservoir
        avail_water = reservoir + produced
        delivered = min(demand[i] * dt, avail_water)
        reservoir = min(res_cap, avail_water - delivered)
        overflow = max(0.0, avail_water - delivered - res_cap)

        c = cols
        c["pv_generation_kw"][i] = pv_kw
        c["pump_power_required_kw"][i] = p_target
        c["pv_to_pump_kw"][i] = pv_to_pump
        c["battery_to_pump_kw"][i] = battery_to_pump
        c["grid_to_pump_kw"][i] = grid_to_pump
        c["battery_charge_kw"][i] = charge_kw
        c["pv_curtailed_kw"][i] = pv_surplus - charge_kw
        c["battery_soc"][i] = soc
        c["pump_fraction"][i] = q / config.pump_flow_m3_per_hour
        c["pump_head_m"][i] = pump.head_at_flow(q)
        c["water_produced_m3"][i] = produced
        c["water_delivered_m3"][i] = delivered
        c["unmet_water_m3"][i] = demand[i] * dt - delivered
        c["reservoir_before_m3"][i] = before
        c["reservoir_after_m3"][i] = reservoir
        c["reservoir_overflow_m3"][i] = overflow
        c["grid_energy_kwh"][i] = grid_to_pump * dt

    out = pd.DataFrame({"timestep": np.arange(n), "irradiance_w_m2": irr,
                        "ambient_temp_c": tamb, "pump_available": available, **cols,
                        "water_demand_m3": demand * dt})
    out["grid_cost"] = out["grid_energy_kwh"] * config.grid_energy_cost_per_kwh
    return out


def _longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


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
        "hours_with_unmet_demand": int((results["unmet_water_m3"] > 1e-9).sum()),
        "longest_unmet_spell_hours": _longest_run((results["unmet_water_m3"] > 1e-9).to_numpy()),
        "total_overflow_m3": float(results["reservoir_overflow_m3"].sum()),
        "total_pv_curtailed_kwh": float(results["pv_curtailed_kw"].sum()),
    }
