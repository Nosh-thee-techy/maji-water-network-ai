"""Corrupt clean hydraulic fields into the only signal solvers may see.

Solvers never receive the clean pressure field or leak labels. They
get: pressure at a sensor subset + inlet flow, with Gaussian noise and
independent dropouts (NaN).
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


# Cheap 10-bar gauge, roughly ±0.3 m RMS after a crude field calibration.
# Full-scale ±1% of 10 bar would be ±1 m; we use a tighter value so the
# inverse problem is not dominated by noise on this small DMA.
DEFAULT_PRESSURE_SIGMA_M = 0.30
DEFAULT_FLOW_SIGMA_LPS = 0.15
DEFAULT_DROPOUT_P = 0.03


def corrupt_frame(
    clean: pd.DataFrame,
    columns: Iterable[str],
    rng: np.random.Generator,
    sigma: float,
    dropout_p: float = DEFAULT_DROPOUT_P,
) -> pd.DataFrame:
    """Return a copy of ``clean[columns]`` with noise and NaN dropouts."""
    cols = list(columns)
    values = clean[cols].to_numpy(dtype=float).copy()
    values += rng.normal(0.0, sigma, size=values.shape)
    if dropout_p > 0.0:
        mask = rng.random(values.shape) < dropout_p
        values[mask] = np.nan
    return pd.DataFrame(values, index=clean.index, columns=cols)


def make_observations(
    pressure_m: pd.DataFrame,
    inlet_flow_lps: pd.Series,
    sensors: list[str],
    *,
    seed: int,
    pressure_sigma_m: float = DEFAULT_PRESSURE_SIGMA_M,
    flow_sigma_lps: float = DEFAULT_FLOW_SIGMA_LPS,
    dropout_p: float = DEFAULT_DROPOUT_P,
) -> dict:
    rng = np.random.default_rng(seed)
    p_obs = corrupt_frame(pressure_m, sensors, rng, pressure_sigma_m, dropout_p)
    flow = inlet_flow_lps.to_numpy(dtype=float).copy()
    flow += rng.normal(0.0, flow_sigma_lps, size=flow.shape)
    if dropout_p > 0.0:
        flow[rng.random(flow.shape) < dropout_p] = np.nan
    return {
        "sensors": list(sensors),
        "pressure_sigma_m": pressure_sigma_m,
        "flow_sigma_lps": flow_sigma_lps,
        "dropout_p": dropout_p,
        "pressure_m": p_obs,
        "inlet_flow_lps": pd.Series(flow, index=inlet_flow_lps.index, name="inlet_flow_lps"),
    }
