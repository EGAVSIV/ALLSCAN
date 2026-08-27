const SCANNERS_JSON = "data/scanners.json";
const TIMEFRAMES_JSON = "data/timeframes.json";
const LAST_CANDLES_JSON = "data/last-candles.json";

const state = { rawRows: [], scanner: null, scanners: [], lastCandles: {} };
const $ = id => document.getElementById(id);

// ---------------------------------------------------------------------
// Scanner categorization — buckets the scanner library into 5 core
// strategy families (+ a catch-all) so the dashboard reads like a
// real trading desk rather than a flat list of names.
// ---------------------------------------------------------------------
const CATEGORY_DEFS = [
  {
    key: "indicator", label: "Indicator Based", icon: "📊", color: "var(--cat-indicator)",
    desc: "Oscillator & moving-average driven scans",
    keywords: ["RSI","MACD","EMA","SMA","MOVING AVERAGE","BOLLINGER","STOCHASTIC","ADX","CCI","SUPERTREND","INDICATOR","WILLIAMS","MFI","ROC","DMI","VWAP"]
  },
  {
    key: "smart-money", label: "Smart Money Based", icon: "🐋", color: "var(--cat-smart)",
    desc: "Institutional flow, delivery & OI footprints",
    keywords: ["SMART MONEY","FII","DII","DELIVERY","ACCUMULATION","DISTRIBUTION","BULK DEAL","BLOCK DEAL","OPEN INTEREST"," OI ","INSTITUTIONAL","VOLUME"]
  },
  {
    key: "chart-pattern", label: "Chart Pattern Based", icon: "🕯️", color: "var(--cat-pattern)",
    desc: "Candlestick & classical pattern setups",
    keywords: ["PATTERN","BREAKOUT","BREAKDOWN","DOJI","ENGULFING","HAMMER","HEAD AND SHOULDER","TRIANGLE","FLAG","WEDGE","CHANNEL","CUP","CANDLESTICK","MARUBOZU","HARAMI","STAR"]
  },
  {
    key: "price-action", label: "Price Action Based", icon: "🎯", color: "var(--cat-price)",
    desc: "Support, resistance & structure breaks",
    keywords: ["SUPPORT","RESISTANCE","TREND","PRICE ACTION","PIVOT","FIBONACCI","GAP","52 WEEK","52-WEEK","ALL TIME HIGH","ATH","NEW HIGH","NEW LOW"]
  },
  {
    key: "volatility-momentum", label: "Volatility & Momentum", icon: "⚡", color: "var(--cat-vol)",
    desc: "Speed, range expansion & momentum bursts",
    keywords: ["VOLATILITY","ATR","MOMENTUM","RALLY","SURGE","SPIKE","BETA","ACCELERAT"]
  },
  {
    key: "other", label: "Other Scans", icon: "🧩", color: "var(--cat-other)",
    desc: "Everything else in the library",
    keywords: []
  }
];

function categorizeScanner(name) {
  const n = ` ${String(name || "").toUpperCase()} `;
  for (const cat of CATEGORY_DEFS) {
    if (cat.key === "other") continue;
    if (cat.keywords.some(k => n.includes(k))) return cat.key;
  }
  return "other";
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function escapeHTML(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setStatus(message, type = "") {
  const el = $("status");
  el.className = `status ${type}`;
  el.textContent = message;
}

function setConnection(text) {
  const el = $("connectionText");
  if (el) el.textContent = text;
}

async function fetchJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`Missing data file: ${path}`);
  return r.json();
}

function safeFilename(name) {
  return name
    .replace(/\//g, "-")
    .replace(/ /g, "_")
    .replace(/→/g, "to")
    .replace(/–/g, "-");
}

function fillSelect(id, values, selected) {
  const el = $(id);
  el.innerHTML = "";
  values.forEach(v => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    o.selected = v === selected;
    el.appendChild(o);
  });
}

