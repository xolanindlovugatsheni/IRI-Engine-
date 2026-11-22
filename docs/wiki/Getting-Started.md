# Getting Started

## Requirements

- Python 3.10 or later
- `numpy`, `pandas` (core); `matplotlib`, `pytest` (examples and tests)

## Install

```bash
git clone https://github.com/xolanindlovugatsheni/IRI-Engine-.git
cd IRI-Engine-
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Check everything works:

```bash
python -m pytest -q          # 19 tests should pass
python examples/run_demo.py  # writes results to outputs/
```

## Your first simulation

IRI needs an hourly weather table with two columns: `irradiance_w_m2` (plane-of-array) and `ambient_temp_c`.

```python
import numpy as np
import pandas as pd
from iri import SystemConfig, simulate_system, summarise_results

# Seven illustrative days. Replace with site data.
h = np.arange(24 * 7) % 24
sun = np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)
weather = pd.DataFrame({"irradiance_w_m2": 850 * sun,
                        "ambient_temp_c": 22 + 8 * sun})

config = SystemConfig(
    pv_capacity_kw=8.0,
    battery_capacity_kwh=8.0,
    pump_flow_m3_per_hour=12.0,
    total_dynamic_head_m=30.0,
    water_demand_m3_per_hour=5.0,
    reservoir_capacity_m3=120.0,
    initial_reservoir_m3=60.0,
    dispatch_policy="reservoir_aware",
)

results = simulate_system(weather, config)
print(summarise_results(results))
```

`results` is an hourly table: PV generation, power routed to the pump, battery state of charge, water produced and delivered, reservoir level, unmet demand, overflow and more.

## Add a real pump and borehole

By default the pump behaves like an ideal positive-displacement pump at fixed head (v0.1 behaviour). For a centrifugal borehole pump, describe the borehole from a pumping test:

```python
from iri import PumpSystem, borehole_from_test

borehole = borehole_from_test(
    static_water_level_m=20,   # depth to water at rest
    delivery_head_m=4,         # height from borehole head to tank inlet
    q_test_m3h=12,             # pumping-test rate
    drawdown_test_m=5,         # drawdown observed at that rate
)
pump = PumpSystem(kind="centrifugal", rated_flow_m3_per_hour=12, rated_head_m=30,
                  pump_efficiency=0.60, drive_efficiency=0.92, friction_k=0.006,
                  **borehole)

print("Power needed before any water flows:", round(pump.min_power_kw, 2), "kW")
results = simulate_system(weather, config, pump=pump)
```

## Estimate reliability under uncertainty

`run_scenarios` repeats the simulation many times with runs of overcast days, day-to-day demand changes and pump failures:

```python
from iri import run_scenarios

samples, summary = run_scenarios(
    weather, config, pump=pump,
    n_simulations=300, seed=1,
    failure_kwargs={"mttf_hours": 24 * 120,       # mean time to failure
                    "mttr_median_hours": 24 * 7}, # median repair time
)
print(summary["probability_satisfaction_at_least_95pct"])
print(summary["longest_unmet_spell_hours"])
```

The weather length must be a whole number of days. The service probability comes with a 95% confidence interval; with few scenarios, that interval is wide.

## Key outputs

| Metric | Meaning |
|---|---|
| `demand_satisfaction_ratio` | Share of demanded water actually delivered |
| `longest_unmet_spell_hours` | Longest continuous stretch with unmet demand |
| `hours_with_unmet_demand` | Total hours with any shortfall |
| `total_overflow_m3` | Water pumped and then lost through tank overflow |
| `total_pv_curtailed_kwh` | Solar energy produced but not used or stored |
| `probability_satisfaction_at_least_95pct` | Share of scenarios meeting ≥95% of demand, with 95% interval |

Next: [Model Overview](Model-Overview).
