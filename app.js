/* ═══════════════════════════════════════════════════════════════
   LA 2028 Olympics Schedule Builder — Web App
   ═══════════════════════════════════════════════════════════════ */

const MEDAL_TYPES = new Set(["Final", "Bronze"]);
const NON_LA_ZONES = new Set(["OKC", "New York", "Columbus", "Nashville", "St. Louis", "San José", "San Diego"]);
const PRICE_CATS = ["Cat A","Cat B","Cat C","Cat D","Cat E","Cat F","Cat G","Cat H","Cat I","Cat J"];

let allEvents = [];
let venueCoords = {};

// ── State (persisted in localStorage) ───────────────────────────
let selections = {};   // {code: {category, price, priority}}
let sportTiers = {};   // {sport: tier}
let excludedEvents = new Set();
let lockedEvents = new Set();

// ── UI state ────────────────────────────────────────────────────
let filteredEvents = [];
let optimizedPlan = [];
let selectedRows = new Set(); // indices in filteredEvents for multi-select
let sortCol = null, sortAsc = true;
let lastClickIdx = null;
let mapObj = null;
let mapMarkers = [];

// ═══════════ INIT ═══════════════════════════════════════════════
async function init() {
  const resp = await fetch("data.json");
  allEvents = await resp.json();
  try {
    const vr = await fetch("venue_coords.json");
    venueCoords = await vr.json();
  } catch(e) { venueCoords = {}; }

  loadState();
  initTabs();
  initFilters();
  initBrowseTable();
  initScheduleTab();
  initTiersTab();
  initShoppingTab();
  initMapTab();
  applyFilters();
}

// ═══════════ PERSISTENCE ════════════════════════════════════════
function saveState() {
  localStorage.setItem("la28_selections", JSON.stringify(selections));
  localStorage.setItem("la28_tiers", JSON.stringify(sportTiers));
  localStorage.setItem("la28_excluded", JSON.stringify([...excludedEvents]));
  localStorage.setItem("la28_locked", JSON.stringify([...lockedEvents]));
}
function loadState() {
  try { selections = JSON.parse(localStorage.getItem("la28_selections")) || {}; } catch(e) { selections = {}; }
  try { sportTiers = JSON.parse(localStorage.getItem("la28_tiers")) || {}; } catch(e) { sportTiers = {}; }
  try { excludedEvents = new Set(JSON.parse(localStorage.getItem("la28_excluded")) || []); } catch(e) { excludedEvents = new Set(); }
  try { lockedEvents = new Set(JSON.parse(localStorage.getItem("la28_locked")) || []); } catch(e) { lockedEvents = new Set(); }
}
function saveProfile(name) {
  const profiles = JSON.parse(localStorage.getItem("la28_profiles") || "{}");
  profiles[name] = { selections, sportTiers, excluded: [...excludedEvents], locked: [...lockedEvents] };
  localStorage.setItem("la28_profiles", JSON.stringify(profiles));
}
function loadProfile(name) {
  const profiles = JSON.parse(localStorage.getItem("la28_profiles") || "{}");
  const p = profiles[name];
  if (!p) return false;
  selections = p.selections || {};
  sportTiers = p.sportTiers || {};
  excludedEvents = new Set(p.excluded || []);
  lockedEvents = new Set(p.locked || []);
  saveState();
  return true;
}
function deleteProfile(name) {
  const profiles = JSON.parse(localStorage.getItem("la28_profiles") || "{}");
  delete profiles[name];
  localStorage.setItem("la28_profiles", JSON.stringify(profiles));
}
function listProfiles() {
  return Object.keys(JSON.parse(localStorage.getItem("la28_profiles") || "{}")).sort();
}