// ---------------------------------------------------------------------
// Live clock (IST) — always visible at the top of the page
// ---------------------------------------------------------------------
function tickClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: true, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dateStr = now.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short", year: "numeric" });
  const t = $("clockTime"), d = $("clockDate");
  if (t) t.textContent = timeStr;
  if (d) d.textContent = dateStr;
}

// ---------------------------------------------------------------------
// Scanner category tiles
// ---------------------------------------------------------------------
function renderTabs() {
  const grouped = {};
  CATEGORY_DEFS.forEach(c => (grouped[c.key] = []));
  state.scanners.forEach(s => grouped[categorizeScanner(s.name)].push(s));

  const box = $("scannerCategories");
  box.innerHTML = CATEGORY_DEFS.map(cat => {
    const items = grouped[cat.key];
    if (!items.length && cat.key === "other") return ""; // hide empty catch-all
    const chips = items.length
      ? items.map(s => `<button class="scanner-tab ${s.name === state.scanner ? "active" : ""}" data-name="${encodeURIComponent(s.name)}" data-cat="${cat.label}" style="--cc:${s.color || cat.color}">${escapeHTML(s.name)}</button>`).join("")
      : `<span class="cat-empty">No scanners in this category yet</span>`;
    return `
      <div class="cat-card" style="--cc:${cat.color}" data-catkey="${cat.key}">
        <div class="cat-head">
          <div class="cat-icon">${cat.icon}</div>
          <div class="cat-info"><h3>${cat.label}</h3><p>${cat.desc}</p></div>
          <div class="cat-count">${items.length}</div>
        </div>
        <div class="cat-chips">${chips}</div>
      </div>`;
  }).join("");

  box.querySelectorAll(".scanner-tab").forEach(b => b.onclick = () => {
    state.scanner = decodeURIComponent(b.dataset.name);
    $("selectedScannerName").textContent = state.scanner;
    $("selectedScannerCat").textContent = `${b.dataset.cat} · ready to execute`;
    renderTabs();
    filterScannerLibrary();
  });

  $("scannerCount").textContent = state.scanners.length;
  $("categoryCount").textContent = CATEGORY_DEFS.filter(c => grouped[c.key].length).length;
  filterScannerLibrary();
}

function filterScannerLibrary() {
  const q = ($("scannerSearch")?.value || "").trim().toUpperCase();
  document.querySelectorAll(".cat-card").forEach(card => {
    let visibleCount = 0;
    card.querySelectorAll(".scanner-tab").forEach(chip => {
      const match = !q || chip.textContent.toUpperCase().includes(q);
      chip.classList.toggle("hidden-chip", !match);
      if (match) visibleCount++;
    });
    card.style.display = (q && visibleCount === 0) ? "none" : "";
  });
}

// ---------------------------------------------------------------------
// Analysis date — auto-select from the latest available candle for the
// selected timeframe, and hard-lock any date beyond it.
// ---------------------------------------------------------------------
function isoToDateValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toISOString().slice(0, 10);
}

function syncAnalysisDate() {
  const tf = $("timeframe").value;
  const iso = state.lastCandles[tf];
  const input = $("analysisDate");
  const hint = $("dateHint");
  const dateVal = isoToDateValue(iso);
  if (dateVal) {
    input.max = dateVal;
    input.value = dateVal;
    if (hint) hint.textContent = `Auto-set to ${tf}'s last candle (${dateVal}) · future dates locked`;
  } else {
    input.removeAttribute("max");
    if (hint) hint.textContent = "Auto-set to the last available candle · future dates locked";
  }
}

// ---------------------------------------------------------------------
// Symbols / candles
// ---------------------------------------------------------------------
async function loadSymbols() {
  const tf = $("timeframe").value.replace(/ /g, "_");
  $("symbol").innerHTML = "<option>Loading…</option>";
  const symbols = await fetchJSON(`data/symbols/${tf}.json`);
  fillSelect("symbol", symbols);
}

