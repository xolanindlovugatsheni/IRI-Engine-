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


SUMMARY_METRICS = [
    "demand_satisfaction_ratio",
    "total_unmet_m3",
    "longest_unmet_spell_hours",
    "hours_with_unmet_demand",
    "total_grid_energy_kwh",
    "minimum_battery_soc",
    "minimum_reservoir_m3",
]


def run_scenarios(
    weather: pd.DataFrame,
    config: SystemConfig,
    pump=None,
    n_simulations: int = 500,
    seed: int = 42,
    weather_kwargs: dict | None = None,
    demand_kwargs: dict | None = None,
    failure_kwargs: dict | None = None,
    hourly_irradiance_cv: float = 0.05,
    service_threshold: float = 0.95,
) -> tuple[pd.DataFrame, dict]:
    """v0.2 Monte Carlo with variability at physically meaningful timescales.

    - irradiance: two-state Markov daily clearness x small hourly noise
    - demand: AR(1) daily multiplier, optional coupling to clearness
    - pump: failure-repair renewal process (pass failure_kwargs=None to disable)

    ``weather`` supplies the clear-sky / typical-day hourly shape; its length
    must be a whole number of days.
    """
    from .scenarios import (markov_daily_clearness, correlated_demand_multiplier,
                            failure_repair_availability, expand_daily)
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")
    n = len(weather)
    if n % 24:
        raise ValueError("weather length must be a whole number of days")
    n_days = n // 24
    rng = np.random.default_rng(seed)
    base_irr = weather["irradiance_w_m2"].to_numpy(dtype=float)
    rows = []
    for sim in range(n_simulations):
        clear, overcast = markov_daily_clearness(n_days, rng, **(weather_kwargs or {}))
        irr = base_irr * expand_daily(clear, n) * np.clip(
            rng.normal(1.0, hourly_irradiance_cv, n), 0.0, 1.5)
        dem = config.water_demand_m3_per_hour * expand_daily(
            correlated_demand_multiplier(n_days, rng, clearness=clear, **(demand_kwargs or {})), n)
        avail = (failure_repair_availability(n, rng, **failure_kwargs)
                 if failure_kwargs is not None else np.ones(n, dtype=bool))
        w = weather.copy()
        w["irradiance_w_m2"] = irr
        m = summarise_results(simulate_system(w, config, dem, avail, pump=pump))
        m["simulation"] = sim
        m["overcast_days"] = int(overcast.sum())
        rows.append(m)
    df = pd.DataFrame(rows)
    summary = {}
    for col in SUMMARY_METRICS:
        v = df[col].to_numpy(dtype=float)
        summary[col] = {"mean": float(v.mean()), "p05": float(np.quantile(v, 0.05)),
                        "median": float(np.median(v)), "p95": float(np.quantile(v, 0.95))}
    p = float(np.mean(df["demand_satisfaction_ratio"] >= service_threshold))
    # Wilson 95% interval: the service probability is itself an estimate
    z, k = 1.96, n_simulations
    centre = (p + z * z / (2 * k)) / (1 + z * z / k)
    half = z * np.sqrt(p * (1 - p) / k + z * z / (4 * k * k)) / (1 + z * z / k)
    summary[f"probability_satisfaction_at_least_{int(service_threshold * 100)}pct"] = {
        "estimate": p, "ci95_low": float(max(0.0, centre - half)),
        "ci95_high": float(min(1.0, centre + half))}
    summary["n_simulations"] = int(n_simulations)
    summary["seed"] = int(seed)
    return df, summary