// ═══════════ HELPERS ════════════════════════════════════════════
function formatDate(d) {
  if (!d) return "TBD";
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
}
function formatTime(t) {
  if (!t) return "TBD";
  const [h,m] = t.split(":").map(Number);
  const ampm = h < 12 ? "AM" : "PM";
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${h12}:${String(m).padStart(2,"0")} ${ampm}`;
}
function timeToMin(t) {
  if (!t) return null;
  const [h,m] = t.split(":").map(Number);
  return h * 60 + m;
}
function cheapestPrice(ev) {
  const vals = Object.values(ev.prices || {});
  return vals.length ? Math.min(...vals) : Infinity;
}
function getEventByCode(code) {
  return allEvents.find(e => e.session_code === code) || null;
}
function tierColor(tier) {
  const b = Math.max(0.3, 1.0 - (tier - 1) * 0.12);
  return `rgb(${Math.round(74*b)},${Math.round(222*b)},${Math.round(128*b)})`;
}
function escHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ═══════════ TABS ═══════════════════════════════════════════════
function initTabs() {
  document.querySelectorAll(".tab").forEach(t => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      document.getElementById("tab-" + t.dataset.tab).classList.add("active");
      if (t.dataset.tab === "schedule") refreshSchedule();
      if (t.dataset.tab === "tiers") refreshTiers();
      if (t.dataset.tab === "shopping") refreshShopping();
      if (t.dataset.tab === "map") refreshMap();
    });
  });
}

// ═══════════ MULTI-SELECT PICKER ════════════════════════════════
function initMultiSelect(el, values, placeholder, formatter) {
  const btn = el.querySelector(".ms-btn");
  const popup = el.querySelector(".ms-popup");
  let selected = new Set(values);

  function render() {
    const n = selected.size;
    if (n === 0 || n === values.length) btn.textContent = placeholder;
    else if (n <= 2) btn.textContent = [...selected].map(v => formatter ? formatter(v) : v).join(", ");
    else btn.textContent = `${n} selected`;
  }

  function buildPopup() {
    popup.innerHTML = "";
    const actions = document.createElement("div");
    actions.className = "ms-popup-actions";
    const btnAll = document.createElement("button"); btnAll.className="btn btn-sm btn-gray"; btnAll.textContent="All";
    const btnNone = document.createElement("button"); btnNone.className="btn btn-sm btn-gray"; btnNone.textContent="None";
    const btnDone = document.createElement("button"); btnDone.className="btn btn-sm btn-green"; btnDone.textContent="Done";
    btnAll.onclick = () => { selected = new Set(values); buildList(); render(); };
    btnNone.onclick = () => { selected.clear(); buildList(); render(); };
    btnDone.onclick = () => { popup.classList.add("hidden"); applyFilters(); };
    actions.append(btnAll, btnNone, btnDone);
    popup.appendChild(actions);
    const list = document.createElement("div"); list.className = "ms-popup-list";
    popup.appendChild(list);
    buildList();
  }
  function buildList() {
    const list = popup.querySelector(".ms-popup-list");
    list.innerHTML = "";
    values.forEach(v => {
      const lbl = document.createElement("label");
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = selected.has(v);
      cb.onchange = () => { cb.checked ? selected.add(v) : selected.delete(v); render(); };
      lbl.append(cb, document.createTextNode(formatter ? formatter(v) : v));
      list.appendChild(lbl);
    });
  }

  btn.onclick = (e) => {
    e.stopPropagation();
    document.querySelectorAll(".ms-popup").forEach(p => { if(p!==popup) p.classList.add("hidden"); });
    if (popup.classList.contains("hidden")) { buildPopup(); popup.classList.remove("hidden"); }
    else popup.classList.add("hidden");
  };
  document.addEventListener("click", (e) => {
    if (!el.contains(e.target) && !popup.classList.contains("hidden")) {
      popup.classList.add("hidden");
      applyFilters();
    }
  });
  render();
  return { getSelected: () => selected, setSelected: (s) => { selected = new Set(s); render(); } };
}

// ═══════════ FILTERS ════════════════════════════════════════════
let sportMS, dateMS;

function initFilters() {
  const sports = [...new Set(allEvents.map(e=>e.sport).filter(Boolean))].sort();
  sportMS = initMultiSelect(document.getElementById("sport-filter"), sports, "All Sports");

  const dates = [...new Set(allEvents.map(e=>e.date).filter(Boolean))].sort();
  dateMS = initMultiSelect(document.getElementById("date-filter"), dates, "All Dates", formatDate);

  const zoneSelect = document.getElementById("zone-filter");
  zoneSelect.innerHTML = '<option>All</option><option selected>LA Area Only</option>';
  const zones = [...new Set(allEvents.map(e=>e.zone).filter(Boolean))].sort();
  zones.forEach(z => { const o = document.createElement("option"); o.textContent = z; zoneSelect.appendChild(o); });

  const typeSelect = document.getElementById("type-filter");
  typeSelect.innerHTML = '<option>All</option>';
  const types = [...new Set(allEvents.map(e=>e.session_type).filter(Boolean))].sort();
  types.forEach(t => { const o = document.createElement("option"); o.textContent = t; typeSelect.appendChild(o); });

  ["zone-filter","type-filter","medal-filter"].forEach(id =>
    document.getElementById(id).addEventListener("change", applyFilters));
  let filterTimer = null;
  function debouncedFilter() { clearTimeout(filterTimer); filterTimer = setTimeout(applyFilters, 150); }
  document.getElementById("search-filter").addEventListener("input", debouncedFilter);
  document.getElementById("price-filter").addEventListener("input", debouncedFilter);
  document.getElementById("selected-only").addEventListener("change", applyFilters);
}

function applyFilters() {
  const sportSel = sportMS.getSelected();
  const dateSel = dateMS.getSelected();
  const zone = document.getElementById("zone-filter").value;
  const type = document.getElementById("type-filter").value;
  const medal = document.getElementById("medal-filter").value;
  const search = document.getElementById("search-filter").value.toLowerCase().trim();
  const maxPrice = parseFloat(document.getElementById("price-filter").value) || Infinity;
  const selOnly = document.getElementById("selected-only").checked;

  filteredEvents = allEvents.filter(ev => {
    if (sportSel.size > 0 && sportSel.size < new Set(allEvents.map(e=>e.sport)).size && !sportSel.has(ev.sport)) return false;
    if (dateSel.size > 0 && dateSel.size < new Set(allEvents.map(e=>e.date).filter(Boolean)).size && !dateSel.has(ev.date)) return false;
    if (zone === "LA Area Only" && !ev.is_la) return false;
    if (zone !== "All" && zone !== "LA Area Only" && ev.zone !== zone) return false;
    if (type !== "All" && ev.session_type !== type) return false;
    if (medal === "Medal Events" && !MEDAL_TYPES.has(ev.session_type)) return false;
    if (medal === "Non-Medal Events" && MEDAL_TYPES.has(ev.session_type)) return false;
    if (search) {
      const hay = `${ev.sport} ${ev.venue} ${ev.description} ${ev.session_code} ${ev.zone}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    if (maxPrice < Infinity && cheapestPrice(ev) > maxPrice) return false;
    if (selOnly && !selections[ev.session_code]) return false;
    return true;
  });

  if (sortCol) {
    filteredEvents.sort((a,b) => {
      let va = getSortVal(a, sortCol), vb = getSortVal(b, sortCol);
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }

  document.getElementById("event-count").textContent = `${filteredEvents.length} events`;
  renderTable();
}

function getSortVal(ev, col) {
  switch(col) {
    case "selected": return selections[ev.session_code] ? 0 : 1;
    case "sport": return ev.sport;
    case "venue": return ev.venue;
    case "zone": return ev.zone;
    case "date": return ev.date || "";
    case "time": return ev.start_time || "";
    case "type": return ev.session_type;
    case "description": return ev.description;
    case "cheapest": return cheapestPrice(ev);
    case "session_code": return ev.session_code;
  }
  return "";
}

// ═══════════ BROWSE TABLE ═══════════════════════════════════════
function initBrowseTable() {
  document.querySelectorAll("#events-table th").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortCol === col) sortAsc = !sortAsc;
      else { sortCol = col; sortAsc = true; }
      document.querySelectorAll("#events-table th").forEach(h => h.classList.remove("sorted-asc","sorted-desc"));
      th.classList.add(sortAsc ? "sorted-asc" : "sorted-desc");
      applyFilters();
    });
  });

  // Use event delegation for row clicks so re-renders don't break handlers
  document.querySelector("#events-table tbody").addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    const idx = Array.from(tr.parentNode.children).indexOf(tr);
    if (idx >= 0) handleRowClick(idx, e);
  });

  document.getElementById("btn-add-selected").addEventListener("click", addSelectedEvents);
  document.getElementById("btn-save-profile").addEventListener("click", showSaveProfileDialog);
  document.getElementById("btn-load-profile").addEventListener("click", showLoadProfileDialog);
}

