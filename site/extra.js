// Top of the page, the headline table and the league chart, adopted from projects-b4's picker (Bo chose top B,
// numbers A, lower A on 30 Oct 2026). Uses el(), svg(), tip(), tipText(), GLOSS and OURS from the page script.
const ALT = {S: null, D: null, TD: null};
const ETYM = "J for joint: one model instead of several averaged. 4 for its four weather models. cat for concatenated: " +
  "their winds go in side by side. DK for DKcast, my weather model's corrected winds at Danish stations.";

// time helpers, all in Copenhagen time
const TZ = {timeZone: "Europe/Copenhagen"};
const fHM = t => new Date(t).toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit", ...TZ});
const isoCph = t => new Date(t).toLocaleDateString("en-CA", TZ);
const fDay = (d, long) => new Date(d + "T12:00Z").toLocaleDateString("en-GB",
  long ? {weekday: "long", day: "numeric", month: "long"} : {weekday: "short", day: "numeric", month: "short"});
const fAt = t => `${fDay(isoCph(t))} at ${fHM(t)}`;
const nextDay = d => isoCph(new Date(d + "T12:00Z").getTime() + 864e5);
const hoursNow = () => { const [h, m] = new Date().toLocaleTimeString("en-GB", {hour: "2-digit", minute: "2-digit", hourCycle: "h23", ...TZ}).split(":"); return +h + m / 60; };
const esc = s => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const tipAttr = src => { const t = tipText(src); return t ? ` class="tip" tabindex="0" data-tip="${esc(t)}"` : ""; };

// what the page knows about today and tomorrow
function dayInfo() {
  const h = ALT.D.health || {}, TD = ALT.TD, F = h.forecasts || {}, TR = h.tries || {};
  const today = isoCph(Date.now()), tomorrow = isoCph(Date.now() + 864e5);
  const one = day => {
    const f = F[day], waits = (TR[day] || []).filter(t => t.result === "waiting").map(t => t.at_utc);
    const missing = !!(f && f.missing && f.missing.j4catdk), scored = !!(h.last_scored_day && h.last_scored_day >= day);
    const state = f ? (missing ? "missing" : "issued") : (day === tomorrow && hoursNow() < 12 ? "due" : "none");
    const live = TD && TD.day === day;
    return {day, f, waits, missing, scored, state, measured: scored ? 24 : live ? TD.hours_measured : 0, total: live ? TD.hours_total : 24};
  };
  return {today: one(today), tomorrow: one(tomorrow)};
}

function nowSentence(I) {
  const t = I.today, m = I.tomorrow;
  const a = t.state === "issued" ? `Today's forecast went out on ${fAt(t.f.issued_utc)}, ` +
      (t.scored ? "and the day is scored." : t.measured ? `and ${t.measured} of ${t.total} hours have been measured so far; the final score comes at 01:30 tonight.`
        : "and no hour has been measured yet; the final score comes at 01:30 tonight.")
    : t.state === "missing" ? "Today has no forecast from my model, because the DKcast feed was not ready by the last try; the day counts as last place."
    : "There is no forecast for today on the page.";
  const b = m.state === "issued" ? `Tomorrow's went out at ${fHM(m.f.issued_utc)}, before the auction closed.`
    : m.state === "due" ? "Tomorrow's goes out between 10:30 and 11:30, before the auction closes at 12:00."
    : m.state === "missing" ? "Tomorrow has no forecast from my model, because the DKcast feed was not ready by 11:30."
    : "Tomorrow's forecast is not on the page yet.";
  return a + " " + b;
}

const modelPara = () => `<p class="mute">My model is <b style="color:var(--ours)" class="tip" tabindex="0" data-tip="${esc(ETYM)}">J4catDK</b>.
  It reads four weather models (ECMWF IFS and AIFS, DMI HARMONIE, DWD ICON-EU) side by side at 34 wind-farm sites, plus my
  own corrected winds at 22 Danish weather stations, so it learns which model to trust where. A second stage learns how much
  offshore output is switched off when prices are low. Hover over or tap any name for a one-line description.</p>`;

const test = () => ALT.S && ALT.S.test_2026;
const testSentence = (lead) => { const T = test(); return T ? `${lead} my model's error was ${T.nmae_pct.j4catdk.toFixed(2)}% of installed capacity, ` +
  `against ${T.nmae_pct.energinet.toFixed(2)}% for Energinet's own forecast.` : ""; };