async function loadLastCandles() {
  const data = await fetchJSON(LAST_CANDLES_JSON);
  state.lastCandles = data;
  const now = Date.now();
  $("lastCandles").innerHTML = Object.entries(data).map(([tf, v]) => {
    const d = v ? new Date(v) : null;
    const stale = d && (now - d.getTime()) > 1000 * 60 * 60 * 24 * 3; // >3 days old
    return `<div class="candle ${stale ? "stale" : ""}"><b>${escapeHTML(tf)}</b>${d ? d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "NA"}</div>`;
  }).join("");
  syncAnalysisDate();
}

// ---------------------------------------------------------------------
// Results table
// ---------------------------------------------------------------------
function renderTableData(rows) {
  const t = $("resultsTable"), e = $("emptyResults");
  if (!rows || !rows.length) {
    t.querySelector("thead").innerHTML = "";
    t.querySelector("tbody").innerHTML = "";
    e.style.display = "block";
    return;
  }
  e.style.display = "none";
  const cols = Object.keys(rows[0]);
  t.querySelector("thead").innerHTML = `<tr>${cols.map(c => `<th>${escapeHTML(c)}</th>`).join("")}</tr>`;
  t.querySelector("tbody").innerHTML = rows.map(row =>
    `<tr>${cols.map(c => {
      const v = row[c] ?? "";
      if (c === "TV_Link" && String(v).includes("http")) {
        const u = String(v).match(/\((.*?)\)/)?.[1] || v;
        return `<td><a href="${escapeHTML(u)}" target="_blank" rel="noopener">TV</a></td>`;
      }
      return `<td>${escapeHTML(v)}</td>`;
    }).join("")}</tr>`
  ).join("");
}

function setResults(rows) {
  state.rawRows = rows || [];
  renderTableData(state.rawRows);
}

function renderZones(z) {
  const x = Object.entries(z || {});
  $("zoneCard").classList.toggle("hidden", !x.length);
  $("zones").innerHTML = x.map(([n, c]) => `<div class="zone">${escapeHTML(n)}: ${escapeHTML(c)}</div>`).join("");
}

async function runScanner() {
  try {
    setStatus(`Loading ${state.scanner}…`);
    $("runBtn").disabled = true;
    const tf = $("timeframe").value.replace(/ /g, "_");
    const file = safeFilename(state.scanner);
    const result = await fetchJSON(`data/scan/${tf}/${file}.json`);
    $("summary").textContent = `${result.total_matches} matches • ${result.timeframe} • ${result.analysis_date}`;
    setResults(result.results || []);
    renderZones(result.zones || {});
    setStatus(`✓ ${state.scanner} loaded (as of ${result.analysis_date})`, "ok");
  } catch (e) {
    setStatus(`🔴 ${e.message}`, "error");
  } finally {
    $("runBtn").disabled = false;
  }
}

async function runMatrix() {
  try {
    setStatus("Loading scanner matrix…");
    $("matrixBtn").disabled = true;
    const tf = $("timeframe").value.replace(/ /g, "_");
    const symbol = $("symbol").value;
    const r = await fetchJSON(`data/matrix/${tf}/${symbol}.json`);
    $("matrixSummary").textContent = `${r.symbol} • ${r.timeframe} • ${r.analysis_date}`;
    $("matrixTable").querySelector("thead").innerHTML = "<tr><th>Scanner</th><th>Result</th></tr>";
    $("matrixTable").querySelector("tbody").innerHTML = (r.results || []).map(x =>
      `<tr><td>${escapeHTML(x.Scanner)}</td><td class="${x.Result ? "yes" : "no"}">${x.Result ? "🟢 YES" : "🔴 NO"}</td></tr>`
    ).join("");
    setStatus("✓ Scanner matrix loaded", "ok");
  } catch (e) {
    setStatus(`🔴 Matrix error: ${e.message}`, "error");
  } finally {
    $("matrixBtn").disabled = false;
  }
}

