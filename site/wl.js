// DK Wind League page: loads the published JSON, fills both tabs and draws the charts. Ported from the design handoff (wl.js).
(function () {
const isIfs = k => k == "ifs" || k == "ecmwf_ifs025";
const NS = "http://www.w3.org/2000/svg", TZ = {timeZone: "Europe/Copenhagen"};
const isoCph = t => new Date(t).toLocaleDateString("en-CA", TZ);
const hm = t => new Date(t).toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit", ...TZ});
const dS = d => new Date(d + "T12:00Z").toLocaleDateString("en-GB", {day: "numeric", month: "short", timeZone: "UTC"}).replace("Sept", "Sep");
const dW = d => new Date(d + "T12:00Z").toLocaleDateString("en-GB", {weekday: "short", day: "numeric", month: "short", timeZone: "UTC"}).replace("Sept", "Sep");
const addD = (d, k) => new Date(new Date(d + "T12:00Z").getTime() + k * 864e5).toISOString().slice(0, 10);
const next = d => addD(d, 1);
const ord = r => r == 1 ? "1st" : r == 2 ? "2nd" : r == 3 ? "3rd" : r + "th";
const th = {ink: "#1d1d1b", mute: "#6b6a65", faint: "#9a988f", line: "#e4e1d9", grid: "#efece5", ours: "#c2410c", en: "#0e8a7d", ifs: "#1e3a8a", alt: "#1d1d1b", other: "#cfccc3", tint: "#fbf1e7", live: "#f3f5fb", font: "'IBM Plex Sans',system-ui,sans-serif", tipBg: "#1d1d1b"};
// Energy goes live with J4catDK on 31 Oct. data.live.from says 30 Oct because the old 4-model forecast was scored that day; it is not used here.
const LIVE_FROM = "2026-10-31";
// Made-up ranks for weather days with no scores yet (design handoff). Off: the chart shows only real scores.
const STAND_IN = false;
const D = {};

function el(tag, a, p, t) { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (t !== undefined) e.textContent = t; if (p) p.appendChild(e); return e; }
function svg(host, w, h) { host.innerHTML = ""; return el("svg", {viewBox: `0 0 ${w} ${h}`, width: "100%", role: "img", style: `display:block;font-family:${th.font}`}, host); }
let tipEl;
function tip(e, html) {
  if (!tipEl) { tipEl = document.createElement("div"); tipEl.style.cssText = `position:fixed;z-index:999;pointer-events:none;padding:8px 10px;border-radius:6px;color:#fff;background:${th.tipBg};font:12.5px/1.45 ${th.font};max-width:280px;box-shadow:0 6px 20px rgba(0,0,0,.18);display:none;font-variant-numeric:tabular-nums`; document.body.appendChild(tipEl); }
  tipEl.innerHTML = html; tipEl.style.display = "block";
  tipEl.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - tipEl.offsetWidth - 8)) + "px";
  tipEl.style.top = (e.clientY + 16 + tipEl.offsetHeight > innerHeight ? e.clientY - tipEl.offsetHeight - 10 : e.clientY + 16) + "px";
}
const untip = () => tipEl && (tipEl.style.display = "none");
const nm = (names, k) => (names[k] || k).replace(" (my own model)", "").replace(", corrected at each station", "").replace(" (bias-corrected)", "").replace(" (AI)", " AI");
const word = n => ["zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve"][n] || String(n);
const esc = s => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

// ---------- data ----------
async function load() {
  const j = u => fetch(u, {cache: "no-store"}).then(r => r.ok ? r.json() : null).catch(() => null);
  const [Dd, TL, SM, TD, WX, RK, RM, WT, FW] = await Promise.all(["data.json", "timeline.json", "summary.json", "today.json", "weather.json", "data_alt/wx_ranks.json", "data_alt/wx_ranks_more.json", "data_alt/wx_timeline.json"].map(j).concat([j("https://bolgacg.github.io/dk-forecast/data/weather.json")]));
  Object.assign(D, {D: Dd, TL, SM, TD, WX, RK, RM, WT, FW});
  return kpis();
}
function wxScores() {
  const V = [["wind", "Wind"], ["temp", "Temperature"], ["sun", "Sunshine"], ["rain", "Rain"]];
  return V.map(([k, label], i) => {
    if (D.FW && D.FW[k]) { const d = D.FW[k], me = d.rows.find(r => r.name == "DKcast"), pub = d.rows.filter(r => r.name != "DKcast").sort((a, b) => a.val - b.val);
      return {k, label, unit: d.unit, me: me.val, best: pub[0], pub}; }
    const w = D.WX && D.WX.vars[i]; if (!w) return null; const br = w.metric.startsWith("Brier");
    const me = br ? w.dkcast_brier : w.dkcast_rmse, ref = br ? w.ref_brier : w.ref_rmse;
    return {k, label, unit: br ? "Brier" : w.unit, me, best: {name: w.ref_name, val: ref}, pub: [{name: w.ref_name, val: ref}].concat(w.ifs_rmse ? [{name: "ECMWF IFS", val: w.ifs_rmse}] : [])};
  }).filter(Boolean);
}
const fmtWx = (v, u) => u == "Brier" ? v.toFixed(3) : v.toFixed(u == "min/h" ? 1 : 2);
const signed = v => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(1) + "%";
function kpis() {
  const T = D.SM.test_2026, bt = D.D.backtest, by = s => bt.overall.find(r => r.source == s), me = by("j4catdk"), en = by("energinet"), ifs = by("ifs");
  const TL = D.TL, today = TL.today, tom = next(today), F = (D.D.health && D.D.health.forecasts) || {};
  const done = TL.days.filter(d => d.complete && d.err && d.err.j4catdk != null), wk = done.filter(d => d.err.j4catdk <= d.err.energinet).length;
  const wx = wxScores(), lead = s => Math.round(100 * (1 - s.me / s.best.val)), f1 = v => v.toFixed(1), f2 = v => v.toFixed(2);
  return {
    testPeriod: T.period, testDays: T.days, testHours: T.hours.toLocaleString("en"),
    tMine: f2(T.nmae_pct.j4catdk), tEn: f2(T.nmae_pct.energinet), tIfs: f2(T.nmae_pct.ifs),
    skillEn: f1(T.skill_vs_energinet_pct), skillEnLo: f1(T.skill_vs_energinet_ci95[0]), skillEnHi: f1(T.skill_vs_energinet_ci95[1]),
    daysBetter: T.days_better_than_energinet_pct, imbMine: f2(T.imbalance_eur_mwh.j4catdk), imbEn: f2(T.imbalance_eur_mwh.energinet),
    today, tom, todayLabel: dW(today), tomLabel: dW(tom), tomShort: dS(tom),
    todayIssued: F[today] ? `${dW(isoCph(F[today].issued_utc))}, ${hm(F[today].issued_utc)}` : null,
    tomIssued: F[tom] ? hm(F[tom].issued_utc) : null,
    measured: D.TD ? D.TD.hours_measured : 0, total: D.TD ? D.TD.hours_total : 24,
    updated: `${dW(isoCph(TL.built_utc))}, ${hm(TL.built_utc)}`,
    btFrom: dS(bt.from), btTo: dS(bt.to), btDays: bt.days, btN: bt.overall.length,
    me, en, ifs, bWinMine: me.wins, wkWins: wk, wkN: done.length,
    wx: wx.map(s => ({label: s.label, rain: s.k == "rain", unit: s.unit == "Brier" ? "Brier score" : s.unit == "min/h" ? "min of sun per hour" : s.unit, unitShort: s.unit == "min/h" ? "min/h" : s.unit,
      me: fmtWx(s.me, s.unit), best: fmtWx(s.best.val, s.unit), bestName: s.best.name.replace(", station-corrected", "").replace("icon_eu", "DWD ICON-EU"), lead: lead(s)}))
  };
}

