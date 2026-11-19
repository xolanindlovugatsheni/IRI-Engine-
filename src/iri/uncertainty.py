"""Monte Carlo uncertainty wrapper for IRI Engine v0.1."""
import numpy as np
import pandas as pd
from .model import SystemConfig, simulate_system, summarise_results


def run_monte_carlo(
    weather: pd.DataFrame,
    config: SystemConfig,
    n_simulations: int = 200,
    seed: int = 42,
    irradiance_cv: float = 0.15,
    demand_cv: float = 0.10,
    pump_hourly_unavailability: float = 0.002,
    pump_efficiency_cv: float = 0.05,
) -> tuple[pd.DataFrame, dict]:
    """Run independent illustrative scenarios and return samples plus summary.

    Multipliers are clipped to physically meaningful ranges. For real projects,
    replace these assumptions with site-specific distributions and correlations.
    """
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")
    for name, value in {
        "irradiance_cv": irradiance_cv,
        "demand_cv": demand_cv,
        "pump_hourly_unavailability": pump_hourly_unavailability,
        "pump_efficiency_cv": pump_efficiency_cv,
    }.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if pump_hourly_unavailability > 1:
        raise ValueError("pump_hourly_unavailability must be <= 1")

    rng = np.random.default_rng(seed)
    samples = []
    base_irr = weather["irradiance_w_m2"].to_numpy(dtype=float)
    base_demand = np.full(len(weather), config.water_demand_m3_per_hour)

    for sim in range(n_simulations):
        irr_multiplier = np.clip(
            rng.normal(1.0, irradiance_cv, len(weather)), 0.0, 1.5
        )
        demand_multiplier = np.clip(
            rng.normal(1.0, demand_cv, len(weather)), 0.5, 1.8
        )
        pump_available = rng.random(len(weather)) >= pump_hourly_unavailability
        efficiency_multiplier = np.clip(
            rng.normal(1.0, pump_efficiency_cv), 0.75, 1.15
        )
        scenario_weather = weather.copy()
        scenario_weather["irradiance_w_m2"] = base_irr * irr_multiplier
        scenario_config = SystemConfig(**vars(config))
        scenario_config.pump_efficiency = min(
            1.0, max(0.1, config.pump_efficiency * efficiency_multiplier)
        )
        scenario_demand = base_demand * demand_multiplier
        results = simulate_system(
            scenario_weather, scenario_config, scenario_demand, pump_available
        )
        metrics = summarise_results(results)
        metrics["simulation"] = sim
        samples.append(metrics)

    sample_df = pd.DataFrame(samples)
    summary = {}
    for column in [
        "demand_satisfaction_ratio",
        "total_unmet_m3",
        "total_grid_energy_kwh",
        "minimum_battery_soc",
        "minimum_reservoir_m3",
    ]:
        values = sample_df[column].to_numpy()
        summary[column] = {
            "mean": float(np.mean(values)),
            "p05": float(np.quantile(values, 0.05)),
            "median": float(np.quantile(values, 0.50)),
            "p95": float(np.quantile(values, 0.95)),
        }
    summary["probability_satisfaction_at_least_95pct"] = float(
        np.mean(sample_df["demand_satisfaction_ratio"] >= 0.95)
    )
    summary["n_simulations"] = int(n_simulations)
    summary["seed"] = int(seed)
    return sample_df, summary
