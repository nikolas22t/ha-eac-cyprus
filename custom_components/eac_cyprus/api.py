"""Client for the EAC DSO meter-reading portal (meterreading-dso.eac.com.cy)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import io
import logging
from zoneinfo import ZoneInfo

import aiohttp

from .const import FALLBACK_RATES, PORTAL, RATES_URL, TZ_NAME

_LOGGER = logging.getLogger(__name__)
TZ = ZoneInfo(TZ_NAME)
UTC = ZoneInfo("UTC")


class EacError(Exception):
    """Generic EAC portal error."""


class EacAuthError(EacError):
    """Wrong e-mail or password."""


@dataclass
class ServicePoint:
    """A supply (premise) on the account."""

    id: str
    address: str
    meter: str | None = None


@dataclass
class Readings:
    """Hourly kWh (UTC hour start -> kWh) for consumption (import) and generation (export)."""

    imported: dict[datetime, float] = field(default_factory=dict)
    exported: dict[datetime, float] = field(default_factory=dict)


class EacClient:
    """Minimal async client for the EAC portal."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._jwt: str | None = None

    async def login(self) -> None:
        """Log in and keep the JWT."""
        try:
            async with self._session.post(
                f"{PORTAL}/login",
                json={"email": self._email, "password": self._password},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status in (401, 403):
                    raise EacAuthError("Invalid e-mail or password")
                if resp.status != 200:
                    raise EacError(f"Login failed: HTTP {resp.status}")
                self._jwt = (await resp.json(content_type=None))["jwt"]
        except aiohttp.ClientError as err:
            raise EacError(f"Cannot reach EAC portal: {err}") from err

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._jwt}"}

    async def service_points(self) -> list[ServicePoint]:
        """Return the supplies registered on the account."""
        if not self._jwt:
            await self.login()
        async with self._session.get(
            f"{PORTAL}/servicePoints", headers=self._headers(), timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status != 200:
                raise EacError(f"servicePoints: HTTP {resp.status}")
            data = await resp.json(content_type=None)
        return [ServicePoint(sp["id"], sp.get("address", ""), sp.get("serialNumber")) for sp in data]

    async def download_xlsx(self, sp_id: str, days: int) -> bytes:
        """Download the 'readings & consumption' report (XLSX) for the last `days` days."""
        if not self._jwt:
            await self.login()
        now = datetime.now(TZ).replace(hour=12, minute=0, second=0, microsecond=0)

        def iso(d: datetime) -> str:
            return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        body = {"spId": sp_id, "dateFrom": iso(now - timedelta(days=days)), "dateTo": iso(now)}
        async with self._session.post(
            f"{PORTAL}/report/scalarinterval/xlsx",
            json=body,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            if resp.status in (401, 403):
                raise EacAuthError("Session rejected")
            if resp.status != 200:
                raise EacError(f"report: HTTP {resp.status}")
            data = await resp.read()
        if data[:2] != b"PK":
            raise EacError("EAC did not return an XLSX file")
        return data


def parse_xlsx(data: bytes) -> Readings:
    """Parse the interval sheet: 30-minute kWh, timestamp = end of interval (local time)."""
    import openpyxl  # noqa: PLC0415 - heavy import, done in the executor

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = next((ws for ws in wb.worksheets if ws.title.lower().startswith("interval")), None)
    out = Readings()
    if sheet is None:
        return out
    imp: dict[datetime, float] = defaultdict(float)
    exp: dict[datetime, float] = defaultdict(float)
    for row in sheet.iter_rows(values_only=True):
        if len(row) < 3 or not isinstance(row[1], str) or not isinstance(row[2], (int, float)):
            continue
        try:
            end = datetime.strptime(row[1], "%d.%m.%Y %H:%M:%S").replace(tzinfo=TZ)
        except ValueError:
            continue
        hour = (end - timedelta(minutes=30)).replace(minute=0, second=0).astimezone(UTC)
        imp[hour] += float(row[2])
        if len(row) > 3 and isinstance(row[3], (int, float)):
            exp[hour] += float(row[3])
    out.imported = dict(sorted(imp.items()))
    out.exported = dict(sorted(exp.items()))
    return out


async def fetch_rates(session: aiohttp.ClientSession, tariff: str) -> tuple[dict[str, float], bool]:
    """Current tariff breakdown (€/kWh excl. VAT). Returns (rates, live)."""
    try:
        async with session.get(
            RATES_URL, params={"tariffCode": tariff}, timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "home-assistant-eac-cyprus"},
        ) as resp:
            data = (await resp.json(content_type=None))["breakdown"]
        rates = {k: float(data.get(k, FALLBACK_RATES[k])) for k in FALLBACK_RATES}
        return rates, True
    except (aiohttp.ClientError, KeyError, ValueError, TimeoutError) as err:
        _LOGGER.warning("Electricity rates API unavailable, using fallback prices: %s", err)
        return dict(FALLBACK_RATES), False