// ---------- timeline: measured vs mine vs the rival, hour by hour (Energy and Meteorology) ----------
// c: {S (rows {t, a, mine, riv}), days ({day, complete, err: {mine, riv}}), today, now, mineName, rivName, rivCol, rivTip,
//     ticks ([values]), tickFmt, unit, val (tooltip value), chip (error value), chipUnit}
function tlChart(host, c) {
  const S = c.S, n = S.length, W = 760, L = 46, R = 6, top = 36, H = 330, bot = 26, bw = (W - L - R) / n;
  const lo = c.ticks[0], hi = c.ticks[c.ticks.length - 1], X = i => L + (i + .5) * bw, Y = v => top + (1 - (v - lo) / (hi - lo)) * (H - top - bot);
  const s = svg(host, W, H);
  const days = c.days.map(d => { const ix = []; S.forEach((r, i) => { if (isoCph(r.t + ":00Z") == d.day) ix.push(i); }); return ix.length ? {...d, a: ix[0], b: ix[ix.length - 1]} : null; }).filter(Boolean);
  days.forEach((d, k) => { const xa = L + d.a * bw, xb = L + (d.b + 1) * bw, mid = (xa + xb) / 2, fut = d.day >= c.today;
    if (fut) el("rect", {x: xa, y: 0, width: xb - xa, height: H - bot, fill: d.day == c.today ? th.tint : th.live}, s);
    if (k) el("line", {x1: xa, x2: xa, y1: 0, y2: H - bot, stroke: th.line}, s);
    el("text", {x: mid, y: H - 8, "text-anchor": "middle", "font-size": 11, fill: fut ? th.ink : th.mute, "font-weight": fut ? 600 : 400}, s, d.day == c.today ? "Today" : d.day > c.today ? "Tomorrow" : dS(d.day));
    const e = d.err || {};
    if (e.mine != null && e.riv != null) { const win = e.mine <= e.riv, col = win ? th.ours : c.rivCol;
      el("rect", {x: xa + 3, y: 0, width: xb - xa - 6, height: 3, rx: 1.5, fill: col}, s);
      el("text", {x: mid, y: 17, "text-anchor": "middle", "font-size": 11, "font-weight": 600, fill: col}, s, (win ? c.mineName : c.rivName) + (d.complete ? " ✓" : " ◌"));  // dotted circle: day still running, so only the current leader
      const t = el("text", {x: mid, y: 30, "text-anchor": "middle", "font-size": 10.5, fill: th.mute}, s);
      el("tspan", {fill: th.ours, "font-weight": win ? 600 : 400}, t, c.chip(e.mine)); el("tspan", {}, t, " vs "); el("tspan", {fill: c.rivCol, "font-weight": win ? 400 : 600}, t, c.chip(e.riv) + c.chipUnit);
    } else el("text", {x: mid, y: 20, "text-anchor": "middle", "font-size": 10, fill: th.faint}, s, `scored ${dS(next(d.day))}`); });
  c.ticks.forEach(v => { el("line", {x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: v == lo ? th.line : th.grid}, s);
    el("text", {x: L - 8, y: Y(v) + 3.5, "text-anchor": "end", "font-size": 10.5, fill: th.mute}, s, c.tickFmt(v)); });
  el("text", {x: L - 8, y: Y(hi) - 14, "text-anchor": "end", "font-size": 10, fill: th.faint}, s, c.unit);
  let seg = []; const flush = () => { if (seg.length > 1) el("path", {d: "M" + seg.map(([i, r]) => `${X(i)},${Y(r.mine)}`).join("L") + "L" + seg.slice().reverse().map(([i, r]) => `${X(i)},${Y(r.a)}`).join("L") + "Z", fill: th.ours, opacity: .14}, s); seg = []; };
  if (c.bars) S.forEach((r, i) => { if (r.a) el("rect", {x: X(i) - bw / 2, y: Y(r.a), width: bw, height: Y(lo) - Y(r.a), fill: th.ink, opacity: .14}, s); });  // rain: measured wet share as bars
  else S.forEach((r, i) => { if (r.a != null && r.mine != null) seg.push([i, r]); else flush(); }); flush();
  const line = (k, col, w) => { let d = "", pen = false; S.forEach((r, i) => { if (r[k] == null) { pen = false; return; } d += (pen ? "L" : "M") + X(i).toFixed(1) + "," + Y(r[k]).toFixed(1); pen = true; });
    el("path", {d, fill: "none", stroke: col, "stroke-width": w, "stroke-linejoin": "round", "stroke-linecap": "round"}, s); };
  line("riv", c.rivCol, 1.5); line("mine", th.ours, 2.2); if (!c.bars) line("a", th.ink, 2);
  const ni = S.findIndex(r => r.a == null && r.t >= c.now.slice(0, 13)), nx = ni < 0 ? null : L + ni * bw;
  if (nx) { el("line", {x1: nx, x2: nx, y1: top, y2: H - bot, stroke: th.ink, "stroke-dasharray": "2 3"}, s);
    el("text", {x: nx + 4, y: top + 10, "font-size": 10.5, fill: th.ink, "font-weight": 600}, s, "now"); }
  const cross = el("line", {y1: top, y2: H - bot, stroke: th.mute, opacity: 0}, s), dots = ["a", "mine", "riv"].map((k, q) => el("circle", {r: 3.5, fill: [th.ink, th.ours, c.rivCol][q], stroke: "#fff", "stroke-width": 1.5, opacity: 0}, s));
  const pad = el("rect", {x: L, y: top, width: W - L - R, height: H - top - bot, fill: "transparent", style: "cursor:crosshair"}, s);
  const mv = ev => { const b = s.getBoundingClientRect(), px = (ev.clientX - b.left) * W / b.width, i = Math.max(0, Math.min(n - 1, Math.floor((px - L) / bw))), r = S[i];
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("opacity", .6);
    ["a", "mine", "riv"].forEach((k, q) => { if (r[k] == null) dots[q].setAttribute("opacity", 0); else { dots[q].setAttribute("cx", X(i)); dots[q].setAttribute("cy", Y(r[k])); dots[q].setAttribute("opacity", 1); } });
    const t = new Date(r.t + ":00Z"), f = (v, none) => v == null ? none : c.val(v);
    tip(ev, `<b>${dW(isoCph(t))}, ${hm(t)}</b><br>Measured ${f(r.a, "not measured yet")}<br><span style="color:#fdba74">${esc(c.mineName)} ${f(r.mine, "no forecast")}</span><br><span style="color:${c.rivTip}">${esc(c.rivLong || c.rivName)} ${f(r.riv, "no forecast")}</span>` + (r.a != null && r.mine != null ? `<br><span style="opacity:.7">${esc(c.mineName)} miss ${c.val(Math.abs(r.mine - r.a))}</span>` : "")); };
  pad.addEventListener("pointermove", mv); pad.addEventListener("pointerleave", () => { cross.setAttribute("opacity", 0); dots.forEach(q => q.setAttribute("opacity", 0)); untip(); });
}
const ticksFor = (vals, step, floor0) => { const v = vals.filter(x => x != null); let lo = floor0 ? 0 : Math.floor(Math.min(...v) / step) * step, hi = Math.ceil(Math.max(...v) / step) * step;
  if (hi == lo) hi = lo + step; const t = []; for (let x = lo; x <= hi + 1e-9; x += step) t.push(+x.toFixed(6)); return t; };
