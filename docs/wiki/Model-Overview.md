# Model Overview

IRI simulates a solar-powered water system hour by hour. Each hour it computes solar power, decides how much water to pump, routes power from PV, battery and (optionally) grid, then updates the battery and the tank.

```
 sun ─► PV array ─┬─► pump ─► borehole lift ─► tank ─► demand
                  └─► battery ─┘                 └─► overflow
```

Full equations: [`docs/TECHNICAL_SPEC.md`](https://github.com/xolanindlovugatsheni/IRI-Engine-/blob/main/docs/TECHNICAL_SPEC.md).

## 1. Solar generation

PV output scales with irradiance and falls as the cells heat up:

    P_pv = P_rated · (G / 1000) · derate · (1 + γ (T_cell − 25))
    T_cell = T_ambient + (NOCT − 20)/800 · G

Irradiance must be **plane-of-array**. Weather datasets usually give horizontal irradiance; transposition (planned via pvlib) is not yet built in.

## 2. Pump and borehole hydraulics

The head the pump must overcome rises with flow:

    H_sys(Q) = H_static + B·Q + (C + k_f)·Q²

- `H_static`: depth to the resting water level plus delivery height
- `B·Q`: aquifer drawdown (Jacob linear loss)
- `C·Q²`: well losses; `k_f·Q²`: pipe friction

**Centrifugal pumps** on a variable-speed drive follow the affinity laws. At low speed the pump cannot beat the static head, so **no water flows until the drive reaches a minimum power**; this cut-off is the main reason cloudy days hurt more than a simple model suggests. Efficiency falls away from the best-efficiency point.

**Positive-displacement pumps** (helical rotor) deliver flow roughly proportional to speed. The v0.1 default is an ideal version of this pump.

## 3. Dispatch

| Policy | Behaviour |
|---|---|
| `rated` | Pump at full rate whenever possible (v0.1). Can overflow the tank and waste battery energy. |
| `reservoir_aware` | Pump only what fits in the tank plus this hour's demand. Battery may run the pump only when the tank is below `battery_pumping_below_level`. |

Power is drawn from PV first, then battery, then grid if enabled.

## 4. Storage

- **Battery:** state of charge moves with charge/discharge efficiencies, inside minimum/maximum limits and power limits.
- **Tank:** mass balance; water above capacity is recorded as overflow, shortfalls as unmet demand.

## 5. Uncertainty

Off-grid water systems fail through *spells*, not hourly noise, so v0.2 puts randomness at the timescales where it matters:

| Source | Model |
|---|---|
| Weather | Two-state Markov chain of clear and overcast days; average overcast spell = 1 / p(overcast → clear) days |
| Demand | Daily AR(1) variation, optionally higher on hot, sunny days |
| Pump failures | Alternating up/down process: exponential time to failure, lognormal (heavy-tailed) repair time |

The v0.1 `run_monte_carlo` (independent hourly noise) is kept for comparison, but it cannot produce multi-day shortages.

## 6. Verification

Every change must keep these properties, checked by `tests/test_v02.py`:

- Solar energy is either used, stored or curtailed — never created or lost.
- Battery energy balances over the whole run.
- Tank water balances over the whole run.
- Centrifugal pumps hit their rated point and stop below the static head.
- Reservoir-aware dispatch never overflows.
- Failure and weather generators reproduce their theoretical long-run statistics.

## What is not modelled yet

Falling groundwater levels over a season, pipe networks, water quality, battery degradation, inverter/string design and manufacturer-specific pump curves.
