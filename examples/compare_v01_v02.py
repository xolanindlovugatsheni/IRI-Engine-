"""Side-by-side: what each v0.2 change does to the v0.1 demo conclusions."""
import json, time
import numpy as np, pandas as pd
from iri import (SystemConfig, simulate_system, summarise_results, PumpSystem,
                 borehole_from_test, run_monte_carlo, run_scenarios)

hours = np.arange(24 * 7); h = hours % 24
d = np.maximum(0.0, np.sin(np.pi * (h - 6) / 12.0)); d[(h < 6) | (h > 18)] = 0.0
weather = pd.DataFrame({"irradiance_w_m2": 850 * d * (0.85 + 0.15 * np.sin(2 * np.pi * (hours // 24) / 7)),
                        "ambient_temp_c": 22 + 8 * d})
base = dict(pv_capacity_kw=4.0, battery_capacity_kwh=8.0, initial_soc=0.8, max_charge_kw=2.0,
            max_discharge_kw=2.0, pump_flow_m3_per_hour=12.0, total_dynamic_head_m=30.0,
            pump_efficiency=0.65, water_demand_m3_per_hour=10.0, reservoir_capacity_m3=60.0,
            initial_reservoir_m3=20.0)
bh = borehole_from_test(static_water_level_m=20, delivery_head_m=4, q_test_m3h=12, drawdown_test_m=5)
cent = PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=12, rated_head_m=30,
                  pump_efficiency=0.65, drive_efficiency=0.92, friction_k=0.006, **bh)

def sat(cfg, pump=None, w=weather):
    s = summarise_results(simulate_system(w, cfg, pump=pump))
    return {k: round(s[k], 3) for k in ("demand_satisfaction_ratio", "longest_unmet_spell_hours",
                                        "total_overflow_m3", "total_pv_curtailed_kwh")}

out = {}
out["v0.1 baseline"] = sat(SystemConfig(**base))
out["+ centrifugal pump & borehole drawdown"] = sat(SystemConfig(**base), cent)
out["+ reservoir-aware dispatch"] = sat(SystemConfig(**base, dispatch_policy="reservoir_aware"), cent)

# hand-calc bound: weekly PV energy vs weekly pumping energy for demand
r = simulate_system(weather, SystemConfig(**base))
need = 1000 * 9.80665 * (10 / 3600) * 30 / 0.65 / 1000 * 168
out["energy bound (PV kWh / pump kWh needed)"] = round(r.pv_generation_kw.sum() / need, 3)

# binding-constraint sweep (v0.2 physics)
sweep = {}
for pv in (4, 6, 8, 12):
    for res in (60, 120, 240):
        c = SystemConfig(**{**base, "pv_capacity_kw": pv, "reservoir_capacity_m3": res,
                            "initial_reservoir_m3": res / 3}, dispatch_policy="reservoir_aware")
        sweep[f"PV {pv} kW / tank {res} m3"] = sat(c, cent)["demand_satisfaction_ratio"]
out["sizing sweep (satisfaction)"] = sweep

# uncertainty: a design that passes on paper. Isolate each modelling change.
h28 = np.arange(24 * 28) % 24
d28 = np.maximum(0.0, np.sin(np.pi * (h28 - 6) / 12.0)); d28[(h28 < 6) | (h28 > 18)] = 0.0
w28 = pd.DataFrame({"irradiance_w_m2": 850 * d28, "ambient_temp_c": 22 + 8 * d28})
bh2 = borehole_from_test(static_water_level_m=20, delivery_head_m=4, q_test_m3h=24, drawdown_test_m=7)
cent2 = PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=24, rated_head_m=32, pump_efficiency=0.65,
                   drive_efficiency=0.92, friction_k=0.002, **bh2)
good = dict(pv_capacity_kw=8, battery_capacity_kwh=0.001, initial_soc=0.2, min_soc=0.2, max_charge_kw=0.001,
            max_discharge_kw=0.001, pump_flow_m3_per_hour=24, total_dynamic_head_m=32, pump_efficiency=0.65,
            water_demand_m3_per_hour=5, reservoir_capacity_m3=180, initial_reservoir_m3=90)
legacy_cfg = SystemConfig(**good)
cfg2 = SystemConfig(**good, dispatch_policy="reservoir_aware")
out["design under test"] = ("8 kW PV direct-drive (no battery), 24 m3/h borehole pump, "
                            "180 m3 tank, 120 m3/day demand, 28 days, 300 scenarios")
out["centrifugal: minimum power before any water flows (kW of rated)"] = [
    round(cent2.min_power_kw, 2), round(cent2.max_power_kw, 2)]
out["deterministic, v0.2 physics"] = sat(cfg2, cent2, w28)

def p95(s):
    v = s["probability_satisfaction_at_least_95pct"]
    return v if not isinstance(v, dict) else round(v["estimate"], 3)

_, s1 = run_monte_carlo(w28, legacy_cfg, n_simulations=300, seed=1)
_, s2 = run_scenarios(w28, legacy_cfg, n_simulations=300, seed=1, failure_kwargs=None)
_, s3 = run_scenarios(w28, cfg2, pump=cent2, n_simulations=300, seed=1, failure_kwargs=None)
_, s4 = run_scenarios(w28, cfg2, pump=cent2, n_simulations=300, seed=1,
                      failure_kwargs={"mttf_hours": 24 * 120, "mttr_median_hours": 24 * 7})
out["P(>=95% of demand met)"] = {
    "v0.1 iid hourly MC, v0.1 pump": p95(s1),
    "Markov weather, v0.1 pump": p95(s2),
    "Markov weather, centrifugal + drawdown": p95(s3),
    "+ failure-repair (MTTF 120 d, MTTR median 7 d)": p95(s4)}
out["p95 longest outage (h)"] = {
    "v0.1 iid": None,
    "Markov, v0.1 pump": s2["longest_unmet_spell_hours"]["p95"],
    "Markov, centrifugal": s3["longest_unmet_spell_hours"]["p95"],
    "+ failure-repair": s4["longest_unmet_spell_hours"]["p95"]}

wy = pd.concat([weather] * 52, ignore_index=True)
t = time.perf_counter(); simulate_system(wy, cfg2, pump=cent2)
out["seconds per 1-year hourly simulation"] = round(time.perf_counter() - t, 3)
print(json.dumps(out, indent=2))