function filterTable() {
  const q = $("search").value.trim().toUpperCase();
  const filtered = q
    ? state.rawRows.filter(r => String(r.Symbol || "").toUpperCase().includes(q))
    : state.rawRows;
  renderTableData(filtered);
}

function downloadCSV() {
  if (!state.rawRows.length) return;
  const c = Object.keys(state.rawRows[0]), esc = v => `"${String(v ?? "").replaceAll('"', '""')}"`;
  const csv = [c.join(","), ...state.rawRows.map(r => c.map(k => esc(r[k])).join(","))].join("\n");
  const b = new Blob([csv], { type: "text/csv" });
  const u = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = u;
  a.download = `${state.scanner}_${$("timeframe").value}.csv`.replaceAll(" ", "_");
  a.click();
  URL.revokeObjectURL(u);
}

async function refreshData() {
  try {
    setStatus("Re-checking latest committed scan data…");
    $("refreshBtn").disabled = true;
    await Promise.all([loadSymbols(), loadLastCandles()]);
    setStatus("✓ Refreshed from latest committed data. (New scans run automatically via GitHub Actions.)", "ok");
  } catch (e) {
    setStatus(`🔴 Refresh error: ${e.message}`, "error");
  } finally {
    $("refreshBtn").disabled = false;
  }
}

// ---------------------------------------------------------------------
// Footer ticker — scrolling stock-market discipline quotes
// ---------------------------------------------------------------------
const TICKER_QUOTES = [
  "Discipline beats prediction in every market cycle.",
  "Risk management is the real edge, not the entry price.",
  "Cut losses fast, let winners run longer.",
  "The trend is your friend until the structure breaks.",
  "Patience compounds louder than any single trade.",
  "Plan the trade, trade the plan.",
  "Markets reward process, not emotion.",
  "Preserve capital first, profits follow.",
  "Volume confirms, price proposes.",
  "Every candle tells a story — read it, don't chase it.",
  "raosab.in — scan smart, trade smarter."
];

function renderTicker() {
  const track = $("tickerTrack");
  if (!track) return;
  const line = TICKER_QUOTES.map(q => `<span>${escapeHTML(q)}</span>`).join("");
  track.innerHTML = line + line; // duplicate for seamless loop
}

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------
async function init() {
  $("runBtn").onclick = runScanner;
  $("matrixBtn").onclick = runMatrix;
  $("refreshBtn").onclick = refreshData;
  $("search").oninput = filterTable;
  $("csvBtn").onclick = downloadCSV;
  $("scannerSearch").oninput = filterScannerLibrary;
  $("footYear").textContent = new Date().getFullYear();

  renderTicker();
  tickClock();
  setInterval(tickClock, 1000);

  const dateInput = $("analysisDate");
  dateInput.addEventListener("change", () => {
    if (dateInput.max && dateInput.value > dateInput.max) dateInput.value = dateInput.max;
  });

  try {
    setConnection("LOADING");
    state.scanners = await fetchJSON(SCANNERS_JSON);
    state.scanner = state.scanners[0]?.name || null;
    $("selectedScannerName").textContent = state.scanner || "—";
    renderTabs();

    const tfs = await fetchJSON(TIMEFRAMES_JSON);
    fillSelect("timeframe", tfs, "Daily");
    await Promise.all([loadSymbols(), loadLastCandles()]);

    setConnection("STATIC DATA");
    setStatus("🟢 Loaded from static GitHub-committed scan data", "ok");
    $("timeframe").onchange = () => {
      loadSymbols().then(syncAnalysisDate).catch(e => setStatus(`🔴 ${e.message}`, "error"));
    };
  } catch (e) {
    setConnection("ERROR");
    setStatus(`🔴 Setup error: ${e.message} — has the "Run Scanners" workflow run yet?`, "error");
  }
}

init();