function renderTable() {
  const tbody = document.querySelector("#events-table tbody");
  tbody.innerHTML = "";
  filteredEvents.forEach((ev, i) => {
    const tr = document.createElement("tr");
    const isSel = !!selections[ev.session_code];
    if (selectedRows.has(i)) tr.classList.add("row-selected");
    tr.innerHTML = `
      <td style="text-align:center">${isSel ? "✓" : ""}</td>
      <td>${escHtml(ev.sport)}</td>
      <td>${escHtml(ev.venue)}</td>
      <td>${escHtml(ev.zone)}</td>
      <td>${escHtml(formatDate(ev.date))}</td>
      <td>${escHtml(formatTime(ev.start_time))} - ${escHtml(formatTime(ev.end_time))}</td>
      <td>${escHtml(ev.session_type)}</td>
      <td title="${escHtml(ev.description)}">${escHtml(ev.description)}</td>
      <td style="text-align:right">${cheapestPrice(ev) < Infinity ? "$" + cheapestPrice(ev).toFixed(2) : "-"}</td>
      <td>${escHtml(ev.session_code)}</td>`;
    tbody.appendChild(tr);
  });
}

function handleRowClick(idx, e) {
  if (e.shiftKey && lastClickIdx !== null) {
    const lo = Math.min(lastClickIdx, idx), hi = Math.max(lastClickIdx, idx);
    for (let i = lo; i <= hi; i++) selectedRows.add(i);
  } else if (e.ctrlKey || e.metaKey) {
    selectedRows.has(idx) ? selectedRows.delete(idx) : selectedRows.add(idx);
  } else {
    selectedRows.clear();
    selectedRows.add(idx);
  }
  lastClickIdx = idx;
  // Update row highlights without full re-render
  const rows = document.querySelectorAll("#events-table tbody tr");
  rows.forEach((tr, i) => {
    tr.classList.toggle("row-selected", selectedRows.has(i));
  });
}

// ═══════════ ADD EVENTS DIALOG ══════════════════════════════════
function addSelectedEvents() {
  const evts = [...selectedRows].map(i => filteredEvents[i]).filter(Boolean);
  if (evts.length === 0) return;
  if (evts.length === 1) showAddDialog(evts[0]);
  else showBulkAddDialog(evts);
}

function showAddDialog(ev) {
  const m = document.getElementById("modal-content");
  const cats = PRICE_CATS.filter(c => ev.prices[c] !== undefined);
  if (cats.length === 0) { alert("No pricing available for this event."); return; }

  // Check conflicts
  const conflicts = [];
  for (const [code, sel] of Object.entries(selections)) {
    const other = getEventByCode(code);
    if (other && other.date === ev.date && other.start_time && ev.start_time) {
      const s1 = timeToMin(ev.start_time), e1 = timeToMin(ev.end_time);
      const s2 = timeToMin(other.start_time), e2 = timeToMin(other.end_time);
      if (s1 !== null && e1 !== null && s2 !== null && e2 !== null && s1 < e2 && s2 < e1)
        conflicts.push(other);
    }
  }

  let conflictHtml = "";
  if (conflicts.length) {
    conflictHtml = `<div class="conflict-box"><h4>Schedule Conflicts</h4>` +
      conflicts.map(c => `<p>${escHtml(c.session_code)} ${escHtml(c.sport)} ${formatTime(c.start_time)}-${formatTime(c.end_time)}</p>`).join("") +
      `</div>`;
  }

  m.innerHTML = `
    <h2>${escHtml(ev.sport)} — ${escHtml(ev.session_code)}</h2>
    <p style="color:#aaa;font-size:13px">${escHtml(ev.venue)} (${escHtml(ev.zone)})</p>
    <p style="color:#aaa;font-size:13px">${formatDate(ev.date)}  ${formatTime(ev.start_time)} - ${formatTime(ev.end_time)}</p>
    <p style="color:#999;font-size:11px;margin-top:4px">${escHtml(ev.description)}</p>
    ${conflictHtml}
    <h3>Ticket Category</h3>
    <div class="radio-group" id="cat-radios">
      ${cats.map((c,i) => `<label><input type="radio" name="cat" value="${c}" ${i===0?"checked":""}> ${c}: $${ev.prices[c].toFixed(2)}</label>`).join("")}
    </div>
    <h3>Priority</h3>
    <div class="radio-group" id="prio-radios">
      <label><input type="radio" name="prio" value="must"> Must-have</label>
      <label><input type="radio" name="prio" value="want" checked> Want</label>
      <label><input type="radio" name="prio" value="maybe"> If available</label>
    </div>
    <div style="text-align:center;margin-top:12px">
      <button class="btn btn-blue" id="btn-confirm-add" style="padding:8px 28px;font-size:13px">Add to Schedule</button>
    </div>`;
  showModal();
  document.getElementById("btn-confirm-add").onclick = () => {
    const cat = m.querySelector('input[name=cat]:checked').value;
    const prio = m.querySelector('input[name=prio]:checked').value;
    selections[ev.session_code] = { category: cat, price: ev.prices[cat], priority: prio };
    saveState();
    hideModal();
    applyFilters();
  };
}

