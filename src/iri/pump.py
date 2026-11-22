"""Pump and borehole hydraulics for IRI Engine v0.2.

The v0.1 model assumed delivered flow is proportional to supplied electrical
power at a fixed head. That is only true for an ideal positive-displacement
pump with constant efficiency and no drawdown. This module makes the pump
type and the hydraulic system explicit and maps electrical power <-> flow
through a precomputed operating table, so the time loop stays cheap.

System curve (head the pump must deliver at flow Q, Q in m3/h):

    H_sys(Q) = H_static + B*Q + (C + k_f)*Q^2

    H_static : static lift (static water level + delivery elevation), m
    B        : linear aquifer (formation) loss coefficient, m/(m3/h)
    C        : non-linear well loss coefficient, m/(m3/h)^2   (Jacob)
    k_f      : pipe friction coefficient, m/(m3/h)^2

Centrifugal pump with variable-speed drive (speed ratio n in [0, 1]):

    H_pump(Q, n) = n^2 * H_0 - a*Q^2,   a = (H_0 - H_r) / Q_r^2

so the curve passes through the rated duty point (Q_r, H_r) at n = 1 and
gives shut-off head H_0 at zero flow. Efficiency follows similarity about
the best-efficiency point: eta = eta_bep * (2x - x^2), x = Q / (n * Q_r).

Positive-displacement (helical rotor) pump: flow proportional to speed,
head set by the system curve, constant hydraulic efficiency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import numpy as np

RHO = 1000.0
G = 9.80665


@dataclass
class PumpSystem:
    kind: str = "positive_displacement"  # or "centrifugal"
    rated_flow_m3_per_hour: float = 12.0
    rated_head_m: float = 30.0
    pump_efficiency: float = 0.65          # hydraulic efficiency at BEP
    drive_efficiency: float = 1.0          # motor + controller (1.0 = wire-to-water folded into pump_efficiency)
    shutoff_head_ratio: float = 1.35       # H_0 / H_r, centrifugal only
    static_head_m: float | None = None     # default: rated head (v0.1 behaviour)
    aquifer_loss_b: float = 0.0
    well_loss_c: float = 0.0
    friction_k: float = 0.0
    table_points: int = 400
    _table: dict = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.kind not in {"positive_displacement", "centrifugal"}:
            raise ValueError("kind must be 'positive_displacement' or 'centrifugal'")
        for name in ("rated_flow_m3_per_hour", "rated_head_m"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if not 0 < self.pump_efficiency <= 1 or not 0 < self.drive_efficiency <= 1:
            raise ValueError("efficiencies must be in (0, 1]")
        if self.kind == "centrifugal" and self.shutoff_head_ratio <= 1:
            raise ValueError("shutoff_head_ratio must be > 1")
        if self.static_head_m is None:
            self.static_head_m = self.rated_head_m
        if min(self.static_head_m, self.aquifer_loss_b, self.well_loss_c, self.friction_k) < 0:
            raise ValueError("static head and loss coefficients must be non-negative")
        self._table = self._build_table()

    # ------------------------------------------------------------------ physics
    def system_head(self, q):
        q = np.asarray(q, dtype=float)
        return (self.static_head_m + self.aquifer_loss_b * q
                + (self.well_loss_c + self.friction_k) * q ** 2)

    def _electric_kw(self, q, head, eta):
        return RHO * G * (np.asarray(q) / 3600.0) * head / (eta * self.drive_efficiency) / 1000.0

    def _build_table(self) -> dict:
        qr, hr = self.rated_flow_m3_per_hour, self.rated_head_m
        if self.kind == "positive_displacement":
            q = np.linspace(0.0, qr, self.table_points)
            head = self.system_head(q)
            eta = np.full_like(q, self.pump_efficiency)
        else:
            h0 = self.shutoff_head_ratio * hr
            a = (h0 - hr) / qr ** 2
            n = np.linspace(0.0, 1.0, self.table_points)
            A = a + self.well_loss_c + self.friction_k
            disc = self.aquifer_loss_b ** 2 - 4.0 * A * (self.static_head_m - n ** 2 * h0)
            q = np.where(n ** 2 * h0 > self.static_head_m,
                         (-self.aquifer_loss_b + np.sqrt(np.maximum(disc, 0.0))) / (2.0 * A),
                         0.0)
            head = self.system_head(q)
            with np.errstate(divide="ignore", invalid="ignore"):
                x = np.where(n > 0, q / (n * qr), 0.0)
            eta = self.pump_efficiency * np.clip(2.0 * x - x ** 2, 0.05, 1.0)
        power = np.where(q > 0, self._electric_kw(q, head, eta), 0.0)
        flowing = q > 1e-9
        if not flowing.any():
            raise ValueError("pump cannot lift water against the static head at full speed")
        # keep the strictly increasing (usable) branch for interpolation
        q_u, p_u, h_u = q[flowing], power[flowing], head[flowing]
        keep = np.concatenate([[True], np.diff(p_u) > 0]) & np.concatenate([[True], np.diff(q_u) > 0])
        return {"q": q_u[keep], "p": p_u[keep], "h": h_u[keep]}

    # --------------------------------------------------------------- interface
    @property
    def max_flow(self) -> float:
        return float(self._table["q"][-1])

    @property
    def max_power_kw(self) -> float:
        return float(self._table["p"][-1])

    @property
    def min_flow(self) -> float:
        """Smallest flow the drive can sustain (0 for an ideal PD pump)."""
        return float(self._table["q"][0])

    @property
    def min_power_kw(self) -> float:
        return float(self._table["p"][0])

    def power_for_flow(self, q: float) -> float:
        if q <= 0:
            return 0.0
        t = self._table
        if self.kind == "positive_displacement" and q < t["q"][0]:
            return float(q / t["q"][0] * t["p"][0]) if t["q"][0] > 0 else 0.0
        return float(np.interp(min(q, t["q"][-1]), t["q"], t["p"]))

    def flow_for_power(self, p_kw: float) -> float:
        t = self._table
        if p_kw <= 0:
            return 0.0
        if self.kind == "centrifugal" and p_kw < t["p"][0]:
            return 0.0  # below minimum drive frequency: controller will not start
        if self.kind == "positive_displacement" and p_kw < t["p"][0]:
            return float(p_kw / t["p"][0] * t["q"][0]) if t["p"][0] > 0 else 0.0
        return float(np.interp(min(p_kw, t["p"][-1]), t["p"], t["q"]))

    def head_at_flow(self, q: float) -> float:
        return float(self.system_head(q)) if q > 0 else float(self.static_head_m)


def legacy_pump(rated_flow: float, head: float, efficiency: float) -> PumpSystem:
    """Reproduce v0.1: ideal PD pump, constant head, constant efficiency."""
    return PumpSystem(kind="positive_displacement", rated_flow_m3_per_hour=rated_flow,
                      rated_head_m=head, pump_efficiency=efficiency)


def borehole_from_test(static_water_level_m: float, delivery_head_m: float,
                       q_test_m3h: float, drawdown_test_m: float,
                       well_loss_fraction: float = 0.3) -> dict:
    """Split a single pumping-test drawdown into B and C coefficients.

    s(Q_test) = B*Q + C*Q^2 with a stated share of the drawdown attributed to
    non-linear well losses. A step-drawdown test should replace this split.
    """
    if not 0 <= well_loss_fraction < 1:
        raise ValueError("well_loss_fraction must be in [0, 1)")
    c = well_loss_fraction * drawdown_test_m / q_test_m3h ** 2
    b = (1 - well_loss_fraction) * drawdown_test_m / q_test_m3h
    return {"static_head_m": static_water_level_m + delivery_head_m,
            "aquifer_loss_b": b, "well_loss_c": c}
