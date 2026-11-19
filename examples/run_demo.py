from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from iri import SystemConfig, simulate_system, run_monte_carlo
from iri.model import summarise_results

# Illustrative 7-day hourly profile. Replace with site-specific data.
hours = np.arange(24 * 7)
hour_of_day = hours % 24
daylight = np.maximum(0.0, np.sin(np.pi * (hour_of_day - 6) / 12.0))
daylight[(hour_of_day < 6) | (hour_of_day > 18)] = 0.0
day_factor = 0.85 + 0.15 * np.sin(2 * np.pi * (hours // 24) / 7)
irradiance = 850.0 * daylight * day_factor

weather = pd.DataFrame({
    "irradiance_w_m2": irradiance,
    "ambient_temp_c": 22.0 + 8.0 * daylight,
})

config = SystemConfig(
    pv_capacity_kw=4.0,
    battery_capacity_kwh=8.0,
    initial_soc=0.80,
    min_soc=0.20,
    max_soc=0.95,
    max_charge_kw=2.0,
    max_discharge_kw=2.0,
    pump_flow_m3_per_hour=12.0,
    total_dynamic_head_m=30.0,
    pump_efficiency=0.65,
    water_demand_m3_per_hour=10.0,
    reservoir_capacity_m3=60.0,
    initial_reservoir_m3=20.0,
    grid_available=False,
)

baseline = simulate_system(weather, config)
baseline.to_csv("baseline_results.csv", index=False)

mc_samples, mc_summary = run_monte_carlo(
    weather, config, n_simulations=250, seed=42,
    irradiance_cv=0.15, demand_cv=0.10,
    pump_hourly_unavailability=0.002,
    pump_efficiency_cv=0.05,
)
mc_samples.to_csv("monte_carlo_samples.csv", index=False)
with open("monte_carlo_summary.json", "w", encoding="utf-8") as f:
    json.dump(mc_summary, f, indent=2)

print("Baseline metrics:")
print(json.dumps(summarise_results(baseline), indent=2))
print("\nMonte Carlo summary:")
print(json.dumps(mc_summary, indent=2))

fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
axes[0].plot(baseline["timestep"], baseline["pv_generation_kw"], label="PV generation (kW)")
axes[0].set_ylabel("Power (kW)")
axes[0].legend()
axes[1].plot(baseline["timestep"], baseline["battery_soc"], label="Battery SOC")
axes[1].set_ylabel("SOC")
axes[1].set_ylim(0, 1)
axes[1].legend()
axes[2].plot(baseline["timestep"], baseline["reservoir_after_m3"], label="Reservoir volume")
axes[2].plot(baseline["timestep"], baseline["water_demand_m3"], label="Hourly demand")
axes[2].set_ylabel("Water (m³)")
axes[2].set_xlabel("Hour")
axes[2].legend()
fig.suptitle("IRI Engine v0.1 — illustrative 7-day simulation")
fig.tight_layout()
fig.savefig("baseline_plot.png", dpi=160)
print("\nWrote baseline_results.csv, monte_carlo_samples.csv, "
      "monte_carlo_summary.json and baseline_plot.png")