function showBulkAddDialog(evts) {
  // Group by sport + price structure
  const groups = {};
  evts.forEach(ev => {
    const cats = PRICE_CATS.filter(c => ev.prices[c] !== undefined);
    const key = ev.sport + "|" + cats.join(",");
    if (!groups[key]) groups[key] = { sport: ev.sport, cats, events: [] };
    groups[key].events.push(ev);
  });

  const m = document.getElementById("modal-content");
  let html = `<h2>Bulk Add — ${evts.length} Events</h2>`;
  let gIdx = 0;
  for (const [key, g] of Object.entries(groups)) {
    html += `<div class="bulk-group">
      <h4>${escHtml(g.sport)} (${g.events.length} events)</h4>
      <div class="bulk-events">${g.events.map(e => `${e.session_code} ${formatDate(e.date)} ${formatTime(e.start_time)} ${e.description.slice(0,60)}`).join("<br>")}</div>
      <div class="radio-group">${g.cats.map((c,i) => `<label><input type="radio" name="bcat${gIdx}" value="${c}" ${i===0?"checked":""}> ${c}: $${g.events[0].prices[c].toFixed(2)}</label>`).join("")}</div>
      <div class="radio-group">
        <label><input type="radio" name="bprio${gIdx}" value="must"> Must-have</label>
        <label><input type="radio" name="bprio${gIdx}" value="want" checked> Want</label>
        <label><input type="radio" name="bprio${gIdx}" value="maybe"> If available</label>
      </div></div>`;
    gIdx++;
  }
  html += `<div style="text-align:center;margin-top:12px"><button class="btn btn-blue" id="btn-bulk-add" style="padding:8px 28px;font-size:13px">Add All ${evts.length} Events</button></div>`;
  m.innerHTML = html;
  showModal();
  document.getElementById("btn-bulk-add").onclick = () => {
    let gi = 0;
    for (const [key, g] of Object.entries(groups)) {
      const cat = m.querySelector(`input[name=bcat${gi}]:checked`).value;
      const prio = m.querySelector(`input[name=bprio${gi}]:checked`).value;
      g.events.forEach(ev => {
        selections[ev.session_code] = { category: cat, price: ev.prices[cat], priority: prio };
      });
      gi++;
    }
    saveState();
    hideModal();
    applyFilters();
  };
}

// ═══════════ PROFILE DIALOGS ════════════════════════════════════
function showSaveProfileDialog() {
  const m = document.getElementById("modal-content");
  const existing = listProfiles();
  m.innerHTML = `
    <h2>Save Current Selections</h2>
    <p style="font-size:12px;color:#888">${Object.keys(selections).length} events, ${Object.keys(sportTiers).length} sport tiers</p>
    <div class="modal-field"><label>Profile name</label><input type="text" id="profile-name" placeholder="e.g. Plan A - Swimming Focus"></div>
    ${existing.length ? `<p style="font-size:11px;color:#666;margin-top:4px">Existing: ${existing.join(", ")}</p>` : ""}
    <div style="text-align:center;margin-top:12px"><button class="btn btn-blue" id="btn-do-save">Save</button></div>`;
  showModal();
  document.getElementById("btn-do-save").onclick = () => {
    const name = document.getElementById("profile-name").value.trim();
    if (!name) return;
    saveProfile(name);
    hideModal();
    alert(`Profile "${name}" saved.`);
  };
}

function showLoadProfileDialog() {
  const profiles = listProfiles();
  const m = document.getElementById("modal-content");
  if (!profiles.length) { m.innerHTML = `<h2>No Profiles</h2><p>No saved profiles found.</p>`; showModal(); return; }
  m.innerHTML = `<h2>Load a Saved Profile</h2>` +
    profiles.map(name => `<div class="profile-row">
      <span>${escHtml(name)}</span>
      <div style="display:flex;gap:4px">
        <button class="btn btn-blue btn-sm" data-load="${escHtml(name)}">Load</button>
        <button class="btn btn-red btn-sm" data-del="${escHtml(name)}">Delete</button>
      </div></div>`).join("");
  showModal();
  m.querySelectorAll("[data-load]").forEach(b => {
    b.onclick = () => {
      loadProfile(b.dataset.load);
      hideModal();
      applyFilters();
      refreshSchedule();
      refreshTiers();
      refreshShopping();
    };
  });
  m.querySelectorAll("[data-del]").forEach(b => {
    b.onclick = () => { if (confirm(`Delete profile "${b.dataset.del}"?`)) { deleteProfile(b.dataset.del); showLoadProfileDialog(); } };
  });
}

function showModal() { document.getElementById("modal-overlay").classList.remove("hidden"); }
function hideModal() { document.getElementById("modal-overlay").classList.add("hidden"); }

document.getElementById("modal-overlay").addEventListener("click", e => {
  if (e.target === document.getElementById("modal-overlay")) hideModal();
});

// ═══════════ SCHEDULE TAB ═══════════════════════════════════════
function initScheduleTab() {
  document.getElementById("btn-refresh-schedule").addEventListener("click", refreshSchedule);
}

