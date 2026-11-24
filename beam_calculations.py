"""Beam statics, section checks, and deflection calculations for Beam Designer."""
from __future__ import annotations

import numpy as np

STEEL = {
    "W8x10": {"Ix": 30.8, "Sx": 7.81, "weight": 10.0},
    "W10x12": {"Ix": 53.8, "Sx": 10.9, "weight": 12.0},
    "W12x26": {"Ix": 204.0, "Sx": 33.4, "weight": 26.0},
    "W14x22": {"Ix": 199.0, "Sx": 29.0, "weight": 22.0},
    "W16x26": {"Ix": 301.0, "Sx": 38.4, "weight": 26.0},
    "W18x35": {"Ix": 510.0, "Sx": 57.6, "weight": 35.0},
    "W21x44": {"Ix": 843.0, "Sx": 81.6, "weight": 44.0},
    "W24x55": {"Ix": 1350.0, "Sx": 114.0, "weight": 55.0},
}
LUMBER = {
    "2x8": {"Ix": 47.63, "Sx": 13.14},
    "2x10": {"Ix": 98.93, "Sx": 21.39},
    "2x12": {"Ix": 177.98, "Sx": 31.64},
}
MATERIALS = {
    "Steel": {"E": 29000.0, "Fb": 30.0, "sections": STEEL},
    "Douglas Fir-Larch No. 2": {"E": 1600.0, "Fb": 0.900, "sections": LUMBER},
}


def calculate_beam(support: str, span: float, material: str, section: str,
                   limit: int, loads: list[dict], step: float = 0.01) -> dict:
    """Return reactions, diagrams, checks, and a lightest passing section.

    Point loads have {type:'point', magnitude: kips downward, position: ft}.
    Uniform loads have {type:'uniform', magnitude: kips/ft downward,
    start: ft, end: ft}. Loads extending beyond the beam are clipped.
    """
    L = float(span)
    if L <= 0:
        raise ValueError("Span must be positive.")
    if support not in ("Simply supported", "Cantilever"):
        raise ValueError("Choose a supported support type.")
    clipped = []
    for load in loads:
        mag = float(load["magnitude"])
        if not np.isfinite(mag) or mag < 0:
            raise ValueError("Load magnitudes must be nonnegative numbers.")
        if load["type"] == "point":
            a = min(max(float(load["position"]), 0.0), L)
            clipped.append({"type": "point", "magnitude": mag, "position": a})
        else:
            a = min(max(float(load["start"]), 0.0), L)
            b = min(max(float(load["end"]), 0.0), L)
            if b < a:
                a, b = b, a
            clipped.append({"type": "uniform", "magnitude": mag, "start": a, "end": b})
    total = sum(q["magnitude"] for q in clipped if q["type"] == "point")
    total += sum(q["magnitude"] * (q["end"] - q["start"]) for q in clipped if q["type"] == "uniform")
    moment_loads = sum(q["magnitude"] * q["position"] for q in clipped if q["type"] == "point")
    moment_loads += sum(q["magnitude"] * (q["end"]**2 - q["start"]**2) / 2 for q in clipped if q["type"] == "uniform")
    if support == "Simply supported":
        right = moment_loads / L
        left = total - right
    else:
        left, right = total, 0.0

    specials = [0.0, L]
    for q in clipped:
        specials.append(q.get("position", q.get("start", 0.0)))
        if q["type"] == "uniform":
            specials.append(q["end"])
    xs = np.unique(np.concatenate((np.linspace(0, L, max(2, int(np.ceil(L / step)) + 1)), specials)))
    shear = np.full(xs.shape, left, dtype=float)
    moment = np.zeros(xs.shape, dtype=float)
    if support == "Simply supported":
        moment = left * xs
        for q in clipped:
            if q["type"] == "point":
                shear -= np.where(xs >= q["position"] - 1e-11, q["magnitude"], 0.0)
                moment -= q["magnitude"] * np.maximum(xs - q["position"], 0.0)
            else:
                a, b, w = q["start"], q["end"], q["magnitude"]
                shear -= w * np.clip(xs - a, 0.0, b - a)
                moment -= w * (np.maximum(xs - a, 0.0)**2 - np.maximum(xs - b, 0.0)**2) / 2
    else:
        # Internal cantilever moment is the moment of the loads to the right of the cut.
        for q in clipped:
            if q["type"] == "point":
                shear -= np.where(xs >= q["position"] - 1e-11, q["magnitude"], 0.0)
                moment -= q["magnitude"] * np.maximum(q["position"] - xs, 0.0)
            else:
                a, b, w = q["start"], q["end"], q["magnitude"]
                shear -= w * np.clip(b - np.maximum(xs, a), 0.0, b - a)
                lo = np.maximum(xs, a)
                moment -= w * (np.maximum(b - xs, 0.0)**2 - np.maximum(lo - xs, 0.0)**2) / 2
    # Enforce the free-end boundary value for numerical roundoff.
    if support == "Cantilever":
        moment[-1] = 0.0

    # Integrate y'' = M/EI. M is kip-ft, converted to kip-in; x to inches.
    E = MATERIALS[material]["E"]
    Ix = MATERIALS[material]["sections"][section]["Ix"]
    xin = xs * 12.0
    curvature = moment * 12.0 / (E * Ix)
    slope0 = np.concatenate(([0.0], np.cumsum((curvature[:-1] + curvature[1:]) * np.diff(xin) / 2)))
    yraw = np.concatenate(([0.0], np.cumsum((slope0[:-1] + slope0[1:]) * np.diff(xin) / 2)))
    if support == "Simply supported":
        y = yraw - (xin / xin[-1]) * yraw[-1]
    else:
        y = yraw
    secs = MATERIALS[material]["sections"]
    current = secs[section]
    max_m_i = int(np.argmax(np.abs(moment)))
    max_y_i = int(np.argmax(np.abs(y)))
    max_v = float(np.max(np.abs(shear))) if len(shear) else 0.0
    max_m = float(abs(moment[max_m_i]))
    stress = max_m * 12.0 / current["Sx"]
    allow_defl = L * 12.0 / int(limit)
    lightest = None
    for name, props in secs.items():
        fb = max_m * 12 / props["Sx"]
        # Deflection scales inversely with Ix and linearly with 1/E; same material here.
        yy = float(np.max(np.abs(y))) * current["Ix"] / props["Ix"]
        if fb <= MATERIALS[material]["Fb"] and yy <= allow_defl:
            weight = props.get("weight", 0)
            if material != "Steel":
                lightest = {"section": name, "weight": weight}
                break
            if lightest is None or weight < lightest["weight"] or (weight == lightest["weight"] and props["Ix"] > secs[lightest["section"]]["Ix"]):
                lightest = {"section": name, "weight": weight}
    return {
        "x": xs, "V": shear, "M": moment, "deflection": y,
        "left_reaction": float(left), "right_reaction": float(right),
        "fixed_moment": float(-moment[0]) if support == "Cantilever" else 0.0,
        "max_shear": max_v, "max_moment": max_m, "max_moment_x": float(xs[max_m_i]),
        "stress": float(stress), "allow_stress": float(MATERIALS[material]["Fb"]),
        "max_deflection": float(abs(y[max_y_i])), "max_deflection_x": float(xs[max_y_i]),
        "allow_deflection": float(allow_defl), "bending_pass": stress <= MATERIALS[material]["Fb"],
        "deflection_pass": abs(y[max_y_i]) <= allow_defl, "lightest": lightest,
        "loads": clipped,
    }
