"""v0.2 tests: conservation laws, pump physics, dispatch, scenario generators."""
import numpy as np
import pandas as pd
import pytest

from iri import (SystemConfig, simulate_system, summarise_results, PumpSystem,
                 borehole_from_test, run_scenarios)
from iri.scenarios import (markov_daily_clearness, failure_repair_availability,
                           correlated_demand_multiplier)


def synthetic_week(days=7, peak=850.0):
    h = np.arange(24 * days) % 24
    d = np.maximum(0.0, np.sin(np.pi * (h - 6) / 12.0))
    d[(h < 6) | (h > 18)] = 0.0
    return pd.DataFrame({"irradiance_w_m2": peak * d, "ambient_temp_c": 22 + 8 * d})


DEMO = dict(pv_capacity_kw=4.0, battery_capacity_kwh=8.0, max_charge_kw=2.0,
            max_discharge_kw=2.0, water_demand_m3_per_hour=10.0,
            reservoir_capacity_m3=60.0, initial_reservoir_m3=20.0)


def centrifugal_borehole():
    bh = borehole_from_test(static_water_level_m=20, delivery_head_m=4,
                            q_test_m3h=12, drawdown_test_m=5)
    return PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=12, rated_head_m=30,
                      pump_efficiency=0.60, drive_efficiency=0.92, friction_k=0.006, **bh)


@pytest.mark.parametrize("policy", ["rated", "reservoir_aware"])
@pytest.mark.parametrize("pump_factory", [lambda: None, centrifugal_borehole])
def test_energy_and_water_conservation(policy, pump_factory):
    cfg = SystemConfig(**DEMO, dispatch_policy=policy, battery_pumping_below_level=0.5)
    r = simulate_system(synthetic_week(), cfg, pump=pump_factory())
    # PV is either used, stored or curtailed - never created or lost
    assert np.allclose(r.pv_generation_kw,
                       r.pv_to_pump_kw + r.battery_charge_kw + r.pv_curtailed_kw, atol=1e-9)
    # battery energy balance over the horizon
    e0 = cfg.initial_soc * cfg.battery_capacity_kwh
    e1 = r.battery_soc.iloc[-1] * cfg.battery_capacity_kwh
    inflow = (r.battery_charge_kw * cfg.charge_efficiency).sum()
    outflow = (r.battery_to_pump_kw / cfg.discharge_efficiency).sum()
    assert e0 + inflow - outflow == pytest.approx(e1, abs=1e-9)
    assert (r.battery_soc >= cfg.min_soc - 1e-12).all()
    assert (r.battery_soc <= cfg.max_soc + 1e-12).all()
    # reservoir mass balance over the horizon
    lhs = cfg.initial_reservoir_m3 + r.water_produced_m3.sum()
    rhs = r.water_delivered_m3.sum() + r.reservoir_overflow_m3.sum() + r.reservoir_after_m3.iloc[-1]
    assert lhs == pytest.approx(rhs, abs=1e-9)
    assert np.allclose(r.water_delivered_m3 + r.unmet_water_m3, r.water_demand_m3)


def test_default_pump_reproduces_v01():
    cfg = SystemConfig(**DEMO)
    r = simulate_system(synthetic_week(), cfg)
    p_rated = 1000 * 9.80665 * (12 / 3600) * 30 / 0.65 / 1000
    on = r.pump_fraction > 0
    assert np.allclose(r.pump_fraction[on],
                       (r.pv_to_pump_kw + r.battery_to_pump_kw)[on] / p_rated, rtol=1e-6)


def test_centrifugal_passes_rated_point_without_losses():
    p = PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=12, rated_head_m=30,
                   static_head_m=30)
    assert p.max_flow == pytest.approx(12.0, rel=1e-3)


def test_centrifugal_has_cutoff_below_static_head():
    p = centrifugal_borehole()
    assert p.min_flow > 0
    assert p.flow_for_power(0.5 * p.min_power_kw) == 0.0
    # part-load: half the power gives much less than half the flow
    assert p.flow_for_power(0.5 * p.max_power_kw) < 0.5 * p.max_flow


def test_drawdown_raises_head_with_flow():
    p = centrifugal_borehole()
    assert p.head_at_flow(12) > p.head_at_flow(4) > p.static_head_m


def test_pump_too_weak_for_static_head_raises():
    with pytest.raises(ValueError):
        PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=12, rated_head_m=30,
                   shutoff_head_ratio=1.2, static_head_m=40)


def test_reservoir_aware_dispatch_never_overflows():
    cfg = SystemConfig(**{**DEMO, "pv_capacity_kw": 12.0, "water_demand_m3_per_hour": 3.0},
                       dispatch_policy="reservoir_aware")
    r = simulate_system(synthetic_week(), cfg)
    assert r.reservoir_overflow_m3.sum() == pytest.approx(0.0, abs=1e-9)
    rated = simulate_system(synthetic_week(), SystemConfig(**{**DEMO, "pv_capacity_kw": 12.0,
                                                               "water_demand_m3_per_hour": 3.0}))
    assert rated.reservoir_overflow_m3.sum() > 0  # the v0.1 rule wastes water and battery


def test_failure_process_long_run_availability():
    rng = np.random.default_rng(0)
    a = failure_repair_availability(24 * 365 * 200, rng, mttf_hours=500,
                                    mttr_median_hours=48, mttr_sigma=0.5)
    expected = 500 / (500 + 48 * np.exp(0.5 ** 2 / 2))
    assert a.mean() == pytest.approx(expected, abs=0.01)


def test_markov_overcast_persistence():
    rng = np.random.default_rng(1)
    _, flags = markov_daily_clearness(200_000, rng, 0.2, 0.5)
    assert flags.mean() == pytest.approx(0.2 / 0.7, abs=0.01)
    starts = np.flatnonzero(np.diff(flags.astype(int)) == 1)
    ends = np.flatnonzero(np.diff(flags.astype(int)) == -1)
    k = min(len(starts), len(ends[ends > starts[0]]))
    spells = ends[ends > starts[0]][:k] - starts[:k]
    assert spells.mean() == pytest.approx(1 / 0.5, rel=0.05)


def test_demand_heat_coupling_sign():
    rng = np.random.default_rng(2)
    clear = np.r_[np.full(50, 1.0), np.full(50, 0.3)]
    d = correlated_demand_multiplier(100, rng, daily_cv=0.0, ar1=0.0,
                                     heat_coupling=0.3, clearness=clear)
    assert d[:50].mean() > d[50:].mean()


def test_run_scenarios_reproducible_and_bounded():
    cfg = SystemConfig(**DEMO)
    kw = dict(n_simulations=20, seed=7, failure_kwargs={"mttf_hours": 2000,
                                                       "mttr_median_hours": 72})
    df1, s1 = run_scenarios(synthetic_week(), cfg, **kw)
    df2, s2 = run_scenarios(synthetic_week(), cfg, **kw)
    pd.testing.assert_frame_equal(df1, df2)
    ci = s1["probability_satisfaction_at_least_95pct"]
    assert 0 <= ci["ci95_low"] <= ci["estimate"] <= ci["ci95_high"] <= 1
    assert ((df1.demand_satisfaction_ratio >= 0) & (df1.demand_satisfaction_ratio <= 1)).all()