function timeline(host) {
  const TL = D.TL, S = TL.series.map(r => ({t: r.t, a: r.a, mine: r.j, riv: r.e}));
  const mx = Math.ceil(Math.max(...S.flatMap(r => [r.a, r.mine, r.riv]).filter(v => v != null)) / 1000) * 1000;
  tlChart(host, {S, days: TL.days.map(d => ({...d, err: d.err ? {mine: d.err.j4catdk, riv: d.err.energinet} : {}})), today: TL.today, now: TL.now_utc,
    mineName: "J4catDK", rivName: "Energinet", rivCol: th.en, rivTip: "#5eead4", ticks: ticksFor([0, mx], 1000, true), tickFmt: v => v ? (v / 1000) + "k" : "0", unit: "MW",
    val: v => v.toLocaleString("en") + " MW", chip: v => v.toFixed(1), chipUnit: "%"});
}
const RIV = "#8b8778";  // the rival on the weather timeline: grey, because measured is black
const SHORT = {ecmwf_ifs025: "IFS", ecmwf_aifs025_single: "AIFS", icon_eu: "ICON-EU", icon_d2: "ICON-D2", dmi_harmonie_arome_europe: "DMI",
  knmi_harmonie_arome_europe: "KNMI", gfs_global: "GFS", ukmo_global_deterministic_10km: "UK Met", metno_nordic: "MET Nor", gem_global: "GEM"};
function wxTimeline(host, a) {
  const T = D.WT && D.WT.vars[a.var]; if (!T) { host.innerHTML = `<p style="font:13px ${th.font};color:${th.mute};padding:24px;text-align:center">Not available yet.</p>`; return; }
  const v = a.var, pl = a.place || "national", rain = v == "rain", S = T.series[pl].map(r => ({t: r.t, a: r.a, mine: r.d, riv: r.r}));
  const vals = S.flatMap(r => [r.a, r.mine, r.riv]);
  const ticks = rain ? [0, .25, .5, .75, 1] : v == "sun" ? [0, 15, 30, 45, 60] : v == "wind" ? ticksFor(vals, 2, true) : ticksFor(vals, Math.max(...vals.filter(x => x != null)) - Math.min(...vals.filter(x => x != null)) > 12 ? 4 : 2, false);
  const val = {wind: x => x.toFixed(1) + " m/s", temp: x => x.toFixed(1) + " °C", sun: x => x.toFixed(0) + " min of sun", rain: x => Math.round(100 * x) + "% chance of rain"}[v];
  tlChart(host, {S, days: T.days[pl].map(d => ({...d, err: d.err && d.err.d != null ? {mine: d.err.d, riv: d.err.r} : {}})), today: D.WT.today, now: D.WT.now_utc,
    mineName: "DKcast", rivName: SHORT[T.rival] || T.rival_name, rivLong: T.rival_name, rivCol: RIV, rivTip: "#d6d3cc", ticks,
    tickFmt: rain ? x => Math.round(100 * x) + "%" : x => String(x), unit: {wind: "m/s", temp: "°C", sun: "min/h", rain: "rain"}[v],
    val: rain ? x => Math.round(100 * x) + "%" : val, chip: rain ? x => x.toFixed(3) : x => x.toFixed(v == "sun" ? 1 : 2), chipUnit: {wind: "", temp: "°", sun: "", rain: ""}[v], bars: rain});
  const done = T.days[pl].filter(d => d.complete && d.err && d.err.d != null), wins = done.filter(d => d.err.d <= d.err.r).length, P = T.places[pl];
  const where = pl == "national" ? `averaged over DKcast's ${P.stations} stations` : `at ${P.station_name}`;
  const intro = document.getElementById("wxtl-intro"); if (intro) intro.textContent = `DKcast had the smaller error on ${wins} of the ${done.length} complete days shown, ${where}, against ${T.rival_name}, the best public model in the leaderboard above. ${rain ? "Grey bars are the measured share of wet hours, the lines each forecast's chance of rain" : "The shaded gap is DKcast's miss"}; above each day: who won, then the two errors (${rain ? "Brier score" : "average miss in " + T.unit}).`;
  const lg = document.getElementById("wxtl-riv"); if (lg) lg.textContent = T.rival_name;
  const ms = document.getElementById("wxtl-meas"); if (ms) ms.innerHTML = rain ? `<span class="sw" style="width:10px;height:10px;background:${th.ink};opacity:.25"></span>Measured, share of wet hours` : `${sw(th.ink, 2)}Measured`;
  const mm = document.getElementById("wxtl-miss"); if (mm) mm.hidden = rain;
  document.querySelectorAll("#pane-weather .places button").forEach(b => { if (b.dataset.place == "aarhus") b.textContent = v == "wind" ? "Århus Lufthavn (Aarhus)" : "Ødum (Aarhus)"; });
}

// ---------- league: average error + days in first place ----------
function league(host) {
  const bt = D.D.backtest, o = bt.overall, W = 760, L = 170, X1 = 470, C0 = 540, R = 30, rowH = 28, top = 34, H = top + o.length * rowH + 18;
  const lo = Math.floor(Math.min(...o.map(r => r.nmae)) - .5), hi = Math.ceil(Math.max(...o.map(r => r.nmae)) + .3), x = v => L + (v - lo) / (hi - lo) * (X1 - L);
  const mw = Math.max(...o.map(r => r.wins)), xw = v => C0 + v / mw * (W - R - C0 - 24), s = svg(host, W, H);
  el("text", {x: L, y: 12, "font-size": 11, "font-weight": 600, fill: th.ink}, s, "Average error, % of capacity");
  el("text", {x: L, y: 25, "font-size": 10.5, fill: th.mute}, s, "lower is better");
  el("text", {x: C0, y: 12, "font-size": 11, "font-weight": 600, fill: th.ink}, s, "Days in first place");
  el("text", {x: C0, y: 25, "font-size": 10.5, fill: th.mute}, s, `of ${bt.days}, among all ${o.length}`);
  for (let v = lo; v <= hi; v++) { el("line", {x1: x(v), x2: x(v), y1: top - 4, y2: H - 16, stroke: th.grid}, s); el("text", {x: x(v), y: H - 3, "text-anchor": "middle", "font-size": 10.5, fill: th.mute}, s, v + "%"); }
  o.forEach((r, i) => { const y = top + i * rowH + rowH / 2, me = r.source == "j4catdk", en = r.source == "energinet", fx = isIfs(r.source), c = me ? th.ours : en ? th.en : fx ? th.ifs : th.faint;
    if (me) el("rect", {x: 0, y: y - rowH / 2 + 2, width: W, height: rowH - 4, fill: th.tint, rx: 4}, s);
    el("text", {x: L - 14, y: y + 4, "text-anchor": "end", "font-size": 12.5, "font-weight": me || en || fx ? 600 : 400, fill: me ? th.ours : en ? th.en : fx ? th.ifs : th.ink}, s, me ? "J4catDK (mine)" : nm(D.TL.names, r.source));
    el("line", {x1: L, x2: x(r.nmae), y1: y, y2: y, stroke: th.line}, s);
    const dot = el("circle", {cx: x(r.nmae), cy: y, r: me ? 6 : 4.5, fill: c}, s);
    dot.addEventListener("pointermove", e => tip(e, `<b>${nm(D.TL.names, r.source)}</b><br>${r.nmae.toFixed(2)}% of capacity<br><span style="opacity:.75">DK1 ${r.nmae_DK1.toFixed(2)}% · DK2 ${r.nmae_DK2.toFixed(2)}%</span>`)); dot.addEventListener("pointerleave", untip);
    el("text", {x: x(r.nmae) + 10, y: y + 4, "font-size": 11.5, fill: me ? th.ours : th.mute, "font-weight": me ? 600 : 400}, s, r.nmae.toFixed(2));
    const bar = el("rect", {x: C0, y: y - 6, width: Math.max(2, xw(r.wins) - C0), height: 12, rx: 2, fill: me ? th.ours : en ? th.en : fx ? th.ifs : th.other}, s);
    bar.addEventListener("pointermove", e => tip(e, `<b>${nm(D.TL.names, r.source)}</b><br>first on ${r.wins} of ${bt.days} days`)); bar.addEventListener("pointerleave", untip);
    el("text", {x: xw(r.wins) + 6, y: y + 4, "font-size": 11.5, fill: me ? th.ours : th.mute, "font-weight": me ? 600 : 400}, s, String(r.wins)); });
}

