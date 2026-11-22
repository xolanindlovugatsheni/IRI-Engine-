# Roadmap and Contributing

## Done

- **v0.1** — Coupled PV–battery–pump–reservoir model, basic Monte Carlo, tests, demo.
- **v0.2** — Centrifugal and positive-displacement pump models with borehole drawdown; reservoir-aware dispatch; Markov weather, correlated demand and failure–repair scenarios; conservation test suite; CI.

## Next

1. **Real site data.** Load PVGIS or NASA POWER weather, convert to plane-of-array irradiance with pvlib, and fit the weather model to a site's daily record.
2. **Validation on one installation.** Pumping-test data, installed equipment and operating logs from a solar borehole in Zimbabwe; compare predicted and measured water delivery.
3. **Failure and repair data.** Replace illustrative failure and repair times with values fitted to field records.
4. **Groundwater dynamics.** Water-table changes over a season, so drought affects supply through the aquifer as well as the sun.
5. **Portfolio mode.** Run many boreholes at once and rank them by risk, with the cheapest change that raises each to a target service level.
6. **Optimisation.** Pump scheduling and component sizing under uncertainty.

`v0.2.0` will be tagged once one site validation is complete.

## How to contribute

Contributions that make IRI more trustworthy are worth the most:

- **Field data:** pumping tests, system specifications, flow or tank-level logs, failure and repair records. Please state units, dates, measurement method and any permission needed to use the data.
- **Benchmark cases:** an analytical result or established tool output that IRI should reproduce.
- **Technical review:** errors in the physics, numerics or assumptions.
- **Code:** bug fixes and features from the roadmap.

### Code workflow

```bash
git checkout -b feature/short-description
python -m pytest -q
```

Then open a pull request describing the change, its assumptions and how you verified it.

Rules for code changes:

- Every physical change keeps the energy and mass-balance tests passing, and adds a test of its own.
- Units go in variable names (`flow_m3_per_hour`, `head_m`).
- Default behaviour stays backwards compatible unless the change is announced in `CHANGELOG.md`.
- No claim of field accuracy without the data that supports it.

### Reporting a problem

Open a GitHub issue with a minimal script that reproduces it, the output you got and the output you expected.