// ---------- top B: status cards ----------
function hourStrip(meas, total) {
  const W = 300, g = 2, cw = (W - g * (total - 1)) / total;
  let s = `<svg viewBox="0 0 ${W} 40" width="100%" role="img" aria-label="${meas} of ${total} hours measured">`;
  for (let i = 0; i < total; i++) s += `<rect x="${(i * (cw + g)).toFixed(1)}" y="0" width="${cw.toFixed(1)}" height="18" rx="2" ` +
    `fill="${i < meas ? "#1d1d1b" : "#ebe7de"}"><title>${String(i).padStart(2, "0")}:00, ${i < meas ? "measured" : "not measured yet"}</title></rect>`;
  for (const h of [0, 6, 12, 18]) s += `<text x="${(h * (cw + g)).toFixed(1)}" y="34" font-size="11" fill="#6b6a65">${String(h).padStart(2, "0")}:00</text>`;
  return s + `</svg>`;
}
function auctionClock(m) {
  // 10:00 to 12:20 today: the three tries, the gate at 12:00, and now
  const W = 300, x = h => 8 + (h - 10) / 2.33 * (W - 16), y = 14, now = hoursNow();
  const issuedToday = m.f && isoCph(m.f.issued_utc) === isoCph(Date.now());
  const ih = issuedToday ? (([a, b]) => +a + b / 60)(fHM(m.f.issued_utc).split(":")) : null;
  const waited = new Set(m.waits.map(t => fHM(t)));
  let s = `<svg viewBox="0 0 ${W} 40" width="100%" role="img" aria-label="forecast tries at 10:30, 11:00 and 11:30; auction closes at 12:00">`;
  s += `<line x1="${x(10)}" x2="${x(12.33)}" y1="${y}" y2="${y}" stroke="#e4e1d9" stroke-width="2"/>`;
  [[10.5, "10:30"], [11, "11:00"], [11.5, "11:30"]].forEach(([h, lab]) => {
    const used = ih != null && ih >= h - .02 && ih < h + .5, wt = waited.has(lab);
    s += `<circle cx="${x(h)}" cy="${y}" r="5.5" fill="${used ? "#c2410c" : wt ? "#9a988f" : "#fff"}" stroke="${used ? "#c2410c" : "#9a988f"}" stroke-width="1.6">` +
      `<title>${lab}: ${used ? "forecast issued" : wt ? "tried, the DKcast feed was not ready" : "forecast try"}</title></circle>`;
    s += `<text x="${x(h)}" y="36" font-size="11" fill="#6b6a65" text-anchor="middle">${lab}</text>`;
  });
  s += `<line x1="${x(12)}" x2="${x(12)}" y1="2" y2="24" stroke="#1d1d1b" stroke-width="2"/>` +
    `<text x="${x(12)}" y="36" font-size="11" fill="#1d1d1b" text-anchor="middle" font-weight="700">12:00</text>`;
  if (m.state === "due" && now >= 10 && now <= 12.33) s += `<path d="M${x(now) - 5},2 L${x(now) + 5},2 L${x(now)},8 Z" fill="#c2410c"><title>now</title></path>`;
  return s + `</svg>`;
}
function cardToday(t) {
  const chip = t.state === "issued" ? (t.scored ? `<span class="chip ok">Scored</span>` : `<span class="chip ok">Published</span>`)
    : t.state === "missing" ? `<span class="chip bad">No forecast</span>` : `<span class="chip bad">Not on the page</span>`;
  const line = t.scored ? "All hours measured and scored." : t.measured ? `${t.measured} of ${t.total} hours measured. Final score at 01:30 tonight.`
    : "No hour measured yet. Final score at 01:30 tonight.";
  const sub = t.state === "issued" ? `Published ${fAt(t.f.issued_utc)}, before the day began.`
    : t.state === "missing" ? "The DKcast feed was not ready by the last try, so the day counts as last place." : "";
  return `<div class="daycard"><h3><span>Today, ${fDay(t.day)}</span>${chip}</h3>${hourStrip(t.measured, t.total)}` +
    `<p class="big">${line}</p><p class="small">${sub}</p></div>`;
}
function cardTomorrow(m) {
  const chip = m.state === "issued" ? `<span class="chip ok">Published</span>` : m.state === "due" ? `<span class="chip wait">Due by 12:00</span>`
    : m.state === "missing" ? `<span class="chip bad">No forecast</span>` : `<span class="chip bad">Not on the page</span>`;
  const line = m.state === "issued" ? `Published at ${fHM(m.f.issued_utc)}, before the auction closed.`
    : m.state === "due" ? (m.waits.length ? `Waiting: the DKcast feed was not ready at ${m.waits.map(fHM).join(" and ")}. Next try on the half hour.`
      : "Not published yet. Tries at 10:30, 11:00 and 11:30.")
    : m.state === "missing" ? "The DKcast feed was not ready by 11:30, so the day counts as last place." : "No forecast on the page yet.";
  return `<div class="daycard"><h3><span>Tomorrow, ${fDay(m.day)}</span>${chip}</h3>${auctionClock(m)}` +
    `<p class="big">${line}</p><p class="small">Scored at 01:30 on ${fDay(nextDay(m.day))}.</p></div>`;
}
function topB(I) {
  document.getElementById("topB").innerHTML = `
  <p class="lede">Every morning before the 12:00 day-ahead auction, I forecast each hour of tomorrow's wind power in Denmark
  and <a href="https://github.com/bolgacg/dk-wind-live/tree/main/forecasts">publish it</a> before the day begins.
  ${testSentence("In a test on 2026 data, frozen before it ran,")}</p>
  <div class="daycards">${cardToday(I.today)}${cardTomorrow(I.tomorrow)}</div>
  ${modelPara()}`;
}

