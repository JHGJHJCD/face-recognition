"use strict";
/* ממשק התוכנה. כל הנתונים מגיעים מהשרת המקומי (webui/backend.py); כאן רק ציור ואינטראקציה. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const daysAgo = n => { const d = new Date(Date.now() - n * 864e5); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };

const ICON = {
  live: '<path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="3"/>',
  people: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  photos: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
  video: '<rect x="2" y="3" width="20" height="18" rx="3"/><path d="M7 3v18M17 3v18M2 9h5M2 15h5M17 9h5M17 15h5"/>',
  attendance: '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18M9 16l2 2 4-4"/>',
  assistant: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 2.9-1.2V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9h.1a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  camoff: '<path d="M1 1l22 22M21 17V7l-7 5M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5 0h4a2 2 0 0 1 2 2v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', play: '<path d="M6 4l14 8-14 8V4z"/>', stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  excel: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13l6 6M15 13l-6 6"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>', trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>', copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L21 2M16 7l3 3"/>', send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
  data: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.7-4 3-9 3s-9-1.3-9-3M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>', x: '<path d="M18 6L6 18M6 6l12 12"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>', upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  cake: '<path d="M20 21v-8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8M4 16s.5-1 2-1 2.5 2 4 2 2.500-2 4-2 2.500 2 4 2 2-1 2-1M2 21h20M7 8v3M12 8v3M17 8v3M7 4h.01M12 4h.01M17 4h.01"/>',
  note: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
};
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[n]}</svg>`;

const PAGES = [
  ["live", "זיהוי חי", "מי נמצא עכשיו מול המצלמה", "זיהוי"],
  ["people", "אנשים", "האנשים שהתוכנה מכירה, והלא-מוכרים שנקלטו"],
  ["photos", "מיון תמונות", "סריקת תיקיות תמונות ומציאת כל התמונות של כל אדם"],
  ["video", "בדיקת סרטון", "מי מופיע, ואיפה יש נשים או ילדות — מקובץ או מקישור יוטיוב"],
  ["attendance", "יומן נוכחות", "הגעות, עזיבות, איחורים ונעדרים", "מעקב"],
  ["assistant", "עוזר AI", "שאל בעברית חופשית על כל מה שהתוכנה רואה ורושמת"],
  ["data", "נתונים ועדכונים", "גיבוי, שחזור, ניקוי, ייצוא ועדכון התוכנה", "מערכת"],
  ["settings", "הגדרות", "השינויים נשמרים מיד"],
];
const empty = (ic, title, text = "", attr = "") => `<div class="empty" ${attr}>${icon(ic)}<b>${title}</b>${text}</div>`;

const S = { page: "live", boot: null, poll: null, lastEv: 0, rev: {}, events: [], camera: false, selPerson: null, selUnknown: null,
            photoSel: null, videoSel: null, att: { view: 0, from: today(), to: today() }, chat: [], chatBusy: false, settings: {} };

// ---------- תקשורת ----------
async function api(path, body) {
  const r = await fetch("api/" + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: "תשובה לא תקינה מהשרת" }));
  if (!r.ok || j.error) throw new Error(j.error || "שגיאה");
  return j;
}
async function act(path, body, okMsg) {
  try { const r = await api(path, body ?? {}); if (okMsg && !r.cancelled) toast(typeof okMsg === "function" ? okMsg(r) : okMsg, "ok"); return r; }
  catch (e) { toast(e.message, "bad"); return null; }
}
function toast(text, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind; t.textContent = text;
  $("#toasts").append(t); setTimeout(() => t.remove(), 4200);
}

// ---------- חלונות ----------
function modal(html, onMount) {
  return new Promise(resolve => {
    const o = document.createElement("div");
    o.className = "overlay"; o.innerHTML = `<div class="modal">${html}</div>`;
    const close = v => { o.remove(); document.removeEventListener("keydown", key); resolve(v); };
    const key = e => { if (e.key === "Escape") close(null); if (e.key === "Enter" && e.target.tagName !== "TEXTAREA") $("[data-ok]", o)?.click(); };
    document.addEventListener("keydown", key);
    o.addEventListener("mousedown", e => { if (e.target === o) close(null); });
    $$("[data-cancel]", o).forEach(b => b.onclick = () => close(null));
    $("#modal-root").append(o); onMount(o, close);
    ($("input,textarea", o) || $("[data-ok]", o))?.focus();
  });
}
function askPerson(title, p = {}) {
  return modal(`<h3>${esc(title)}</h3>
    <div class="two"><label class="field">שם פרטי<input type="text" id="m-first" value="${esc(p.first)}"></label>
    <label class="field">שם משפחה<input type="text" id="m-last" value="${esc(p.last)}"></label></div>
    <label class="field">תאריך לידה (לא חובה — אם יוזן, הגיל יחושב ממנו במקום הערכה)<input type="date" id="m-birth" max="${today()}" value="${esc(p.birth)}"></label>
    <label class="field">הערות (לא חובה)<input type="text" id="m-notes" value="${esc(p.notes)}" placeholder="תפקיד, טלפון, כל דבר שעוזר"></label>
    <div class="err" id="m-err"></div>
    <div class="actions"><button class="btn primary" data-ok>אישור</button><button class="btn" data-cancel>ביטול</button></div>`,
    (o, close) => { $("[data-ok]", o).onclick = () => {
      const first = $("#m-first", o).value.trim(), last = $("#m-last", o).value.trim();
      if (!first || !last) { $("#m-err", o).textContent = "יש למלא שם פרטי ושם משפחה."; return; }
      close({ first, last, birth: $("#m-birth", o).value || "", notes: $("#m-notes", o).value.trim() }); }; });
}
function choose(title, options, okText = "אישור") {
  return modal(`<h3>${esc(title)}</h3><select id="m-sel">${options.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("")}</select>
    <div class="actions"><button class="btn primary" data-ok>${esc(okText)}</button><button class="btn" data-cancel>ביטול</button></div>`,
    (o, close) => { $("[data-ok]", o).onclick = () => close($("#m-sel", o).value); });
}
function askRecord(title, r = {}) {
  return modal(`<h3>${esc(title)}</h3>
    ${r.pid ? "" : `<label class="field">אדם<select id="m-pid">${(S.peopleList || []).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select></label>`}
    <label class="field">תאריך<input type="date" id="m-date" value="${esc(r.date || today())}"></label>
    <div class="two"><label class="field">הגעה<input type="time" id="m-in" value="${esc(r.t_in || "08:00")}"></label><label class="field">עזיבה<input type="time" id="m-out" value="${esc(r.t_out || "16:00")}"></label></div>
    <div class="actions"><button class="btn primary" data-ok>שמור</button><button class="btn" data-cancel>ביטול</button></div>`,
    (o, close) => { $("[data-ok]", o).onclick = () => close({ pid: r.pid || +$("#m-pid", o).value, date: $("#m-date", o).value, t_in: $("#m-in", o).value, t_out: $("#m-out", o).value }); });
}
function confirmBox(text, okText = "מחק") {
  return modal(`<h3>${esc(text)}</h3><div class="actions"><button class="btn danger" data-ok>${esc(okText)}</button><button class="btn" data-cancel>ביטול</button></div>`,
    (o, close) => { $("[data-ok]", o).onclick = () => close(true); });
}

// ---------- ניווט ----------
function go(page) {
  S.page = page;
  const [, title, sub] = PAGES.find(p => p[0] === page);
  $("#page-title").textContent = title; $("#page-sub").textContent = sub; $("#top-actions").innerHTML = "";
  $$("#menu button").forEach(b => b.classList.toggle("on", b.dataset.page === page));
  const el = $("#page"); el.style.animation = "none"; void el.offsetWidth; el.style.animation = "";
  RENDER[page]();
}
function buildMenu() {
  $("#menu").innerHTML = PAGES.map(([id, t, , group], i) => `${group ? `<div class="group">${group}</div>` : ""}<button data-page="${id}">${icon(id)}<span>${t}</span><kbd>Ctrl ${i + 1}</kbd></button>`).join("");
  $$("#menu button").forEach(b => b.onclick = () => go(b.dataset.page));
  $("#nav-search-ic").outerHTML = icon("search");
  $("#nav-search").onclick = palette;
  document.addEventListener("keydown", e => {
    if (!e.ctrlKey || e.altKey) return;
    if (e.key.toLowerCase() === "k" || e.key === "ל") { e.preventDefault(); palette(); }
    else if (e.key >= "1" && e.key <= String(PAGES.length) && !$(".overlay")) { e.preventDefault(); go(PAGES[+e.key - 1][0]); }
  });
}
// חיפוש מהיר (Ctrl+K): מסכים ואנשים
async function palette() {
  if ($(".overlay")) return;
  const o = document.createElement("div"); o.className = "overlay pal";
  o.innerHTML = `<div class="palette"><input type="text" placeholder="לאן לעבור? מסך או שם של אדם…"><div class="pal-list"></div></div>`;
  const inp = $("input", o), box = $(".pal-list", o); let items = [], cur = 0;
  const close = () => o.remove();
  const pick = it => { close(); if (it.pid) S.selPerson = it.pid; go(it.page); };
  const draw = () => {
    const q = inp.value.trim().toLowerCase();
    const all = [...PAGES.map(([page, label]) => ({ page, label, ic: page })), ...(S.peopleList || []).map(p => ({ page: "people", pid: p.id, label: p.name }))];
    items = all.filter(it => !q || it.label.toLowerCase().includes(q)).slice(0, 40); cur = Math.min(cur, Math.max(0, items.length - 1));
    box.innerHTML = items.map((it, i) => `<div class="pal-item ${i === cur ? "on" : ""}" data-i="${i}">${it.pid ? `<img src="img/person/${it.pid}">` : icon(it.ic)}<span>${esc(it.label)}</span><small>${it.pid ? "אדם" : ""}</small></div>`).join("")
      || `<div class="empty" style="padding:22px">לא נמצא מסך או אדם בשם הזה.</div>`;
    $(".pal-item.on", box)?.scrollIntoView({ block: "nearest" });
  };
  box.onclick = e => { const el = e.target.closest(".pal-item"); if (el) pick(items[+el.dataset.i]); };
  box.onmousemove = e => { const el = e.target.closest(".pal-item"); if (el && +el.dataset.i !== cur) { cur = +el.dataset.i; draw(); } };
  inp.oninput = () => { cur = 0; draw(); };
  inp.onkeydown = e => {
    if (e.key === "Escape") close();
    else if (e.key === "Enter") { if (items[cur]) pick(items[cur]); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); cur = (cur + (e.key === "ArrowDown" ? 1 : -1) + items.length) % Math.max(1, items.length); draw(); }
  };
  o.onmousedown = e => { if (e.target === o) close(); };
  $("#modal-root").append(o); draw(); inp.focus();
  if (!S.peopleList) { S.peopleList = await api("people").catch(() => null); if (o.isConnected) draw(); }
}
function setChips() {
  const i = S.boot.info;
  $("#brand-sub").textContent = i.model;
  $("#chip-device").textContent = "רץ על: " + i.device;
  $("#chip-ver").textContent = "גרסה " + S.boot.version;
  const c = $("#chip-ai"); c.textContent = i.ai ? `AI פעיל, ${i.keys} מפתחות` : "AI כבוי, הכול מקומי"; c.classList.toggle("off", !i.ai);
}

const RENDER = {};

// ====================================================================== זיהוי חי
const COLORS = { known: "#3fba80", unknown: "#eaa23c", spoof: "#f06a58", pending: "#e8c547" };
RENDER.live = () => {
  $("#page").innerHTML = `<div class="live">
    <div class="stage"><canvas id="cv" hidden></canvas>
      <div class="placeholder" id="ph"><div>${icon("camoff")}<div id="ph-text">המצלמה כבויה</div></div></div>
      <div class="hud" id="hud" hidden><span class="pill rec">חי</span><span class="pill" id="fps"></span></div></div>
    <div class="side">
      <div class="controls"><button class="btn primary wide" id="cam-btn"></button>
        <button class="btn wide" id="enroll-btn"></button>
        <div id="enroll-box" hidden><div class="bar"><i id="enroll-bar" style="width:0"></i></div><p class="hint" id="enroll-msg" style="margin-top:8px"></p></div></div>
      <div class="card ai-card" id="ai-card" hidden><h3>${icon("assistant")} מה רואים עכשיו <small id="ai-ts"></small></h3><p id="ai-text"></p></div>
      <div class="card feed"><h3>אירועים אחרונים</h3><div class="feed-list" id="feed"></div></div>
    </div></div>`;
  $("#cam-btn").onclick = async () => { $("#cam-btn").disabled = true; await act("camera", { on: !S.camera }); };
  $("#enroll-btn").onclick = async () => {
    if (S.poll?.enroll.active) return act("enroll/cancel");
    const p = await askPerson("רישום אדם חדש מהמצלמה"); if (p) act("enroll/start", p);
  };
  liveSync(); drawFeed();
};
function liveSync() {
  if (S.page !== "live" || !S.poll) return;
  const p = S.poll, cb = $("#cam-btn"), eb = $("#enroll-btn");
  cb.disabled = !p.engine;
  cb.innerHTML = !p.engine ? (p.load_error ? "טעינת המנועים נכשלה" : "טוען מנועי זיהוי…") : S.camera ? icon("stop") + "עצור מצלמה" : icon("play") + "הפעל מצלמה";
  eb.disabled = !S.camera;
  eb.innerHTML = p.enroll.active ? icon("x") + "בטל רישום" : icon("plus") + "רישום אדם חדש מהמצלמה";
  $("#cv").hidden = !S.camera; $("#hud").hidden = !S.camera; $("#ph").hidden = S.camera;
  $("#ph-text").textContent = p.camera_error || "המצלמה כבויה";
  $("#enroll-box").hidden = !p.enroll.active;
  $("#enroll-bar").style.width = (100 * p.enroll.n / Math.max(1, p.enroll.total)) + "%";
  $("#enroll-msg").textContent = p.enroll.msg;
  const show = p.ai_on && S.camera && p.ai.text;
  $("#ai-card").hidden = !show;
  if (show) { $("#ai-text").textContent = p.ai.text; $("#ai-ts").textContent = p.ai.ts; }
}
function drawFeed() {
  const f = $("#feed"); if (!f) return;
  f.innerHTML = S.events.length ? S.events.slice().reverse().map(e => `<div class="ev ${e.kind}">
    ${e.img ? `<img src="${esc(e.img)}" onerror="this.style.visibility='hidden'">` : `<div class="ph">${icon("assistant")}</div>`}
    <div><b>${esc(e.text)}</b><small>${esc(e.time)}</small></div></div>`).join("") : empty("live", "עדיין אין אירועים", "הפעל את המצלמה, וכל מי שיזוהה יופיע כאן.");
}
async function frameLoop() {
  let last = 0;
  while (true) {
    if (!S.camera || S.page !== "live" || document.hidden) { await sleep(250); continue; }
    try {
      const r = await fetch("frame?last=" + last);
      if (r.status !== 200) { await sleep(60); continue; }
      const meta = JSON.parse(atob(r.headers.get("X-Meta")));
      const bmp = await createImageBitmap(await r.blob());
      last = meta.id; drawFrame(bmp, meta); bmp.close();
    } catch { await sleep(400); }
  }
}
function roundRect(c, x, y, w, h, r) { c.beginPath(); c.roundRect(x, y, w, h, r); }
function drawFrame(bmp, meta) {
  const cv = $("#cv"); if (!cv) return;
  if (cv.width !== meta.w) { cv.width = meta.w; cv.height = meta.h; }
  const c = cv.getContext("2d"), k = cv.width / Math.max(1, cv.clientWidth);   // k = פיקסלי תמונה לכל פיקסל מסך
  c.drawImage(bmp, 0, 0);
  $("#fps").textContent = `${Math.round(meta.fps)} תמונות בשנייה · ${meta.labels.length} פנים`;
  for (const lb of meta.labels) {
    const [x1, y1, x2, y2] = lb.bbox, w = x2 - x1, h = y2 - y1, col = COLORS[lb.state];
    
    // מסגרת דקה ושקופה + פינות מעוגלות מודגשות
    const R = Math.min(w, h) * .12, L = Math.min(w, h) * .2;
    c.strokeStyle = col; c.lineCap = "round"; c.lineJoin = "round";
    c.globalAlpha = .35; c.lineWidth = 1.5 * k; roundRect(c, x1, y1, w, h, R); c.stroke(); c.globalAlpha = 1;
    c.lineWidth = 3 * k;
    for (const [cx, cy, dx, dy] of [[x1, y1, 1, 1], [x2, y1, -1, 1], [x1, y2, 1, -1], [x2, y2, -1, -1]]) {
      c.beginPath(); c.moveTo(cx + dx * L, cy); c.arcTo(cx, cy, cx, cy + dy * L, R); c.lineTo(cx, cy + dy * L); c.stroke();
    }
    // תווית: רקע כהה שקוף, נקודת מצב בצבע, טקסט לבן
    const pill = (text, font, cy, dot, above) => {
      c.font = font; c.direction = "rtl"; c.textAlign = "right"; c.textBaseline = "middle";
      const d = dot ? 14 * k : 0, tw = c.measureText(text).width + 22 * k + d, th = 26 * k, px = (x1 + x2) / 2 - tw / 2, py = above ? cy - th : cy;
      c.fillStyle = "rgba(12,13,17,.78)"; roundRect(c, px, py, tw, th, th / 2); c.fill();
      if (dot) { c.fillStyle = col; c.beginPath(); c.arc(px + tw - 14 * k, py + th / 2, 4 * k, 0, 7); c.fill(); }
      c.fillStyle = dot ? "#fff" : "#c9cdd6"; c.fillText(text, px + tw - 11 * k - d, py + th / 2 + k);
    };
    pill(lb.title, `500 ${14.5 * k}px UI, "Segoe UI"`, y1 - 8 * k, true, true);
    if (lb.sub) pill(lb.sub, `${12.5 * k}px UI, "Segoe UI"`, y2 + 8 * k, false, false);
  }
}

// ====================================================================== אנשים
RENDER.people = async () => {
  $("#top-actions").innerHTML = `<button class="btn" id="p-export">${icon("excel")}ייצוא לאקסל</button><button class="btn primary" id="p-new">${icon("plus")}אדם חדש מתמונות</button>`;
  $("#p-export").onclick = () => act("people/export");
  $("#p-new").onclick = async () => { const p = await askPerson("אדם חדש"); if (p) { toast("בחר תמונות של האדם בחלון שנפתח…"); await act("people/from_files", p, r => `${r.name} נרשם עם ${r.added} תמונות`); } };
  $("#page").innerHTML = `<div class="split">
    <div class="card"><h3>אנשים רשומים <small id="p-count"></small></h3><div class="scroll"><div class="people-grid" id="p-grid"><div class="skel"></div><div class="skel"></div><div class="skel"></div></div></div>
      <div id="p-detail"></div></div>
    <div class="card"><h3>לא מוכרים שנקלטו במצלמה</h3><p class="hint" style="margin-bottom:10px">בחר תמונה ותן לה שם, והאדם יזוהה מעכשיו.</p>
      <div class="scroll"><div class="thumbs" id="u-grid"></div></div><div id="u-note"></div>
      <div class="row" style="margin-top:12px"><button class="btn primary small" id="u-name">תן שם</button><button class="btn small" id="u-del">מחק</button><button class="btn small danger" id="u-clear">מחק הכל</button></div></div></div>`;
  $("#u-name").onclick = async () => { if (!S.selUnknown) return toast("בחר קודם תמונה"); const p = await askPerson("מי זה?"); if (p && await act("unknown/name", { id: S.selUnknown, ...p }, "נרשם — מעכשיו יזוהה")) S.selUnknown = null; };
  $("#u-del").onclick = () => S.selUnknown && act("unknown/delete", { id: S.selUnknown });
  $("#u-clear").onclick = async () => { if (await confirmBox("למחוק את כל הלא-מוכרים שנקלטו?")) act("unknown/clear"); };
  await Promise.all([loadPeople(), loadUnknown()]);
};
async function loadPeople() {
  const list = await api("people").catch(() => []); if (S.page !== "people") return;
  S.peopleList = list; $("#p-count").textContent = list.length + " אנשים";
  $("#p-grid").innerHTML = list.length ? list.map(p => `<div class="person ${p.id === S.selPerson ? "on" : ""}" data-id="${p.id}">
    <img src="img/person/${p.id}?v=${S.rev.people}" onerror="this.style.opacity=.2"><div><b>${esc(p.name)}${p.birthday ? icon("cake") : ""}</b>
    <dl>${p.age != null ? `<span><dt>גיל</dt><dd>${p.age}</dd></span>` : ""}<span><dt>דגימות</dt><dd>${p.samples}</dd></span>${p.photos ? `<span><dt>תמונות</dt><dd>${p.photos.toLocaleString()}</dd></span>` : ""}</dl></div></div>`).join("") : empty("people", "עדיין לא נרשם אף אחד", "הוסף אדם מתמונות, או רשום אותו מול המצלמה במסך הזיהוי החי.", 'style="grid-column:1/-1"');
  $$("#p-grid .person").forEach(el => el.onclick = () => { S.selPerson = +el.dataset.id; loadPeople(); });
  const p = list.find(x => x.id === S.selPerson), d = $("#p-detail");
  if (!p) { d.innerHTML = ""; return; }
  const samples = await api("samples?id=" + p.id).catch(() => []);
  d.innerHTML = `<div class="detail">
    <div class="row"><b class="name">${esc(p.name)}</b><span class="muted">${p.birth ? "נולד " + p.birth.split("-").reverse().join("/") : "ללא תאריך לידה"}</span><span class="grow"></span>
    <button class="btn small" id="d-add">${icon("photos")}הוסף תמונות</button><button class="btn small" id="d-edit">${icon("edit")}ערוך פרטים</button><button class="btn small" id="d-merge" title="אם אותו אדם נרשם פעמיים">מזג לאדם אחר</button><button class="btn small danger" id="d-del">${icon("trash")}מחק</button></div>
    ${p.notes ? `<div class="note">${icon("note")}<span>${esc(p.notes)}</span></div>` : ""}
    <p class="hint" style="margin-top:10px">דגימות הזיהוי = התמונות שלפיהן התוכנה מכירה את האדם (מספיקות 5–30). ${p.photos ? `כל ${p.photos.toLocaleString()} התמונות שבהן הוא נמצא מחכות <a href="#photos">במיון תמונות</a>.` : ""}</p>
    <div class="thumbs" style="margin-top:8px;max-height:180px;overflow:auto">${samples.map(s => `<div class="thumb"><img src="img/sample/${s.id}"><span>${esc(s.source)}</span><button class="x" data-sid="${s.id}" title="מחק דגימה">×</button></div>`).join("")}</div></div>`;
  $("#d-add").onclick = () => act("people/add_files", { id: p.id }, r => `נוספו ${r.added} דגימות`);
  $("#d-edit").onclick = async () => { const v = await askPerson("עריכת פרטים", p); if (v) act("people/update", { id: p.id, ...v }, "הפרטים עודכנו"); };
  $("#d-del").onclick = async () => { if (await confirmBox(`למחוק את ${p.name} וכל הנתונים שלו?`)) { S.selPerson = null; act("people/delete", { id: p.id }); } };
  $("#d-merge").onclick = async () => {
    const others = list.filter(x => x.id !== p.id).map(x => ({ value: x.id, label: x.name }));
    if (!others.length) return toast("אין אדם אחר למזג אליו");
    const dst = await choose(`למזג את ${p.name} לתוך…`, others, "מזג");
    if (dst && await confirmBox(`כל הדגימות, הנוכחות והתמונות של ${p.name} יעברו ל-${list.find(x => x.id === +dst).name}, ו-${p.name} יימחק.`, "מזג")) { S.selPerson = +dst; act("people/merge", { src: p.id, dst: +dst }, "מוזג"); }
  };
  $$("#p-detail .x").forEach(b => b.onclick = e => { e.stopPropagation(); act("samples/delete", { id: +b.dataset.sid }); });
}
async function loadUnknown() {
  const list = await api("unknown").catch(() => []); if (S.page !== "people") return;
  $("#u-grid").innerHTML = list.length ? list.map(u => `<div class="thumb ${u.id === S.selUnknown ? "on" : ""}" data-id="${u.id}" title="${esc(u.note)}"><img src="img/unknown/${u.id}"><span>${esc(u.time)}</span></div>`).join("") : empty("people", "אין לא-מוכרים", "מי שהמצלמה לא תזהה יישמר כאן.", 'style="grid-column:1/-1"');
  $$("#u-grid .thumb").forEach(el => el.onclick = () => { S.selUnknown = +el.dataset.id; loadUnknown(); });
  const u = list.find(x => x.id === S.selUnknown);
  $("#u-note").innerHTML = u?.note ? `<div class="note">${icon("assistant")}<span>${esc(u.note)}</span></div>` : "";
}

// ====================================================================== תמונות
RENDER.photos = async () => {
  $("#top-actions").innerHTML = `<button class="btn" id="ph-cluster">${icon("search")}מצא אנשים שעדיין לא רשומים</button><button class="btn primary" id="ph-scan"></button>`;
  $("#ph-scan").onclick = () => S.poll?.photo.running ? act("photos/stop") : act("photos/scan");
  $("#ph-cluster").onclick = async () => { const b = $("#ph-cluster"); b.disabled = true; toast("מקבץ פנים דומות…"); const r = await act("photos/cluster"); b.disabled = false; if (r && !r.count) toast("לא נמצאו קבוצות של אנשים לא רשומים (נדרשות לפחות 4 הופעות)."); };
  $("#page").innerHTML = `<div class="split" style="grid-template-columns:300px 1fr">
    <div class="card"><h3>מי מופיע בתמונות</h3><div class="scroll"><div class="list" id="ph-people"></div></div></div>
    <div class="card"><div id="ph-progress" hidden style="margin-bottom:12px"><div class="bar"><i id="ph-bar"></i></div><p class="hint" id="ph-file" style="margin-top:6px"></p></div>
      <div class="row" style="margin-bottom:12px"><b id="ph-title" style="font-size:15px;font-weight:600"></b><span class="muted" id="ph-stats"></span><span class="grow"></span>
      <button class="btn small primary" id="ph-name" hidden>תן שם לקבוצה</button><button class="btn small" id="ph-copy" hidden>${icon("copy")}העתק את התמונות לתיקייה</button></div>
      <div class="scroll"><div class="photo-grid" id="ph-grid"></div></div><p class="hint" style="margin-top:8px">לחיצה כפולה פותחת את התמונה המלאה.</p></div></div>`;
  $("#ph-name").onclick = async () => { const p = await askPerson("מי זה?"); if (p && await act("photos/name_cluster", { idx: S.photoSel.id, ...p }, "נרשם")) S.photoSel = null; };
  $("#ph-copy").onclick = () => S.photoSel && act("photos/copy", S.photoSel, r => `הועתקו ${r.copied} תמונות. המקור לא השתנה.`);
  photosSync(); await loadPhotos();
};
function photosSync() {
  if (S.page !== "photos" || !S.poll) return;
  const p = S.poll.photo;
  $("#ph-scan").innerHTML = p.running ? icon("stop") + "עצור סריקה" : icon("folder") + "בחר תיקייה וסרוק";
  $("#ph-progress").hidden = !p.running;
  $("#ph-bar").style.width = (100 * p.i / Math.max(1, p.n)) + "%";
  $("#ph-file").textContent = p.running ? `${p.i.toLocaleString()} / ${p.n.toLocaleString()} · ${p.file}` : "";
  if (p.result) { toast(`נסרקו ${p.result.new.toLocaleString()} תמונות חדשות ונמצאו בהן ${p.result.faces.toLocaleString()} פנים.`, "ok"); act("photos/ack"); p.result = null; }
}
async function loadPhotos() {
  const o = await api("photos").catch(() => null); if (!o || S.page !== "photos") return;
  $("#ph-stats").textContent = `נסרקו ${o.photos.toLocaleString()} תמונות · ${o.faces.toLocaleString()} פנים`;
  const sel = S.photoSel, is = (k, id) => sel && sel.kind === k && sel.id === id;
  $("#ph-people").innerHTML = (o.people.map(p => `<div class="li ${is("p", p.id) ? "on" : ""}" data-kind="p" data-id="${p.id}"><img src="img/person/${p.id}"><div><b>${esc(p.name)}</b><small>${p.count} תמונות</small></div></div>`).join("") +
    o.clusters.map(c => `<div class="li ${is("c", c.idx) ? "on" : ""}" data-kind="c" data-id="${c.idx}"><img src="img/cluster/${c.idx}?v=${S.rev.photos}"><div><b>לא רשום #${c.idx + 1}</b><small>${c.count} הופעות</small></div></div>`).join(""))
    || empty("photos", "עדיין לא נסרקו תמונות", "בחר תיקייה, והתוכנה תמצא מי מופיע בכל תמונה.");
  $$("#ph-people .li").forEach(el => el.onclick = () => { S.photoSel = { kind: el.dataset.kind, id: +el.dataset.id }; loadPhotos(); });
  $("#ph-name").hidden = !(sel && sel.kind === "c"); $("#ph-copy").hidden = !sel;
  if (!sel) { $("#ph-title").textContent = ""; $("#ph-grid").innerHTML = empty("people", "בחר אדם מהרשימה", "כל התמונות שבהן הוא מופיע יוצגו כאן.", 'style="grid-column:1/-1"'); return; }
  const items = await api(`photos/list?kind=${sel.kind}&id=${sel.id}`).catch(() => []);
  const name = sel.kind === "p" ? (o.people.find(p => p.id === sel.id)?.name || "") : `אדם לא רשום #${sel.id + 1}`;
  $("#ph-title").textContent = `${name} — ${items.length} תמונות`;
  $("#ph-grid").innerHTML = items.map((it, i) => `<div class="thumb" data-i="${i}"><img loading="lazy" src="${it.img}?v=${S.rev.photos}"><span>${esc(it.name)}</span></div>`).join("");
  $$("#ph-grid .thumb").forEach(el => el.ondblclick = () => act("photos/open", { path: items[+el.dataset.i].path }));
}

// ====================================================================== וידאו
RENDER.video = async () => {
  $("#top-actions").innerHTML = `<button class="btn" id="v-name">תן שם ללא-מוכר</button><button class="btn" id="v-export">${icon("excel")}ייצוא לאקסל</button><button class="btn primary" id="v-scan"></button>`;
  $("#v-scan").onclick = () => S.poll?.video.running ? act("video/stop") : act("video/scan");
  $("#v-export").onclick = () => act("video/export");
  $("#v-name").onclick = async () => { if (S.videoSel == null) return toast("בחר בטבלה שורה של אדם לא מוכר"); const p = await askPerson("מי זה?"); if (p) act("video/name", { idx: S.videoSel, ...p }, "נרשם"); };
  $("#page").innerHTML = `<div class="split" style="grid-template-columns:1fr 400px">
    <div class="card" style="gap:10px">
      <div class="row" id="v-urlrow"><input type="text" id="v-url" placeholder="הדבק קישור יוטיוב (youtube.com / youtu.be)" style="flex:1;min-width:200px" dir="ltr">
        <button class="btn primary" id="v-go">${icon("video")}בדוק קישור</button></div>
      <div id="v-progress" hidden><div class="bar"><i id="v-bar"></i></div><small class="muted" id="v-phase"></small></div>
      <p class="muted" id="v-status"></p><div id="v-notes"></div>
      <h3 style="margin:0">מי מופיע בסרטון</h3>
      <div class="table-wrap" style="flex:0 1 auto;max-height:30%"><table><thead><tr><th></th><th>שם</th><th>זמן מסך</th><th>מופיע בדקות</th></tr></thead><tbody id="v-body"></tbody></table></div>
      <h3 style="margin:0">נשים וילדות בסרטון</h3><small class="muted" id="v-sum"></small>
      <div class="table-wrap" style="flex:1"><table><thead><tr><th></th><th>מי</th><th>גיל משוער</th><th>קטע</th><th>מקור</th><th>הערה</th></tr></thead><tbody id="v-fem"></tbody></table></div></div>
    <div class="card"><h3>תצוגה מקדימה</h3><div class="stage" style="flex:1"><img id="v-prev" style="max-width:100%;max-height:100%" hidden></div></div></div>`;
  const go = () => { const u = $("#v-url").value.trim(); if (!u) return toast("הדבק קישור יוטיוב"); act("video/url", { url: u }, "מתחיל…"); };
  $("#v-go").onclick = go; $("#v-url").onkeydown = e => { if (e.key === "Enter") go(); };
  videoSync(); await loadVideo();
};
function videoSync() {
  if (S.page !== "video" || !S.poll) return;
  const v = S.poll.video;
  $("#v-scan").innerHTML = v.running ? icon("stop") + "עצור" : icon("video") + "בחר קובץ וסרוק";
  $("#v-go").disabled = v.running;
  $("#v-progress").hidden = !v.running; $("#v-bar").style.width = v.pct + "%"; $("#v-phase").textContent = v.phase || "";
  $("#v-status").textContent = v.running ? `${v.file} · ${v.pct}%${v.phase ? " · " + v.phase : ""}` : (v.file ? `${v.file} · ${v.status}` : "בחר קובץ וידאו או הדבק קישור יוטיוב: התוכנה מוצאת מי מופיע, ובאילו קטעים יש נשים או ילדות (הגיל לפי Gemini).");
  $("#v-notes").innerHTML = (v.notes || []).map(n => `<p class="muted" style="color:var(--warn)">${esc(n)}</p>`).join("");
  if (v.preview && v.preview !== S.vPrev) { S.vPrev = v.preview; const im = $("#v-prev"); im.hidden = false; im.src = "img/videopreview?n=" + v.preview; }
}
async function loadVideo() {
  const r = await api("video").catch(() => null); if (!r || S.page !== "video") return;
  if (r.url && !$("#v-url").value) $("#v-url").value = r.url;
  $("#v-body").innerHTML = r.people.map(p => `<tr data-idx="${p.idx}" class="${p.idx === S.videoSel ? "on" : ""}"><td><img src="img/vid/${p.idx}?v=${S.rev.video}"></td>
    <td><b>${esc(p.name)}</b> ${p.known ? "" : '<span class="tag">לא מוכר</span>'}</td><td>${esc(p.total)}</td><td class="muted" dir="ltr" style="text-align:right">${esc(p.ranges.join("  ,  "))}</td></tr>`).join("")
    || `<tr><td colspan="4" class="muted">${r.females.length ? "לא זוהו פנים מוכרות (זיהוי אנשים דורש את קובץ הסרטון)" : "אין תוצאות עדיין"}</td></tr>`;
  $$("#v-body tr[data-idx]").forEach(tr => tr.onclick = () => { S.videoSel = +tr.dataset.idx; loadVideo(); });
  $("#v-sum").textContent = r.summary || "";
  $("#v-fem").innerHTML = r.females.map(f => {
    const who = f.small ? `<span class="tag ok">ילדה קטנה</span>` : `<span class="tag">${esc(f.kind)}</span>`;
    const dim = f.ai_female === false ? ' style="opacity:.5"' : "";
    return `<tr${dim}><td>${f.thumb ? `<img src="img/vidf/${f.idx}?v=${S.rev.video}">` : ""}</td><td>${who}</td><td>${f.age != null ? "~" + f.age : ""}</td>
      <td dir="ltr" style="text-align:right">${esc(f.start)}–${esc(f.end)}</td><td class="muted">${esc(f.source)}</td><td class="muted">${esc(f.ai)}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="muted">${r.people.length ? "לא נמצאו נשים או ילדות" : ""}</td></tr>`;
}

// ====================================================================== נוכחות
RENDER.attendance = async () => {
  const a = S.att;
  $("#top-actions").innerHTML = `<button class="btn" id="a-add">${icon("plus")}רשומה ידנית</button><button class="btn primary" id="a-export">${icon("excel")}ייצוא לאקסל</button>`;
  $("#a-export").onclick = () => act("attendance/export", a);
  $("#a-add").onclick = async () => { if (!S.peopleList) S.peopleList = await api("people").catch(() => []); if (!S.peopleList.length) return toast("אין אנשים רשומים"); const r = await askRecord("רשומת נוכחות ידנית"); if (r) act("attendance/add", r, "נוסף"); };
  $("#page").innerHTML = `<div class="att">
    <div class="kpis" id="a-kpis"></div>
    <div class="row filters"><div class="seg" id="a-views">${S.boot.views.map((v, i) => `<button data-v="${i}" class="${i === a.view ? "on" : ""}">${v}</button>`).join("")}</div><span class="grow"></span><div class="seg"><button data-span="0">היום</button><button data-span="6">השבוע</button><button data-span="29">30 יום</button></div>
      <span class="hint">מתאריך</span><input type="date" id="a-from" value="${a.from}"><span class="hint">עד</span><input type="date" id="a-to" value="${a.to}"></div>
    <div class="table-wrap"><table><thead id="a-head"></thead><tbody id="a-body"></tbody></table></div></div>`;
  $$("#a-views button").forEach(b => b.onclick = () => { a.view = +b.dataset.v; RENDER.attendance(); });
  $$("[data-span]").forEach(b => b.onclick = () => { a.from = daysAgo(+b.dataset.span); a.to = today(); RENDER.attendance(); });
  $("#a-from").onchange = e => { a.from = e.target.value || today(); loadAttendance(); };
  $("#a-to").onchange = e => { a.to = e.target.value || today(); loadAttendance(); };
  await loadAttendance();
};
async function loadAttendance() {
  const a = S.att;
  const [r, day, people] = await Promise.all([api(`attendance?view=${a.view}&from=${a.from}&to=${a.to}`), api(`attendance?view=0&from=${today()}&to=${today()}`), api("people")]).catch(() => [null]);
  if (!r || S.page !== "attendance") return;
  const late = day.rows.filter(x => x[6] && x[6] !== "בזמן").length;
  $("#a-kpis").innerHTML = [[day.rows.length, "נוכחים היום"], [Math.max(0, people.length - day.rows.length), "טרם נראו היום"], [late, "איחורים היום"], [people.length, "אנשים רשומים"]]
    .map(([n, t]) => `<div class="kpi"><b>${n}</b><small>${t}</small></div>`).join("");
  if (a.view === 1) {
    const rows = await api(`attendance/rows?from=${a.from}&to=${a.to}`).catch(() => []);
    $("#a-head").innerHTML = "<tr><th>שם</th><th>תאריך</th><th>הגעה</th><th>עזיבה</th><th>משך</th><th></th></tr>";
    $("#a-body").innerHTML = rows.map(x => `<tr data-id="${x.id}"><td><b>${esc(x.name)}</b></td><td>${esc(x.date.split("-").reverse().join("/"))}</td><td>${esc(x.t_in)}</td><td>${esc(x.t_out)}</td><td class="muted">${esc(x.dur)}</td>
      <td style="white-space:nowrap"><button class="ghost small" data-edit="${x.id}">${icon("edit")}</button> <button class="ghost small" data-del="${x.id}">${icon("trash")}</button></td></tr>`).join("")
      || `<tr><td colspan="6">${empty("attendance", "אין רשומות בטווח הזה", "נסה טווח תאריכים רחב יותר.")}</td></tr>`;
    $$("#a-body [data-edit]").forEach(b => b.onclick = async () => { const x = rows.find(r => r.id === +b.dataset.edit); const v = await askRecord(`עריכת רשומה — ${x.name}`, x); if (v) act("attendance/update", { id: x.id, ...v }, "עודכן"); });
    $$("#a-body [data-del]").forEach(b => b.onclick = async () => { if (await confirmBox("למחוק את הרשומה?")) act("attendance/delete", { ids: [+b.dataset.del] }); });
    return;
  }
  $("#a-head").innerHTML = "<tr>" + r.headers.map(h => `<th>${esc(h)}</th>`).join("") + "</tr>";
  $("#a-body").innerHTML = r.rows.map(row => "<tr>" + row.map((c, i) => `<td>${r.headers[i] === "איחור" && c ? `<span class="tag ${c === "בזמן" ? "ok" : ""}">${esc(c)}</span>` : esc(c)}</td>`).join("") + "</tr>").join("")
    || `<tr><td colspan="${r.headers.length}">${empty("attendance", "אין רשומות בטווח הזה", "נסה טווח תאריכים רחב יותר.")}</td></tr>`;
}

// ====================================================================== עוזר
const QUICK = ["סכם לי את היום", "מי נעדר היום?", "מה קורה עכשיו מול המצלמה?", "מי איחר השבוע?", "היו אנשים לא מוכרים לאחרונה?"];
RENDER.assistant = () => {
  $("#page").innerHTML = `<div class="chat"><div class="msgs" id="msgs"></div>
    <div class="quick">${QUICK.map(q => `<button>${q}</button>`).join("")}</div>
    <div class="ask"><input type="text" id="ask" placeholder="שאל כל שאלה בעברית — על הנוכחות, על האנשים, על מה שהמצלמה רואה…"><button class="btn primary" id="ask-btn">${icon("send")}שלח</button></div>
    <p class="hint" style="text-align:center">השאלות, נתוני היומן ותמונת המצלמה (כשהיא פועלת) נשלחים ל-Gemini של גוגל.</p></div>`;
  $$(".quick button").forEach(b => b.onclick = () => ask(b.textContent));
  $("#ask-btn").onclick = () => ask($("#ask").value);
  $("#ask").onkeydown = e => { if (e.key === "Enter") ask($("#ask").value); };
  drawChat(); $("#ask").focus();
};
function drawChat() {
  const m = $("#msgs"); if (!m) return;
  m.innerHTML = (S.chat.length ? S.chat.map(c => `<div class="msg ${c.err ? "err" : c.me ? "me" : "bot"}">${esc(c.text)}</div>`).join("")
    : empty("assistant", "שאל אותי כל דבר", "אני רואה את יומן הנוכחות, את רשימת האנשים, את הלא-מוכרים ואת מה שהמצלמה מצלמת.", 'style="margin:auto;max-width:420px"'))
    + (S.chatBusy ? `<div class="msg bot typing"><i></i><i></i><i></i></div>` : "");
  m.scrollTop = m.scrollHeight;
}
async function ask(q) {
  q = (q || "").trim(); if (!q || S.chatBusy) return;
  const history = S.chat.filter(c => !c.err);
  S.chat.push({ me: true, text: q }); S.chatBusy = true; if ($("#ask")) $("#ask").value = ""; drawChat();
  try { const r = await api("assistant", { q, history }); S.chat.push({ text: r.answer }); }
  catch (e) { S.chat.push({ err: true, text: "לא התקבלה תשובה: " + e.message }); }
  S.chatBusy = false; drawChat();
}

// ====================================================================== הגדרות
RENDER.settings = () => {
  const s = S.settings;
  const sw = (k, t, d = "") => `<div class="opt"><div><b>${t}</b><small>${d}</small></div><label class="switch"><input type="checkbox" data-k="${k}" ${s[k] ? "checked" : ""}><i></i></label></div>`;
  const num = (k, t, d, min, max, step = 1) => `<div class="opt"><div><b>${t}</b><small>${d}</small></div><input type="number" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${s[k]}"></div>`;
  $("#page").innerHTML = `<div class="settings">
    <div class="card"><h3>זיהוי</h3>
      <div class="opt"><div><b>רמת הקפדה בזיהוי: <span id="thr-v">${Math.round(s.threshold * 100)}</span></b><small>נמוך = מזהה בקלות אך עלול לטעות · גבוה = מזהה רק כשבטוח. ברירת המחדל (40) מתאימה לרוב.</small>
        <input type="range" min="25" max="60" value="${Math.round(s.threshold * 100)}" id="thr"></div></div>
      ${sw("auto_learn", "למידה אוטומטית", "הזיהוי משתפר לבד כשאדם מוכר נראה קצת אחרת")}
      ${sw("antispoof", "הגנה מזיוף", "תמונה או מסך מול המצלמה")}
      ${sw("show_age", "הצג גיל ומין", "גיל מדויק למי שהוזן לו תאריך לידה, הערכה לשאר")}
      ${sw("show_emotion", "הצג הבעת פנים")}
      ${num("min_face", "גודל פנים מינימלי", "בפיקסלים, לזיהוי חי", 30, 300)}</div>
    <div class="card"><h3>מצלמה והתרעות</h3>
      ${num("camera", "מספר מצלמה", "0 = המובנית", 0, 9)}
      ${sw("mirror", "תצוגת מראה", "כמו בסלפי")}
      ${sw("alert_unknown", "שמור והתרע על אדם לא מוכר")}
      ${sw("alert_sound", "צליל בהתרעה")}
      ${num("video_step", "סריקת וידאו: דגימה כל כמה שניות", "", 0.2, 10, 0.1)}
      ${num("girl_age", "בדיקת סרטון: ילדה נחשבת קטנה עד גיל", "לפי הערכת Gemini", 2, 18)}</div>
    <div class="card"><h3>נוכחות</h3>
      ${sw("attendance", "רשום יומן נוכחות")}
      ${num("attendance_gap_min", "דקות היעדרות שפותחות כניסה חדשה", "", 1, 240)}
      <div class="opt"><div><b>שעת התחלה לחישוב איחורים</b><small>השאר ריק כדי לא לחשב איחורים</small></div><input type="time" data-k="work_start" value="${esc(s.work_start)}"></div></div>
    <div class="card ai-card"><h3>${icon("assistant")} בינה מלאכותית (Gemini)</h3>
      ${sw("ai_enabled", "הפעל AI", "זה החלק היחיד ששולח תמונות מהמצלמה ונתוני יומן לענן של גוגל. כבוי = הכול מקומי.")}
      ${num("ai_interval", "תיאור אוטומטי של המצלמה כל כמה שניות", "", 10, 600)}
      <div class="opt"><div><b>מפתחות API</b><small id="keys-n">${S.boot.info.keys} מפתחות פעילים — מתחלפים לבד כשנגמרת מכסה</small></div><button class="btn small" id="keys-btn">${icon("key")}ערוך</button></div></div>
    </div>`;
  const save = async obj => { const r = await act("settings", obj); if (r) { S.settings = r.settings; S.boot.info = r.info; setChips(); } };
  $$("[data-k]").forEach(el => el.onchange = () => save({ [el.dataset.k]: el.type === "checkbox" ? el.checked : el.value }));
  $("#thr").oninput = e => $("#thr-v").textContent = e.target.value;
  $("#thr").onchange = e => save({ threshold: e.target.value / 100 });
  $("#keys-btn").onclick = async () => {
    const cur = await api("keys").catch(() => ({ keys: "" }));
    const v = await modal(`<h3>מפתחות Gemini</h3><p class="hint">מפתח API אחד בכל שורה (מ-Google AI Studio, חינם). אפשר כמה — התוכנה מתחלפת ביניהם.</p>
      <textarea id="m-keys">${esc(cur.keys)}</textarea><div class="actions"><button class="btn primary" data-ok>שמור</button><button class="btn" data-cancel>ביטול</button></div>`,
      (o, close) => { $("[data-ok]", o).onclick = () => close($("#m-keys", o).value); });
    if (v != null) { const r = await act("keys", { keys: v }, "המפתחות נשמרו"); if (r) { S.boot.info = r.info; setChips(); RENDER.settings(); } }
  };
};

// ====================================================================== נתונים ועדכונים
const MB = b => (b / 1048576).toFixed(1) + " MB";
RENDER.data = async () => {
  $("#page").innerHTML = `<div class="settings" id="data-grid"></div>`;
  const st = await api("stats").catch(() => null); if (!st || S.page !== "data") return;
  const u = S.poll?.update || { version: S.boot.version };
  const since = st.first_attendance ? new Date(st.first_attendance * 1000).toLocaleDateString("he-IL") : "—";
  $("#data-grid").innerHTML = `
    <div class="card" id="upd-card"></div>
    <div class="card"><h3>${icon("data")} מה יש במאגר</h3>
      <div class="kpis" style="grid-template-columns:repeat(3,1fr)">
        <div class="kpi"><b>${st.persons}</b><small>אנשים · ${st.samples} דגימות</small></div>
        <div class="kpi"><b>${st.attendance}</b><small>רשומות נוכחות מאז ${since}</small></div>
        <div class="kpi"><b>${st.photos.toLocaleString()}</b><small>תמונות · ${st.faces.toLocaleString()} פנים</small></div>
        <div class="kpi"><b>${st.unknown}</b><small>לא-מוכרים (${MB(st.unknown_dir_bytes)})</small></div>
        <div class="kpi"><b>${st.ai_notes}</b><small>הערות AI</small></div>
        <div class="kpi"><b>${MB(st.db_bytes)}</b><small>גודל מסד הנתונים</small></div></div>
      <p class="path">${esc(st.data_dir)}</p></div>
    <div class="card"><h3>גיבוי ושחזור</h3>
      <p class="hint" style="margin-bottom:12px">הגיבוי כולל את כל האנשים, הנוכחות, אינדקס התמונות, הלא-מוכרים, ההגדרות והמפתחות — קובץ ZIP אחד שאפשר להעביר למחשב אחר.</p>
      <div class="row"><button class="btn primary" id="bk">${icon("download")}גבה עכשיו</button><button class="btn" id="rs">${icon("upload")}שחזר מגיבוי…</button></div>
      <p class="hint" style="margin-top:10px">לפני שחזור נשמר עותק ביטחון של המצב הנוכחי בתיקיית הנתונים.</p></div>
    <div class="card"><h3>ניקוי</h3>
      <div class="opt"><div><b>לא-מוכרים ישנים</b><small>מחיקת צילומים של לא-מוכרים שנקלטו לפני יותר מ-X ימים</small></div><input type="number" id="pg-days" value="30" min="1" max="3650"><button class="btn small" id="pg">מחק</button></div>
      <div class="opt"><div><b>יומן נוכחות בטווח</b><small>מחיקת רשומות בין שני תאריכים</small></div><input type="date" id="ca-from" value="${daysAgo(30)}"><input type="date" id="ca-to" value="${today()}"><button class="btn small danger" id="ca">מחק</button></div>
      <div class="opt"><div><b>הערות AI</b><small>כל התיאורים שה-AI רשם מהמצלמה</small></div><button class="btn small" id="cn">מחק הכל</button></div>
      <div class="opt"><div><b>אינדקס התמונות</b><small>שכחת כל התמונות שנסרקו (הקבצים עצמם לא נמחקים). אפשר גם תיקייה בודדת למטה.</small></div><button class="btn small danger" id="cp">נקה אינדקס</button></div>
      <div id="folders" style="margin-top:8px">${st.folders.map(f => `<div class="row folder-row"><span class="grow">${esc(f.folder)}</span><span class="muted">${f.count}</span><button class="ghost small" data-forget="${esc(f.folder)}">שכח</button></div>`).join("")}</div></div>
    <div class="card danger-zone"><h3>אזור מסוכן</h3>
      <div class="opt"><div><b>מחיקת כל יומן הנוכחות</b></div><button class="btn small danger" id="c-att">מחק</button></div>
      <div class="opt"><div><b>מחיקת כל הלא-מוכרים</b></div><button class="btn small danger" id="c-unk">מחק</button></div>
      <div class="opt"><div><b>איפוס מלא</b><small>מוחק את כל האנשים, הדגימות, הנוכחות, התמונות והלא-מוכרים. ההגדרות והמפתחות נשארים. כדאי לגבות קודם.</small></div><button class="btn small danger" id="c-all">אפס הכל</button></div></div>`;
  drawUpdate();
  $("#bk").onclick = () => act("backup", {}, r => `הגיבוי נשמר (${MB(r.bytes)})`);
  $("#rs").onclick = async () => { if (await confirmBox("השחזור יחליף את כל הנתונים הנוכחיים בנתונים שבגיבוי. להמשיך?", "שחזר")) { const r = await act("restore", {}, "השחזור הושלם"); if (r?.restored) RENDER.data(); } };
  $("#pg").onclick = async () => { const d = +$("#pg-days").value; if (await confirmBox(`למחוק לא-מוכרים ישנים מ-${d} ימים?`)) { await act("unknown/purge", { days: d }, r => `נמחקו ${r.removed}`); RENDER.data(); } };
  $("#ca").onclick = async () => { if (await confirmBox("למחוק את רשומות הנוכחות בטווח הזה?")) { await act("clear", { kind: "attendance", from: $("#ca-from").value, to: $("#ca-to").value }, "נמחק"); RENDER.data(); } };
  $("#cn").onclick = async () => { if (await confirmBox("למחוק את כל הערות ה-AI?")) { await act("clear", { kind: "ai_notes" }, "נמחק"); RENDER.data(); } };
  $("#cp").onclick = async () => { if (await confirmBox("לנקות את כל אינדקס התמונות? (הקבצים לא נמחקים)")) { await act("clear", { kind: "photos" }, "נוקה"); RENDER.data(); } };
  $$("[data-forget]").forEach(b => b.onclick = async () => { if (await confirmBox("לשכוח את התיקייה הזו מהאינדקס?", "שכח")) { await act("photos/forget", { folder: b.dataset.forget }, r => `הוסרו ${r.removed} תמונות מהאינדקס`); RENDER.data(); } });
  $("#c-att").onclick = async () => { if (await confirmBox("למחוק את כל יומן הנוכחות? אי אפשר לבטל.")) { await act("clear", { kind: "attendance" }, "נמחק"); RENDER.data(); } };
  $("#c-unk").onclick = async () => { if (await confirmBox("למחוק את כל הלא-מוכרים?")) { await act("clear", { kind: "unknown" }, "נמחק"); RENDER.data(); } };
  $("#c-all").onclick = async () => { if (await confirmBox("איפוס מלא — כל האנשים והנתונים יימחקו. בטוח?", "אפס הכל") && await confirmBox("בטוח-בטוח? זו הפעם האחרונה לשאול.", "כן, אפס")) { await act("clear", { kind: "all" }, "המאגר אופס"); RENDER.data(); } };
};
function drawUpdate() {
  const c = $("#upd-card"); if (!c) return;
  const u = S.poll?.update || { version: S.boot.version, downloading: -1 };
  const av = u.available;
  c.innerHTML = `<h3>עדכון תוכנה <small>גרסה ${esc(u.version)}${u.frozen ? "" : " · מריץ מהקוד"}</small></h3>
    ${av ? `<div class="note good" style="margin:0 0 12px"><b>גרסה ${esc(av.version)} זמינה</b><br><span class="muted" style="white-space:pre-line">${esc(av.notes.slice(0, 600))}</span></div>` : `<p class="hint" style="margin-bottom:12px">${u.checked ? "אתה בגרסה העדכנית ביותר." : "עדיין לא נבדק."}</p>`}
    ${u.downloading >= 0 ? `<div class="bar" style="margin-bottom:8px"><i style="width:${u.downloading}%"></i></div><p class="muted">מוריד… ${u.downloading}% — התוכנה תיסגר ותיפתח מחדש לבד.</p>` :
      `<div class="row">${av ? `<button class="btn primary" id="upd-go">${icon("download")}עדכן עכשיו</button>` : ""}<button class="btn" id="upd-chk">בדוק עכשיו</button></div>`}
    ${u.error ? `<p style="color:var(--bad);font-size:13px;margin-top:8px">${esc(u.error)}</p>` : ""}
    <p class="hint" style="margin-top:10px">התוכנה בודקת לבד כל חצי שעה. ${av && !u.frozen ? "מריצים מהקוד — כאן מעדכנים עם git pull." : ""}</p>`;
  $("#upd-chk") && ($("#upd-chk").onclick = async () => { $("#upd-chk").disabled = true; const r = await act("update/check"); if (r && !r.available) toast("אין עדכון חדש", "ok"); });
  $("#upd-go") && ($("#upd-go").onclick = () => act("update/install"));
}

// ====================================================================== לולאת עדכון
async function pollLoop() {
  while (true) {
    try {
      const p = await api("poll?ev=" + S.lastEv);
      const prev = S.rev; S.poll = p; S.camera = p.camera; S.rev = p.rev;
      if (p.engine && !S.boot.info.engine) { S.boot.info = (await api("boot")).info; setChips(); }
      if (p.events.length) { S.events.push(...p.events); S.events = S.events.slice(-60); S.lastEv = p.events.at(-1).id; drawFeed(); }
      if (p.enroll.done) {
        if (p.enroll.done.ok && $(".stage")) { const st = document.createElement("div"); st.className = "stamp"; st.textContent = "נרשם"; $(".stage").append(st); setTimeout(() => st.remove(), 2600); }
        toast(p.enroll.done.text, p.enroll.done.ok ? "ok" : "bad"); act("enroll/ack"); }
      const ch = k => prev[k] !== undefined && prev[k] !== p.rev[k];
      if (S.page === "live") liveSync();
      if (S.page === "people") { if (ch("people")) loadPeople(); if (ch("unknown")) loadUnknown(); }
      if (S.page === "photos") { photosSync(); if (ch("photos") || ch("people")) loadPhotos(); }
      if (S.page === "video") { videoSync(); if (ch("video")) loadVideo(); }
      if (S.page === "attendance" && ch("attendance")) loadAttendance();
      if (S.page === "data" && JSON.stringify(p.update) !== S.updJson) { S.updJson = JSON.stringify(p.update); drawUpdate(); }
      const b = $("#chip-upd"); if (b) { b.hidden = !p.update?.available; if (p.update?.available) b.textContent = `גרסה ${p.update.available.version} זמינה`; }
      const badge = $('#menu [data-page="people"] .badge'); if (badge) badge.remove();
    } catch { /* השרת עסוק — ננסה שוב */ }
    await sleep(700);
  }
}

