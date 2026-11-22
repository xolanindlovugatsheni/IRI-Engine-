# Changelog

## 0.2.0.dev0 — `v0.2-core`

### Physics
- Explicit pump/borehole model: centrifugal (affinity laws, shut-off head,
  part-load efficiency) or positive-displacement; static head + Jacob drawdown
  + pipe friction. v0.1 behaviour kept as `legacy_pump` (default).
- Reservoir-aware dispatch policy; battery reserve rule.

### Uncertainty
- `run_scenarios`: Markov daily weather, AR(1) demand, failure-repair process,
  Wilson interval on service probability. `run_monte_carlo` unchanged.

### Metrics
- Longest unmet spell, unmet hours, overflow, PV curtailment.

### Engineering
- Time loop on NumPy arrays (no `iterrows`): ~0.08 s per simulated year.
- 14 new tests (19 total). GitHub Actions CI on Python 3.10 and 3.12.
- Demo writes to `outputs/`; generated files removed from version control.
- `examples/compare_v01_v02.py` quantifies each change; results in
  `docs/v0.2_comparison.json`.

### Findings that change the v0.1 narrative
- The v0.1 demo's 55.8% is an energy bound (weekly PV ≈ 53% of the pumping
  energy the demand needs), not a stochastic result. The Monte Carlo cannot
  move it, which is why baseline and MC means agree.
- i.i.d. hourly irradiance noise averages out over a solar day; it cannot
  produce multi-day droughts. On an 8 kW / 180 m3 direct-drive design, v0.1
  methods give P(>=95% service) = 1.00; Markov weather with real centrifugal
  physics gives 0.84; adding failure-repair gives 0.62.
