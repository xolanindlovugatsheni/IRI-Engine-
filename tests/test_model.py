import numpy as np
import pandas as pd
import pytest

from iri.model import SystemConfig, pv_power_kw, pump_power_kw, simulate_system


def test_pv_zero_irradiance_is_zero():
    assert pv_power_kw(10, 0) == 0


def test_pv_output_increases_with_irradiance_under_same_conditions():
    low = pv_power_kw(10, 300, ambient_temp_c=20)
    high = pv_power_kw(10, 700, ambient_temp_c=20)
    assert high > low


def test_pump_power_matches_hydraulic_equation_order_of_magnitude():
    power = pump_power_kw(10, 20, 0.70)
    assert power == pytest.approx(0.7783, rel=0.01)


def test_reservoir_balance_and_nonnegative_volume():
    weather = pd.DataFrame({
        "irradiance_w_m2": [0, 0, 0],
        "ambient_temp_c": [25, 25, 25],
    })
    cfg = SystemConfig(
        pv_capacity_kw=1, battery_capacity_kwh=1,
        initial_soc=0.2, min_soc=0.2, max_soc=0.95,
        max_discharge_kw=0.1, pump_flow_m3_per_hour=5,
        total_dynamic_head_m=10, pump_efficiency=0.7,
        water_demand_m3_per_hour=10,
        reservoir_capacity_m3=20, initial_reservoir_m3=5,
    )
    result = simulate_system(weather, cfg)
    assert (result["reservoir_after_m3"] >= 0).all()
    assert (result["water_delivered_m3"] <= result["water_demand_m3"]).all()
    assert np.allclose(
        result["reservoir_before_m3"] + result["water_produced_m3"]
        - result["water_delivered_m3"] - result["reservoir_overflow_m3"],
        result["reservoir_after_m3"],
    )


def test_pump_unavailable_means_no_production():
    weather = pd.DataFrame({
        "irradiance_w_m2": [1000],
        "ambient_temp_c": [25],
    })
    cfg = SystemConfig()
    result = simulate_system(weather, cfg, pump_available=[False])
    assert result.loc[0, "water_produced_m3"] == 0
