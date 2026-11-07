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
