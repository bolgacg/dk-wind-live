// Round 2 of the live page, adopted from projects-b4's picker (Bo's picks, 30 Oct 2026): meteorology tab B, timeline A,
// links A, and the fixed window around go-live for who came first each day. Uses el, svg, tipText from the page script.
const LV = {TL: null, D: null, FW: null, RK: null, DK: null, wxVar: "wind"};
const PUB = "https://bolgacg.github.io/";
const lvj = u => fetch(u, {cache: "no-store"}).then(r => r.json()).catch(() => null);
const lvBox = document.getElementById("tipbox");
function lvTip(e, html) { lvBox.innerHTML = html; lvBox.style.display = "block"; lvBox.style.left = Math.min(e.clientX + 12, innerWidth - lvBox.offsetWidth - 8) + "px"; lvBox.style.top = (e.clientY + 16) + "px"; }
function lvOff() { lvBox.style.display = "none"; }
const lvDay = d => new Date(d + "T12:00Z").toLocaleDateString("en-GB", {day: "numeric", month: "short"});

// ---------- rank chart with hover: the line under the pointer is named and highlighted ----------
function lvRank(host, rows, names, ours, fmt, kindOf, focus, win) {
  const days = win ? win.days : [...new Set(rows.map(r => r.day))].sort(), srcs = [...new Set(rows.map(r => r.source))], n = Math.max(...rows.map(r => r.rank));
  const W = 760, L = 30, R = 150, top = 14, step = 22, H = top + (n - 1) * step + 44, x = i => L + 10 + i * (W - L - R - 10) / Math.max(1, days.length - 1), y = r => top + (r - 1) * step;
  const avg = k => { const v = rows.filter(r => r.source == k).map(r => r.rank); return v.reduce((a, b) => a + b, 0) / v.length; };
  focus = focus || [ours, "energinet"]; const PAL = ["#c2410c", "#1e40af", "#0f766e"], FC = {}; focus.forEach((k, j) => FC[k] = PAL[j]);
  const s = svg(host, W, H + 26), col = k => FC[k] || "#d9d5cc";
  el("rect", {x: L, y: y(1) - step / 2, width: W - L - R + 20, height: step, fill: "#fbf3ea"}, s);
  if (win) { const i0 = days.indexOf(win.liveFrom), xb = (x(i0 - 1) + x(i0)) / 2;
    el("rect", {x: xb, y: top - 12, width: x(days.length - 1) - xb + 10, height: (n - 1) * step + 24, fill: "#f3f7ff", opacity: .8}, s);
    el("line", {x1: xb, x2: xb, y1: top - 12, y2: y(n) + 12, stroke: "#1d1d1b", "stroke-dasharray": "4 3"}, s);
    el("text", {x: xb + 6, y: y(n) + 10, "font-size": 11.5, "font-weight": 700, fill: "#1d1d1b"}, s, `live from ${lvDay(win.liveFrom)}`);
    el("text", {x: xb - 6, y: y(n) + 10, "font-size": 11.5, fill: "#6b6a65", "text-anchor": "end"}, s, "replayed before");
    days.forEach((d, i) => { if (!rows.some(r => r.day == d)) el("line", {x1: x(i), x2: x(i), y1: top - 6, y2: y(n) + 2, stroke: "#c9c6bd", "stroke-dasharray": "2 4"}, s); }); }
  for (let r = 1; r <= n; r++) el("text", {x: L - 6, y: y(r) + 4, "text-anchor": "end", "font-size": 11, fill: "#6b6a65"}, s, r == 1 ? "1st" : r == 2 ? "2nd" : r == 3 ? "3rd" : r + "th");
  days.forEach((d, i) => { if (win || i % Math.ceil(days.length / 10) == 0 || i == days.length - 1) el("text", {x: x(i), y: H - 22, "text-anchor": "middle", "font-size": 11, fill: kindOf && kindOf(d) == "replayed" ? "#9a978f" : "#1d1d1b"}, s, lvDay(d)); });
  const G = {}, order = srcs.sort((a, b) => focus.includes(a) - focus.includes(b) || (a == ours) - (b == ours));
  const label = el("text", {x: W - R + 10, y: 0, "font-size": 13, "font-weight": 700}, s, "");
  for (const k of order) {
    const pts = days.map((d, i) => { const r = rows.find(q => q.day == d && q.source == k); return r ? [x(i), y(r.rank), r] : null; }).filter(Boolean); if (!pts.length) continue;
    const hi = focus.includes(k), g = el("g", {class: "rk"}, s), d = "M" + pts.map(p => p[0] + "," + p[1]).join("L");
    el("path", {d, fill: "none", stroke: col(k), "stroke-width": k == ours ? 3.2 : hi ? 2 : 1.2, class: "ln"}, g);
    if (hi) pts.forEach(p => el("circle", {cx: p[0], cy: p[1], r: k == ours ? 4.5 : 3.5, fill: col(k), stroke: "#fff", "stroke-width": 1.2}, g));
    if (hi) { const p = pts[pts.length - 1]; el("text", {x: p[0] + 10, y: p[1] + 4 + (k == ours ? 0 : 12 * focus.indexOf(k)) * (Math.abs(p[1] - y(1)) < 1 && k != ours ? 1 : 0), "font-size": 12, "font-weight": 700, fill: col(k)}, g, (names[k] || k).replace(" (my own model)", "").replace(", corrected at each station", "").replace(" (bias-corrected)", "")); }
    const hit = el("path", {d, fill: "none", stroke: "transparent", "stroke-width": 12, style: "cursor:pointer"}, g);
    G[k] = g;
    const on = e => { for (const q in G) G[q].setAttribute("opacity", q == k ? 1 : .15); g.querySelector(".ln").setAttribute("stroke-width", 4.5);
      if (g.querySelector(".ln").getAttribute("stroke") == "#b9b6ad") g.querySelector(".ln").setAttribute("stroke", "#1d1d1b");
      const bb = host.getBoundingClientRect(), px = (e.clientX - bb.left) * W / bb.width, near = pts.reduce((a, p) => Math.abs(p[0] - px) < Math.abs(a[0] - px) ? p : a);
      lvTip(e, `<b>${names[k] || k}</b><br>${lvDay(near[2].day)}: rank ${near[2].rank} of ${n}, ${fmt(near[2])}`);
      label.setAttribute("y", pts[pts.length - 1][1] + 4); label.setAttribute("fill", col(k) == "#b9b6ad" ? "#1d1d1b" : col(k)); if (!hi) label.textContent = (names[k] || k).replace(", corrected at each station", ""); };
    const off = () => { for (const q in G) G[q].setAttribute("opacity", 1); g.querySelector(".ln").setAttribute("stroke-width", hi ? 3 : 1.5); g.querySelector(".ln").setAttribute("stroke", col(k)); label.textContent = ""; lvOff(); };
    hit.addEventListener("pointermove", on); hit.addEventListener("pointerleave", off);
  }
  focus.forEach((k, j) => { el("line", {x1: L + j * 190, x2: L + j * 190 + 20, y1: H + 8, y2: H + 8, stroke: col(k), "stroke-width": 3}, s);
    el("text", {x: L + j * 190 + 26, y: H + 12, "font-size": 12, fill: "#1d1d1b"}, s, (names[k] || k).replace(", corrected at each station", "")); });
  el("line", {x1: L + focus.length * 190, x2: L + focus.length * 190 + 20, y1: H + 8, y2: H + 8, stroke: "#d9d5cc", "stroke-width": 1.5}, s);
  el("text", {x: L + focus.length * 190 + 26, y: H + 12, "font-size": 12, fill: "#6b6a65"}, s, "every other forecast");
  el("text", {x: L, y: H - 4, "font-size": 11.5, fill: "#6b6a65"}, s, "Hover or tap any line to name it and bring it forward.");
}