function refreshSchedule() {
  const area = document.getElementById("schedule-scroll");
  const budget = parseFloat(document.getElementById("budget-input").value) || 5000;

  if (!Object.keys(selections).length) {
    area.innerHTML = `<p style="padding:30px;text-align:center;color:#888">No events selected yet. Browse events and add them to your schedule.</p>`;
    document.getElementById("budget-label").textContent = "";
    return;
  }

  // Group by date
  const byDate = {};
  let total = 0, mustTotal = 0;
  for (const [code, sel] of Object.entries(selections)) {
    const ev = getEventByCode(code);
    if (!ev) continue;
    const key = ev.date || "TBD";
    if (!byDate[key]) byDate[key] = [];
    byDate[key].push({ ev, sel, code });
    total += sel.price * 2;
    if (sel.priority === "must") mustTotal += sel.price * 2;
  }

  const lbl = document.getElementById("budget-label");
  lbl.textContent = `Total: $${total.toFixed(2)}  |  Must-haves: $${mustTotal.toFixed(2)}  |  Budget: $${budget.toFixed(2)}`;
  lbl.style.color = total <= budget ? "#4ade80" : "#f87171";

  // Sort dates
  const sortedDates = Object.keys(byDate).sort();
  let html = "";
  for (const date of sortedDates) {
    const items = byDate[date].sort((a,b) => (a.ev.start_time||"").localeCompare(b.ev.start_time||""));
    const dayTotal = items.reduce((s,i) => s + i.sel.price * 2, 0);
    html += `<div class="day-header">${formatDate(date)}  (${items.length} events, $${dayTotal.toFixed(2)})</div>`;
    for (const item of items) {
      const { ev, sel, code } = item;
      // Check conflicts
      const hasConflict = items.some(other => {
        if (other.code === code) return false;
        const s1 = timeToMin(ev.start_time), e1 = timeToMin(ev.end_time);
        const s2 = timeToMin(other.ev.start_time), e2 = timeToMin(other.ev.end_time);
        return s1 !== null && e1 !== null && s2 !== null && e2 !== null && s1 < e2 && s2 < e1;
      });
      const cls = hasConflict ? "conflict" : sel.priority === "must" ? "must" : "default";
      const prioLabel = sel.priority === "must" ? "[MUST]" : sel.priority === "want" ? "[WANT]" : "[MAYBE]";
      const prioClass = "priority-" + sel.priority;
      html += `<div class="sched-row ${cls}">
        <div class="sched-left">
          <span class="priority ${prioClass}">${prioLabel}</span>
          ${formatTime(ev.start_time)} - ${formatTime(ev.end_time)} | ${escHtml(ev.sport)} | ${escHtml(ev.venue)}
          ${hasConflict ? '<span style="color:#ff6b6b;font-weight:700"> CONFLICT</span>' : ''}
        </div>
        <div class="sched-right">
          ${sel.category}: $${sel.price.toFixed(2)}
          <button class="sched-remove" data-code="${ev.session_code}">&times;</button>
        </div>
      </div>`;
    }
  }
  area.innerHTML = html;
  area.querySelectorAll(".sched-remove").forEach(b => {
    b.onclick = () => { delete selections[b.dataset.code]; lockedEvents.delete(b.dataset.code); saveState(); refreshSchedule(); applyFilters(); };
  });
}

// ═══════════ TIERS TAB ══════════════════════════════════════════
function initTiersTab() {
  document.getElementById("btn-save-tiers").addEventListener("click", () => { saveState(); refreshShopping(); });
}

function refreshTiers() {
  const area = document.getElementById("tiers-scroll");
  const sports = [...new Set(Object.keys(selections).map(c => getEventByCode(c)?.sport).filter(Boolean))].sort();
  if (!sports.length) { area.innerHTML = `<p style="padding:30px;color:#888">Select some events first, then come back to rank your sports.</p>`; return; }

  // Assign default tiers if missing
  sports.forEach((s, i) => { if (!sportTiers[s]) sportTiers[s] = i + 1; });

  // Group by tier
  const maxTier = Math.max(...sports.map(s => sportTiers[s] || 1));
  const byTier = {};
  sports.forEach(s => {
    const t = sportTiers[s] || 1;
    if (!byTier[t]) byTier[t] = [];
    byTier[t].push(s);
  });

  let html = "";
  for (let t = 1; t <= maxTier + 1; t++) {
    const tierSports = byTier[t] || [];
    if (!tierSports.length && t > maxTier) continue;
    const count = tierSports.reduce((s, sp) => s + Object.keys(selections).filter(c => getEventByCode(c)?.sport === sp).length, 0);
    html += `<div class="tier-frame"><div class="tier-header" style="color:${tierColor(t)}">Tier ${t}</div>`;
    tierSports.forEach(sp => {
      const evCount = Object.keys(selections).filter(c => getEventByCode(c)?.sport === sp).length;
      html += `<div class="tier-sport">
        <span class="tier-sport-name">${escHtml(sp)}  (${evCount} event(s))</span>
        <button class="tier-btn" data-sport="${escHtml(sp)}" data-dir="up">▲</button>
        <button class="tier-btn" data-sport="${escHtml(sp)}" data-dir="down">▼</button>
        <select class="tier-select" data-sport="${escHtml(sp)}">${Array.from({length:maxTier+1},(_,i)=>`<option ${i+1===t?"selected":""}>${i+1}</option>`).join("")}</select>
      </div>`;
    });
    html += `</div>`;
  }
  area.innerHTML = html;

  area.querySelectorAll(".tier-btn").forEach(b => {
    b.onclick = () => {
      const sp = b.dataset.sport, dir = b.dataset.dir;
      const cur = sportTiers[sp] || 1;
      sportTiers[sp] = dir === "up" ? Math.max(1, cur - 1) : cur + 1;
      saveState();
      refreshTiers();
    };
  });
  area.querySelectorAll(".tier-select").forEach(sel => {
    sel.onchange = () => { sportTiers[sel.dataset.sport] = parseInt(sel.value); saveState(); refreshTiers(); };
  });
}

// ═══════════ SHOPPING LIST TAB ══════════════════════════════════
function initShoppingTab() {
  document.getElementById("btn-recalculate").addEventListener("click", refreshShopping);
  document.getElementById("btn-export-csv").addEventListener("click", exportCSV);
  ["opt-max-events","opt-tickets","opt-gap","opt-one-sport","opt-consecutive"].forEach(id =>
    document.getElementById(id).addEventListener("change", refreshShopping));
}