// ---------- DKcast vs every public model ----------
function wxRel(host) {
  const sc = wxScores(), W = 760, L = 110, LR = 96, top = 10, rowH = 46, H = top + sc.length * rowH + 30, R = W - LR;
  const ratios = sc.flatMap(s => [s.me / s.best.val, ...s.pub.map(p => p.val / s.best.val)]), lo = Math.floor(Math.min(...ratios) * 10 - .3) / 10, hi = Math.ceil(Math.max(...ratios) * 10 + .1) / 10;
  const x = q => L + (q - lo) / (hi - lo) * (R - L - 20), s = svg(host, W, H);
  for (let q = lo; q <= hi + 1e-9; q += .1) { el("line", {x1: x(q), x2: x(q), y1: top, y2: H - 22, stroke: th.grid}, s); el("text", {x: x(q), y: H - 6, "font-size": 10.5, fill: th.mute, "text-anchor": "middle"}, s, Math.round(q * 100) + "%"); }
  el("line", {x1: x(1), x2: x(1), y1: top, y2: H - 22, stroke: th.ink, "stroke-dasharray": "3 3"}, s);
  el("text", {x: R + 4, y: top + 4, "font-size": 10.5, fill: th.mute}, s, "DKcast's lead");
  sc.forEach((sc1, i) => { const y = top + 22 + i * rowH;
    el("text", {x: L - 14, y: y + 4, "font-size": 12.5, "font-weight": 600, "text-anchor": "end", fill: th.ink}, s, sc1.label);
    el("line", {x1: x(sc1.me / sc1.best.val), x2: x(1), y1: y, y2: y, stroke: th.ours, "stroke-width": 2, opacity: .35}, s);
    sc1.pub.slice().sort((p, q) => /^ECMWF IFS/.test(p.name) - /^ECMWF IFS/.test(q.name)).forEach(r => { const c = el("circle", {cx: x(r.val / sc1.best.val), cy: y, r: 4.5, fill: /^ECMWF IFS/.test(r.name) ? th.ifs : th.other, stroke: "#fff", "stroke-width": 1}, s);
      c.addEventListener("pointermove", e => tip(e, `${esc(r.name)}<br>${fmtWx(r.val, sc1.unit)} ${sc1.unit}`)); c.addEventListener("pointerleave", untip); });
    const c = el("circle", {cx: x(sc1.me / sc1.best.val), cy: y, r: 7, fill: th.ours, stroke: "#fff", "stroke-width": 1.5}, s);
    c.addEventListener("pointermove", e => tip(e, `<b>DKcast</b> ${fmtWx(sc1.me, sc1.unit)} ${sc1.unit}<br>Best public, ${esc(sc1.best.name)}: ${fmtWx(sc1.best.val, sc1.unit)}`)); c.addEventListener("pointerleave", untip);
    el("text", {x: R + 4, y: y + 4.5, "font-size": 13, "font-weight": 700, fill: th.ours}, s, Math.round(100 * (1 - sc1.me / sc1.best.val)) + (sc1.k == "rain" ? "% better" : "% less")); });
}

