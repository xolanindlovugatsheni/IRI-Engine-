# IRI Engine

Open-source computational engine for infrastructure resilience modelling, uncertainty quantification, and coupled water-energy systems.

> **Status:** Research prototype (v0.1). Not validated or certified for engineering design or safety-critical use.

## Overview

IRI Engine is an early-stage Python framework for exploring the operational resilience of solar-powered water pumping systems. It combines simplified photovoltaic generation, battery storage, pump energy requirements, reservoir mass balance, and Monte Carlo uncertainty analysis.

## Features in v0.1

- Hourly photovoltaic output approximation using irradiance and temperature derating.
- Battery state-of-charge accounting with charge and discharge efficiencies.
- Pump power estimation from flow, head, and efficiency.
- Reservoir mass balance, unmet demand, and overflow accounting.
- Optional grid supply.
- Monte Carlo sampling for selected operating uncertainties.
- CSV outputs and a baseline visualisation.

## Quick start

Python 3.10 or later is recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python examples/run_demo.py
```

Run tests with `python -m pytest -q`.

## Project structure

- `src/iri/`: simulation and uncertainty modules
- `tests/`: automated tests
- `examples/`: reproducible demonstration
- `docs/`: technical specification

## Limitations

This is a research prototype, not a validated engineering design package. Pump dispatch is a simplified rated-duty rule, not a reservoir-aware controller or mathematical optimiser. Pump curves, equipment degradation, weather-demand correlations, and failure processes are simplified. The included scenario is synthetic and illustrative; it must not be interpreted as a performance prediction for a real installation.

Engineering decisions require site-specific data, independent review by qualified professionals, and validation against suitable established tools and measured installations.

## Roadmap

- [x] Deterministic coupled solar-water baseline model
- [x] Initial Monte Carlo uncertainty wrapper
- [x] Basic automated tests and reproducible demo
- [ ] Reservoir-aware, demand-responsive pump dispatch
- [ ] Energy and mass conservation test suite
- [ ] Correlated weather, demand, and equipment scenarios
- [ ] Benchmarking against analytical cases and established modelling tools
- [ ] Optimisation of pumping and storage schedules
- [ ] Calibration and validation using measured installation data

## Licence

Apache License 2.0. See [LICENSE](LICENSE).

## Contributing

Issues, reproducible examples, benchmark cases, and technical reviews are welcome. Please include assumptions, units, data provenance, and expected behaviour when reporting model results.
