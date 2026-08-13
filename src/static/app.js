"use strict";

const CATEGORICAL_VARS = [
  "--series-1", "--series-2", "--series-3", "--series-4",
  "--series-5", "--series-6", "--series-7", "--series-8",
];
const MAX_HISTORY = 60; // ~60 samples at 1s poll interval = last minute

const el = (id) => document.getElementById(id);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function humanBytes(n) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}
const humanRate = (n) => `${humanBytes(n)}/s`;

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${path} failed (${res.status})`);
  }
  return res.json();
}

// ---------- App state ----------
const state = {
  polling: null,
  history: [],           // [{t, bytesPerSec}]
  protocolColors: new Map(),
  devicesSort: { key: "total_bytes", dir: -1 },
  connectionsSort: { key: "bytes_total", dir: -1 },
  lastDevices: [],
  lastConnections: [],
};

// ---------- Setup / start / stop ----------
async function loadInterfaces() {
  const select = el("iface-select");
  select.innerHTML = "";
  const interfaces = await api("/api/interfaces");
  if (interfaces.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "No interfaces found";
    select.appendChild(opt);
    return;
  }
  for (const iface of interfaces) {
    const opt = document.createElement("option");
    opt.value = iface.name;
    const ip = iface.ipv4[0] || "no IPv4";
    opt.textContent = `${iface.name}  [${iface.is_up ? "UP" : "DOWN"}]  ${ip}`;
    select.appendChild(opt);
  }
}

function showError(msg) {
  const banner = el("error-banner");
  banner.textContent = msg;
  banner.classList.remove("hidden");
}
function clearError() {
  el("error-banner").classList.add("hidden");
}

async function startCapture() {
  clearError();
  const iface = el("iface-select").value;
  if (!iface) return;
  el("start-btn").disabled = true;
  try {
    await api("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ iface }),
    });
    enterDashboard(iface);
  } catch (err) {
    showError(err.message);
  } finally {
    el("start-btn").disabled = false;
  }
}

async function stopCapture() {
  await api("/api/stop", { method: "POST" });
  exitDashboard();
}

function enterDashboard(iface) {
  state.history = [];
  el("setup").classList.add("hidden");
  el("dashboard").classList.remove("hidden");
  el("stop-btn").classList.remove("hidden");
  el("status-dot").classList.add("on");
  el("status-text").textContent = `Capturing on ${iface}`;
  startPolling();
}

function exitDashboard() {
  stopPolling();
  el("dashboard").classList.add("hidden");
  el("setup").classList.remove("hidden");
  el("stop-btn").classList.add("hidden");
  el("status-dot").classList.remove("on");
  el("status-text").textContent = "Stopped";
  loadInterfaces();
}

// ---------- Polling ----------
function startPolling() {
  stopPolling();
  poll();
  state.polling = setInterval(poll, 1000);
}
function stopPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = null;
}

async function poll() {
  let data;
  try {
    data = await api("/api/stats");
  } catch (err) {
    // Capture likely died (e.g. interface went down) — fall back to setup.
    exitDashboard();
    showError(err.message);
    return;
  }
  renderTiles(data.throughput);
  pushHistory(data.throughput.bytes_per_sec);
  renderChart();
  renderProtocols(data.protocols);
  state.lastDevices = data.devices;
  state.lastConnections = data.connections;
  renderDevicesTable();
  renderConnectionsTable();
}

// ---------- Tiles ----------
function renderTiles(t) {
  el("tile-throughput").textContent = humanRate(t.bytes_per_sec);
  el("tile-pps").textContent = t.packets_per_sec.toFixed(1);
  el("tile-total").textContent = `${t.total_packets.toLocaleString()} pkts`;
  el("tile-total-sub").textContent = humanBytes(t.total_bytes);
}

// ---------- Throughput chart ----------
function pushHistory(bytesPerSec) {
  state.history.push({ t: Date.now(), v: bytesPerSec });
  if (state.history.length > MAX_HISTORY) state.history.shift();
}

function renderChart() {
  const svg = el("chart");
  const W = 600, H = 180, padTop = 14, padBottom = 14;
  const pts = state.history;
  svg.innerHTML = "";
  if (pts.length < 2) return;

  const maxV = Math.max(...pts.map((p) => p.v), 1);
  const x = (i) => (i / (MAX_HISTORY - 1)) * W;
  const y = (v) => H - padBottom - (v / maxV) * (H - padTop - padBottom);

  const offset = MAX_HISTORY - pts.length;
  const coords = pts.map((p, i) => [x(i + offset), y(p.v)]);

  const ns = "http://www.w3.org/2000/svg";
  const seriesColor = cssVar("--series-1");

  // gridline + max label
  const gridY = y(maxV);
  const grid = document.createElementNS(ns, "line");
  grid.setAttribute("x1", 0); grid.setAttribute("x2", W);
  grid.setAttribute("y1", gridY); grid.setAttribute("y2", gridY);
  grid.setAttribute("stroke", cssVar("--grid"));
  grid.setAttribute("stroke-width", "1");
  svg.appendChild(grid);

  const label = document.createElementNS(ns, "text");
  label.setAttribute("x", 4); label.setAttribute("y", Math.max(gridY - 4, 10));
  label.setAttribute("fill", cssVar("--text-muted"));
  label.setAttribute("font-size", "10");
  label.textContent = humanRate(maxV);
  svg.appendChild(label);

  // baseline
  const baseline = document.createElementNS(ns, "line");
  baseline.setAttribute("x1", 0); baseline.setAttribute("x2", W);
  baseline.setAttribute("y1", H - padBottom); baseline.setAttribute("y2", H - padBottom);
  baseline.setAttribute("stroke", cssVar("--baseline"));
  baseline.setAttribute("stroke-width", "1");
  svg.appendChild(baseline);

  // area fill
  const areaD =
    `M ${coords[0][0]} ${H - padBottom} ` +
    coords.map(([cx, cy]) => `L ${cx} ${cy}`).join(" ") +
    ` L ${coords[coords.length - 1][0]} ${H - padBottom} Z`;
  const area = document.createElementNS(ns, "path");
  area.setAttribute("d", areaD);
  area.setAttribute("fill", seriesColor);
  area.setAttribute("opacity", "0.10");
  svg.appendChild(area);

  // line
  const lineD = coords.map(([cx, cy], i) => `${i === 0 ? "M" : "L"} ${cx} ${cy}`).join(" ");
  const line = document.createElementNS(ns, "path");
  line.setAttribute("d", lineD);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", seriesColor);
  line.setAttribute("stroke-width", "2");
  line.setAttribute("stroke-linejoin", "round");
  line.setAttribute("stroke-linecap", "round");
  svg.appendChild(line);

  // end marker
  const [lx, ly] = coords[coords.length - 1];
  const dot = document.createElementNS(ns, "circle");
  dot.setAttribute("cx", lx); dot.setAttribute("cy", ly);
  dot.setAttribute("r", 4);
  dot.setAttribute("fill", seriesColor);
  dot.setAttribute("stroke", cssVar("--surface-1"));
  dot.setAttribute("stroke-width", "2");
  svg.appendChild(dot);

  // interaction layer (crosshair + tooltip)
  setupCrosshair(svg, coords, pts, seriesColor, H, padBottom);
}

function setupCrosshair(svg, coords, pts, seriesColor, H, padBottom) {
  const ns = "http://www.w3.org/2000/svg";
  const guide = document.createElementNS(ns, "line");
  guide.setAttribute("y1", 0); guide.setAttribute("y2", H);
  guide.setAttribute("stroke", cssVar("--baseline"));
  guide.setAttribute("stroke-width", "1");
  guide.setAttribute("visibility", "hidden");
  svg.appendChild(guide);

  const marker = document.createElementNS(ns, "circle");
  marker.setAttribute("r", 4);
  marker.setAttribute("fill", seriesColor);
  marker.setAttribute("stroke", cssVar("--surface-1"));
  marker.setAttribute("stroke-width", "2");
  marker.setAttribute("visibility", "hidden");
  svg.appendChild(marker);

  const hit = document.createElementNS(ns, "rect");
  hit.setAttribute("x", 0); hit.setAttribute("y", 0);
  hit.setAttribute("width", 600); hit.setAttribute("height", H);
  hit.setAttribute("fill", "transparent");
  svg.appendChild(hit);

  const tooltip = el("chart-tooltip");

  hit.addEventListener("mousemove", (evt) => {
    const rect = svg.getBoundingClientRect();
    const relX = ((evt.clientX - rect.left) / rect.width) * 600;
    let nearest = 0, best = Infinity;
    coords.forEach(([cx], i) => {
      const d = Math.abs(cx - relX);
      if (d < best) { best = d; nearest = i; }
    });
    const [cx, cy] = coords[nearest];
    guide.setAttribute("x1", cx); guide.setAttribute("x2", cx);
    guide.setAttribute("visibility", "visible");
    marker.setAttribute("cx", cx); marker.setAttribute("cy", cy);
    marker.setAttribute("visibility", "visible");

    const p = pts[nearest];
    const secsAgo = Math.round((Date.now() - p.t) / 1000);
    tooltip.textContent = `${humanRate(p.v)} · ${secsAgo === 0 ? "now" : secsAgo + "s ago"}`;
    const pxX = rect.left + (cx / 600) * rect.width;
    const pxY = rect.top + cy;
    tooltip.style.left = `${pxX - rect.left}px`;
    tooltip.style.top = `${pxY - rect.top}px`;
    tooltip.classList.add("visible");
  });
  hit.addEventListener("mouseleave", () => {
    guide.setAttribute("visibility", "hidden");
    marker.setAttribute("visibility", "hidden");
    tooltip.classList.remove("visible");
  });
}

// ---------- Protocol breakdown ----------
function colorForProtocol(name) {
  if (state.protocolColors.has(name)) return state.protocolColors.get(name);
  const idx = state.protocolColors.size;
  const varName = idx < CATEGORICAL_VARS.length ? CATEGORICAL_VARS[idx] : "--series-other";
  const color = cssVar(varName);
  state.protocolColors.set(name, color);
  return color;
}

function renderProtocols(breakdown) {
  const container = el("protocols");
  const entries = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, c]) => s + c, 0) || 1;
  container.innerHTML = "";
  for (const [name, count] of entries) {
    const pct = (count / total) * 100;
    const row = document.createElement("div");
    row.className = "proto-row";
    row.innerHTML = `
      <div class="name">${name}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${colorForProtocol(name)}"></div></div>
      <div class="value">${count} · ${pct.toFixed(1)}%</div>
    `;
    container.appendChild(row);
  }
}

// ---------- Tables ----------
function sortRows(rows, sort) {
  const copy = [...rows];
  copy.sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key];
    if (typeof av === "string") return av.localeCompare(bv) * sort.dir;
    return (av - bv) * sort.dir;
  });
  return copy;
}

function bindSortHeaders(tableId, sortState, renderFn) {
  const table = el(tableId);
  table.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (sortState.key === key) sortState.dir *= -1;
      else { sortState.key = key; sortState.dir = -1; }
      renderFn();
    });
  });
}

function updateSortIndicators(tableId, sortState) {
  const table = el(tableId);
  table.querySelectorAll("th").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.key === sortState.key);
    th.querySelector(".arrow")?.remove();
    if (th.dataset.key === sortState.key) {
      const arrow = document.createElement("span");
      arrow.className = "arrow";
      arrow.textContent = sortState.dir === 1 ? "▲" : "▼";
      th.appendChild(arrow);
    }
  });
}

function renderDevicesTable() {
  const tbody = document.querySelector("#devices-table tbody");
  const rows = sortRows(state.lastDevices, state.devicesSort);
  tbody.innerHTML = "";
  if (rows.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="5">No traffic yet</td></tr>`;
  }
  for (const d of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${d.ip}</td>
      <td class="num">${humanBytes(d.bytes_sent)}</td>
      <td class="num">${humanBytes(d.bytes_recv)}</td>
      <td class="num">${humanBytes(d.total_bytes)}</td>
      <td class="num">${d.packets}</td>
    `;
    tbody.appendChild(tr);
  }
  updateSortIndicators("devices-table", state.devicesSort);
}

function renderConnectionsTable() {
  const tbody = document.querySelector("#connections-table tbody");
  const rows = sortRows(
    state.lastConnections.map((c) => ({
      ...c,
      src: c.src_port ? `${c.src_ip}:${c.src_port}` : c.src_ip,
      dst: c.dst_port ? `${c.dst_ip}:${c.dst_port}` : c.dst_ip,
    })),
    state.connectionsSort
  );
  tbody.innerHTML = "";
  if (rows.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="5">No connections yet</td></tr>`;
  }
  for (const c of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${c.src}</td>
      <td class="mono">${c.dst}</td>
      <td>${c.protocol}</td>
      <td class="num">${humanBytes(c.bytes_total)}</td>
      <td class="num">${c.packets}</td>
    `;
    tbody.appendChild(tr);
  }
  updateSortIndicators("connections-table", state.connectionsSort);
}

// ---------- Init ----------
async function init() {
  el("start-btn").addEventListener("click", startCapture);
  el("stop-btn").addEventListener("click", stopCapture);
  bindSortHeaders("devices-table", state.devicesSort, renderDevicesTable);
  bindSortHeaders("connections-table", state.connectionsSort, renderConnectionsTable);

  await loadInterfaces();

  const status = await api("/api/status");
  if (status.capturing) {
    enterDashboard(status.iface);
  }
}

init();
