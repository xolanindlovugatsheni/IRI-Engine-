# Welcome to IRI Engine

**IRI Technologies — computational intelligence for resilient physical infrastructure.**

IRI Engine is an open-source Python engine that estimates **how reliably an off-grid water system delivers water**, not just whether it is big enough on paper. Version 0.2 models solar-powered borehole pumping: PV generation, battery storage, pump and borehole hydraulics, reservoir storage, and the uncertainty that decides whether people actually get water — runs of overcast days, demand swings and pump breakdowns that take days to repair.

> **Status:** research prototype (`0.2.0.dev0`). Not yet validated against a measured installation. Do not use for engineering design or safety-critical decisions. See [Limitations](#limitations).

---

## Why IRI exists

Most solar-pump sizing tools answer one question: *will this system pump enough water in a typical or worst month?* Remote-monitoring platforms answer another: *has this pump failed?*

The question in between is rarely answered: **across a whole programme of boreholes, how often will people go without water, for how long, and which change buys the most reliability per dollar?**

IRI is built to answer that question. It sits between design and monitoring, for whoever funds, builds or maintains a portfolio of solar boreholes.

## What v0.2 shows

The same design, an 8 kW direct-drive PV array, a 24 m³/h borehole pump, a 180 m³ tank and 120 m³/day of demand, assessed with progressively more realistic models:

| Model | Probability that ≥95% of demand is met |
|---|---|
| Typical-conditions methods (as in v0.1) | **1.00** |
| + runs of overcast days, ideal pump | 1.00 |
| + real centrifugal pump and borehole drawdown | 0.84 |
| + pump failures with week-long repairs | **0.62** |

Neither the weather model nor the pump physics changes the answer alone; the risk appears when they interact. In the worst 5% of scenarios, the longest outage reaches about 11 days.

*The weather and failure parameters are illustrative until fitted to site data.* Reproduce it with `python examples/compare_v01_v02.py`.

## Start here

| If you want to… | Go to |
|---|---|
| Install and run your first simulation | [Getting Started](Getting-Started) |
| Understand the equations and assumptions | [Model Overview](Model-Overview) |
| See what's next, or contribute | [Roadmap and Contributing](Roadmap-and-Contributing) |
| Read the full specification | [`docs/TECHNICAL_SPEC.md`](https://github.com/xolanindlovugatsheni/IRI-Engine-/blob/main/docs/TECHNICAL_SPEC.md) |

## Design principles

1. **Physics before machine learning.** Transparent, conservation-checked models first. Machine learning only where it measurably improves accuracy, speed or decisions.
2. **Uncertainty at the right timescale.** Risk comes from multi-day weather spells and multi-day repairs, not hourly noise.
3. **Verified, not just tested.** Every run must conserve energy and water; the test suite checks it.
4. **Honest outputs.** Results carry their assumptions and confidence intervals. No claim of field accuracy without field data.

## Limitations

- Not validated against a measured installation yet.
- Weather, demand and failure parameters are illustrative defaults, not fitted to a site.
- Groundwater level is fixed over time; only drawdown during pumping is modelled.
- No pipe network, water quality or battery degradation.

## Licence and contact

Apache License 2.0. Built by **Xolani Ndlovu**, Bulawayo, Zimbabwe — [xolanimart@gmail.com](mailto:xolanimart@gmail.com) · X [@gatshXolani](https://x.com/gatshXolani).

Field data, benchmark cases and technical reviews are especially welcome.
