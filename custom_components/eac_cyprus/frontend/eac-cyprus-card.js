/* EAC Cyprus card — bill, period progress, daily / monthly / hourly charts and bill history.
 * Served by the eac_cyprus integration; no extra resources needed.
 * type: custom:eac-cyprus-card
 * entity: sensor.eac_<supply>_overview      (optional: first EAC overview sensor is used)
 * view: full | bill | daily | monthly | profile | periods   (default full)
 * days: 30   months: 13   title: "..."   language: en|el
 */
const VERSION = "0.2.0";

const T = {
  en: {
    title: "Electricity (EAC)", so_far: "Bill so far", projected: "Projected bill", period: "Billing period",
    day: "Day", of: "of", import: "Imported", export: "Exported", billable: "Billable",
    credit_in: "Credit carried in", credit_out: "Credit to next bill", last_day: "Last day",
    daily: "Daily energy", monthly: "Monthly energy", profile: "Average day (last 30 days)",
    periods: "Bills (estimated)", start: "Period", total: "Total", data_until: "Data until",
    stale: "EAC data is late", price: "Import price", credit: "Export credit",
    breakdown: "Bill breakdown", energy: "Energy", fuel: "Fuel adjustment", network: "Network",
    pso: "PSO", fixed: "Fixed fees", vat: "VAT", res: "RES fund", loading: "Waiting for EAC data…",
    net: "Net", last_bill: "Last bill", no_entity: "No EAC Cyprus overview sensor found.",
    vs_last: "vs last bill", fallback: "fallback prices",
  },
  el: {
    title: "Ρεύμα (ΑΗΚ)", so_far: "Λογαριασμός μέχρι τώρα", projected: "Εκτίμηση λογαριασμού", period: "Περίοδος χρέωσης",
    day: "Ημέρα", of: "από", import: "Εισαγωγή", export: "Εξαγωγή", billable: "Χρεώσιμες",
    credit_in: "Πιστωτικές μονάδες", credit_out: "Μονάδες για επόμενο", last_day: "Τελευταία ημέρα",
    daily: "Ημερήσια ενέργεια", monthly: "Μηνιαία ενέργεια", profile: "Μέση ημέρα (30 ημέρες)",
    periods: "Λογαριασμοί (εκτίμηση)", start: "Περίοδος", total: "Σύνολο", data_until: "Δεδομένα έως",
    stale: "Καθυστέρηση δεδομένων ΑΗΚ", price: "Τιμή εισαγωγής", credit: "Πίστωση εξαγωγής",
    breakdown: "Ανάλυση λογαριασμού", energy: "Ενέργεια", fuel: "Αναπροσαρμογή καυσίμων", network: "Δίκτυο",
    pso: "ΥΚΩ", fixed: "Πάγια", vat: "ΦΠΑ", res: "Ταμείο ΑΠΕ", loading: "Τα στοιχεία φορτώνουν…",
    net: "Καθαρό", last_bill: "Τελευταίος λογαριασμός", no_entity: "Δεν βρέθηκε αισθητήρας επισκόπησης ΑΗΚ.",
    vs_last: "έναντι προηγούμενου", fallback: "εφεδρικές τιμές",
  },
};
const C_IMP = "var(--energy-grid-consumption-color, #488fc2)";
const C_EXP = "var(--energy-grid-return-color, #8353d1)";

const eur = (v, d = 2) => (v == null || isNaN(v) ? "–" : "€" + Number(v).toFixed(d));
const kwh = (v, d = 1) => (v == null || isNaN(v) ? "–" : Number(v).toFixed(d) + " kWh");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function findOverview(hass) {
  return Object.keys(hass.states).find(
    (e) => e.startsWith("sensor.") && hass.states[e].attributes.eac_cyprus_card
  );
}