// ---------- meteorology tab ----------
const WXV = [["wind", "Wind"], ["temp", "Temperature"], ["sun", "Sunshine"], ["rain", "Rain"]];
const wxF = (v, u) => u == "Brier" ? v.toFixed(3) : v.toFixed(u == "min/h" ? 1 : 2), wxU = u => u == "Brier" ? "Brier score" : u == "min/h" ? "minutes of sun per hour" : u;
function wxSc(k) { const d = LV.FW[k], me = d.rows.find(r => r.name == "DKcast"), pub = d.rows.filter(r => r.name != "DKcast").sort((a, b) => a.val - b.val); return {u: d.unit, me: me.val, best: pub[0], pub}; }
const wxLead = () => { const s = WXV.map(([k]) => Math.round(100 * (1 - wxSc(k).me / wxSc(k).best.val)));
  const e = s.slice(0, 3);  // rain is scored as rain or no rain (Brier score), not as an error size
  return `My power forecast stands on my own weather forecast, DKcast. On 2026 data it never saw, at Danish weather stations, DKcast had ${Math.min(...e)} to ${Math.max(...e)}% less error than the best public forecast for wind, temperature and sunshine, and was ${s[3]}% better at calling rain or no rain.`; };
function wxTable() { return `<div style="overflow-x:auto"><table class="sans" style="width:100%;border-collapse:collapse;font-size:.92rem;background:var(--card);border:1px solid var(--line);border-radius:10px">
  <tr style="color:var(--mute);font-size:.8rem"><th style="text-align:left;font-weight:500;padding:8px 10px">Typical miss per hour</th><th style="text-align:right;font-weight:600;padding:8px 10px;color:var(--ours)">DKcast</th><th style="text-align:right;font-weight:500;padding:8px 10px">Best public forecast</th><th style="text-align:right;font-weight:500;padding:8px 10px">DKcast's lead</th></tr>` +
  WXV.map(([k, nm]) => { const s = wxSc(k); return `<tr style="border-top:1px solid var(--line)"><td style="padding:8px 10px">${nm}<div style="font-size:.75rem;color:var(--mute)">${wxU(s.u)}</div></td>
    <td style="text-align:right;padding:8px 10px;font-weight:700;color:var(--ours)">${wxF(s.me, s.u)}</td><td style="text-align:right;padding:8px 10px">${wxF(s.best.val, s.u)}<div style="font-size:.75rem;color:var(--mute)">${s.best.name}</div></td>
    <td style="text-align:right;padding:8px 10px;font-weight:700">${Math.round(100 * (1 - s.me / s.best.val))}% less</td></tr>`; }).join("") + `</table></div>`; }
