"""Data update coordinator: downloads EAC readings, imports statistics, estimates the bill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
from .billing import Bill, billing_period, carried_credit, estimate, kwh_prices, sum_between
from .const import (
    CONF_BILLING_DAY,
    CONF_BILLING_MONTHS,
    CONF_FIXED_FEES,
    CONF_SERVICE_POINT,
    CONF_TARIFF,
    DEFAULT_BILLING_DAY,
    DEFAULT_BILLING_MONTHS,
    DEFAULT_FIXED_FEES,
    DEFAULT_TARIFF,
    DOMAIN,
    HISTORY_DAYS,
    REFRESH_DAYS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class EacData:
    """What the sensors show."""

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


class EacCoordinator(DataUpdateCoordinator[EacData]):
    """Fetch readings every few hours (EAC publishes them about a day late)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.sp_id: str = entry.data[CONF_SERVICE_POINT]
        self.client = EacClient(async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
        self._first_run = True

    def stat_id(self, kind: str) -> str:
        """External statistic id, e.g. eac_cyprus:123456789012_consumption."""
        return f"{DOMAIN}:{self.sp_id}_{kind}"

    def _opt(self, key: str, default):
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    async def _async_update_data(self) -> EacData:
        days = HISTORY_DAYS if self._first_run else REFRESH_DAYS
        try:
            await self.client.login()
            raw = await self.client.download_xlsx(self.sp_id, days)
        except EacAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EacError as err:
            raise UpdateFailed(str(err)) from err
        readings: Readings = await self.hass.async_add_executor_job(parse_xlsx, raw)
        tariff = self._opt(CONF_TARIFF, DEFAULT_TARIFF)
        rates, live = await fetch_rates(async_get_clientsession(self.hass), tariff)
        p_imp, p_exp = kwh_prices(rates)

        if readings.imported:
            await self._import(readings.imported, "consumption", "EAC grid consumption", UnitOfEnergy.KILO_WATT_HOUR, 1.0)
            await self._import(readings.exported, "export", "EAC grid export", UnitOfEnergy.KILO_WATT_HOUR, 1.0)
            await self._import(readings.imported, "cost", "EAC grid cost", "EUR", p_imp)
            await self._import(readings.exported, "compensation", "EAC grid compensation", "EUR", p_exp)
        self._first_run = False
        return self._build(readings, rates, live, p_imp, p_exp)

    async def _import(self, hours: dict[datetime, float], kind: str, name: str, unit: str, factor: float) -> None:
        """Write hourly values as an external statistic, continuing the running sum."""
        if not hours:
            return
        sid = self.stat_id(kind)
        first = next(iter(hours))
        total = await get_instance(self.hass).async_add_executor_job(self._sum_before, sid, first)
        stats: list[StatisticData] = []
        for hour, value in hours.items():
            total += value * factor
            stats.append(StatisticData(start=hour, state=round(value * factor, 4), sum=round(total, 4)))
        meta = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=name,
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

    def _build(self, r: Readings, rates: dict[str, float], live: bool, p_imp: float, p_exp: float) -> EacData:
        day = int(self._opt(CONF_BILLING_DAY, DEFAULT_BILLING_DAY))
        months = self._opt(CONF_BILLING_MONTHS, DEFAULT_BILLING_MONTHS)
        fees = float(self._opt(CONF_FIXED_FEES, DEFAULT_FIXED_FEES))
        now = datetime.now(TZ)
        start, end = billing_period(now, day, months)
        imp = sum_between(r.imported, start, end)
        exp = sum_between(r.exported, start, end)
        # credit units: chain from the oldest complete period we downloaded (assumed 0 there)
        credit = 0.0
        if r.imported:
            oldest = next(iter(r.imported)).astimezone(TZ)
            p_start, p_end = billing_period(oldest, day, months)
            first_full = p_start if p_start >= oldest else p_end
            credit = carried_credit(r.imported, r.exported, first_full, start, day, months)
        bill = estimate(imp, exp, credit, rates, fees)
        data_until = (max(r.imported) + timedelta(hours=1)).astimezone(TZ) if r.imported else None
        frac = ((data_until - start) / (end - start)) if data_until and data_until > start else 0
        fixed = fees * 1.05
        projected = (bill.total - fixed) / frac + fixed if frac > 0.02 else bill.total
        last_day = last_imp = last_exp = None
        if data_until:
            d_end = data_until.replace(hour=0, minute=0, second=0, microsecond=0)
            d_start = d_end - timedelta(days=1)
            last_day = d_start.date().isoformat()
            last_imp = round(sum_between(r.imported, d_start, d_end), 2)
            last_exp = round(sum_between(r.exported, d_start, d_end), 2)
        return EacData(start, end, data_until, bill, projected, p_imp, p_exp, rates, live, last_day, last_imp, last_exp)