/* Bars: rows = [[label, a, b], ...]; a = import (up), b = export (down). */
function bars(rows, opts = {}) {
  const W = 600, H = opts.h || 170, pad = 22, mid = opts.split ? H * 0.62 : H - pad;
  if (!rows.length) return "";
  const maxA = Math.max(0.001, ...rows.map((r) => r[1]));
  const maxB = Math.max(0.001, ...rows.map((r) => r[2] || 0));
  const upH = mid - 8, downH = H - mid - pad;
  const scale = opts.split ? Math.max(maxA / upH, maxB / downH) : maxA / upH;
  const bw = (W - 30) / rows.length;
  const every = Math.ceil(rows.length / (opts.labels || 10));
  let g = "";
  rows.forEach((r, i) => {
    const x = 30 + i * bw, w = Math.max(1, bw * 0.72);
    const ha = r[1] / scale, hb = (r[2] || 0) / scale;
    const tip = `${esc(opts.fmt ? opts.fmt(r[0]) : r[0])}: ↓ ${kwh(r[1], 2)}` + (opts.split ? ` / ↑ ${kwh(r[2], 2)}` : "");
    g += `<g><title>${tip}</title><rect x="${x}" y="${mid - ha}" width="${w}" height="${ha}" rx="2" fill="${C_IMP}"/>`;
    if (opts.split && hb > 0) g += `<rect x="${x}" y="${mid}" width="${w}" height="${hb}" rx="2" fill="${C_EXP}"/>`;
    g += `<rect x="${x}" y="0" width="${bw}" height="${H}" fill="transparent"/></g>`;
    if (i % every === 0)
      g += `<text x="${x + w / 2}" y="${H - 6}" text-anchor="middle" class="lbl">${esc(opts.fmt ? opts.fmt(r[0]) : r[0])}</text>`;
  });
  const top = maxA;
  g += `<text x="0" y="12" class="lbl">${top.toFixed(top < 10 ? 1 : 0)}</text>`;
  g += `<line x1="30" x2="${W}" y1="${mid}" y2="${mid}" class="axis"/>`;
  if (opts.avg != null) {
    const y = mid - opts.avg / scale;
    g += `<line x1="30" x2="${W}" y1="${y}" y2="${y}" class="avg"/><text x="${W}" y="${y - 3}" text-anchor="end" class="lbl">⌀ ${opts.avg.toFixed(1)}</text>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="chart">${g}</svg>`;
}

class EacCyprusCard extends HTMLElement {
  setConfig(config) {
    this._config = { view: "full", days: 30, months: 13, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }
  static getStubConfig(hass) {
    return { entity: findOverview(hass) || "", view: "full" };
  }
  getCardSize() {
    return { full: 12, bill: 4, periods: 5 }[this._config.view] || 4;
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }
  set hass(hass) {
    const id = this._config.entity || findOverview(hass);
    const st = id && hass.states[id];
    const key = st ? st.last_updated + (hass.language || "") : "none";
    if (key === this._key) return;
    this._key = key;
    this._hass = hass;
    this._render(st);
  }

  _t(k) {
    const lang = this._config.language || (this._hass.language || "en").slice(0, 2);
    return (T[lang] || T.en)[k] || T.en[k] || k;
  }
  _date(s, o = { day: "numeric", month: "short" }) {
    const lang = this._config.language || this._hass.language || "en";
    return new Date(s.length === 7 ? s + "-01T12:00" : s.length === 10 ? s + "T12:00" : s).toLocaleDateString(lang, o);
  }

  _bill(a) {
    const b = a.bill, pct = Math.min(100, (a.days_elapsed / a.days_in_period) * 100);
    const last = a.last_bill;
    const diff = last ? a.projected - last.total : null;
    const end = new Date(a.period_end + "T12:00"); end.setDate(end.getDate() - 1);
    return `
      <div class="hero">
        <div><div class="big">${eur(b.total)}</div><div class="sub">${this._t("so_far")}</div></div>
        <div class="right"><div class="mid">${eur(a.projected)}</div><div class="sub">${this._t("projected")}
          ${diff != null ? `<span class="${diff > 0 ? "up" : "down"}">${diff > 0 ? "▲" : "▼"} ${eur(Math.abs(diff))}</span>` : ""}</div></div>
      </div>
      <div class="prog"><div style="width:${pct}%"></div></div>
      <div class="sub row"><span>${this._date(a.period_start)} → ${this._date(end.toISOString().slice(0, 10))}</span>
        <span>${this._t("day")} ${Math.ceil(a.days_elapsed)} ${this._t("of")} ${a.days_in_period}</span></div>
      <div class="tiles">
        <div class="tile"><ha-icon icon="mdi:transmission-tower-import" style="color:${C_IMP}"></ha-icon><b>${kwh(b.imported, 0)}</b><span>${this._t("import")}</span></div>
        <div class="tile"><ha-icon icon="mdi:transmission-tower-export" style="color:${C_EXP}"></ha-icon><b>${kwh(b.exported, 0)}</b><span>${this._t("export")}</span></div>
        <div class="tile"><ha-icon icon="mdi:scale-balance"></ha-icon><b>${kwh(b.net, 0)}</b><span>${this._t("billable")}</span></div>
        <div class="tile"><ha-icon icon="mdi:battery-charging"></ha-icon><b>${kwh(b.credit_in, 0)}</b><span>${this._t("credit_in")}</span></div>
      </div>
      ${b.credit_out > 0 ? `<div class="sub center">${this._t("credit_out")}: <b>${kwh(b.credit_out, 0)}</b></div>` : ""}`;
  }

  _breakdown(a) {
    const b = a.bill;
    const items = [["energy", b.energy], ["fuel", b.fuel_adjustment], ["network", b.network], ["pso", b.pso],
      ["fixed", b.fixed], ["vat", b.vat], ["res", b.res_fund]];
    const tot = Math.max(0.01, b.total);
    const cols = ["#488fc2", "#f4b400", "#43a047", "#9e9e9e", "#8d6e63", "#e57373", "#26a69a"];
    const seg = items.map((x, i) => `<div title="${this._t(x[0])}: ${eur(x[1])}" style="flex:${Math.max(0, x[1]) / tot};background:${cols[i]}"></div>`).join("");
    const leg = items.map((x, i) => `<span><i style="background:${cols[i]}"></i>${this._t(x[0])} ${eur(x[1])}</span>`).join("");
    return `<h3>${this._t("breakdown")}</h3><div class="stack">${seg}</div><div class="legend">${leg}</div>
      <div class="sub row"><span>${this._t("price")}: <b>€${a.import_price.toFixed(4)}</b>/kWh</span>
      <span>${this._t("credit")}: <b>€${a.export_credit.toFixed(4)}</b>/kWh</span></div>
      ${a.rates_live ? "" : `<div class="sub warn">${this._t("fallback")}</div>`}`;
  }

  _daily(a) {
    const rows = (a.daily || []).slice(-this._config.days);
    const avg = rows.length ? rows.reduce((s, r) => s + r[1], 0) / rows.length : null;
    const split = rows.some((r) => r[2] > 0);
    return `<h3>${this._t("daily")}</h3>${bars(rows, { split, avg, fmt: (d) => this._date(d), labels: 8 })}
      ${a.last_day ? `<div class="sub row"><span>${this._t("last_day")} ${this._date(a.last_day)}</span>
      <span>↓ ${kwh(a.last_day_import, 1)}${split ? ` · ↑ ${kwh(a.last_day_export, 1)}` : ""}</span></div>` : ""}`;
  }
  _monthly(a) {
    const rows = (a.monthly || []).slice(-this._config.months);
    const split = rows.some((r) => r[2] > 0);
    return `<h3>${this._t("monthly")}</h3>${bars(rows, { split, fmt: (m) => this._date(m, { month: "short" }), labels: 13 })}`;
  }
  _profile(a) {
    const rows = a.profile || [];
    const split = rows.some((r) => r[2] > 0);
    return `<h3>${this._t("profile")}</h3>${bars(rows, { split, h: 140, fmt: (h) => String(h).padStart(2, "0") + ":00", labels: 8 })}`;
  }
  _periods(a) {
    const ps = a.periods || [];
    if (!ps.length) return "";
    const max = Math.max(...ps.map((p) => p.total), 1);
    const rows = ps.map((p) => `<tr><td>${this._date(p.start)} – ${this._date(p.end)}</td>
      <td class="n">${p.import.toFixed(0)}</td><td class="n">${p.export.toFixed(0)}</td><td class="n">${p.credit_in.toFixed(0)}</td>
      <td class="n"><div class="pbar"><div style="width:${(p.total / max) * 100}%"></div><b>${eur(p.total)}</b></div></td></tr>`).join("");
    return `<h3>${this._t("periods")}</h3><table><tr><th>${this._t("start")}</th><th class="n">↓ kWh</th><th class="n">↑ kWh</th>
      <th class="n">${this._t("credit_in").split(" ")[0]}</th><th class="n">${this._t("total")}</th></tr>${rows}</table>`;
  }

  _render(st) {
    let body;
    if (!st) body = `<div class="sub">${this._t("no_entity")}</div>`;
    else if (!st.attributes.bill) body = `<div class="sub">${this._t("loading")}</div>`;
    else {
      const a = st.attributes, v = this._config.view;
      const parts = {
        bill: () => this._bill(a), breakdown: () => this._breakdown(a), daily: () => this._daily(a),
        monthly: () => this._monthly(a), profile: () => this._profile(a), periods: () => this._periods(a),
      };
      const order = v === "full" ? ["bill", "daily", "monthly", "profile", "breakdown", "periods"] : [v];
      body = order.filter((k) => parts[k]).map((k) => `<section>${parts[k]()}</section>`).join("");
      if (a.stale) body = `<div class="stale"><ha-icon icon="mdi:clock-alert-outline"></ha-icon>${this._t("stale")}</div>` + body;
      if (a.data_until)
        body += `<div class="foot">${this._t("data_until")} ${this._date(a.data_until, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div>`;
    }
    const title = this._config.title ?? this._t("title");
    this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card>
      ${title ? `<div class="hdr"><ha-icon icon="mdi:lightning-bolt"></ha-icon>${esc(title)}</div>` : ""}
      <div class="content">${body}</div></ha-card>`;
  }
}

const CSS = `
ha-card{padding:0 0 8px}
.hdr{display:flex;gap:8px;align-items:center;padding:14px 16px 4px;font-size:1.15em;font-weight:500}
.hdr ha-icon{color:var(--state-sensor-energy-color,#ff9800)}
.content{padding:4px 16px}
section{padding:8px 0;border-bottom:1px solid var(--divider-color)}
section:last-of-type{border-bottom:none}
h3{margin:4px 0 8px;font-size:.95em;font-weight:500;color:var(--secondary-text-color)}
.hero{display:flex;justify-content:space-between;align-items:flex-end}
.big{font-size:2.4em;font-weight:600;line-height:1.1}
.mid{font-size:1.5em;font-weight:500;text-align:right}
.right{text-align:right}
.sub{font-size:.85em;color:var(--secondary-text-color)}
.row{display:flex;justify-content:space-between;gap:8px;margin-top:4px}
.center{text-align:center;margin-top:6px}
.up{color:var(--error-color,#db4437);margin-left:4px}.down{color:var(--success-color,#43a047);margin-left:4px}
.warn{color:var(--warning-color,#ffa600)}
.prog{height:8px;border-radius:4px;background:var(--secondary-background-color,#eee);margin:10px 0 2px;overflow:hidden}
.prog div{height:100%;background:var(--primary-color);border-radius:4px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
.tile{display:flex;flex-direction:column;align-items:center;padding:8px 2px;border-radius:12px;background:var(--secondary-background-color,rgba(127,127,127,.08));text-align:center}
.tile b{font-size:1.05em;margin-top:2px}.tile span{font-size:.72em;color:var(--secondary-text-color)}
@media (max-width:420px){.tiles{grid-template-columns:repeat(2,1fr)}}
.chart{width:100%;height:170px;display:block}
.chart .lbl{font-size:11px;fill:var(--secondary-text-color)}
.chart .axis{stroke:var(--divider-color)}
.chart .avg{stroke:var(--secondary-text-color);stroke-dasharray:4 4;opacity:.6}
.chart g:hover rect{opacity:.75}
.stack{display:flex;height:14px;border-radius:7px;overflow:hidden}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.78em;margin:8px 0 4px;color:var(--secondary-text-color)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
table{width:100%;border-collapse:collapse;font-size:.85em}
th{font-weight:500;color:var(--secondary-text-color);text-align:left;padding:4px 2px}
td{padding:4px 2px;border-top:1px solid var(--divider-color)}
.n{text-align:right;white-space:nowrap}
.pbar{position:relative;min-width:80px;height:20px;line-height:20px}
.pbar div{position:absolute;right:0;top:3px;height:14px;border-radius:3px;background:var(--primary-color);opacity:.25}
.pbar b{position:relative}
.stale{display:flex;gap:6px;align-items:center;padding:6px 10px;border-radius:8px;background:rgba(255,166,0,.15);color:var(--warning-color,#ffa600);font-size:.85em}
.foot{font-size:.75em;color:var(--secondary-text-color);text-align:right;margin-top:4px}
`;

if (!customElements.get("eac-cyprus-card")) {
  customElements.define("eac-cyprus-card", EacCyprusCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "eac-cyprus-card", name: "EAC Cyprus", preview: true,
    description: "Bill estimate, net metering, daily/monthly/hourly charts and bill history from the EAC smart meter.",
  });
  console.info(`%c EAC-CYPRUS-CARD %c v${VERSION} `, "background:#ff9800;color:#fff", "");
}
