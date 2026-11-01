"""CIS / billing ingest. Apparent loss is a billed-file problem.

Pressure and leftover inlet flow estimate *real* loss. They cannot
split theft, unmetered use, and meter error. That split needs a
customer-information-system export (SmartTerra / Upande / WASREB).

This module is the partner surface: billed volume in, IWA residual
out. It does not raise a leak event from the residual. Unmetered
accounts are tagged, not punished.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sim.balance import _integrate_lps


CIS_COLUMNS = (
    "account_id",
    "node",
    "billed_m3",
    "period_start",
    "period_end",
    "account_class",
)
ACCOUNT_CLASSES = ("metered", "unmetered", "unknown")


@dataclass
class IwaFromCis:
    billed_m3: float
    leftover_real_loss_m3: float
    supplied_m3: float
    apparent_residual_m3: float
    unmetered_tagged_m3: float
    n_accounts: int
    n_unmetered: int
    alarms_from_apparent: bool
    note: str


def _class_of(value: str) -> str:
    v = (value or "unknown").strip().lower()
    return v if v in ACCOUNT_CLASSES else "unknown"


def ingest_cis(source) -> pd.DataFrame:
    """Read a CIS export (path or file-like). Extra columns are kept."""
    df = pd.read_csv(source)
    missing = [c for c in ("account_id", "node", "billed_m3") if c not in df.columns]
    if missing:
        raise ValueError(f"CIS file missing columns {missing}")
    if "account_class" not in df.columns:
        df["account_class"] = "unknown"
    if "period_start" not in df.columns:
        df["period_start"] = ""
    if "period_end" not in df.columns:
        df["period_end"] = ""
    df["billed_m3"] = pd.to_numeric(df["billed_m3"], errors="coerce").fillna(0.0)
    df["account_class"] = df["account_class"].map(_class_of)
    df["account_id"] = df["account_id"].astype(str)
    df["node"] = df["node"].astype(str)
    return df


def export_cis_from_scenario(
    *,
    customer_lps: pd.DataFrame,
    unmetered_share: dict[str, float],
    meter_bias: float,
    timestep_s: float,
    period_start: str = "sim-start",
    period_end: str = "sim-end",
) -> pd.DataFrame:
    """Build a *simulated* CIS extract from the hidden water-balance terms.

    Label every row simulated. This is not a utility billing file.
    """
    rows = []
    for node in customer_lps.columns:
        cust = _integrate_lps(customer_lps[node], timestep_s)
        share = float(unmetered_share.get(node, 0.0))
        unmetered = share * cust
        metered = max(0.0, cust - unmetered)
        billed = metered * (1.0 - float(meter_bias))
        if cust <= 1e-9 and share <= 0.0:
            continue
        rows.append(
            {
                "account_id": f"N-{node}",
                "node": str(node),
                "billed_m3": billed,
                "period_start": period_start,
                "period_end": period_end,
                "account_class": "unmetered" if share > 0.0 else "metered",
                "label": "simulated",
            }
        )
    return pd.DataFrame(rows, columns=list(CIS_COLUMNS) + ["label"])


def split_iwa(
    *,
    supplied_m3: float,
    leftover_real_loss_m3: float,
    cis: pd.DataFrame,
) -> IwaFromCis:
    """IWA residual from leftover (hydraulics) + billed (CIS).

    ``apparent_residual`` is everything that is not leftover and not billed.
    That bag still mixes theft, meter error, and unmetered use. We do not
    open a leak event from it.
    """
    billed = float(cis["billed_m3"].sum()) if len(cis) else 0.0
    unmetered = 0.0
    if len(cis) and "account_class" in cis.columns:
        unmetered = float(cis.loc[cis["account_class"] == "unmetered", "billed_m3"].sum())
        # Unmetered accounts often bill 0; count their *rows*, not billed.
    n_unmetered = int((cis["account_class"] == "unmetered").sum()) if len(cis) else 0
    leftover = max(0.0, float(leftover_real_loss_m3))
    apparent = max(0.0, float(supplied_m3) - leftover - billed)
    return IwaFromCis(
        billed_m3=billed,
        leftover_real_loss_m3=leftover,
        supplied_m3=float(supplied_m3),
        apparent_residual_m3=apparent,
        unmetered_tagged_m3=unmetered,
        n_accounts=int(len(cis)),
        n_unmetered=n_unmetered,
        alarms_from_apparent=False,
        note=(
            "Leftover inlet flow is real loss. The billed file gives the "
            "commercial residual. Pressure cannot split theft from meter error "
            "or unmetered use. Unmetered accounts are tagged, not alarmed."
        ),
    )


def write_cis(path: Path | str, cis: pd.DataFrame) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cis.to_csv(path, index=False)
    return path