// ---------- numbers A: one table ----------
function numA(d) {
  const host = document.getElementById("numA"), o = d.overall, by = s => o.find(r => r.source === s);
  const cols = [[OURS, "My model (J4catDK)", "c-ours"], ["ifs", "ECMWF IFS", ""], ["energinet", "Energinet's forecast", "c-en"]].map(([s, nm, c]) => ({r: by(s), s, nm, c}));
  if (!cols[0].r) { host.innerHTML = "<p class='mute sans'>No scored days yet.</p>"; return; }
  const sign = v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%";
  const rows = [
    {k: "Error", u: "% of installed capacity, the wind industry's measure. Lower is better.", v: r => r.nmae, f: v => v.toFixed(2) + "%", low: true,
      sub: r => `DK1 ${r.nmae_DK1.toFixed(2)}<br>DK2 ${r.nmae_DK2.toFixed(2)}`, g: "nmae"},
    {k: "Skill against ECMWF IFS", u: "how much less error than IFS on the same hours, the meteorologist's measure. Higher is better.", v: r => r.skill_ifs,
      f: (v, r) => r.source === "ifs" ? "0 (reference)" : sign(v), low: false, g: "skill"},
    {k: "Imbalance cost", u: "€ per MWh produced, the trader's measure. Lower is better.", v: r => r.imb_eur_mwh, f: v => "€" + v.toFixed(2), low: true, g: "imbalance"},
    {k: "Days with the smallest error", u: `out of ${d.days}, among all ${o.length} sources. Higher is better.`, v: r => r.wins, f: v => String(v), low: false}];
  const head = `<tr><th>${d.days} days, ${o.length} sources</th>${cols.map(c => `<th class="${c.c}"><span${tipAttr(c.s)}>${c.nm}</span></th>`).join("")}</tr>`;
  const body = rows.map(R => {
    const vals = cols.map(c => c.r ? R.v(c.r) : null), ok = vals.filter(v => v != null), best = R.low ? Math.min(...ok) : Math.max(...ok);
    const lab = `<span class="k"${R.g && GLOSS[R.g] ? ` data-tip="${esc(GLOSS[R.g].text)}" tabindex="0"` : ""}>${R.k}</span><span class="u">${R.u}</span>`;
    return `<tr><td>${lab}</td>${cols.map((c, i) => `<td data-l="${c.nm}" class="${c.c}${vals[i] === best ? " best" : ""}">${vals[i] == null ? "n/a" : R.f(vals[i], c.r)}` +
      `${R.sub && c.r ? `<span class="sub">${R.sub(c.r)}</span>` : ""}</td>`).join("")}</tr>`;
  }).join("");
  const me = cols[0].r, en = cols[2].r, T = test();
  const imbNote = en && me.imb_eur_mwh > en.imb_eur_mwh && T ? ` Over these days Energinet's imbalance cost is a little lower than mine;
    in the 2026 test it was higher, €${T.imbalance_eur_mwh.energinet.toFixed(2)} against my €${T.imbalance_eur_mwh.j4catdk.toFixed(2)}.` : "";
  host.innerHTML = `<div class="tblwrap"><table class="scales"><thead>${head}</thead><tbody>${body}</tbody></table></div>
    <p class="note">Bold marks the best of these three in each row. Accuracy, 100% minus total error over total output, is
    ${me.acc.toFixed(1)}% for my model${en ? ` and ${en.acc.toFixed(1)}% for Energinet` : ""}.${imbNote}</p>`;
}

