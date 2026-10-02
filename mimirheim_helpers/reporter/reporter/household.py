"""Household view renderer for mimirheim solve dumps.

A second, parallel report aimed at the people who live in the house rather than
the operator. Where ``render.build_report_html`` produces the technical report
(Plotly flows, per-device SOC, data table), this module produces one calm,
editorial page answering the layperson's question: *what is our house doing with
electricity today, and is it smart?*

What this module does:
    - Produce a complete, self-contained HTML page from a dump pair, with the
      per-step series and summary embedded as a JSON data block and a small
      client script (hand-drawn SVG, no Plotly) that presents it, NL/EN.
    - Expose ``build_household_html(inp, out) -> str`` as the sole public function.

What this module does not do:
    - Read or write files, or publish MQTT.
    - Import from ``mimirheim``.
    - Re-derive economics or energy totals — those come from ``metrics``.

The visual design and client presentation logic were ported from a working
standalone prototype; here they are driven by the dump pair server-side.
"""
from __future__ import annotations

import html
import json
from typing import Any

from reporter.metrics import compute_economic_metrics, compute_schedule_metrics

_LOAD_TYPES = ("static_load", "deferrable_load")


def build_household_html(inp: dict, out: dict) -> str:
    """Build the household (layperson) HTML page from a mimirheim dump pair.

    Args:
        inp: Parsed SolveBundle JSON (the ``*_input.json`` dump).
        out: Parsed SolveResult JSON (the ``*_output.json`` dump).

    Returns:
        A complete standalone HTML document string. Self-contained: no Plotly,
        no network calls. All data is embedded as a JSON block the page's own
        script reads and presents.
    """
    payload = _build_payload(inp, out)
    data_json = json.dumps(payload, separators=(",", ":"))
    # The payload is numeric + ISO timestamps, so it cannot contain "</script>";
    # escaping the forward slash is belt-and-braces against a stray sequence.
    data_json = data_json.replace("</", "<\\/")
    return _PAGE.replace("__HOUSEHOLD_DATA__", data_json)