function setTheme(t) {
  document.documentElement.dataset.theme = t; try { localStorage.setItem("theme", t); } catch { }
  $("#theme-btn").innerHTML = t === "light" ? icon("moon") + "מצב לילה" : icon("sun") + "מצב יום";
}

(async function boot() {
  let t = "dark"; try { t = localStorage.getItem("theme") || "dark"; } catch { }
  setTheme(t); $("#theme-btn").onclick = () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  while (true) {
    const b = await fetch("api/boot").then(r => r.json()).catch(() => null);
    if (b?.ready) { S.boot = b; S.settings = b.settings; break; }
    if (b?.progress) { $("#splash-msg").textContent = b.progress.msg; if (b.progress.pct >= 0) { $(".loader i").style.animation = "none"; $(".loader i").style.width = b.progress.pct + "%"; $(".loader i").style.transform = "none"; } }
    if (b?.load_error) { $("#splash-msg").textContent = "טעינת המודלים נכשלה: " + b.load_error; $(".loader").hidden = true; return; }
    await sleep(600);
  }
  buildMenu(); setChips();
  $("#splash").remove(); $("#app").hidden = false;
  go(location.hash.slice(1) && RENDER[location.hash.slice(1)] ? location.hash.slice(1) : "live");
  window.addEventListener("hashchange", () => { const p = location.hash.slice(1); if (RENDER[p]) go(p); });
  pollLoop(); frameLoop();
})();