function buildOptimizedPlan() {
  const maxEvents = parseInt(document.getElementById("opt-max-events").value);
  const gapMin = parseInt(document.getElementById("opt-gap").value) * 60;
  const oneSport = document.getElementById("opt-one-sport").checked;
  const consecutive = document.getElementById("opt-consecutive").checked;
  const prioOrder = { must: 0, want: 1, maybe: 2 };

  // Build candidates
  const candidates = [];
  for (const [code, sel] of Object.entries(selections)) {
    if (excludedEvents.has(code)) continue;
    const ev = getEventByCode(code);
    if (!ev || !ev.date || !ev.start_time) continue;
    const tier = sportTiers[ev.sport] || 999;
    const isMedal = MEDAL_TYPES.has(ev.session_type) ? 0 : 1;
    const prio = prioOrder[sel.priority] ?? 1;
    candidates.push({ code, event: ev, selection: sel, tier, isMedal, prio,
      sortKey: [tier, isMedal, prio, sel.price || 9999] });
  }
  candidates.sort((a,b) => compareSortKeys(a.sortKey, b.sortKey));

  function checkGap(e1, e2) {
    if (e1.date !== e2.date) return true;
    if (gapMin === 0) return true;
    const s1 = timeToMin(e1.start_time), e1t = timeToMin(e1.end_time);
    const s2 = timeToMin(e2.start_time), e2t = timeToMin(e2.end_time);
    if ([s1,e1t,s2,e2t].some(v => v === null)) return true;
    return s1 < s2 ? (s2 - e1t) >= gapMin : (s1 - e2t) >= gapMin;
  }

  // Phase 0: Locked events
  const plan = [];
  const usedSports = new Set();
  const planDays = new Set();
  candidates.forEach(c => {
    if (lockedEvents.has(c.code)) {
      plan.push(c);
      if (oneSport) usedSports.add(c.event.sport);
      planDays.add(c.event.date);
    }
  });

  function dayProximity(d) {
    if (!planDays.size) return 0;
    let min = Infinity;
    for (const pd of planDays) {
      const diff = Math.abs((new Date(d) - new Date(pd)) / 86400000);
      if (diff < min) min = diff;
    }
    return min;
  }

  // Phase 1: Best per sport
  const bestPerSport = {};
  candidates.forEach(c => { if (!bestPerSport[c.event.sport]) bestPerSport[c.event.sport] = c; });
  const sportOrder = Object.keys(bestPerSport).sort((a,b) => compareSortKeys(bestPerSport[a].sortKey, bestPerSport[b].sortKey));

  // Phase 2: Greedy
  for (const sport of sportOrder) {
    if (plan.length >= maxEvents) break;
    if (oneSport && usedSports.has(sport)) continue;
    let sportCands = candidates.filter(c => c.event.sport === sport);
    if (consecutive) {
      sportCands.sort((a,b) => {
        const pa = dayProximity(a.event.date), pb = dayProximity(b.event.date);
        if (pa !== pb) return pa - pb;
        return compareSortKeys(a.sortKey, b.sortKey);
      });
    }
    for (const cand of sportCands) {
      if (plan.every(p => checkGap(cand.event, p.event))) {
        plan.push(cand);
        if (oneSport) usedSports.add(sport);
        planDays.add(cand.event.date);
        break;
      }
    }
  }

  plan.sort((a,b) => {
    if (a.tier !== b.tier) return a.tier - b.tier;
    if (a.event.date !== b.event.date) return a.event.date < b.event.date ? -1 : 1;
    return (a.event.start_time || "").localeCompare(b.event.start_time || "");
  });
  return plan;
}

function compareSortKeys(a, b) {
  for (let i = 0; i < a.length; i++) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return 0;
}