function wxRankBlock(id) {
  return `<h2 style="margin-top:28px">Who came first each day</h2><div class="tabs wxtabs" data-id="${id}" role="group" aria-label="Weather component">${WXV.map(([k, nm]) => `<button data-v="${k}" aria-pressed="${k == LV.wxVar}">${nm}</button>`).join("")}</div>
    <figure><div id="${id}"></div><figcaption id="${id}cap"></figcaption></figure>`; }
function wxRankDraw(id) {
  const host = document.getElementById(id), cap = document.getElementById(id + "cap"); if (!host) return;
  document.querySelectorAll(`.wxtabs[data-id="${id}"] button`).forEach(b => { b.setAttribute("aria-pressed", b.dataset.v == LV.wxVar); b.onclick = () => { LV.wxVar = b.dataset.v; wxRankDraw(id); }; });
  const RKv = LV.wxVar == "wind" ? LV.RK : LV.RM && LV.RM[LV.wxVar]; if (!RKv) { host.innerHTML = `<p class="mute sans" style="padding:30px 10px;text-align:center">Scores not available.</p>`; cap.textContent = ""; return; }
  const FM = {wind: r => `typical miss ${r.mae.toFixed(2)} m/s`, temp: r => `typical miss ${r.mae.toFixed(2)} °C`, sun: r => `typical miss ${r.mae.toFixed(1)} minutes of sun`, rain: r => `Brier score ${r.mae.toFixed(3)}`};
  const best2 = [...new Set(RKv.ranks.map(r => r.source))].filter(k => k != "dkcast").map(k => [k, RKv.ranks.filter(r => r.source == k).reduce((a, r) => a + r.rank, 0)]).sort((a, b) => a[1] - b[1]).slice(0, 2).map(q => q[0]);
  lvRank(host, RKv.ranks, RKv.names, "dkcast", FM[LV.wxVar], null, ["dkcast", ...best2]);
  const d = [...new Set(RKv.ranks.map(r => r.day))], f = RKv.ranks.filter(r => r.source == "dkcast" && r.rank == 1).length;
  const WHAT = {wind: "10 m wind speed (average miss)", temp: "temperature (average miss)", sun: "sunshine minutes (average miss)", rain: "rain or no rain (Brier score)"};
  cap.textContent = `Daily rank of each forecast on ${WHAT[LV.wxVar]} at the DMI stations, ${lvDay(d[0])} to ${lvDay(d[d.length - 1])} 2026, the last four weeks of the test. ` +
    `DKcast had the smallest error on ${f} of ${d.length} days. ${LV.wxVar == "wind" ? "The public models are as issued the day before at the nearest wind-farm forecast point" : "The public models are as issued the day before at each station"}, each with a straight-line correction per station fitted on 2025, so the comparison is fair to them.`;
}
function wxRel(id) {
  const S = svg(document.getElementById(id), 760, 270), L = 150, R = 670, lo = .8, hi = 1.45, x = q => L + (Math.min(hi, Math.max(lo, q)) - lo) / (hi - lo) * (R - L);
  for (let q = .8; q <= 1.401; q += .1) { el("line", {x1: x(q), x2: x(q), y1: 10, y2: 236, stroke: "#eee"}, S); el("text", {x: x(q), y: 254, "font-size": 11, fill: "#6b6a65", "text-anchor": "middle"}, S, Math.round(q * 100) + "%"); }
  el("line", {x1: x(1), x2: x(1), y1: 10, y2: 236, stroke: "#1d1d1b", "stroke-dasharray": "4 3"}, S);
  WXV.forEach(([k, nm], i) => { const s = wxSc(k), y = 36 + i * 56;
    el("text", {x: L - 12, y: y + 4, "font-size": 14, "font-weight": 600, "text-anchor": "end", fill: "#1d1d1b"}, S, nm);
    s.pub.forEach(r => { const c = el("circle", {cx: x(r.val / s.best.val), cy: y, r: 5.5, fill: r.name == "ECMWF IFS" ? "#1e40af" : "#b9b6ad", stroke: "#fff"}, S);
      c.addEventListener("pointermove", e => lvTip(e, `${r.name}: ${wxF(r.val, s.u)} ${wxU(s.u)}`)); c.addEventListener("pointerleave", lvOff); });
    const c = el("circle", {cx: x(s.me / s.best.val), cy: y, r: 8, fill: "#c2410c", stroke: "#fff", "stroke-width": 1.5}, S);
    c.addEventListener("pointermove", e => lvTip(e, `DKcast: ${wxF(s.me, s.u)} ${wxU(s.u)}<br>best public, ${s.best.name}: ${wxF(s.best.val, s.u)}`)); c.addEventListener("pointerleave", lvOff);
    el("text", {x: R + 10, y: y + 5, "font-size": 13, "font-weight": 700, fill: "#c2410c"}, S, Math.round(100 * (1 - s.me / s.best.val)) + (k == "rain" ? "% better" : "% less")); });
}
function wxCities() {
  if (!LV.DK) return ""; const C = [["06188", "Copenhagen area"], ["06072", "Aarhus area"], ["06126", "Odense area"], ["06031", "Aalborg area"]], D1 = LV.DK.days[1] || LV.DK.days[0];
  return `<h2 style="margin-top:28px">DKcast for tomorrow</h2><p class="mute sans" style="font-size:.9rem;margin:0 0 6px">${new Date(D1.day + "T12:00Z").toLocaleDateString("en-GB", {weekday: "long", day: "numeric", month: "long"})}, from the same model, updated twice a day.</p>
    <table class="sans" style="width:100%;border-collapse:collapse;font-size:.92rem;background:var(--card);border:1px solid var(--line)"><tr style="color:var(--mute);font-size:.8rem;text-align:right"><th style="text-align:left;font-weight:500;padding:6px 10px">Near</th><th style="font-weight:500;padding:6px 10px">High, 8 in 10</th><th style="font-weight:500;padding:6px 10px">Low</th><th style="font-weight:500;padding:6px 10px">Sun</th><th style="font-weight:500;padding:6px 10px">Rain</th></tr>` +
    C.filter(([k]) => D1.stations[k]).map(([k, c]) => { const H = D1.stations[k].hours, h = H.reduce((a, b) => b.temp > a.temp ? b : a);
      return `<tr style="border-top:1px solid var(--line);text-align:right"><td style="text-align:left;padding:6px 10px">${c}</td><td style="padding:6px 10px"><b>${Math.round(h.temp)}°</b> <span class="mute">(${Math.round(h.temp_lo)} to ${Math.round(h.temp_hi)})</span></td><td style="padding:6px 10px">${Math.round(Math.min(...H.map(x => x.temp)))}°</td><td style="padding:6px 10px">${(H.reduce((a, x) => a + x.sun, 0) / 60).toFixed(1)} h</td><td style="padding:6px 10px">${Math.max(...H.map(x => x.rain))}%</td></tr>`; }).join("") + `</table>`; }
