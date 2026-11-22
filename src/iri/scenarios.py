"""Stochastic scenario generators for IRI Engine v0.2.

v0.1 perturbed every hour independently. Over a 12-hour solar day an i.i.d.
hourly multiplier with CV 15% averages to a daily-energy CV of roughly
15%/sqrt(12) ~ 4%, so the dominant risk for an off-grid water system -
consecutive overcast days and multi-day pump outages - was structurally
absent. These generators put the variability at the timescales where it acts.
"""
from __future__ import annotations

import numpy as np


def markov_daily_clearness(
    n_days: int,
    rng: np.random.Generator,
    p_clear_to_overcast: float = 0.15,
    p_overcast_to_clear: float = 0.45,
    clear_mean: float = 1.0,
    clear_sd: float = 0.07,
    overcast_mean: float = 0.40,
    overcast_sd: float = 0.15,
) -> tuple[np.ndarray, np.ndarray]:
    """Two-state Markov chain of daily irradiance multipliers.

    Returns (multipliers, overcast_flags). Persistence of overcast spells is
    1 / p_overcast_to_clear days on average. Defaults are illustrative and
    must be fitted to site data (e.g. NASA POWER / PVGIS daily series).
    """
    for p in (p_clear_to_overcast, p_overcast_to_clear):
        if not 0 <= p <= 1:
            raise ValueError("transition probabilities must be in [0, 1]")
    # start from the stationary distribution
    pi_overcast = p_clear_to_overcast / max(p_clear_to_overcast + p_overcast_to_clear, 1e-12)
    state = rng.random() < pi_overcast
    flags = np.empty(n_days, dtype=bool)
    for d in range(n_days):
        flags[d] = state
        u = rng.random()
        state = (u >= p_overcast_to_clear) if state else (u < p_clear_to_overcast)
    mult = np.where(
        flags,
        rng.normal(overcast_mean, overcast_sd, n_days),
        rng.normal(clear_mean, clear_sd, n_days),
    )
    return np.clip(mult, 0.05, 1.3), flags


def correlated_demand_multiplier(
    n_days: int,
    rng: np.random.Generator,
    daily_cv: float = 0.10,
    ar1: float = 0.6,
    heat_coupling: float = 0.0,
    clearness: np.ndarray | None = None,
) -> np.ndarray:
    """AR(1) daily demand multiplier, optionally raised on sunny (hot) days.

    heat_coupling > 0 makes demand rise when irradiance is high - the usual
    sign for irrigation and livestock - which *reduces* the benefit of sunny
    days. Ignoring that coupling biases reliability upward.
    """
    if not -1 < ar1 < 1:
        raise ValueError("ar1 must be in (-1, 1)")
    eps = rng.normal(0.0, daily_cv * np.sqrt(1 - ar1 ** 2), n_days)
    x = np.empty(n_days)
    x[0] = rng.normal(0.0, daily_cv)
    for d in range(1, n_days):
        x[d] = ar1 * x[d - 1] + eps[d]
    if clearness is not None and heat_coupling:
        x = x + heat_coupling * (np.asarray(clearness) - np.mean(clearness))
    return np.clip(1.0 + x, 0.3, 2.0)


def failure_repair_availability(
    n_hours: int,
    rng: np.random.Generator,
    mttf_hours: float = 24 * 180,
    mttr_median_hours: float = 24 * 5,
    mttr_sigma: float = 0.8,
) -> np.ndarray:
    """Alternating renewal process: exponential up-times, lognormal repairs.

    Long-run availability ~ MTTF / (MTTF + E[repair]). Rural repair times are
    dominated by logistics (spares, technician travel), hence the heavy-tailed
    lognormal rather than an hourly Bernoulli draw.
    """
    if mttf_hours <= 0 or mttr_median_hours <= 0:
        raise ValueError("MTTF and MTTR must be > 0")
    avail = np.ones(n_hours, dtype=bool)
    # random phase: start up with probability = availability
    t = 0.0
    mean_repair = mttr_median_hours * np.exp(mttr_sigma ** 2 / 2)
    if rng.random() > mttf_hours / (mttf_hours + mean_repair):
        rep = rng.lognormal(np.log(mttr_median_hours), mttr_sigma)
        avail[: int(min(n_hours, rep))] = False
        t = rep
    while t < n_hours:
        t += rng.exponential(mttf_hours)
        if t >= n_hours:
            break
        rep = rng.lognormal(np.log(mttr_median_hours), mttr_sigma)
        avail[int(t): int(min(n_hours, t + rep))] = False
        t += rep
    return avail


def expand_daily(daily: np.ndarray, n_hours: int, hours_per_day: int = 24) -> np.ndarray:
    return np.repeat(np.asarray(daily, dtype=float), hours_per_day)[:n_hours]
