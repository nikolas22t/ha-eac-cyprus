"""Billing logic checked against real EAC bills (no Home Assistant needed)."""
import importlib.util, pathlib, sys, types
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "eac_cyprus"
pkg = types.ModuleType("eac_cyprus"); pkg.__path__ = [str(ROOT)]; sys.modules["eac_cyprus"] = pkg
def load(name):
    spec = importlib.util.spec_from_file_location(f"eac_cyprus.{name}", ROOT / f"{name}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m); return m
load("const"); billing = load("billing")
TZ = ZoneInfo("Europe/Nicosia")

def test_bill_24_07_to_24_09_2026():  # €135.48: 1306 in, 940 out, 95 credit, fuel 0.067552
    r = {"electricityGeneration": 0.1789, "networkUsage": 0.0393, "fuelAdjustment": 0.067552,
         "publicServiceObligation": 0.00051, "resEsFund": 0.005}
    b = billing.estimate(1306, 940, 95, r, 8.94)
    assert round(b.net) == 271 and abs(b.total - 135.48) < 0.05

def test_bill_27_05_to_24_07_2026():  # €49.69: export > import → only network, 95 carried forward
    r = {"electricityGeneration": 0.1789, "networkUsage": 0.0393, "fuelAdjustment": 0.05,
         "publicServiceObligation": 0.00051, "resEsFund": 0.005}
    b = billing.estimate(964, 972, 87, r, 8.94)
    assert b.net == 0 and round(b.credit_out) == 95 and abs(b.total - 49.69) < 0.05

def test_bill_03_08_to_02_10_2026():  # €152.81 (other house)
    r = {"electricityGeneration": 0.1789, "networkUsage": 0.0393, "fuelAdjustment": 0.080151,
         "publicServiceObligation": 0.00051, "resEsFund": 0.005}
    assert abs(billing.estimate(1165, 823, 0, r, 8.94).total - 152.81) < 0.05

def test_periods():
    p = billing.billing_period
    assert p(datetime(2026, 11, 7, tzinfo=TZ), 24, "odd")[0].date().isoformat() == "2026-09-24"
    assert p(datetime(2026, 11, 7, tzinfo=TZ), 3, "even")[0].date().isoformat() == "2026-10-03"
    assert p(datetime(2027, 1, 5, tzinfo=TZ), 3, "even")[0].date().isoformat() == "2026-12-03"
    s, e = p(datetime(2026, 12, 1, tzinfo=TZ), 24, "odd")
    assert (s.date().isoformat(), e.date().isoformat()) == ("2026-11-24", "2027-01-24")
