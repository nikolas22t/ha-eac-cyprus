"""Bimonthly EAC bill estimation with net metering (pure logic, no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import VAT


def billing_period(now: datetime, day: int, months: str) -> tuple[datetime, datetime]:
    """Return [start, end) of the bimonthly billing period containing `now` (tz-aware).

    `months` is "odd" or "even": the months in which billing periods start.
    """
    parity = 1 if months == "odd" else 0
    y, m = now.year, now.month
    if m % 2 != parity:
        m -= 1
    elif now.day < day:
        m -= 2
    if m < 1:
        m += 12
        y -= 1
    start = now.replace(year=y, month=m, day=day, hour=0, minute=0, second=0, microsecond=0)
    em, ey = (m + 2, y) if m + 2 <= 12 else (m - 10, y + 1)
    return start, start.replace(year=ey, month=em)


def kwh_prices(rates: dict[str, float]) -> tuple[float, float]:
    """(price per imported kWh, credit per exported kWh), VAT included.

    Under net metering an exported kWh offsets generation + fuel adjustment (+RES fund),
    but the network charge and PSO are always paid on every imported kWh.
    """
    gen = rates["electricityGeneration"] + rates["fuelAdjustment"]
    imp = (gen + rates["networkUsage"] + rates["publicServiceObligation"]) * (1 + VAT) + rates["resEsFund"]
    exp = gen * (1 + VAT) + rates["resEsFund"]
    return imp, exp


@dataclass
class Bill:
    """Estimated bill for one period."""

    imported: float
    exported: float
    credit_in: float
    credit_out: float
    net: float
    energy: float
    fuel_adjustment: float
    network: float
    pso: float
    fixed: float
    vat: float
    res_fund: float
    total: float


def estimate(imported: float, exported: float, credit_in: float, rates: dict[str, float], fixed_fees: float) -> Bill:
    """Reproduce the EAC bimonthly bill (tariff with net metering)."""
    net = max(0.0, imported - exported - credit_in)
    credit_out = max(0.0, credit_in + exported - imported)
    energy = net * rates["electricityGeneration"]
    fuel = net * rates["fuelAdjustment"]
    network = imported * rates["networkUsage"]
    pso = imported * rates["publicServiceObligation"]
    base = energy + fuel + network + pso + fixed_fees
    vat = base * VAT
    res = net * rates["resEsFund"]
    return Bill(imported, exported, credit_in, credit_out, net, energy, fuel, network, pso,
                fixed_fees, vat, res, base + vat + res)


def sum_between(hours: dict[datetime, float], start: datetime, end: datetime) -> float:
    """Sum hourly values with start <= hour < end."""
    return sum(v for h, v in hours.items() if start <= h < end)


def carried_credit(imported: dict[datetime, float], exported: dict[datetime, float],
                   first_start: datetime, current_start: datetime, day: int, months: str) -> float:
    """Chain credit units through the complete periods between first_start and current_start (credit 0 at first_start)."""
    credit = 0.0
    x = first_start
    while x < current_start:
        _, nxt = billing_period(x + timedelta(hours=12), day, months)
        credit = max(0.0, credit + sum_between(exported, x, nxt) - sum_between(imported, x, nxt))
        x = nxt
    return credit


# ---------------------------------------------------------------- aggregations for cards

def daily_totals(imported: dict[datetime, float], exported: dict[datetime, float], tz, days: int) -> list[list]:
    """[[YYYY-MM-DD, import, export], ...] for the last `days` days that have data (local dates)."""
    out: dict[str, list[float]] = {}
    for src, idx in ((imported, 0), (exported, 1)):
        for h, v in src.items():
            d = h.astimezone(tz).date().isoformat()
            out.setdefault(d, [0.0, 0.0])[idx] += v
    keys = sorted(out)[-days:]
    return [[k, round(out[k][0], 2), round(out[k][1], 2)] for k in keys]


def monthly_totals(imported: dict[datetime, float], exported: dict[datetime, float], tz, months: int) -> list[list]:
    """[[YYYY-MM, import, export], ...] for the last `months` calendar months."""
    out: dict[str, list[float]] = {}
    for src, idx in ((imported, 0), (exported, 1)):
        for h, v in src.items():
            m = h.astimezone(tz).strftime("%Y-%m")
            out.setdefault(m, [0.0, 0.0])[idx] += v
    keys = sorted(out)[-months:]
    return [[k, round(out[k][0], 1), round(out[k][1], 1)] for k in keys]


def hourly_profile(imported: dict[datetime, float], exported: dict[datetime, float], tz,
                   end: datetime, days: int) -> list[list]:
    """Average kWh per local hour-of-day over the `days` days before `end`: [[hour, import, export] x24]."""
    start = end - timedelta(days=days)
    acc = [[0.0, 0.0] for _ in range(24)]
    seen: set = set()
    for src, idx in ((imported, 0), (exported, 1)):
        for h, v in src.items():
            if start <= h < end:
                loc = h.astimezone(tz)
                acc[loc.hour][idx] += v
                seen.add(loc.date())
    n = max(1, len(seen))
    return [[i, round(a / n, 3), round(b / n, 3)] for i, (a, b) in enumerate(acc)]


def period_history(imported: dict[datetime, float], exported: dict[datetime, float], day: int, months: str,
                   first_start: datetime, current_start: datetime, credit0: float,
                   rates: dict[str, float], fixed_fees: float) -> tuple[list[dict], float]:
    """Estimate every complete billing period from first_start up to current_start.

    Returns (periods newest-first, credit carried into the current period).
    """
    out: list[dict] = []
    credit = credit0
    x = first_start
    while x < current_start:
        _, nxt = billing_period(x + timedelta(hours=12), day, months)
        imp, exp = sum_between(imported, x, nxt), sum_between(exported, x, nxt)
        b = estimate(imp, exp, credit, rates, fixed_fees)
        out.append({"start": x.date().isoformat(), "end": (nxt - timedelta(days=1)).date().isoformat(),
                    "import": round(imp, 1), "export": round(exp, 1), "credit_in": round(credit, 1),
                    "credit_out": round(b.credit_out, 1), "billable": round(b.net, 1), "total": round(b.total, 2)})
        credit = b.credit_out
        x = nxt
    return out[::-1], credit
