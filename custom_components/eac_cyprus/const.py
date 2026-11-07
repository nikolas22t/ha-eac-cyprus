"""Constants for the EAC Cyprus integration."""

from datetime import timedelta

DOMAIN = "eac_cyprus"

PORTAL = "https://meterreading-dso.eac.com.cy/api/portal"
RATES_URL = "https://electricity-calculator.cy/api/getCurrentRate"
TZ_NAME = "Europe/Nicosia"

CONF_SERVICE_POINT = "service_point"
CONF_BILLING_DAY = "billing_day"
CONF_BILLING_MONTHS = "billing_months"  # "odd" or "even": months in which a billing period starts
CONF_TARIFF = "tariff"
CONF_FIXED_FEES = "fixed_fees"

DEFAULT_BILLING_DAY = 24
DEFAULT_BILLING_MONTHS = "odd"
DEFAULT_TARIFF = "01"
# Meter data management (0.94) + electricity supply (8.00) per bimonthly bill, excl. VAT
DEFAULT_FIXED_FEES = 8.94

VAT = 0.05
UPDATE_INTERVAL = timedelta(hours=6)
HISTORY_DAYS = 400  # downloaded on the first run
REFRESH_DAYS = 150  # downloaded on every later run (covers current + 2 previous bills)

# Fallback prices (tariff 01, €/kWh excl. VAT) if the rates API is unreachable
FALLBACK_RATES = {
    "electricityGeneration": 0.1789,
    "networkUsage": 0.0393,
    "fuelAdjustment": 0.08,
    "publicServiceObligation": 0.00051,
    "resEsFund": 0.005,
}