function wxB() { const h = document.getElementById("wxB"); h.innerHTML = `<p class="lede">${wxLead()}</p>${wxRankBlock("wxBrk")}<h2 style="margin-top:28px">Against every public model, all of 2026's test</h2><figure><div id="wxBrel"></div><figcaption>Each row is one kind of weather. The dashed line is the best public forecast for it, set to 100%; grey dots are the other public models, blue is ECMWF IFS and orange is DKcast. Hover a dot for its exact error.</figcaption></figure>`;
  wxRankDraw("wxBrk"); wxRel("wxBrel"); }
function tlA() {
  const TL = LV.TL, S = TL.series, host = document.getElementById("tlA"), W = 760, L = 56, R = 10, top = 46, bot = 40, H = 360, n = S.length;
  const mx = Math.ceil(Math.max(...S.flatMap(r => [r.a, r.j, r.e]).filter(v => v != null)) / 1000) * 1000, X = i => L + i * (W - L - R) / (n - 1), Y = v => top + (1 - v / mx) * (H - top - bot);
  const s = svg(host, W, H + 30);
  [["#1d1d1b", "measured output", 0], ["#c2410c", "my forecast, J4catDK", 0], ["#1e40af", "Energinet's forecast", 0], ["#c2410c", "my miss", 1]].forEach(([c, t, area], j) => { const x0 = L + j * 168;
    if (area) el("rect", {x: x0, y: H + 8, width: 20, height: 12, fill: c, opacity: .2}, s); else el("line", {x1: x0, x2: x0 + 20, y1: H + 14, y2: H + 14, stroke: c, "stroke-width": 2.6}, s);
    el("text", {x: x0 + 26, y: H + 18, "font-size": 12, fill: "#1d1d1b"}, s, t); });
  for (let v = 0; v <= mx; v += 1000) { el("line", {x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: "#eee"}, s); el("text", {x: L - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "#6b6a65"}, s, v.toLocaleString("en")); }
  // the gap between my forecast and what happened, shaded: the bigger the shading, the bigger the miss
  let seg = []; const flush = () => { if (seg.length > 1) el("path", {d: "M" + seg.map(([i, r]) => `${X(i)},${Y(r.j)}`).join("L") + "L" + seg.slice().reverse().map(([i, r]) => `${X(i)},${Y(r.a)}`).join("L") + "Z", fill: "#c2410c", opacity: .16}, s); seg = []; };
  S.forEach((r, i) => { if (r.a != null && r.j != null) seg.push([i, r]); else flush(); }); flush();
  const line = (k, c, w) => el("path", {d: S.map((r, i) => r[k] == null ? "" : `${i && S[i - 1][k] != null ? "L" : "M"}${X(i)},${Y(r[k])}`).join(""), fill: "none", stroke: c, "stroke-width": w}, s);
  line("e", "#1e40af", 1.6); line("j", "#c2410c", 2.4); line("a", "#1d1d1b", 2);
  TL.days.forEach(d => { const i0 = S.findIndex(r => isoCph(new Date(r.t + ":00Z")) == d.day); if (i0 < 0) return;
    el("line", {x1: X(i0), x2: X(i0), y1: top - 34, y2: H - bot, stroke: "#e4e1d9"}, s);
    el("text", {x: X(i0) + 4, y: H - bot + 16, "font-size": 11, fill: d.day == TL.today ? "#c2410c" : "#6b6a65", "font-weight": d.day == TL.today ? 700 : 400}, s, d.day == TL.today ? "today" : lvDay(d.day));
    if (d.err && d.err.j4catdk != null) { const win = d.err.j4catdk <= d.err.energinet;
      el("rect", {x: X(i0) + 4, y: top - 34, width: 64, height: 22, rx: 11, fill: win ? "#fff1e6" : "#eef2ff"}, s);
      el("text", {x: X(i0) + 36, y: top - 19, "font-size": 11, "text-anchor": "middle", fill: win ? "#9a3412" : "#1e40af", "font-weight": 600}, s, `${d.err.j4catdk.toFixed(1)} vs ${d.err.energinet.toFixed(1)}`); } });
  el("text", {x: L, y: 10, "font-size": 11, fill: "#6b6a65"}, s, "each day: my error vs Energinet's, % of capacity");
  const g = el("line", {x1: 0, x2: 0, y1: top, y2: H - bot, stroke: "#1d1d1b", "stroke-dasharray": "3 3", opacity: 0}, s);
  S.forEach((r, i) => { const h = el("rect", {x: X(i) - (W - L - R) / n / 2, y: top, width: (W - L - R) / n, height: H - top - bot, fill: "transparent"}, s);
    h.addEventListener("pointermove", e => { g.setAttribute("x1", X(i)); g.setAttribute("x2", X(i)); g.setAttribute("opacity", .5);
      lvTip(e, `<b>${fDay(isoCph(new Date(r.t + ":00Z")))} ${fHM(new Date(r.t + ":00Z"))}</b><br>measured ${r.a != null ? r.a.toLocaleString("en") + " MW" : "not yet"}<br>J4catDK ${r.j != null ? r.j.toLocaleString("en") + " MW" : "n/a"}<br>Energinet ${r.e != null ? r.e.toLocaleString("en") + " MW" : "n/a"}` +
        (r.a != null && r.j != null ? `<br>my miss ${Math.abs(r.j - r.a).toLocaleString("en")} MW` : "")); });
    h.addEventListener("pointerleave", () => { g.setAttribute("opacity", 0); lvOff(); }); });
  document.getElementById("tlAcap").textContent = "Total Danish wind output, hour by hour, in MW. Black is what was measured, orange is my forecast (J4catDK), blue is Energinet's own day-ahead forecast. " +
    "The orange shading is the gap between my forecast and what happened, so a wide band is a big miss. The chip above each day reads mine vs Energinet's, the day's error as a % of installed capacity: orange when mine was smaller, blue when Energinet's was. Hover for the hour's numbers.";
}
const SITES = [["dk-forecast/", "thumb-forecast.jpg", "Can one person forecast Danish weather better than the big public models?", "The one-page summary: DKcast against ECMWF, DMI and yr.no, and the power forecast against Energinet."],
  ["dkcast/", "thumb-dkcast.jpg", "DKcast: so I built a weather website", "It started as a wind power project and ended with me running a weather site. Tomorrow at 21 Danish stations, how sure it is, and every morning it checks itself against DMI."],
  ["dk-wind-blend/", "thumb-study.jpg", "Denmark wind and weather study", "The full study: storm anatomy, error maps, blending and the uncertainty check, with a PDF."]];