// ---------- daily rank: a 14-day window around go-live that fills in nightly ----------
function rankWin(a) {
  const rep = [], live = [], put = (arr, r) => { if (![...rep, ...live].some(q => q.day == r.day && q.source == r.source)) arr.push({day: r.day, source: r.source, rank: r.rank, err: r.nmae != null ? r.nmae : r.mae}); };
  let names, ours, liveFrom, fmt, repLabel, errCol;
  if (a.src == "wx") { const v = a.var || "wind", RK = v == "wind" ? D.RK : D.RM && D.RM[v]; if (!RK || !RK.ranks) return null;
    names = RK.names; ours = "dkcast"; liveFrom = RK.live_from || LIVE_FROM; repLabel = RK.ranks.some(r => r.kind == "replayed") ? "Replayed" : "2026 test";
    (RK.live || []).forEach(r => put(live, r)); RK.ranks.forEach(r => put(r.kind == "live" || r.day >= liveFrom ? live : rep, r));
    errCol = {wind: ["m/s", e => e.toFixed(2)], temp: ["°C", e => e.toFixed(2)], sun: ["min of sun", e => e.toFixed(1)], rain: ["Brier score", e => e.toFixed(3)]}[v];
    fmt = {wind: e => `miss ${e.toFixed(2)} m/s`, temp: e => `miss ${e.toFixed(2)} °C`, sun: e => `miss ${e.toFixed(1)} min of sun`, rain: e => `Brier ${e.toFixed(3)}`}[v];
  } else { const TL = D.TL; names = TL.names; ours = "j4catdk"; liveFrom = TL.live_from || LIVE_FROM; repLabel = "Replayed";
    ((D.D.live && D.D.live.daily) || []).filter(r => r.day >= liveFrom && !r.no_forecast).forEach(r => put(live, r));
    TL.ranks.forEach(r => put(r.kind == "live" || r.day >= liveFrom ? live : rep, r));
    fmt = e => `error ${e.toFixed(2)}% of capacity`; errCol = ["% of capacity", e => e.toFixed(2) + "%"]; }
  const SL = 14, HALF = 7, ld = [...new Set(live.map(r => r.day))].sort(), last = ld[ld.length - 1];
  let end = addD(liveFrom, HALF - 1); if (last && next(last) > end) end = next(last);
  let all = []; for (let k = SL - 1; k >= 0; k--) all.push(addD(end, -k));
  let gapFrom = null;
  if (a.src == "wx" && rep.length && STAND_IN) { // stand-in rows for window days with no scores yet; replaced automatically when real rows exist
    const ks = [...new Set(rep.map(r => r.source))], mean = {}, errM = {};
    ks.forEach(k => { const v = rep.filter(r => r.source == k); mean[k] = v.reduce((p, q) => p + q.rank, 0) / v.length; errM[k] = v.reduce((p, q) => p + q.err, 0) / v.length; });
    const vh = [...(a.var || "wind")].reduce((p, c) => p * 31 + c.charCodeAt(0), 7);
    all.forEach(d => { if (d >= D.TL.today || rep.concat(live).some(r => r.day == d)) return;
      let seed = (+d.replace(/-/g, "") * 7 + vh) % 2147483647 || 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      ks.map(k => ({k, v: mean[k] + (rnd() - .5) * 5})).sort((p, q) => p.v - q.v)
        .forEach((q, i) => (d >= liveFrom ? live : rep).push({day: d, source: q.k, rank: i + 1, err: errM[q.k] * (.85 + rnd() * .3), stand: true})); });
  } else if (a.src == "wx" && !rep.some(r => all.includes(r.day) && r.day < liveFrom)) {
    // the weather test ends before the window: show its last 7 scored days, then the live days, with a break between them
    const rd = [...new Set(rep.map(r => r.day))].sort().slice(-HALF);
    if (rd.length) { gapFrom = next(rd[rd.length - 1]); all = rd.concat(all.filter(d => d >= liveFrom)); }
  }
  const rows = rep.filter(r => all.includes(r.day)).concat(live.filter(r => all.includes(r.day)));
  if (!rows.length) return null;
  const at = (d, k) => rows.find(r => r.day == d && r.source == k), has = d => rows.some(r => r.day == d);
  const srcs = [...new Set(rows.map(r => r.source))].map(k => { const rk = rows.filter(r => r.source == k).map(r => r.rank); return {k, avg: rk.reduce((p, q) => p + q, 0) / rk.length}; }).sort((p, q) => p.avg - q.avg);
  const rival = a.src == "wx" ? srcs.find(q => q.k != ours).k : "energinet", li = all.findIndex(d => d >= liveFrom);
  return {errCol, stand: rows.some(r => r.stand), all, rows, at, has, srcs, names, ours, rival, fmt, repLabel, liveFrom, li, gapFrom, liveRows: rows.some(r => r.day >= liveFrom), n: Math.max(...rows.map(r => r.rank)), wx: a.src == "wx"};
}
function bump(host, a) {
  const R0 = rankWin(a); if (!R0) { host.innerHTML = `<p style="font:13px ${th.font};color:${th.mute};padding:24px;text-align:center">Scores not available yet.</p>`; return; }
  const {all, n, srcs, ours, rival, li} = R0, W = 760, L = 44, R = 112, top = 34, step = R0.wx ? 18 : 21, H = top + (n - 1) * step + 30;
  const x = i => L + 20 + i * (W - L - R - 40) / Math.max(1, all.length - 1), y = r => top + (r - 1) * step, s = svg(host, W, H);
  const short = k => k == "energinet" ? "Energinet" : nm(R0.names, k);
  const col = k => k == ours ? th.ours : k == "energinet" ? th.en : isIfs(k) ? th.ifs : k == rival ? th.alt : "#dcd8cf", xEnd = x(all.length - 1) + 20;
  el("rect", {x: L, y: y(1) - step / 2, width: xEnd - L, height: step * 3, fill: th.tint, rx: 4}, s);
  for (let r = 1; r <= n; r++) el("text", {x: L - 8, y: y(r) + 3.5, "text-anchor": "end", "font-size": 10.5, fill: r == 1 ? th.ink : th.faint, "font-weight": r == 1 ? 600 : 400}, s, ord(r));
  const empty = all.map((d, i) => R0.has(d) ? -1 : i).filter(i => i >= 0), nx = empty.find(i => all[i] >= R0.liveFrom);
  if (li >= 0) { const xb = li > 0 ? (x(li - 1) + x(li)) / 2 : L;
    el("rect", {x: xb, y: top - 12, width: xEnd - xb, height: y(n) - top + 24, fill: th.live, rx: 4}, s);
    if (li > 0) { el("line", {x1: xb, x2: xb, y1: 4, y2: y(n) + 12, stroke: th.ink, "stroke-dasharray": "3 3"}, s);
      el("text", {x: xb - 8, y: 12, "text-anchor": "end", "font-size": 11, fill: th.mute}, s, R0.repLabel + (R0.gapFrom ? `, ${dS(all[0])} to ${dS(all[li - 1])}` : "")); }
    const tail = nx != null ? "  ·  next score " + dS(next(all[nx])) + (R0.wx ? ", morning" : ", 01:30") : "";
    el("text", {x: xb + 8, y: 12, "font-size": 11, "font-weight": 600, fill: th.ink}, s, (li > 0 ? "Live from " + dS(R0.liveFrom) : "Live") + tail); }
  if (R0.stand) el("text", {x: L, y: 12, "font-size": 11, fill: th.ours, "font-weight": 600}, s, "STAND-IN DATA");
  empty.forEach(i => el("line", {x1: x(i), x2: x(i), y1: top - 4, y2: y(n) + 4, stroke: th.line, "stroke-dasharray": "2 3"}, s));
  all.forEach((d, i) => el("text", {x: x(i), y: H - 6, "text-anchor": "middle", "font-size": 10, fill: R0.has(d) ? th.mute : th.faint, "font-weight": i === nx ? 600 : 400}, s, dS(d)));
  const path = pts => "M" + pts[0][0] + "," + pts[0][1] + pts.slice(1).map((p, i) => { const q = pts[i], m = (q[0] + p[0]) / 2; return `C${m},${q[1]} ${m},${p[1]} ${p[0]},${p[1]}`; }).join("");
  const ifsK = srcs.map(q => q.k).find(isIfs), focus = [ifsK, rival, ours].filter((k, i, A) => k && A.indexOf(k) == i), order = srcs.map(q => q.k).sort((p, q) => focus.indexOf(p) - focus.indexOf(q)), G = {}, ends = [];
  for (const k of order) {
    const pts = all.map((d, i) => { const r = R0.at(d, k); return r ? [x(i), y(r.rank), r] : null; }).filter(Boolean); if (!pts.length) continue;
    const hi = focus.includes(k), w = k == ours ? 2.6 : k == rival ? 2 : hi ? 1.8 : 1.2, g = el("g", {}, s), dd = path(pts);
    if (hi) el("path", {d: dd, fill: "none", stroke: "#fff", "stroke-width": w + 4, "stroke-linecap": "round"}, g);
    const ln = el("path", {d: dd, fill: "none", stroke: col(k), "stroke-width": w, "stroke-linejoin": "round", "stroke-linecap": "round"}, g);
    if (hi) { pts.forEach(p => el("circle", {cx: p[0], cy: p[1], r: k == ours || k == rival ? 4 : 3, fill: col(k), stroke: "#fff", "stroke-width": 1.5}, g));
      const lp = pts[pts.length - 1]; ends.push({k, x: lp[0], y: lp[1], y0: lp[1]}); }
    const hit = el("path", {d: dd, fill: "none", stroke: "#000", "stroke-opacity": 0, "stroke-width": 12, cursor: "pointer"}, g); G[k] = {g, ln};
    hit.addEventListener("pointermove", e => { for (const q in G) G[q].g.setAttribute("opacity", q == k ? 1 : .18); if (!hi) { ln.setAttribute("stroke", th.ink); ln.setAttribute("stroke-width", 2.2); }
      const b = s.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width, near = pts.reduce((p, q) => Math.abs(q[0] - px) < Math.abs(p[0] - px) ? q : p);
      tip(e, `<b>${esc(nm(R0.names, k))}</b><br>${dS(near[2].day)}: ${ord(near[2].rank)} of ${n}<br><span style="opacity:.75">${R0.fmt(near[2].err)}${near[2].stand ? " · stand-in" : ""}</span>`); });
    hit.addEventListener("pointerleave", () => { for (const q in G) G[q].g.setAttribute("opacity", 1); ln.setAttribute("stroke", col(k)); ln.setAttribute("stroke-width", w); untip(); });
  }
  ends.sort((p, q) => p.y - q.y); for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  ends.forEach(e => { if (e.x < xEnd - 8) el("path", {d: `M${e.x + 6},${e.y0}L${xEnd + 2},${e.y}`, stroke: col(e.k), "stroke-width": 1, "stroke-dasharray": "2 2", fill: "none"}, s);
    el("text", {x: xEnd + 6, y: e.y + 4, "font-size": 12, "font-weight": 600, fill: col(e.k), "paint-order": "stroke", stroke: th.live, "stroke-width": 3}, s, short(e.k)); });
}
function rankTable(host, a) {
  const R0 = rankWin(a); if (!R0) { host.innerHTML = ""; return; }
  const days = R0.all.filter(R0.has), N = days.length;
  const rows = R0.srcs.map(q => { const rk = R0.rows.filter(r => r.source == q.k).map(r => r.rank); const er = R0.rows.filter(r => r.source == q.k && r.err != null).map(r => r.err); return {k: q.k, avg: q.avg, err: er.length ? er.reduce((p, v) => p + v, 0) / er.length : null, first: rk.filter(v => v == 1).length, worst: Math.max(...rk)}; });
  const cell = "padding:10px 14px;border-top:1px solid " + th.grid, grid = "display:grid;grid-template-columns:minmax(0,2fr) repeat(4,minmax(0,1fr))";
  host.innerHTML = `<div style="overflow-x:auto;margin-top:16px"><div style="font:13.5px/1.3 ${th.font};color:${th.ink};border:1px solid ${th.line};border-radius:8px;overflow:hidden;min-width:580px">
  <div style="${grid};font-size:12px;font-weight:600;color:${th.mute};background:#faf9f6">
  <div style="padding:10px 14px">Source</div><div style="padding:10px 14px;text-align:right">Average rank</div><div style="padding:10px 14px;text-align:right">Average error<br><span style="font-weight:400">${R0.errCol[0]}</span></div><div style="padding:10px 14px;text-align:right">Days in first place</div><div style="padding:10px 14px;text-align:right">Worst day</div></div>` +
  rows.map(r => { const me = r.k == R0.ours, rv = r.k == R0.rival, c = me ? th.ours : r.k == "energinet" ? th.en : isIfs(r.k) ? th.ifs : th.ink, w = me || rv || r.k == "energinet" || isIfs(r.k) ? 600 : 400;
    return `<div style="${grid};color:${c};font-weight:${w};${me ? "background:" + th.tint : ""}">
    <div style="${cell}">${esc((R0.names[r.k] || r.k).replace(" (my own model)", "").replace(", corrected at each station", ""))}</div>
    <div style="${cell};text-align:right">${r.avg.toFixed(1)}</div><div style="${cell};text-align:right">${r.err == null ? "" : R0.errCol[1](r.err)}</div><div style="${cell};text-align:right">${r.first} of ${N}</div><div style="${cell};text-align:right">${r.worst}</div></div>`; }).join("") + `</div></div>
  <div style="font:12px ${th.font};color:${th.mute};margin-top:8px">Over the ${N} scored day${N == 1 ? "" : "s"} in the chart above, ${dS(days[0])} to ${dS(days[N - 1])}. Updates each night with the chart.${R0.stand ? ` <b style="color:${th.ours}">Stand-in data for days without scores yet; real scores replace it as they arrive.</b>` : ""}</div>`;
}

