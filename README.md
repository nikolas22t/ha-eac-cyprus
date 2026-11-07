# EAC Cyprus for Home Assistant

Brings your **Electricity Authority of Cyprus (EAC / ΑΗΚ) smart-meter data** into Home Assistant and estimates your **next bill**, including **net metering** (συμψηφισμός μετρήσεων) for homes with solar.

It signs in to the official EAC meter-reading portal ([meterreading-dso.eac.com.cy](https://meterreading-dso.eac.com.cy)) with your own account, the same way you would in the browser.

> Unofficial. Not affiliated with or endorsed by the Electricity Authority of Cyprus.

## What you get

**Energy dashboard history** (hourly, imported with the real timestamps):

| Statistic | Use it in *Settings → Dashboards → Energy → Electricity grid* as |
|---|---|
| `eac_cyprus:<supply>_consumption` | Grid consumption |
| `eac_cyprus:<supply>_export` | Return to grid |
| `eac_cyprus:<supply>_cost` | "Use an entity tracking the total costs" (consumption) |
| `eac_cyprus:<supply>_compensation` | "Use an entity tracking the total compensation" (return) |

On the first run it downloads about 13 months of history.

**Sensors** for the current billing period:

- Bill so far / Bill projected (€)
- Imported, exported and billable kWh this period
- Credit units carried in from the previous bill
- Last day imported / exported
- Import price and export credit (€/kWh, VAT included)
- Data available until

The bill estimate reproduces the EAC bill lines: electricity generation, fuel adjustment, network use, public service obligation, fixed fees, VAT 5 % and the RES & EE fund. Prices come from the [Cyprus electricity cost API](https://electricity-calculator.cy/api/) and follow the monthly fuel adjustment.

## Requirements

- An EAC smart meter.
- An account on [meterreading-dso.eac.com.cy](https://meterreading-dso.eac.com.cy) with your supply registered (if you can download the "readings & consumption" XLSX there, this integration will work).

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/nikolas22t/ha-eac-cyprus`, category **Integration**.
2. Search for **EAC Cyprus**, install, restart Home Assistant.

### Manual

Copy `custom_components/eac_cyprus` into your `config/custom_components/` folder and restart.

## Setup

*Settings → Devices & services → Add integration → EAC Cyprus*

1. Enter the e-mail and password of your EAC portal account.
2. If the account has several supplies, pick one (add the integration again for each extra supply).
3. Enter the billing cycle from your last bill, using the **first** date of the period:
   - "24/07/2026 – 24/09/2026" → day **24**, **odd** months (July)
   - "03/08/2026 – 02/10/2026" → day **3**, **even** months (August), not 2

You can change the billing settings later under *Configure*.

## Good to know

- **Data is a day late.** EAC publishes the readings the next day, so the Energy dashboard always shows up to yesterday. The integration checks every 6 hours.
- **Net metering:** each exported kWh offsets an imported kWh, but the network charge and PSO are still paid on every imported kWh. Extra exports become credit units for the next bill. Credit is counted from the oldest complete billing period the integration downloaded (about 5 months back), assuming no credit before that.
- **Cost history uses today's prices** for every hour, so older periods are an estimate, not what you actually paid.
- The projected bill scales the energy part of the bill so far to the full period.
- Your password is stored in Home Assistant's config entry, like any other integration that logs in to a cloud service.

## Ελληνικά

Η ενσωμάτωση συνδέεται με τον λογαριασμό σας στην πύλη μετρήσεων της ΑΗΚ, φέρνει την ωριαία κατανάλωση και εξαγωγή του έξυπνου μετρητή στο Energy dashboard του Home Assistant και υπολογίζει τον επόμενο λογαριασμό, μαζί με τον συμψηφισμό μετρήσεων για φωτοβολταϊκά. Τα δεδομένα έρχονται με μία μέρα καθυστέρηση, όπως και στην πύλη της ΑΗΚ.

## License

MIT