function refreshShopping() {
  const area = document.getElementById("shopping-scroll");
  const tix = parseInt(document.getElementById("opt-tickets").value) || 2;

  if (!Object.keys(selections).length) {
    area.innerHTML = `<p style="padding:30px;text-align:center;color:#888">No events selected yet.</p>`;
    return;
  }
  if (!Object.keys(sportTiers).length) {
    area.innerHTML = `<p style="padding:30px;text-align:center;color:#888">Set your sport tiers first in the Sport Tiers tab, then come back.</p>`;
    return;
  }

  optimizedPlan = buildOptimizedPlan();
  if (!optimizedPlan.length) {
    area.innerHTML = `<p style="padding:30px;text-align:center;color:#888">No valid plan could be built. Check your selections and excluded events.</p>`;
    return;
  }

  const total = optimizedPlan.reduce((s,c) => s + c.selection.price * tix, 0);
  const uniqueDays = new Set(optimizedPlan.map(c => c.event.date)).size;
  const lockedCount = optimizedPlan.filter(c => lockedEvents.has(c.code)).length;

  let html = `<div class="plan-summary">
    <h3>Your Plan</h3>
    <div class="total">${optimizedPlan.length} events  |  ${optimizedPlan.length * tix} tickets (${tix}/event)  |  ${uniqueDays} day(s)  |  Total: $${total.toFixed(2)}</div>
    ${lockedCount ? `<div class="status-locked">${lockedCount} locked in</div>` : ""}
    ${excludedEvents.size ? `<div class="status-excluded">${excludedEvents.size} event(s) marked unavailable</div>` : ""}
  </div>`;

  // Plan items
  let running = 0;
  optimizedPlan.forEach((cand, i) => {
    const { event: ev, selection: sel, code, tier, isMedal } = cand;
    const ticketCost = sel.price * tix;
    running += ticketCost;
    const isLocked = lockedEvents.has(code);
    const medalStr = isMedal === 0 ? " (Medal)" : "";
    const bg = isLocked ? "#1a2a2a" : (i % 2 === 0 ? "#1a2a1a" : "#1a1a2e");
    const desc = ev.description || "";

    // Check if sport has medal events in selections
    const sportHasMedals = Object.keys(selections).some(c => {
      if (excludedEvents.has(c)) return false;
      const e = getEventByCode(c);
      return e && e.sport === ev.sport && MEDAL_TYPES.has(e.session_type);
    });

    html += `<div class="plan-item" style="background:${bg}">
      <div class="plan-item-top">
        <span class="plan-item-idx">#${i+1}</span>
        <span class="plan-item-tier" style="color:${tierColor(tier)}">Tier ${tier}</span>
        <span class="plan-item-sport">${escHtml(ev.sport)}${medalStr}</span>
        <span class="plan-item-code">[${escHtml(code)}]</span>
        <span class="plan-item-desc">${desc ? "— " + escHtml(desc) : ""}</span>
        <span class="plan-item-price">${sel.category}: $${sel.price.toFixed(2)} x${tix} = $${ticketCost.toFixed(2)}</span>
      </div>
      <div class="plan-item-bot">
        <span class="plan-item-venue">${escHtml(ev.venue)}  |  ${formatDate(ev.date)}  ${formatTime(ev.start_time)} - ${formatTime(ev.end_time)}</span>
        <div class="plan-item-actions">
          ${sportHasMedals ? `<button class="btn btn-dark-red btn-sm" data-drop-medals="${escHtml(ev.sport)}">Drop Medals</button>` : ""}
          <button class="btn btn-dark-red btn-sm" data-drop-sport="${escHtml(ev.sport)}">Drop Sport</button>
          <button class="btn btn-red btn-sm" data-exclude="${code}">Unavailable / Too Expensive</button>
          <button class="btn ${isLocked ? "btn-green" : "btn-lock"} btn-sm" data-lock="${code}">${isLocked ? "Locked In" : "Lock In"}</button>
        </div>
        <span class="plan-item-running">Running: $${running.toFixed(2)}</span>
      </div>
    </div>`;
  });

  // Calendar
  html += renderCalendar(optimizedPlan, tix);

  // Excluded section
  if (excludedEvents.size) {
    const exclBySport = {};
    for (const code of [...excludedEvents].sort()) {
      const ev = getEventByCode(code);
      if (!ev) continue;
      if (!exclBySport[ev.sport]) exclBySport[ev.sport] = [];
      exclBySport[ev.sport].push({ code, ev });
    }
    html += `<div class="excl-frame"><div class="excl-header">Excluded Events (marked unavailable/too expensive):</div>`;
    for (const sport of Object.keys(exclBySport).sort()) {
      const items = exclBySport[sport];
      html += `<div class="excl-sport-header">
        <span class="excl-sport-name">${escHtml(sport)} (${items.length} excluded)</span>
        <button class="btn btn-gray btn-sm" data-restore-sport="${escHtml(sport)}">Restore Sport</button>
      </div>`;
      items.forEach(({ code, ev }) => {
        html += `<div class="excl-row">
          <span>(${escHtml(code)}) - ${formatDate(ev.date)} ${formatTime(ev.start_time)}  ${escHtml(ev.description || "")}</span>
          <button class="btn btn-gray btn-sm" data-restore="${code}">Restore</button>
        </div>`;
      });
    }
    html += `</div>`;
  }

  area.innerHTML = html;

  // Wire up buttons
  area.querySelectorAll("[data-lock]").forEach(b => {
    b.onclick = () => {
      const c = b.dataset.lock;
      lockedEvents.has(c) ? lockedEvents.delete(c) : lockedEvents.add(c);
      saveState(); refreshShopping();
    };
  });
  area.querySelectorAll("[data-exclude]").forEach(b => {
    b.onclick = () => {
      lockedEvents.delete(b.dataset.exclude);
      excludedEvents.add(b.dataset.exclude);
      saveState(); refreshShopping();
    };
  });
  area.querySelectorAll("[data-drop-sport]").forEach(b => {
    b.onclick = () => {
      const sport = b.dataset.dropSport;
      Object.keys(selections).forEach(c => {
        const ev = getEventByCode(c);
        if (ev && ev.sport === sport) { lockedEvents.delete(c); excludedEvents.add(c); }
      });
      saveState(); refreshShopping();
    };
  });
  area.querySelectorAll("[data-drop-medals]").forEach(b => {
    b.onclick = () => {
      const sport = b.dataset.dropMedals;
      Object.keys(selections).forEach(c => {
        const ev = getEventByCode(c);
        if (ev && ev.sport === sport && MEDAL_TYPES.has(ev.session_type)) { lockedEvents.delete(c); excludedEvents.add(c); }
      });
      saveState(); refreshShopping();
    };
  });
  area.querySelectorAll("[data-restore]").forEach(b => {
    b.onclick = () => { excludedEvents.delete(b.dataset.restore); saveState(); refreshShopping(); };
  });
  area.querySelectorAll("[data-restore-sport]").forEach(b => {
    b.onclick = () => {
      const sport = b.dataset.restoreSport;
      [...excludedEvents].forEach(c => { const ev = getEventByCode(c); if (ev && ev.sport === sport) excludedEvents.delete(c); });
      saveState(); refreshShopping();
    };
  });
}