def _build_payload(inp: dict, out: dict) -> dict[str, Any]:
    """Compute the embedded data payload from a dump pair.

    Per-step series follow the same sign conventions as ``metrics.py``:
    PV is the positive kW of ``type == "pv"`` devices; load is the negated kW of
    ``static_load``/``deferrable_load`` devices; grid flows come straight off the
    step. Summary figures are taken from the shared metrics functions so the
    household view can never disagree with the technical report.
    """
    schedule = out.get("schedule", []) or []
    eco = compute_economic_metrics(out)
    m = compute_schedule_metrics(schedule)

    t: list[str] = []
    price: list[float] = []
    exp: list[float] = []
    pv: list[float] = []
    load: list[float] = []
    imp: list[float] = []
    expo: list[float] = []

    for s in schedule:
        t.append(s.get("t", ""))
        price.append(float(s.get("import_price_eur_per_kwh", 0.0) or 0.0))
        exp.append(float(s.get("export_price_eur_per_kwh", 0.0) or 0.0))
        imp.append(max(0.0, float(s.get("grid_import_kw", 0.0) or 0.0)))
        expo.append(max(0.0, float(s.get("grid_export_kw", 0.0) or 0.0)))
        devices = s.get("devices", {}) or {}
        pv.append(
            round(
                sum(
                    max(0.0, float(d.get("kw", 0.0) or 0.0))
                    for d in devices.values()
                    if d.get("type") == "pv"
                ),
                4,
            )
        )
        load.append(
            round(
                sum(
                    max(0.0, -float(d.get("kw", 0.0) or 0.0))
                    for d in devices.values()
                    if d.get("type") in _LOAD_TYPES
                ),
                4,
            )
        )

    solve = (
        inp.get("triggered_at_utc")
        or inp.get("solve_time_utc")
        or (t[0] if t else "")
    )
    summary = {
        "solve": solve,
        "naive": eco.naive_cost_eur,
        # Effective cost (after SOC terminal credit) is the honest "with plan"
        # figure; saving = naive - effective, matching the economic metrics.
        "opt": eco.effective_cost_eur,
        "saving": round(max(0.0, eco.saving_eur), 4),
        "import": m.grid_import_kwh,
        "export": m.grid_export_kwh,
        "pv": m.pv_total_kwh,
        "load": m.load_total_kwh,
        "self": m.self_sufficiency_pct,
    }
    return {
        "t": t,
        "price": price,
        "exp": exp,
        "pv": pv,
        "load": load,
        "imp": imp,
        "expo": expo,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# The page. Self-contained: CSS + body + a JSON data block + a presenter script.
# __HOUSEHOLD_DATA__ is replaced with the embedded payload at render time.
# ---------------------------------------------------------------------------
_PAGE = r"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- Reload periodically so a left-open tablet / embedded frame tracks new solves. -->
<meta http-equiv="refresh" content="300">
<title>Ons huis vandaag — energieplan</title>
<style>
:root{
  --paper:#F5EFE3; --card:#FFFBF3; --ink:#1E2733; --soft:#5E6673; --line:#E4DACA;
  --sun:#F0A92E; --sun2:#FFD27A; --batt:#2E8C80; --batt2:#9AD3C9; --grid:#7D879A; --grid2:#C9CFDA;
  --cheap:#6E9E5C; --mid:#E2A93B; --dear:#D25F3A;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --sans:"Avenir Next",Avenir,"Segoe UI","Helvetica Neue",sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased}
body{background:
  radial-gradient(1200px 500px at 85% -10%, rgba(240,169,46,.22), transparent 60%),
  radial-gradient(900px 500px at -10% 30%, rgba(46,140,128,.10), transparent 60%),
  var(--paper);}
.wrap{max-width:1120px;margin:0 auto;padding:28px 24px 64px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.kicker{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--soft);font-weight:600}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(34px,5vw,56px);line-height:1.04;margin:8px 0 0;letter-spacing:-.01em}
h1 em{font-style:italic;color:var(--batt)}
h2{font-family:var(--serif);font-weight:400;font-size:28px;margin:0 0 4px}
.sub{color:var(--soft);font-size:15px;margin:0 0 18px;line-height:1.5}
.lang{display:flex;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px;flex-shrink:0}
.lang button{border:0;background:transparent;font:600 13px var(--sans);padding:7px 14px;border-radius:999px;cursor:pointer;color:var(--soft)}
.lang button.on{background:var(--ink);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:26px;box-shadow:0 1px 0 rgba(0,0,0,.02),0 12px 30px -18px rgba(60,40,10,.25)}
.hero{display:grid;grid-template-columns:1.25fr 1fr;gap:20px;margin-top:26px}
.save{position:relative;overflow:hidden;background:linear-gradient(135deg,#21463F 0%,#2E8C80 100%);color:#F6FFFC;border:0}
.save .big{font-family:var(--serif);font-size:clamp(64px,9vw,104px);line-height:1;margin:14px 0 6px;letter-spacing:-.02em}
.save .big small{font-size:.45em;opacity:.8;margin-right:4px}
.save p{margin:0;font-size:17px;line-height:1.5;max-width:30em;opacity:.95}
.save .kicker{color:#BFE7E0}
.save svg.deco{position:absolute;right:-40px;bottom:-40px;opacity:.13}
.compare{margin-top:22px;display:grid;gap:10px}
.cbar{display:grid;grid-template-columns:150px 1fr 70px;align-items:center;gap:12px;font-size:14px}
.cbar .track{height:14px;background:rgba(255,255,255,.12);border-radius:8px;overflow:hidden}
.cbar .fill{height:100%;border-radius:8px;width:0;transition:width 1.2s cubic-bezier(.2,.7,.2,1)}
.cbar .v{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.now{display:flex;flex-direction:column;gap:14px}
.now .state{display:flex;gap:16px;align-items:center}
.icon{width:58px;height:58px;border-radius:18px;display:grid;place-items:center;flex-shrink:0}
.now .what{font-family:var(--serif);font-size:25px;line-height:1.2}
.now .why{color:var(--soft);font-size:15px;line-height:1.55}
.next{border-top:1px dashed var(--line);padding-top:14px;display:flex;gap:12px;align-items:center;font-size:15px}
.next .icon{width:38px;height:38px;border-radius:12px}
.next b{font-weight:600}
section{margin-top:22px}
.tl{position:relative;margin-top:8px}
.tl-bar{display:flex;height:64px;border-radius:16px;overflow:hidden;border:1px solid var(--line)}
.tl-seg{position:relative;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:filter .2s,transform .2s;transform-origin:bottom}
.tl-seg:hover,.tl-seg.sel{filter:brightness(1.06) saturate(1.1)}
.tl-seg svg{opacity:.95}
.tl-ticks{position:relative;height:22px;margin-top:6px;font-size:12px;color:var(--soft);font-variant-numeric:tabular-nums}
.tl-ticks span{position:absolute;transform:translateX(-50%)}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:10px;font-size:14px;color:var(--soft)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:4px;margin-right:7px;vertical-align:-1px}
.steps{list-style:none;margin:22px 0 0;padding:0;display:grid;gap:2px}
.steps li{display:grid;grid-template-columns:110px 46px 1fr auto;align-items:center;gap:16px;padding:12px 14px;border-radius:14px;cursor:pointer;transition:background .2s}
.steps li:hover,.steps li.sel{background:#F3EBDD}
.steps .time{font-variant-numeric:tabular-nums;font-weight:600;font-size:15px}
.steps .icon{width:42px;height:42px;border-radius:13px}
.steps .t1{font-size:16px;font-weight:600}
.steps .t2{font-size:14px;color:var(--soft);margin-top:2px;line-height:1.45}
.pill{font-size:13px;font-weight:600;padding:5px 11px;border-radius:999px;white-space:nowrap;font-variant-numeric:tabular-nums}
.two{display:grid;grid-template-columns:1.5fr 1fr;gap:20px}
.chart{position:relative;width:100%}
.chart svg{display:block;width:100%;overflow:visible}
.tip{position:absolute;pointer-events:none;background:var(--ink);color:#fff;font-size:13px;padding:8px 11px;border-radius:10px;line-height:1.45;white-space:nowrap;opacity:0;transition:opacity .15s;transform:translate(-50%,-110%);z-index:5}
.tip b{font-size:15px}
.tips{display:grid;gap:12px;margin-top:6px}
.tipcard{display:flex;gap:14px;align-items:flex-start;padding:14px;border-radius:16px;background:#F6EFE2}
.tipcard .icon{width:44px;height:44px;border-radius:13px}
.tipcard b{display:block;font-size:16px;margin-bottom:2px}
.tipcard span{font-size:14px;color:var(--soft);line-height:1.5}
.srcbar{display:flex;height:46px;border-radius:14px;overflow:hidden;margin:18px 0 14px}
.srcbar div{display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat{padding:16px;border-radius:16px;background:#F6EFE2}
.stat .n{font-family:var(--serif);font-size:32px;line-height:1.1}
.stat .n small{font-family:var(--sans);font-size:14px;color:var(--soft);margin-left:3px}
.stat .l{font-size:13px;color:var(--soft);margin-top:4px;line-height:1.4}
footer{margin-top:30px;color:var(--soft);font-size:12.5px;line-height:1.6;text-align:center}
.wait{padding:70px 20px;text-align:center;color:var(--soft);font-family:var(--serif);font-size:24px}
@media (max-width:860px){.hero,.two{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.steps li{grid-template-columns:86px 42px 1fr}.steps .pill{display:none}.cbar{grid-template-columns:110px 1fr 60px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div><div class="kicker" id="dateline"></div><h1 id="title"></h1></div>
    <div class="lang"><button data-l="nl" class="on">NL</button><button data-l="en">EN</button></div>
  </header>
  <div class="hero">
    <div class="card save">
      <svg class="deco" width="320" height="320" viewBox="0 0 100 100"><circle cx="50" cy="50" r="20" fill="#fff"/><g stroke="#fff" stroke-width="5" stroke-linecap="round"><path d="M50 8v12M50 80v12M8 50h12M80 50h12M20 20l8 8M72 72l8 8M80 20l-8 8M28 72l-8 8"/></g></svg>
      <div class="kicker" id="saveK"></div><div class="big" id="saveBig"></div><p id="saveP"></p>
      <div class="compare">
        <div class="cbar"><span id="cb1"></span><div class="track"><div class="fill" id="f1" style="background:#F2B9A3"></div></div><span class="v" id="v1"></span></div>
        <div class="cbar"><span id="cb2"></span><div class="track"><div class="fill" id="f2" style="background:#FFE3A3"></div></div><span class="v" id="v2"></span></div>
      </div>
    </div>
    <div class="card now">
      <div class="kicker" id="nowK"></div>
      <div class="state"><div class="icon" id="nowIcon"></div><div class="what" id="nowWhat"></div></div>
      <div class="why" id="nowWhy"></div>
      <div class="next"><div class="icon" id="nextIcon"></div><div id="nextTxt"></div></div>
    </div>
  </div>
  <section class="card"><h2 id="planH"></h2><p class="sub" id="planS"></p>
    <div class="tl"><div class="tl-bar" id="tlbar"></div><div class="tl-ticks" id="tlticks"></div></div>
    <div class="legend" id="legend"></div><ul class="steps" id="steps"></ul></section>
  <div class="two">
    <section class="card"><h2 id="priceH"></h2><p class="sub" id="priceS"></p><div class="chart" id="priceChart"><div class="tip"></div></div></section>
    <section class="card"><h2 id="tipsH"></h2><p class="sub" id="tipsS"></p><div class="tips" id="tips"></div></section>
  </div>
  <section class="card"><h2 id="flowH"></h2><p class="sub" id="flowS"></p><div class="chart" id="flowChart"><div class="tip"></div></div><div class="legend" id="flowLegend"></div></section>
  <section class="card"><h2 id="srcH"></h2><p class="sub" id="srcS"></p><div class="srcbar" id="srcbar"></div><div class="stats" id="stats"></div></section>
  <footer id="foot"></footer>
</div>

<script id="household-data" type="application/json">__HOUSEHOLD_DATA__</script>
<script>
const D = JSON.parse(document.getElementById('household-data').textContent);
const TZ = (Intl.DateTimeFormat().resolvedOptions().timeZone) || 'UTC';
let L = 'nl';
// Step duration straight from the data (fallback 15 min for a 0/1-step plan).
const STEP_MS = D.t.length>1 ? (new Date(D.t[1])-new Date(D.t[0])) : 900000;

const IC = {
  sun:  c=>`<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.2" fill="${c}"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/></svg>`,
  batt: c=>`<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round"><rect x="3" y="7" width="16" height="10" rx="2.5"/><path d="M21 10.5v3" stroke-linecap="round"/><rect x="5.5" y="9.5" width="7" height="5" rx="1" fill="${c}" stroke="none"/></svg>`,
  charge:c=>`<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round"><rect x="3" y="7" width="16" height="10" rx="2.5"/><path d="M21 10.5v3" stroke-linecap="round"/><path d="M12 8.5l-3 4h3l-1.5 3.5 4-4.6h-3l1.5-2.9z" fill="${c}" stroke="none"/></svg>`,
  grid: c=>`<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5L7 21.5M12 2.5l5 19M8.6 15.5h6.8M9.7 10.5h4.6M5 6h14M8 6l4 4.5L16 6"/></svg>`,
  wash: c=>`<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2"><rect x="4" y="3" width="16" height="18" rx="3"/><circle cx="12" cy="13" r="4.5"/><path d="M7.5 6.5h2" stroke-linecap="round"/></svg>`,
  coin: c=>`<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2"><circle cx="12" cy="12" r="8.5"/><path d="M14.8 9a3.5 3.5 0 100 6M8 11h5M8 13.2h5" stroke-linecap="round"/></svg>`
};
const MODE = {
  battery:{col:'#2E8C80',bg:'#DDF1EC',ic:'batt'}, grid_charge:{col:'#3E6FB0',bg:'#DEE8F6',ic:'charge'},
  solar_charge:{col:'#E39A1F',bg:'#FDEFD2',ic:'charge'}, sun:{col:'#F0A92E',bg:'#FDEFD2',ic:'sun'}, grid:{col:'#8A93A5',bg:'#E8EBF0',ic:'grid'}
};
const T = {
 nl:{title:'Wat doet ons huis <em>vandaag</em> met stroom?',saveK:'Besparing vandaag dankzij de thuisbatterij',
  saveP:p=>`Door slim te laden als stroom goedkoop is en de batterij te gebruiken als stroom duur is, betalen we vandaag zo'n <b>${p}%</b> minder.`,
  saveP0:`Door slim te laden als stroom goedkoop is en de batterij te gebruiken als stroom duur is, houden we vandaag een flink bedrag over.`,
  cb1:'Zonder slim plan',cb2:'Met slim plan',nowK:t=>`Nu, om ${t}`,nextPre:'Daarna',nextAt:'vanaf',
  planH:'Het plan voor de rest van de dag',planS:'Elke kleur is een stukje van de dag. Klik op een blok of een regel om te zien wat er gebeurt en waarom.',
  m:{battery:{a:'Huis draait op de batterij',b:c=>`Stroom is nu duur (rond ${c} cent). We gebruiken wat we eerder hebben opgeslagen.`},
   grid_charge:{a:'Batterij tankt goedkope stroom',b:c=>`Een goedkoop moment (rond ${c} cent). We vullen de batterij voor de dure uren.`},
   solar_charge:{a:'De zon vult de batterij',b:()=>`De panelen leveren meer dan het huis nodig heeft. Het overschot gaat de batterij in.`},
   sun:{a:'Huis draait op de zon',b:()=>`De zonnepanelen leveren genoeg voor het hele huis.`},
   grid:{a:'Gewoon stroom van het net',b:c=>`Stroom is nu redelijk goedkoop (rond ${c} cent). We sparen de batterij voor later.`}},
  priceH:'Wat kost stroom vandaag?',priceS:'Prijs per kWh, per kwartier. Groen is goedkoop, rood is duur.',
  cheapest:'goedkoopst',dearest:'duurst',cent:'cent',tipsH:'Handig om te weten',tipsS:'Zelf iets aanzetten? Dan ben je hier het voordeligst uit.',
  tWash:(a,b,c)=>[`Was of vaatwasser: ${a} - ${b}`,`De goedkoopste twee uur van nu af, gemiddeld ${c} cent per kWh.`],
  tAvoid:(a,b,c)=>[`Liever niet: ${a} - ${b}`,`De duurste uren, tot ${c} cent per kWh. De batterij vangt dit zoveel mogelijk op.`],
  tSun:(a,b)=>[`Meeste zon: ${a} - ${b}`,`Dan maken de panelen het meeste stroom.`],
  flowH:'Waar komt onze stroom vandaan, per uur?',flowS:'Boven de lijn: wat het huis gebruikt en waar dat vandaan komt. Onder de lijn: stroom die de batterij in gaat.',
  lg:{sun:'Zon',batt:'Batterij',grid:'Net',cs:'Batterij laden (zon)',cg:'Batterij laden (net)'},
  srcH:'De dag in cijfers',srcS:'Alles opgeteld van nu tot het einde van de planning.',
  st:{use:'stroom die het huis gebruikt',sun:'opgewekt door de zonnepanelen',imp:'gekocht van het net',self:'van ons verbruik hoefden we niet te kopen'},
  foot:(t,h)=>`Plan berekend om ${t} voor de komende ${h} uur. Bedragen zijn verwachtingen, de werkelijkheid kan iets afwijken.<br>Gemaakt door Mimirheim. Batterijstroom is afgeleid uit verbruik, zon en net.`,
  dateFmt:'nl-NL',wait:'Nog geen plan van Mimirheim.'},
 en:{title:'What is our house doing with <em>power</em> today?',saveK:'Saved today thanks to the home battery',
  saveP:p=>`By charging when power is cheap and using the battery when it is expensive, we pay about <b>${p}%</b> less today.`,
  saveP0:`By charging when power is cheap and using the battery when it is expensive, we come out a good amount ahead today.`,
  cb1:'Without smart plan',cb2:'With smart plan',nowK:t=>`Right now, at ${t}`,nextPre:'Next',nextAt:'from',
  planH:'The plan for the rest of the day',planS:'Each colour is a part of the day. Click a block or a row to see what happens and why.',
  m:{battery:{a:'House runs on the battery',b:c=>`Power is expensive now (around ${c} cents). We use what we stored earlier.`},
   grid_charge:{a:'Battery fills up with cheap power',b:c=>`A cheap moment (around ${c} cents). We top up the battery for the expensive hours.`},
   solar_charge:{a:'The sun fills the battery',b:()=>`The panels make more than the house needs. The extra goes into the battery.`},
   sun:{a:'House runs on sunshine',b:()=>`The solar panels make enough for the whole house.`},
   grid:{a:'Normal power from the grid',b:c=>`Power is fairly cheap now (around ${c} cents). We save the battery for later.`}},
  priceH:'What does power cost today?',priceS:'Price per kWh, per quarter hour. Green is cheap, red is expensive.',
  cheapest:'cheapest',dearest:'most expensive',cent:'cents',tipsH:'Good to know',tipsS:'Switching something on yourself? These are the best times.',
  tWash:(a,b,c)=>[`Laundry or dishwasher: ${a} - ${b}`,`The cheapest two hours from now, on average ${c} cents per kWh.`],
  tAvoid:(a,b,c)=>[`Better avoid: ${a} - ${b}`,`The most expensive hours, up to ${c} cents per kWh. The battery covers as much as it can.`],
  tSun:(a,b)=>[`Most sunshine: ${a} - ${b}`,`When the panels make the most power.`],
  flowH:'Where does our power come from, hour by hour?',flowS:'Above the line: what the house uses and where it comes from. Below the line: power going into the battery.',
  lg:{sun:'Sun',batt:'Battery',grid:'Grid',cs:'Battery charging (sun)',cg:'Battery charging (grid)'},
  srcH:'The day in numbers',srcS:'Everything added up from now until the end of the plan.',
  st:{use:'power used by the house',sun:'made by the solar panels',imp:'bought from the grid',self:'of our usage we did not have to buy'},
  foot:(t,h)=>`Plan calculated at ${t} for the next ${h} hours. Amounts are forecasts, reality may differ a little.<br>Made by Mimirheim. Battery flow is derived from usage, solar and grid.`,
  dateFmt:'en-GB',wait:'No plan from Mimirheim yet.'}
};

const N = D.t.length;
let steps=[], blocks=[], endTime=null, solveT=null, pmin=0, pmax=0, wash=null, avoid=null, sunBest=null;
function prep(){
  steps = D.t.map((t,i)=>{
    const P=D.pv[i], Ld=D.load[i], I=D.imp[i], E=D.expo[i];
    const b=I-E-Ld+P;
    const sunHome=Math.min(P,Ld);
    const battHome=Math.min(Math.max(-b,0),Ld-sunHome);
    const gridHome=Math.max(Ld-sunHome-battHome,0);
    const chg=Math.max(b,0);
    const chgSun=Math.min(Math.max(P-sunHome,0),chg);
    const chgGrid=Math.max(chg-chgSun,0);
    let m;
    if(b<-0.03)m='battery';else if(chgGrid>0.03)m='grid_charge';else if(chgSun>0.03)m='solar_charge';
    else if(I<0.01&&P>=Ld*0.9)m='sun';else if(I<0.01)m='battery';else m='grid';
    return {t:new Date(t),price:D.price[i],P,Ld,I,b,sunHome,battHome,gridHome,chgSun,chgGrid,m};
  });
  for(let k=0;k<2;k++)for(let i=1;i<N-1;i++){if(steps[i].m!==steps[i-1].m&&steps[i].m!==steps[i+1].m&&steps[i].m!=='grid_charge')steps[i].m=steps[i-1].m;}
  blocks=[];
  steps.forEach((s,i)=>{const last=blocks[blocks.length-1];if(last&&last.m===s.m)last.end=i;else blocks.push({m:s.m,start:i,end:i});});
  blocks=blocks.reduce((acc,b,k)=>{const prev=acc[acc.length-1];if(prev&&(prev.m===b.m||(b.end===b.start&&k<blocks.length-1)))prev.end=b.end;else acc.push(b);return acc;},[]);
  blocks.forEach(b=>{const sl=steps.slice(b.start,b.end+1);b.avg=sl.reduce((a,s)=>a+s.price,0)/sl.length;b.from=steps[b.start].t;b.to=new Date(steps[b.end].t.getTime()+STEP_MS);});
  endTime=new Date(steps[N-1].t.getTime()+STEP_MS);
  solveT=new Date(D.summary.solve);
  pmin=Math.min(...D.price);pmax=Math.max(...D.price);
  const wb=(len,dir)=>{let best=null;for(let i=0;i+len<=N;i++){const a=D.price.slice(i,i+len).reduce((x,y)=>x+y,0)/len;if(best===null||dir*a<dir*best.a)best={i,a};}return best;};
  const wlen=Math.min(8,N);
  wash=wb(wlen,1);avoid=wb(wlen,-1);
  sunBest=null;for(let i=0;i+wlen<=N;i++){const s=D.pv.slice(i,i+wlen).reduce((x,y)=>x+y,0);if(!sunBest||s>sunBest.s)sunBest={i,s};}
}
const hm=d=>d.toLocaleTimeString(T[L].dateFmt,{hour:'2-digit',minute:'2-digit',timeZone:TZ});
const hr=d=>+d.toLocaleString('en-GB',{hour:'2-digit',hour12:false,timeZone:TZ});
const nf=(v,dg=1)=>new Intl.NumberFormat(T[L].dateFmt,{minimumFractionDigits:dg,maximumFractionDigits:dg}).format(v);
const eur=v=>'€ '+nf(v,2);
const cents=v=>Math.round(v*100);
const tAt=i=>i>=N?endTime:steps[i].t;
const WLEN=()=>Math.min(8,N);

function render(){
  const t=T[L];document.documentElement.lang=L;
  document.querySelectorAll('.lang button').forEach(b=>b.classList.toggle('on',b.dataset.l===L));
  document.getElementById('dateline').textContent=solveT.toLocaleDateString(t.dateFmt,{weekday:'long',day:'numeric',month:'long',timeZone:TZ});
  document.getElementById('title').innerHTML=t.title;
  const s=D.summary,pct=s.naive>0?Math.round(s.saving/s.naive*100):0;
  document.getElementById('saveK').textContent=t.saveK;document.getElementById('saveBig').innerHTML=`<small>€</small>${nf(s.saving,2)}`;document.getElementById('saveP').innerHTML=pct>0?t.saveP(pct):t.saveP0;
  document.getElementById('cb1').textContent=t.cb1;document.getElementById('cb2').textContent=t.cb2;document.getElementById('v1').textContent=eur(s.naive);document.getElementById('v2').textContent=eur(s.opt);
  requestAnimationFrame(()=>{document.getElementById('f1').style.width='100%';document.getElementById('f2').style.width=(s.naive>0?Math.max(0,Math.min(100,s.opt/s.naive*100)):0)+'%';});
  const cur=blocks[0],nxt=blocks[1]||blocks[0],mc=MODE[cur.m],mn=MODE[nxt.m];
  document.getElementById('nowK').textContent=t.nowK(hm(solveT));
  document.getElementById('nowIcon').style.background=mc.bg;document.getElementById('nowIcon').innerHTML=IC[mc.ic](mc.col);
  document.getElementById('nowWhat').textContent=t.m[cur.m].a;document.getElementById('nowWhy').textContent=t.m[cur.m].b(cents(cur.avg));
  document.getElementById('nextIcon').style.background=mn.bg;document.getElementById('nextIcon').innerHTML=IC[mn.ic](mn.col);
  document.getElementById('nextTxt').innerHTML=`${t.nextPre}, ${t.nextAt} <b>${hm(nxt.from)}</b>: ${t.m[nxt.m].a.toLowerCase()}`;
  document.getElementById('planH').textContent=t.planH;document.getElementById('planS').textContent=t.planS;
  const bar=document.getElementById('tlbar'),ul=document.getElementById('steps');bar.innerHTML='';ul.innerHTML='';
  blocks.forEach((b,k)=>{const m=MODE[b.m],n=b.end-b.start+1;
    const seg=document.createElement('div');seg.className='tl-seg';seg.style.flex=n;seg.style.background=m.col;seg.dataset.k=k;
    seg.title=`${hm(b.from)} - ${hm(b.to)}  ${t.m[b.m].a}`;if(n>=3)seg.innerHTML=IC[m.ic]('#fff');bar.appendChild(seg);
    const li=document.createElement('li');li.dataset.k=k;
    li.innerHTML=`<span class="time">${hm(b.from)} - ${hm(b.to)}</span><div class="icon" style="background:${m.bg}">${IC[m.ic](m.col)}</div><div><div class="t1">${t.m[b.m].a}</div><div class="t2">${t.m[b.m].b(cents(b.avg))}</div></div><span class="pill" style="background:${m.bg};color:${m.col}">± ${cents(b.avg)} ${t.cent}</span>`;
    ul.appendChild(li);});
  const sel=k=>document.querySelectorAll('.tl-seg,.steps li').forEach(e=>e.classList.toggle('sel',e.dataset.k==k));
  bar.onclick=ul.onclick=e=>{const el=e.target.closest('[data-k]');if(el){sel(el.dataset.k);if(el.classList.contains('tl-seg')){const r=ul.querySelector(`li[data-k="${el.dataset.k}"]`);if(r)r.scrollIntoView({behavior:'smooth',block:'nearest'});}}};
  bar.onmouseover=e=>{const el=e.target.closest('[data-k]');if(el)sel(el.dataset.k);};
  const ticks=document.getElementById('tlticks');ticks.innerHTML='';
  steps.forEach((st,i)=>{if(st.t.getUTCMinutes()===0&&hr(st.t)%2===0){const sp=document.createElement('span');sp.style.left=(i/N*100)+'%';sp.textContent=hm(st.t);ticks.appendChild(sp);}});
  const used=[...new Set(blocks.map(b=>b.m))];
  document.getElementById('legend').innerHTML=used.map(m=>`<span><i style="background:${MODE[m].col}"></i>${t.m[m].a}</span>`).join('');
  document.getElementById('tipsH').textContent=t.tipsH;document.getElementById('tipsS').textContent=t.tipsS;
  const tc=(ic,col,bg,arr)=>`<div class="tipcard"><div class="icon" style="background:${bg}">${IC[ic](col)}</div><div><b>${arr[0]}</b><span>${arr[1]}</span></div></div>`;
  const wl=WLEN(),avoidMax=Math.max(...D.price.slice(avoid.i,avoid.i+wl));
  document.getElementById('tips').innerHTML=tc('wash','#4E8A3E','#E2EFDB',t.tWash(hm(tAt(wash.i)),hm(tAt(wash.i+wl)),cents(wash.a)))+
    tc('coin','#C2502C','#F8E0D6',t.tAvoid(hm(tAt(avoid.i)),hm(tAt(avoid.i+wl)),cents(avoidMax)))+
    tc('sun','#D9901A','#FDEFD2',t.tSun(hm(tAt(sunBest.i)),hm(tAt(sunBest.i+wl))));
  document.getElementById('priceH').textContent=t.priceH;document.getElementById('priceS').textContent=t.priceS;
  document.getElementById('flowH').textContent=t.flowH;document.getElementById('flowS').textContent=t.flowS;
  const lg=t.lg;
  document.getElementById('flowLegend').innerHTML=[['var(--sun)',lg.sun],['var(--batt)',lg.batt],['var(--grid2)',lg.grid],['var(--sun2)',lg.cs],['#9DB7DE',lg.cg]].map(([c,n])=>`<span><i style="background:${c}"></i>${n}</span>`).join('')+`<span><i style="background:none;border-top:2px dashed var(--ink);border-radius:0;height:0;width:16px"></i>${L==='nl'?'Huisverbruik':'House usage'}</span>`;
  document.getElementById('srcH').textContent=t.srcH;document.getElementById('srcS').textContent=t.srcS;
  const sunT=steps.reduce((a,s)=>a+s.sunHome,0),battT=steps.reduce((a,s)=>a+s.battHome,0),gridT=steps.reduce((a,s)=>a+s.gridHome,0),tot=sunT+battT+gridT||1;
  const seg2=(v,c,n)=>`<div style="flex:${v};background:${c}">${v/tot>.12?`${n} ${Math.round(v/tot*100)}%`:''}</div>`;
  document.getElementById('srcbar').innerHTML=seg2(sunT,'var(--sun)',lg.sun)+seg2(battT,'var(--batt)',lg.batt)+seg2(gridT,'var(--grid)',lg.grid);
  const stt=t.st;
  document.getElementById('stats').innerHTML=[[nf(s.load,1),'kWh',stt.use],[nf(s.pv,1),'kWh',stt.sun],[nf(s.import,1),'kWh',stt.imp],[nf(s.self,0),'%',stt.self]]
    .map(([n,u,l])=>`<div class="stat"><div class="n">${n}<small>${u}</small></div><div class="l">${l}</div></div>`).join('');
  document.getElementById('foot').innerHTML=t.foot(hm(solveT),nf((endTime-steps[0].t)/36e5,0));
  drawPrice();drawFlow();
}

function drawPrice(){
  const box=document.getElementById('priceChart'),tip=box.querySelector('.tip');box.querySelectorAll('svg').forEach(e=>e.remove());
  const W=box.clientWidth||600,H=270,ml=34,mr=10,mt=30,mb=28;
  const lo=Math.floor(pmin*20)/20-0.02,hi=Math.ceil(pmax*20)/20||0.05;
  const x=i=>ml+(i/(Math.max(1,N-1)))*(W-ml-mr),y=p=>mt+(1-(p-lo)/((hi-lo)||1))*(H-mt-mb);
  let path='';D.price.forEach((p,i)=>{path+=(i?'L':'M')+x(i).toFixed(1)+','+y(p).toFixed(1);});
  const yl=y(pmax),yh=y(pmin);
  let g=`<defs><linearGradient id="pg" gradientUnits="userSpaceOnUse" x1="0" y1="${yl}" x2="0" y2="${yh}"><stop offset="0" stop-color="#D25F3A"/><stop offset=".5" stop-color="#E2A93B"/><stop offset="1" stop-color="#6E9E5C"/></linearGradient><linearGradient id="pa" gradientUnits="userSpaceOnUse" x1="0" y1="${yl}" x2="0" y2="${H-mb}"><stop offset="0" stop-color="#D25F3A" stop-opacity=".22"/><stop offset=".6" stop-color="#E2A93B" stop-opacity=".12"/><stop offset="1" stop-color="#6E9E5C" stop-opacity=".02"/></linearGradient></defs>`;
  for(let v=Math.ceil(lo*20)/20;v<=hi+1e-9;v+=0.05){g+=`<line x1="${ml}" x2="${W-mr}" y1="${y(v)}" y2="${y(v)}" stroke="#EADFCD"/><text x="${ml-6}" y="${y(v)+4}" text-anchor="end" font-size="11" fill="#8B8578">${Math.round(v*100)}</text>`;}
  g+=`<text x="${ml-6}" y="${mt-14}" text-anchor="end" font-size="11" fill="#8B8578">${T[L].cent}</text>`;
  steps.forEach((st,i)=>{if(st.t.getUTCMinutes()===0&&hr(st.t)%3===2)g+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle" font-size="11" fill="#8B8578">${hm(st.t)}</text>`;});
  g+=`<path d="${path}L${x(N-1)},${H-mb}L${x(0)},${H-mb}Z" fill="url(#pa)"/><path d="${path}" fill="none" stroke="url(#pg)" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>`;
  const imin=D.price.indexOf(pmin),imax=D.price.indexOf(pmax);
  const lab=(i,txt,c,up)=>`<circle cx="${x(i)}" cy="${y(D.price[i])}" r="5.5" fill="#fff" stroke="${c}" stroke-width="3"/><text x="${x(i)}" y="${y(D.price[i])+(up?-12:22)}" text-anchor="middle" font-size="12" font-weight="600" fill="${c}">${txt}</text>`;
  g+=lab(imin,`${T[L].cheapest} ${hm(steps[imin].t)} · ${cents(pmin)}c`,'#4E8A3E',false);
  g+=lab(imax,`${T[L].dearest} ${hm(steps[imax].t)} · ${cents(pmax)}c`,'#C2502C',true);
  g+=`<line id="pcur" y1="${mt}" y2="${H-mb}" stroke="#1E2733" stroke-width="1" stroke-dasharray="3 3" opacity="0"/><circle id="pdot" r="5" fill="#1E2733" opacity="0"/><rect x="${ml}" y="0" width="${W-ml-mr}" height="${H}" fill="transparent" id="phit"/>`;
  box.insertAdjacentHTML('afterbegin',`<svg height="${H}" viewBox="0 0 ${W} ${H}">${g}</svg>`);
  const hit=box.querySelector('#phit'),cur=box.querySelector('#pcur'),dot=box.querySelector('#pdot');
  hit.onmousemove=e=>{const r=box.getBoundingClientRect();const i=Math.max(0,Math.min(N-1,Math.round((e.clientX-r.left-ml)/(W-ml-mr)*(N-1))));const p=D.price[i];
    cur.setAttribute('x1',x(i));cur.setAttribute('x2',x(i));cur.setAttribute('opacity',1);dot.setAttribute('cx',x(i));dot.setAttribute('cy',y(p));dot.setAttribute('opacity',1);
    tip.style.left=x(i)+'px';tip.style.top=y(p)+'px';tip.style.opacity=1;tip.innerHTML=`${hm(steps[i].t)}<br><b>${cents(p)} ${T[L].cent}</b> / kWh`;};
  hit.onmouseleave=()=>{tip.style.opacity=0;cur.setAttribute('opacity',0);dot.setAttribute('opacity',0);};
}

function drawFlow(){
  const box=document.getElementById('flowChart'),tip=box.querySelector('.tip');box.querySelectorAll('svg').forEach(e=>e.remove());
  const H={},order=[];
  steps.forEach(s=>{const k=hr(s.t);if(!(k in H)){H[k]={h:k,sun:0,batt:0,grid:0,cs:0,cg:0,use:0,price:0,n:0};order.push(k);}const o=H[k];o.sun+=s.sunHome;o.batt+=s.battHome;o.grid+=s.gridHome;o.cs+=s.chgSun;o.cg+=s.chgGrid;o.use+=s.Ld;o.price+=s.price;o.n++;});
  const hrs=order.map(k=>H[k]);
  hrs.forEach(o=>{o.sun*=0.25;o.batt*=0.25;o.grid*=0.25;o.cs*=0.25;o.cg*=0.25;o.use*=0.25;});
  const W=box.clientWidth||600,Ht=320,ml=40,mr=10,mt=16,mb=30;
  const up=Math.max(...hrs.map(o=>o.sun+o.batt+o.grid),0.1),dn=Math.max(...hrs.map(o=>o.cs+o.cg),0.1);
  const top=Math.ceil(up*4)/4,bot=Math.ceil(dn*4)/4,y=v=>mt+(top-v)/((top+bot)||1)*(Ht-mt-mb);
  const bw=(W-ml-mr)/hrs.length,pad=Math.max(3,bw*.18);let g='';
  for(let v=-bot;v<=top+1e-9;v+=0.25){g+=`<line x1="${ml}" x2="${W-mr}" y1="${y(v)}" y2="${y(v)}" stroke="${v===0?'#B9AE9A':'#EFE6D6'}" ${v===0?'stroke-width="1.5"':''}/>`;if(Math.abs(v*2-Math.round(v*2))<1e-6)g+=`<text x="${ml-6}" y="${y(v)+4}" text-anchor="end" font-size="11" fill="#8B8578">${nf(Math.abs(v),1)}</text>`;}
  g+=`<text x="${ml-6}" y="${mt-4}" text-anchor="end" font-size="11" fill="#8B8578">kWh</text>`;
  const rect=(x0,v0,v1,c,r)=>{const a=y(Math.max(v0,v1)),b=y(Math.min(v0,v1));return b-a<0.5?'':`<rect x="${x0}" y="${a}" width="${bw-2*pad}" height="${b-a}" fill="${c}" rx="${r}"/>`;};
  let linePts=[];
  hrs.forEach((o,i)=>{const x0=ml+i*bw+pad;let acc=0;g+=rect(x0,acc,acc+=o.sun,'#F0A92E',2);g+=rect(x0,acc,acc+=o.batt,'#2E8C80',2);g+=rect(x0,acc,acc+=o.grid,'#C9CFDA',2);
    let d=0;g+=rect(x0,d,d-=o.cs,'#FFD27A',2);g+=rect(x0,d,d-=o.cg,'#9DB7DE',2);linePts.push([ml+i*bw+bw/2,y(o.use)]);
    g+=`<text x="${ml+i*bw+bw/2}" y="${Ht-10}" text-anchor="middle" font-size="11" fill="#8B8578">${String(o.h).padStart(2,'0')}${bw>40?':00':''}</text>`;});
  g+=`<polyline points="${linePts.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#1E2733" stroke-width="1.6" stroke-dasharray="4 4"/><rect id="fhl" y="${mt}" height="${Ht-mt-mb}" width="${bw}" fill="#1E2733" opacity="0" rx="8"/><rect x="${ml}" y="0" width="${W-ml-mr}" height="${Ht}" fill="transparent" id="fhit"/>`;
  box.insertAdjacentHTML('afterbegin',`<svg height="${Ht}" viewBox="0 0 ${W} ${Ht}">${g}</svg>`);
  const hit=box.querySelector('#fhit'),hl=box.querySelector('#fhl'),lg=T[L].lg;
  hit.onmousemove=e=>{const r=box.getBoundingClientRect();const i=Math.max(0,Math.min(hrs.length-1,Math.floor((e.clientX-r.left-ml)/bw)));const o=hrs[i];
    hl.setAttribute('x',ml+i*bw);hl.setAttribute('opacity',.05);
    const row=(c,n,v)=>v>0.005?`<span style="color:${c}">■</span> ${n}: ${nf(v,2)} kWh<br>`:'';
    tip.innerHTML=`<b>${String(o.h).padStart(2,'0')}:00 - ${String((o.h+1)%24).padStart(2,'0')}:00</b> · ${cents(o.price/o.n)} ${T[L].cent}<br>`+row('#F0A92E',lg.sun,o.sun)+row('#5FC2B4',lg.batt,o.batt)+row('#C9CFDA',lg.grid,o.grid)+row('#FFD27A',lg.cs,o.cs)+row('#9DB7DE',lg.cg,o.cg);
    tip.style.left=Math.min(Math.max(ml+i*bw+bw/2,110),W-110)+'px';tip.style.top=(y(Math.max(o.sun+o.batt+o.grid,o.use))-6)+'px';tip.style.opacity=1;};
  hit.onmouseleave=()=>{tip.style.opacity=0;hl.setAttribute('opacity',0);};
}

function boot(){
  if(!N){document.querySelector('.wrap').innerHTML=`<div class="wait">${T[L].wait}</div>`;return;}
  prep();
  document.querySelectorAll('.lang button').forEach(b=>b.onclick=()=>{L=b.dataset.l;render();});
  let rt;window.addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(()=>{drawPrice();drawFlow();},120);});
  render();
}
boot();
</script>
</body>
</html>
"""
