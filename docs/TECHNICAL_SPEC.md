# IRI Engine v0.1 — Technical Specification

## 1. Product objective

Provide a reproducible hourly screening model for a stand-alone or hybrid
solar-powered water-pumping system. The model couples PV generation, battery
storage, pump energy demand and reservoir water balance, then quantifies
uncertainty through Monte Carlo scenarios.

## 2. Intended user

Engineering and industrial consultancies undertaking preliminary feasibility,
scenario analysis and infrastructure resilience assessments.

## 3. Scope

### Included
- Hourly PV power approximation.
- Pump hydraulic duty-point power.
- Battery state-of-charge accounting.
- PV -> battery -> optional grid dispatch logic.
- Pump flow curtailment under power shortage.
- Reservoir water balance.
- Unmet water demand and overflow accounting.
- Monte Carlo uncertainty wrapper.
- CSV exports and summary indicators.

### Excluded
- Detailed hydraulic network and pipe transients.
- Manufacturer-specific pump curves.
- PV module string/inverter design.
- Battery electrochemistry and degradation.
- Detailed protection and electrical design.
- Autonomous control.
- Safety certification or guaranteed engineering design.
- Calibrated failure-rate claims.

## 4. Mathematical model

PV:
P_pv(t) = P_rated * G(t)/G_STC * derate * max(0, 1 + gamma*(T_cell-T_ref))

Approximate cell temperature:
T_cell = T_ambient + ((NOCT-20)/800)*G

Hydraulic pump input:
P_pump = rho*g*Q*H/(eta*3600*1000)
where Q is in m^3/hour and P is in kW.

Battery:
SOC evolves from charge and discharge energy, adjusted by charge/discharge
efficiencies and constrained by minimum/maximum SOC and power limits.

Reservoir:
V(t+1) = clip(V(t) + Q_produced(t) - Q_demand_delivered(t), 0, V_max)
with overflow and unmet demand recorded separately.

## 5. Dispatch policy

1. Calculate PV power.
2. Allocate PV directly to pump demand.
3. Use battery discharge to meet remaining pump demand.
4. Use grid supply if enabled.
5. Curtail pump flow proportionally if supply is insufficient.
6. Use PV surplus to charge the battery.
7. Update reservoir volume and unmet demand.

This is a simple heuristic dispatch strategy, not a globally optimal controller.
The current pump rule requests rated duty whenever the pump is available; it
does not yet optimise operation against reservoir level or forecast demand.

## 6. Monte Carlo model

The demo samples:
- Hourly irradiance multiplier.
- Hourly demand multiplier.
- Pump availability.
- Pump efficiency multiplier.

The current demo assumes independent random variations. Future work should
consider temporal autocorrelation, weather-demand dependence, seasonal effects,
component failure/repair processes and parameter posterior distributions.

## 7. Outputs

Hourly:
- PV generation.
- Energy allocation.
- Battery SOC.
- Pump availability and flow fraction.
- Water produced and delivered.
- Reservoir volume.
- Unmet demand.
- Grid energy and cost.

Aggregate:
- Demand satisfaction ratio.
- Total unmet water.
- Minimum SOC.
- Reservoir range.
- Grid energy and cost.
- Monte Carlo quantiles and service-level probability.

## 8. Validation plan

- Analytical PV calculations at selected irradiance and temperature points.
- Hydraulic pump power checks against hand calculations and manufacturer duty
  points.
- Battery energy conservation checks.
- Reservoir mass-balance tests.
- Comparison against a spreadsheet reference.
- Cross-check with EPANET/WNTR for a future hydraulic-network module.
- Comparison with measured site data before commercial engineering use.

## 9. Release criteria

- All automated tests pass.
- Example runs from a clean environment.
- Inputs and units documented.
- Random seed reproducibility demonstrated.
- Limitations visible in all generated reports.
- No claim of certification or validated field accuracy without evidence.

---

## 10. v0.2 additions (branch `v0.2-core`)

### 10.1 Pump and borehole hydraulics (`iri/pump.py`)

v0.1 delivered flow proportional to supplied power at fixed head. That is an
ideal positive-displacement pump with no drawdown; it remains the default
(`legacy_pump`) so v0.1 results are reproducible.

System curve (Q in m3/h):

    H_sys(Q) = H_static + B*Q + (C + k_f)*Q^2

B and C are the Jacob aquifer and well-loss coefficients; `borehole_from_test`
splits a single pumping-test drawdown into B and C (a step-drawdown test
should replace that split). Centrifugal pump on a variable-speed drive:

    H_pump(Q, n) = n^2 H_0 - a Q^2,  a = (H_0 - H_r)/Q_r^2
    eta(Q, n)    = eta_bep (2x - x^2),  x = Q/(n Q_r)

The operating point solves H_pump = H_sys. Below the speed at which
n^2 H_0 = H_static no water flows; the controller will not start below that
minimum power. Power <-> flow is tabulated once per pump and interpolated in
the time loop.

### 10.2 Dispatch

`dispatch_policy="reservoir_aware"` requests only the flow that fits the
reservoir headroom plus the hour's demand (no overflow by construction) and
lets the battery drive the pump only below `battery_pumping_below_level`.

### 10.3 Scenario generators (`iri/scenarios.py`, `run_scenarios`)

- Daily irradiance: two-state (clear/overcast) Markov chain; spell length
  1/p(overcast->clear) days. Fit to site daily data before use.
- Demand: AR(1) daily multiplier with optional coupling to clearness.
- Pump availability: alternating renewal process, exponential time to
  failure, lognormal repair time.
- Service probability reported with a Wilson 95% interval.

### 10.4 New outputs

`pv_curtailed_kw`, `pump_head_m`, `hours_with_unmet_demand`,
`longest_unmet_spell_hours`, `total_overflow_m3`, `total_pv_curtailed_kwh`.

### 10.5 Verification

`tests/test_v02.py`: energy conservation (PV used + stored + curtailed),
battery energy balance, reservoir mass balance, v0.1 reproduction, centrifugal
rated-point and cut-off behaviour, no-overflow dispatch, long-run availability
of the failure process, Markov spell statistics, scenario reproducibility.