function lkA() { document.getElementById("lkA").innerHTML = `<h2>More from this project</h2><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">` +
  SITES.map(([u, img, t, d]) => `<a href="${PUB + u}" style="display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden">
    <img src="data_alt/${img}" alt="" style="width:100%;display:block;border-bottom:1px solid var(--line)"><div class="sans" style="padding:10px 12px"><b style="font-size:.95rem">${t}</b><p class="mute" style="font-size:.84rem;margin:4px 0 0">${d}</p></div></a>`).join("") + `</div>`; }
// energy: the fixed window around go-live, 7 replayed days and the first 7 live days; empty slots fill in one per night
function lvEnergyWindow() {
  const live = "2026-10-31", days = []; for (let k = -7; k < 7; k++) days.push(new Date(new Date(live + "T12:00Z").getTime() + k * 864e5).toISOString().slice(0, 10));
  const rows = LV.TL.ranks.filter(r => days.includes(r.day)).map(r => ({day: r.day, source: r.source, rank: r.rank, nmae: r.nmae}));
  if (LV.D && LV.D.live) LV.D.live.daily.forEach(r => { if (days.includes(r.day) && !rows.some(q => q.day == r.day && q.source == r.source)) rows.push({day: r.day, source: r.source, rank: r.rank, nmae: r.nmae}); });
  const names = Object.assign({}, LV.TL.names); const host = document.getElementById("week");
  if (!rows.length) { host.innerHTML = ""; return; }
  lvRank(host, rows, names, "j4catdk", r => `error ${r.nmae.toFixed(2)}% of capacity`, null, ["j4catdk", "energinet"], {days, liveFrom: live});
  const cap = document.getElementById("weekcap"); if (cap) cap.textContent = `Daily rank of every forecast, 1st = smallest error that day, as a % of installed capacity. The seven days before ${lvDay(live)} are replayed: my model run on the weather forecasts as they stood the day before. From ${lvDay(live)} every forecast is live, published before the noon market close, and the empty slots fill in one per night. Orange is J4catDK, blue is Energinet's own forecast.`;
}
function lvStart(D, TL) {
  // the page's own data, plus DKcast's test scores and station data from the sister sites
  Object.assign(LV, {D, TL});
  Promise.all([lvj(PUB + "dk-forecast/data/weather.json"), lvj("data_alt/wx_ranks.json"), lvj(PUB + "dkcast/dkcast.json"), lvj("data_alt/wx_ranks_more.json")])
    .then(([FW, RK, DK, RM]) => { Object.assign(LV, {FW, RK, DK, RM}); if (FW) wxB(); });
  if (TL) { tlA(); lvEnergyWindow(); }
  lkA();
}