// ---------- the two tabs ----------
const T = (tip, html, cls) => `<span data-tip="${esc(tip)}"${cls ? ` class="${cls}"` : ""}>${html}</span>`;
const sw = (c, h, extra) => `<span class="sw" style="height:${h}px;background:${c};${extra || ""}"></span>`;
function energyHtml(k) {
  const others = k.btN - 2, grey = k.btN - 3, me = k.me, en = k.en, ifs = k.ifs, f2 = v => v.toFixed(2);
  const errBest = Math.min(me.nmae, ifs.nmae, en.nmae), imbBest = Math.min(me.imb_eur_mwh, ifs.imb_eur_mwh, en.imb_eur_mwh), skBest = Math.max(me.skill_ifs, en.skill_ifs);
  const b = (v, best) => v == best ? " b" : "";
  // pipeline: forecast published, gate, wind blows, scored
  const nowCph = new Date().toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit", hour12: false, ...TZ}), gatePassed = nowCph >= "12:00";
  const st = [!!k.tomIssued, gatePassed, false, false], nxt = st.indexOf(false), cls = i => st[i] ? "done" : i == nxt ? "next" : "";
  const nDone = st.filter(Boolean).length;
  const step = (i, t, h, sub) => `<div class="step"><div class="dot ${cls(i)}"></div><div class="step-t ${cls(i)}">${t}</div><div class="step-h">${h}</div><div class="step-s">${sub}</div></div>`;
  return `
<p class="lede">Every morning before the 12:00 day-ahead auction, I publish an hourly forecast of tomorrow's Danish wind power from my model, ${T("J for joint: one model instead of several averaged. 4 for its four weather models. cat for concatenated: their winds go in side by side, so it learns which model to trust where. DK for DKcast, my weather model's corrected winds at Danish stations.", "J4catDK", "term-ours")}. Once the day has blown, it is scored against what was measured, against ${T("The Danish grid operator's own day-ahead wind forecast, rescaled by its actual-to-forecast ratio over the previous 60 days, because its DK1 offshore forecast covers only part of the fleet.", "Energinet's own forecast")}, and against ${word(others)} forecasts built from public weather models.</p>
<div class="kpis">
  <div class="kpi"><div class="kpi-l">Against Energinet</div>${T(`Skill score: 1 minus my error over Energinet's, on the same hours. 95% confidence interval ${k.skillEnLo}% to ${k.skillEnHi}%.`, k.skillEn + "%", "kpi-n ours")}<div class="kpi-w">less error</div><div class="kpi-x">My average miss was ${k.tMine}% of capacity; Energinet's was ${k.tEn}%.</div></div>
  <div class="kpi"><div class="kpi-l">Day by day</div>${T(`Each day is scored on its 24 hourly errors. On ${k.daysBetter}% of the ${k.testDays} test days, my day's error was smaller than Energinet's.`, k.daysBetter + "%", "kpi-n")}<div class="kpi-w">of days ahead</div><div class="kpi-x">Roughly three days in four, my forecast beat Energinet's.</div></div>
  <div class="kpi"><div class="kpi-l">Average error</div>${T(`The wind industry's standard day-ahead measure: mean absolute error of each area's hourly total (DK1, DK2) as a % of installed capacity. Lower is better. ECMWF IFS: ${k.tIfs}%. Energinet: ${k.tEn}%.`, k.tMine + "%", "kpi-n")}<div class="kpi-w">of installed capacity</div><div class="kpi-x">The wind industry's yardstick. Lower is better.</div></div>
  <div class="kpi"><div class="kpi-l">Imbalance cost</div>${T("What the forecast's errors would cost a wind producer that sells its forecast day-ahead: each hour's error settled at the difference between the day-ahead and imbalance price, per MWh produced. A perfect forecast costs nothing.", "€" + k.imbMine, "kpi-n")}<div class="kpi-w">per MWh produced</div><div class="kpi-x">What the misses would cost a trader. Energinet: €${k.imbEn}.</div></div>
</div>
<p class="note">Trained on 18 Feb to 31 Dec 2025. All four numbers come from one ${T(`One run of a script fixed before it ran, on ${k.testHours} hours none of the models saw in training.`, "frozen test")} on 2026 data the model never saw: ${k.testPeriod}, ${k.testDays} days, ${k.testHours} hours.</p>

<h2>Published before the gate</h2>
<p class="intro">Each forecast is committed to GitHub before the day it covers begins, so nothing can be adjusted after the fact.</p>
<div class="card" style="padding:22px 24px">
  <div class="pipe"><div class="rail"></div><div class="done-rail" style="width:calc(${25 * nDone}% - 8px);${nDone ? "" : "display:none"}"></div>
    ${step(0, k.tomIssued ? "DONE · " + k.tomIssued : "DUE · 10:30", "Forecast published", "for " + k.tomLabel)}
    ${step(1, "12:00", "Auction gate", gatePassed ? "locked, no edits" : "locks the forecast")}
    ${step(2, k.tomShort, "Wind blows", "measured hourly")}
    ${step(3, "01:30 NEXT NIGHT", "Scored", `against ${k.btN - 1} other sources`)}
  </div>
  <div class="today"><span style="font-weight:600;color:var(--ink)">Today, ${k.todayLabel}</span><span>${k.measured} of ${k.total} hours measured</span><span style="color:var(--mute)">${k.todayIssued ? "published " + k.todayIssued + " · " : ""}final score 01:30 tonight</span></div>
</div>

<h2>Who came first each day</h2>
<p class="intro">All ${k.btN} forecasts ranked by that day's error. The days before 31 Oct are ${T("Every source run on the weather forecasts as they stood the day before, exactly as the morning run would have. My model was trained only on data up to 18 Oct.", "replayed")}; from 31 Oct each new day is live and joins the chart at 01:30 the night after.</p>
<div class="card">
  <div class="chart" data-chart="bump"></div>
  <div class="legend"><span>${sw(th.ours, 3)}J4catDK</span><span>${sw(th.en, 2)}Energinet</span><span>${sw(th.ifs, 2)}ECMWF IFS</span><span>${sw("#b9b6ad", 1)}The other ${word(grey)} forecasts</span><span class="hint">Hover a grey line to name it</span></div>
  <div data-chart="ranktable"></div>
</div>

<h2>The last week, hour by hour</h2>
<p class="intro">J4catDK had the smaller error on ${k.wkWins} of the ${k.wkN} complete days shown. The shaded gap is my miss; above each day: who won, then my error vs Energinet's, in % of capacity.</p>
<div class="card">
  <div class="chart" data-chart="timeline"></div>
  <div class="legend"><span>${sw(th.ink, 2)}Measured</span><span>${sw(th.ours, 2)}J4catDK</span><span>${sw(th.en, 2)}Energinet</span><span><span class="sw" style="width:14px;height:10px;background:${th.ours};opacity:.18"></span>My miss</span><span class="hint">Hover for any hour</span></div>
</div>

<h2>Over ${k.btDays} days, the smallest average error of ${k.btN}</h2>
<p class="intro">${T(`Every source run as it would have been live, on ${k.btFrom} to ${k.btTo} 2026: months none of the power models saw in training.`, "Backtest")}, ${k.btFrom} to ${k.btTo} 2026. First on only ${k.bWinMine} days: on most days a different source wins, but none is as steady.</p>
<div class="card" style="padding:20px"><div class="chart" data-chart="league"></div></div>
<div class="score">
  <div class="r h"><div>${k.btDays} days, ${k.btN} sources</div><div class="num" style="color:var(--ours);font-weight:600;background:var(--tint2)">J4catDK</div><div class="num" style="font-weight:600;color:var(--ifs)">ECMWF IFS</div><div class="num" style="font-weight:600;color:var(--en)">Energinet</div></div>
  <div class="r"><div>${T("Mean absolute error of each area's hourly total as a % of installed capacity. Capacity is estimated as the 99.5th percentile of the previous 60 days' hourly output.", "Error, % of capacity", "lab")}<div class="sub">Wind industry · lower is better</div></div>
    <div class="num me${b(me.nmae, errBest)}" data-tip="DK1 (west) ${f2(me.nmae_DK1)}% · DK2 (east) ${f2(me.nmae_DK2)}%">${f2(me.nmae)}</div><div class="num${b(ifs.nmae, errBest)}" data-tip="DK1 ${f2(ifs.nmae_DK1)}% · DK2 ${f2(ifs.nmae_DK2)}%">${f2(ifs.nmae)}</div><div class="num${b(en.nmae, errBest)}" data-tip="DK1 ${f2(en.nmae_DK1)}% · DK2 ${f2(en.nmae_DK2)}%">${f2(en.nmae)}</div></div>
  <div class="r"><div>${T("1 minus my error divided by ECMWF IFS's error, on the same hours. +10% means 10% less error than IFS; negative means worse.", "Skill against ECMWF IFS", "lab")}<div class="sub">Meteorology · higher is better</div></div>
    <div class="num me${b(me.skill_ifs, skBest)}">${signed(me.skill_ifs)}</div><div class="num" style="color:var(--mute)">reference</div><div class="num${b(en.skill_ifs, skBest)}">${signed(en.skill_ifs)}</div></div>
  <div class="r"><div>${T(`Each hour's error settled at the gap between the day-ahead price and Energinet's imbalance price, per MWh produced. Over the full 2026 test, Energinet's was €${k.imbEn} against my €${k.imbMine}.`, "Imbalance cost, €/MWh", "lab")}<div class="sub">Trading · lower is better</div></div>
    <div class="num me${b(me.imb_eur_mwh, imbBest)}">€${f2(me.imb_eur_mwh)}</div><div class="num${b(ifs.imb_eur_mwh, imbBest)}">€${f2(ifs.imb_eur_mwh)}</div><div class="num${b(en.imb_eur_mwh, imbBest)}" style="${en.imb_eur_mwh == imbBest ? "color:var(--en)" : ""}">€${f2(en.imb_eur_mwh)}</div></div>
</div>
<p class="note" style="margin-top:10px">Bold is the best of the three in each row. Hover a number for DK1/DK2.</p>

<h2 style="margin-bottom:12px">Method</h2>
<div class="method">
  <p><b>J4catDK</b> reads four weather models (ECMWF IFS and AIFS, DMI HARMONIE, DWD ICON-EU) side by side at 34 wind-farm sites, plus ${T("My own weather model: it corrects the public models' wind forecasts against what DMI's station anemometers actually measured.", "DKcast")}'s corrected winds at 22 stations. A second stage learns how much offshore output is curtailed when prices are low.</p>
  <p>Every model was trained on forecasts as they stood a day earlier, so the lead time matches a real day-ahead decision. Results are on three scales: error as % of capacity (industry), skill against ECMWF IFS (meteorology) and imbalance cost per MWh (trading).</p>
</div>`;
}
function weatherHtml(k, v) {
  const pills = [["wind", "Wind"], ["temp", "Temperature"], ["sun", "Sunshine"], ["rain", "Rain"]].map(([id, l]) => `<button data-var="${id}" aria-pressed="${id == v}">${l}</button>`).join("");
  const bn = n => n == "Average of all models" ? "the average of all models" : n;
  return `
<p class="lede">The power forecast stands on my own weather forecast, ${T("My own weather model: it corrects the public models' forecasts against what DMI's stations actually measured, and gives a range as well as a single number.", "DKcast", "term-ours")}. On 2026 data it never saw, at Danish weather stations, it beat the best public forecast for every kind of weather.</p>
<div class="kpis">${k.wx.map(w => `
  <div class="kpi"><div class="kpi-l">${w.label}</div>${T(`DKcast ${w.me} against ${w.best} for the best public forecast (${w.bestName}), ${w.unit}.`, w.lead + "%", "kpi-n ours")}<div class="kpi-w">${w.rain ? "better at calling rain or no rain" : "less error"}</div><div class="kpi-x">${w.me} vs ${w.best} ${w.rain ? "Brier" : w.unitShort} for ${esc(bn(w.bestName))}.</div></div>`).join("")}
</div>
<p class="note">Trained on 1 Mar to 31 Dec 2025, then tested once on 1 Jan to 18 Oct 2026, which it never saw: wind at 33 DMI stations (6,983 hours), temperature at 20 (6,984 hours), sunshine at 19 (6,113 daylight hours) and rain at 20 (6,941 hours). Typical miss per hour (${T("Root mean square error of each hourly day-ahead forecast at the stations. For rain, the Brier score of calling rain or no rain.", "RMSE")}); the public models are each corrected at every station, so the comparison is fair to them.</p>

<h2>Who came first each day</h2>
<p class="intro" style="margin-bottom:16px">Every model ranked by its error at the DMI stations that day. The days before 31 Oct are ${T("DKcast refitted on data up to 18 Oct only and run on the public forecasts as they stood the day before, exactly as the morning run would have.", "replayed")}; from 31 Oct each new day is live and joins the next morning.</p>
<div class="card" style="padding:16px 20px 14px">
  <div class="pills" role="group" aria-label="Weather variable">${pills}</div>
  <div class="chart" data-chart="bump" data-src="wx" data-var="${v}"></div>
  <div class="legend"><span>${sw(th.ours, 3)}DKcast</span><span>${sw(th.ink, 2)}Best public model in the window</span><span>${sw(th.ifs, 2)}ECMWF IFS</span><span>${sw("#b9b6ad", 1)}Other public models</span><span class="hint">Hover a grey line to name it</span></div>
  <div data-chart="ranktable" data-src="wx" data-var="${v}"></div>
</div>

<h2>The last week, hour by hour</h2>
<p class="intro" id="wxtl-intro"></p>
<div class="card">
  <div class="pills places" role="group" aria-label="Place">${[["national", "National average"], ["odense", "Årslev (Odense)"], ["aarhus", v == "wind" ? "Århus Lufthavn (Aarhus)" : "Ødum (Aarhus)"]].map(([id, l]) => `<button data-place="${id}" aria-pressed="${id == state.wxPlace}">${l}</button>`).join("")}</div>
  <div class="chart" data-chart="wxtimeline" data-src="wx" data-var="${v}" data-place="${state.wxPlace}"></div>
  <div class="legend"><span id="wxtl-meas">${sw(th.ink, 2)}Measured</span><span>${sw(th.ours, 2)}DKcast</span><span>${sw(RIV, 2)}<span id="wxtl-riv"></span></span><span id="wxtl-miss"><span class="sw" style="width:14px;height:10px;background:${th.ours};opacity:.18"></span>DKcast's miss</span><span class="hint">Hover for any hour</span></div>
</div>

<h2>Against every public model, all of the 2026 test</h2>
<p class="intro">The dashed line is the best public forecast for each kind of weather, set to 100%. Left of it is less error.</p>
<div class="card">
  <div class="chart" data-chart="wxrel"></div>
  <div class="legend"><span><span class="sw" style="width:10px;height:10px;border-radius:50%;background:${th.ours}"></span>DKcast</span><span><span class="sw" style="width:8px;height:8px;border-radius:50%;background:${th.ifs}"></span>ECMWF IFS</span><span><span class="sw" style="width:8px;height:8px;border-radius:50%;background:${th.other}"></span>Other public models</span></div>
</div>`;
}

const CH = {bump: (h, a) => bump(h, a), ranktable: (h, a) => rankTable(h, a), timeline, wxtimeline: wxTimeline, league, wxrel: wxRel};
function charts(root) { root.querySelectorAll("[data-chart]").forEach(h => { try { CH[h.dataset.chart](h, h.dataset); } catch (e) { console.warn("chart", h.dataset.chart, e); } }); }
const state = {k: null, mode: "weather", wxVar: "wind", wxPlace: "national"};
try { const m = new URLSearchParams(location.search).get("tab") || sessionStorage.getItem("wl-tab"); if (m == "energy" || m == "weather") state.mode = m; } catch (e) {}
function render() {
  const k = state.k; if (!k) return;
  document.getElementById("updated").textContent = "Updated " + k.updated;
  const pe = document.getElementById("pane-energy"), pw = document.getElementById("pane-weather");
  pe.innerHTML = energyHtml(k); pw.innerHTML = weatherHtml(k, state.wxVar);
  charts(pe); charts(pw); setMode(state.mode);
}
function setMode(m) {
  state.mode = m; try { sessionStorage.setItem("wl-tab", m); } catch (e) {}
  document.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode == m)));
  document.getElementById("pane-energy").hidden = m != "energy"; document.getElementById("pane-weather").hidden = m != "weather";
}
document.addEventListener("click", e => {
  const t = e.target.closest(".tabs button"); if (t) { setMode(t.dataset.mode); untip(); return; }
  const q = e.target.closest(".places button"); if (q) { state.wxPlace = q.dataset.place;
    document.querySelectorAll("#pane-weather .places button").forEach(b => b.setAttribute("aria-pressed", String(b == q)));
    document.querySelectorAll("#pane-weather [data-chart=wxtimeline]").forEach(h => { h.dataset.place = state.wxPlace; CH.wxtimeline(h, h.dataset); }); return; }
  const p = e.target.closest(".pills:not(.places) button"); if (p) { state.wxVar = p.dataset.var; const pw = document.getElementById("pane-weather");
    pw.querySelectorAll(".pills:not(.places) button").forEach(b => b.setAttribute("aria-pressed", String(b == p)));
    pw.querySelectorAll("[data-src=wx]").forEach(h => { h.dataset.var = state.wxVar; CH[h.dataset.chart](h, h.dataset); }); }
});
// tooltips for HTML terms and numbers
const tipHost = e => e.target.closest && e.target.closest("[data-tip]");
document.addEventListener("pointerover", e => { const n = tipHost(e); if (n && !(n instanceof SVGElement)) tip(e, esc(n.dataset.tip)); });
document.addEventListener("pointermove", e => { const n = tipHost(e); if (n && !(n instanceof SVGElement)) tip(e, esc(n.dataset.tip)); });
document.addEventListener("pointerout", e => { const n = tipHost(e); if (n && !(n instanceof SVGElement)) untip(); });

const refresh = () => load().then(k => { state.k = k; render(); }).catch(e => console.warn(e));
refresh();
setInterval(refresh, 10 * 60 * 1000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