// ---------- lower A: league chart ----------
function lowA(d) {
  const host = document.getElementById("lowAfig"), cap = document.getElementById("lowAcap"), o = d.overall;
  const W = 760, L = 218, X1 = 496, C0 = 580, R = 16, rowH = 30, top = 46, H = top + o.length * rowH + 14;
  const lo = Math.max(0, Math.floor(Math.min(...o.map(r => r.nmae)) - .5)), hi = Math.ceil(Math.max(...o.map(r => r.nmae)) + .5);
  const x = v => L + (v - lo) / (hi - lo) * (X1 - L), mw = Math.max(1, ...o.map(r => r.wins)), xw = v => C0 + v / mw * (W - R - C0 - 62);
  const s = svg(host, W, H);
  el("text", {x: (L + X1) / 2, y: 14, "text-anchor": "middle", "font-size": 12.5, "font-weight": 600, fill: "#1d1d1b"}, s, "Average error, % of installed capacity");
  el("text", {x: (L + X1) / 2, y: 30, "text-anchor": "middle", "font-size": 11.5, fill: "#6b6a65"}, s, "lower is better");
  el("text", {x: C0, y: 14, "font-size": 12.5, "font-weight": 600, fill: "#1d1d1b"}, s, "Days in first place");
  el("text", {x: C0, y: 30, "font-size": 11.5, fill: "#6b6a65"}, s, `smallest error of all, out of ${d.days}`);
  for (let v = lo; v <= hi; v++) {
    el("line", {x1: x(v), x2: x(v), y1: top - 8, y2: H - 14, stroke: "#eee"}, s);
    el("text", {x: x(v), y: H - 2, "text-anchor": "middle", "font-size": 11, fill: "#6b6a65"}, s, v + "%");
  }
  o.forEach((r, i) => {
    const y = top + i * rowH, b = r.source === OURS, c = b ? "#c2410c" : r.source === "energinet" ? "#1e40af" : "#9a988f";
    if (b) el("rect", {x: 0, y: y - 14, width: W, height: 28, fill: "#fff7ed", rx: 4}, s);
    tip(el("text", {x: L - 12, y: y + 5, "text-anchor": "end", "font-size": 14, "font-weight": b ? 700 : 400, fill: b ? c : "#1d1d1b"}, s, r.name), r.source);
    el("line", {x1: L, x2: x(r.nmae), y1: y, y2: y, stroke: "#e4e1d9"}, s);
    const dot = el("circle", {cx: x(r.nmae), cy: y, r: b ? 7.5 : 5.5, fill: c}, s);
    el("title", {}, dot, `${r.name}: ${r.nmae.toFixed(2)}% of installed capacity`);
    el("text", {x: x(r.nmae) + 12, y: y + 4, "font-size": 12.5, fill: b ? c : "#6b6a65", "font-weight": b ? 700 : 400}, s, r.nmae.toFixed(2) + "%");
    const wb = el("rect", {x: C0, y: y - 7, width: Math.max(1.5, xw(r.wins) - C0), height: 14, rx: 2, fill: b ? c : r.source === "energinet" ? "#1e40af" : "#c9c6bd"}, s);
    el("title", {}, wb, `${r.name}: smallest error on ${r.wins} of ${d.days} days`);
    el("text", {x: xw(r.wins) + 7, y: y + 4, "font-size": 12.5, fill: b ? c : "#6b6a65", "font-weight": b ? 700 : 400}, s, String(r.wins));
  });
  const me = o.find(r => r.source === OURS), most = me && me.wins >= Math.max(...o.map(r => r.wins));
  cap.textContent = me ? `Each row is one forecast source, sorted by its average error over the period. The dot is that average as a % of installed ` +
    `capacity; the bar on the right counts the days the source had the smallest error of all ${o.length}. ` +
    `${o[0].source === OURS ? "My model has the smallest average error" : `My model ranks ${o.indexOf(me) + 1} of ${o.length} on average error`}, ` +
    `but it is first on only ${me.wins} of ${d.days} days${most ? ", and no other source is first as often" : ""}: on most days a different source wins.` : "";
}

