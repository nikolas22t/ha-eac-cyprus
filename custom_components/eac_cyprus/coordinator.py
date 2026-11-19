"""Data update coordinator: downloads EAC readings, imports statistics, estimates the bill."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TZ, EacAuthError, EacClient, EacError, Readings, fetch_rates, parse_xlsx
from .billing import (
    Bill,
    billing_period,
    daily_totals,
    estimate,
    hourly_profile,
    kwh_prices,
    monthly_totals,
    period_history,
    sum_between,
)
from .const import (
    CONF_BILLING_DAY,
    CONF_BILLING_MONTHS,
    CONF_CREDIT_DATE,
    CONF_CREDIT_KWH,
    CONF_FIXED_FEES,
    CONF_SCAN_HOURS,
    CONF_SERVICE_POINT,
    CONF_STALE_DAYS,
    CONF_TARIFF,
    DAILY_DAYS,
    DEFAULT_BILLING_DAY,
    DEFAULT_BILLING_MONTHS,
    DEFAULT_FIXED_FEES,
    DEFAULT_SCAN_HOURS,
    DEFAULT_STALE_DAYS,
    DEFAULT_TARIFF,
    DOMAIN,
    FULL_HISTORY_YEARS,
    HISTORY_DAYS,
    MONTHS_KEPT,
    PROFILE_DAYS,
    REFRESH_DAYS,
    VAT,
)

_LOGGER = logging.getLogger(__name__)
KINDS = (("consumption", "EAC grid consumption"), ("export", "EAC grid export"),
         ("cost", "EAC grid cost"), ("compensation", "EAC grid compensation"))


@dataclass
class EacData:
    """What the sensors and cards show."""

    period_start: datetime
    period_end: datetime
    data_until: datetime | None
    bill: Bill
    projected_total: float
    import_price: float
    export_credit: float
    rates: dict[str, float]
    rates_live: bool
    last_day: str | None
    last_day_import: float | None
    last_day_export: float | None
    fixed_fees: float
    fetched_at: datetime
    lag_hours: float | None
    stale: bool
    daily: list = field(default_factory=list)
    monthly: list = field(default_factory=list)
    periods: list = field(default_factory=list)
    profile: list = field(default_factory=list)
    last_bill: dict | None = None
    days_in_period: int = 0
    days_elapsed: float = 0.0


class EacCoordinator(DataUpdateCoordinator[EacData]):
    """Fetch readings every few hours (EAC publishes them about a day late)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        hours = float(entry.options.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS))
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=timedelta(hours=hours))
        self.sp_id: str = entry.data[CONF_SERVICE_POINT]
        self.client = EacClient(async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
        self._first_run = True
        # hourly readings kept in memory between polls (UTC hour -> kWh)
        self._imp: dict[datetime, float] = {}
        self._exp: dict[datetime, float] = {}

    def stat_id(self, kind: str) -> str:
        """External statistic id, e.g. eac_cyprus:123456789012_consumption."""
        return f"{DOMAIN}:{self.sp_id}_{kind}"

    def _opt(self, key: str, default):
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    # ------------------------------------------------------------------ polling
    async def _download(self, days: int, until: datetime | None = None) -> Readings:
        try:
            await self.client.login()
            raw = await self.client.download_xlsx(self.sp_id, days, until)
        except EacAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EacError as err:
            raise UpdateFailed(str(err)) from err
        return await self.hass.async_add_executor_job(parse_xlsx, raw)

    async def _async_update_data(self) -> EacData:
        days = HISTORY_DAYS if self._first_run else REFRESH_DAYS
        readings = await self._download(days)
        self._imp.update(readings.imported)
        self._exp.update(readings.exported)
        self._imp = dict(sorted(self._imp.items()))
        self._exp = dict(sorted(self._exp.items()))
        rates, live = await fetch_rates(async_get_clientsession(self.hass), self._opt(CONF_TARIFF, DEFAULT_TARIFF))
        p_imp, p_exp = kwh_prices(rates)
        if readings.imported:
            await self._import_all(readings.imported, readings.exported, p_imp, p_exp, reset=False)
        self._first_run = False
        return self._build(rates, live, p_imp, p_exp)

    async def async_import_full_history(self) -> dict:
        """Download everything the portal has (year by year) and rewrite all statistics from zero."""
        imp: dict[datetime, float] = {}
        exp: dict[datetime, float] = {}
        until = datetime.now(TZ)
        for _ in range(FULL_HISTORY_YEARS):
            r = await self._download(366, until)
            if not r.imported:
                break
            imp.update(r.imported)
            exp.update(r.exported)
            until -= timedelta(days=365)
        imp, exp = dict(sorted(imp.items())), dict(sorted(exp.items()))
        if not imp:
            return {"hours": 0}
        rates, _ = await fetch_rates(async_get_clientsession(self.hass), self._opt(CONF_TARIFF, DEFAULT_TARIFF))
        p_imp, p_exp = kwh_prices(rates)
        await self._import_all(imp, exp, p_imp, p_exp, reset=True)
        self._imp.update(imp)
        self._exp.update(exp)
        self._imp = dict(sorted(self._imp.items()))
        self._exp = dict(sorted(self._exp.items()))
        self.async_set_updated_data(self._build(rates, True, p_imp, p_exp))
        first = next(iter(imp)).astimezone(TZ).date().isoformat()
        return {"hours": len(imp), "from": first, "import_kwh": round(sum(imp.values()), 1),
                "export_kwh": round(sum(exp.values()), 1)}

    async def _import_all(self, imp, exp, p_imp: float, p_exp: float, reset: bool) -> None:
        await self._import(imp, "consumption", UnitOfEnergy.KILO_WATT_HOUR, 1.0, reset)
        await self._import(exp, "export", UnitOfEnergy.KILO_WATT_HOUR, 1.0, reset)
        await self._import(imp, "cost", "EUR", p_imp, reset)
        await self._import(exp, "compensation", "EUR", p_exp, reset)

    async def _import(self, hours: dict[datetime, float], kind: str, unit: str, factor: float, reset: bool) -> None:
        """Write hourly values as an external statistic, continuing the running sum."""
        if not hours:
            return
        sid = self.stat_id(kind)
        first = next(iter(hours))
        total = 0.0 if reset else await get_instance(self.hass).async_add_executor_job(self._sum_before, sid, first)
        stats: list[StatisticData] = []
        for hour, value in hours.items():
            total += value * factor
            stats.append(StatisticData(start=hour, state=round(value * factor, 4), sum=round(total, 4)))
        meta = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=dict(KINDS)[kind],
            source=DOMAIN,
            statistic_id=sid,
            unit_class="energy" if unit == UnitOfEnergy.KILO_WATT_HOUR else None,
            unit_of_measurement=unit,
        )
        async_add_external_statistics(self.hass, meta, stats)

    def _sum_before(self, sid: str, first: datetime) -> float:
        """Running sum of `sid` at the last hour before `first` (0 if none)."""
        rows = statistics_during_period(self.hass, first - timedelta(days=60), first, {sid}, "hour", None, {"sum"})
        if rows.get(sid):
            return float(rows[sid][-1]["sum"] or 0)
        last = get_last_statistics(self.hass, 1, sid, True, {"sum"})
        if last.get(sid) and last[sid][0]["start"] < first.timestamp():
            return float(last[sid][0]["sum"] or 0)
        return 0.0

    # ------------------------------------------------------------------ figures
    def _credit_start(self, day: int, months: str) -> tuple[datetime | None, float]:
        """Where to start chaining credit units: the configured anchor, else the oldest full period."""
        anchor = self._opt(CONF_CREDIT_DATE, None)
        if anchor:
            try:
                d = date.fromisoformat(str(anchor))
                start, _ = billing_period(datetime(d.year, d.month, d.day, 12, tzinfo=TZ), day, months)
                return start, float(self._opt(CONF_CREDIT_KWH, 0) or 0)
            except ValueError:
                _LOGGER.warning("Ignoring invalid credit anchor date %s", anchor)
        if not self._imp:
            return None, 0.0
        oldest = next(iter(self._imp)).astimezone(TZ)
        p_start, p_end = billing_period(oldest, day, months)
        return (p_start if p_start >= oldest else p_end), 0.0

    def _build(self, rates: dict[str, float], live: bool, p_imp: float, p_exp: float) -> EacData:
        r_imp, r_exp = self._imp, self._exp
        day = int(self._opt(CONF_BILLING_DAY, DEFAULT_BILLING_DAY))
        months = self._opt(CONF_BILLING_MONTHS, DEFAULT_BILLING_MONTHS)
        fees = float(self._opt(CONF_FIXED_FEES, DEFAULT_FIXED_FEES))
        now = datetime.now(TZ)
        start, end = billing_period(now, day, months)

        periods: list[dict] = []
        credit = 0.0
        c_start, c0 = self._credit_start(day, months)
        if c_start is not None and c_start <= start:
            periods, credit = period_history(r_imp, r_exp, day, months, c_start, start, c0, rates, fees)

        bill = estimate(sum_between(r_imp, start, end), sum_between(r_exp, start, end), credit, rates, fees)
        data_until = (max(r_imp) + timedelta(hours=1)).astimezone(TZ) if r_imp else None
        frac = ((data_until - start) / (end - start)) if data_until and data_until > start else 0
        fixed = fees * (1 + VAT)
        projected = (bill.total - fixed) / frac + fixed if frac > 0.02 else bill.total

        last_day = last_imp = last_exp = None
        profile: list = []
        if data_until:
            d_end = data_until.replace(hour=0, minute=0, second=0, microsecond=0)
            d_start = d_end - timedelta(days=1)
            last_day = d_start.date().isoformat()
            last_imp = round(sum_between(r_imp, d_start, d_end), 2)
            last_exp = round(sum_between(r_exp, d_start, d_end), 2)
            profile = hourly_profile(r_imp, r_exp, TZ, d_end, PROFILE_DAYS)

        lag = (now - data_until).total_seconds() / 3600 if data_until else None
        stale_days = float(self._opt(CONF_STALE_DAYS, DEFAULT_STALE_DAYS))
        return EacData(
            period_start=start, period_end=end, data_until=data_until, bill=bill, projected_total=projected,
            import_price=p_imp, export_credit=p_exp, rates=rates, rates_live=live, last_day=last_day,
            last_day_import=last_imp, last_day_export=last_exp, fixed_fees=fees, fetched_at=now,
            lag_hours=round(lag, 1) if lag is not None else None,
            stale=lag is None or lag > stale_days * 24,
            daily=daily_totals(r_imp, r_exp, TZ, DAILY_DAYS),
            monthly=monthly_totals(r_imp, r_exp, TZ, MONTHS_KEPT),
            periods=periods[:12],
            profile=profile,
            last_bill=periods[0] if periods else None,
            days_in_period=(end - start).days,
            days_elapsed=round(max(0.0, (now - start).total_seconds() / 86400), 1),
        )