// ═══════════ CALENDAR ═══════════════════════════════════════════
function renderCalendar(plan) {
  if (!plan.length) return "";

  const planDates = [...new Set(plan.map(c => c.event.date))].sort();
  const first = new Date(planDates[0] + "T00:00:00");
  const last = new Date(planDates[planDates.length-1] + "T00:00:00");
  const allDates = [];
  for (let d = new Date(first); d <= last; d.setDate(d.getDate()+1)) {
    allDates.push(new Date(d).toISOString().slice(0,10));
  }

  const starts = plan.map(c => timeToMin(c.event.start_time)).filter(v => v !== null);
  const ends = plan.map(c => timeToMin(c.event.end_time)).filter(v => v !== null);
  if (!starts.length || !ends.length) return "";

  const earliest = Math.max(0, Math.min(...starts) - 30);
  const latest = Math.min(1440, Math.max(...ends) + 30);
  const timeSpan = latest - earliest;
  if (timeSpan <= 0) return "";

  const ppm = 0.75;
  const headerH = 36;
  const gutterW = 55;
  const numDays = allDates.length;
  const colW = Math.max(140, Math.min(220, Math.floor(900 / numDays)));
  const bodyH = Math.round(timeSpan * ppm);
  const totalW = gutterW + colW * numDays;
  const planDateSet = new Set(planDates);

  const tierClasses = { 1:"tier-1", 2:"tier-2", 3:"tier-3", 4:"tier-4", 5:"tier-5" };

  // Header
  let html = `<div class="calendar-frame"><h3>Your Schedule</h3>
    <div class="calendar-grid" style="width:${totalW}px">
    <div class="cal-header">
      <div class="cal-gutter"></div>
      ${allDates.map(d => {
        const dt = new Date(d + "T00:00:00");
        const has = planDateSet.has(d);
        return `<div class="cal-day-header ${has?"has-event":"no-event"}" style="width:${colW}px">${dt.toLocaleDateString("en-US",{weekday:"short"})}<br>${dt.toLocaleDateString("en-US",{month:"short",day:"numeric"})}</div>`;
      }).join("")}
    </div>
    <div class="cal-body" style="height:${bodyH + headerH}px">
      <div class="cal-time-col">`;

  // Hour labels
  let firstHour = Math.floor(earliest / 60) * 60;
  for (let h = firstHour; h <= latest; h += 60) {
    const y = (h - earliest) * ppm;
    const h12 = (h/60) === 0 ? 12 : (h/60) > 12 ? (h/60) - 12 : (h/60);
    const ampm = (h/60) < 12 ? "AM" : "PM";
    html += `<div class="cal-time-label" style="top:${y}px">${Math.floor(h12)} ${ampm}</div>`;
  }
  html += `</div>`;

  // Day columns with hour lines and events
  const dateIdx = {};
  allDates.forEach((d,i) => dateIdx[d] = i);

  allDates.forEach(d => {
    html += `<div class="cal-day-col" style="width:${colW}px;height:${bodyH}px">`;
    // Hour lines
    for (let h = firstHour; h <= latest; h += 60) {
      const y = (h - earliest) * ppm;
      html += `<div class="cal-hour-line" style="top:${y}px"></div>`;
    }
    // Events on this day
    plan.filter(c => c.event.date === d).forEach(cand => {
      const sm = timeToMin(cand.event.start_time), em = timeToMin(cand.event.end_time);
      if (sm === null || em === null) return;
      let y1 = (sm - earliest) * ppm;
      let y2 = (em - earliest) * ppm;
      if (y2 - y1 < 38) y2 = y1 + 38;
      const tierCls = tierClasses[cand.tier] || "tier-default";
      const isLocked = lockedEvents.has(cand.code);
      const medalStr = cand.isMedal === 0 ? " *" : "";
      const desc = cand.event.description || "";
      html += `<div class="cal-event ${tierCls} ${isLocked?"locked":""}" style="top:${y1}px;height:${y2-y1}px">
        <div class="ev-sport">${escHtml(cand.event.sport)}${medalStr}</div>
        <div class="ev-detail">[${escHtml(cand.code)}] ${formatTime(cand.event.start_time)} - ${formatTime(cand.event.end_time)}</div>
        ${desc ? `<div class="ev-desc">${escHtml(desc)}</div>` : ""}
        ${isLocked ? `<div class="ev-lock">LOCKED</div>` : ""}
      </div>`;
    });
    html += `</div>`;
  });

  html += `</div></div></div>`;
  return html;
}

// ═══════════ CSV EXPORT ═════════════════════════════════════════
function exportCSV() {
  if (!optimizedPlan.length) { alert("No plan to export. Recalculate first."); return; }
  const tix = parseInt(document.getElementById("opt-tickets").value) || 2;
  const rows = [["Order","Tier","Sport","Session Code","Venue","Zone","Date","Start Time","End Time","Description","Type","Category","Price Each",`Price x${tix}`]];
  optimizedPlan.forEach((c, i) => {
    const ev = c.event, sel = c.selection;
    rows.push([i+1, c.tier, ev.sport, c.code, ev.venue, ev.zone,
      ev.date || "TBD", formatTime(ev.start_time), formatTime(ev.end_time),
      ev.description, ev.session_type, sel.category,
      sel.price.toFixed(2), (sel.price * tix).toFixed(2)]);
  });
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "LA2028_shopping_list.csv";
  a.click();
}

// ═══════════ MAP TAB ════════════════════════════════════════════
function initMapTab() {
  document.getElementById("map-selected-only").addEventListener("change", refreshMap);
}

function refreshMap() {
  const container = document.getElementById("map-container");
  const selOnly = document.getElementById("map-selected-only").checked;

  // Gather venues to show
  const venueData = {};
  allEvents.forEach(ev => {
    if (!ev.venue || !ev.is_la) return;
    if (!venueData[ev.venue]) venueData[ev.venue] = { sports: new Set(), selected: 0, total: 0, coords: venueCoords[ev.venue] };
    venueData[ev.venue].sports.add(ev.sport);
    venueData[ev.venue].total++;
    if (selections[ev.session_code]) venueData[ev.venue].selected++;
  });

  if (selOnly) {
    for (const v of Object.keys(venueData)) {
      if (venueData[v].selected === 0) delete venueData[v];
    }
  }

  // Use Leaflet if available, otherwise embed a simple map
  if (!mapObj) {
    // Load Leaflet
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link");
      link.id = "leaflet-css"; link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }
    const loadLeaflet = () => {
      return new Promise(resolve => {
        if (window.L) return resolve();
        const script = document.createElement("script");
        script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
        script.onload = resolve;
        document.head.appendChild(script);
      });
    };
    loadLeaflet().then(() => {
      container.innerHTML = "";
      mapObj = L.map(container).setView([34.0, -118.3], 10);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; OpenStreetMap'
      }).addTo(mapObj);
      setTimeout(() => mapObj.invalidateSize(), 200);
      addMarkers(venueData);
    });
  } else {
    addMarkers(venueData);
  }
}

function addMarkers(venueData) {
  if (!mapObj) return;
  mapMarkers.forEach(m => mapObj.removeLayer(m));
  mapMarkers = [];
  for (const [venue, data] of Object.entries(venueData)) {
    if (!data.coords) continue;
    const [lat, lng] = data.coords;
    const color = data.selected > 0 ? "#4ade80" : "#60a5fa";
    const icon = L.divIcon({
      className: "custom-marker",
      html: `<div style="background:${color};width:12px;height:12px;border-radius:50%;border:2px solid #fff"></div>`,
      iconSize: [16, 16], iconAnchor: [8, 8]
    });
    const marker = L.marker([lat, lng], { icon }).addTo(mapObj);
    const sports = [...data.sports].slice(0, 3).join(", ");
    marker.bindPopup(`<b>${venue}</b><br>${data.total} events (${sports}${data.sports.size > 3 ? "..." : ""})<br>${data.selected} selected`);
    mapMarkers.push(marker);
  }
}

// ═══════════ BOOT ═══════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", init);
