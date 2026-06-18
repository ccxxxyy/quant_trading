/* Quant Trading Dashboard - Frontend Application */

const API = "/api";
let systemInfo = null;
let strategiesMeta = {};
let charts = {};
let lastBacktestResult = null;

const PAGE_META = {
  dashboard: { title: "总览", desc: "系统状态与核心指标一览" },
  data: { title: "数据管理", desc: "获取、存储与预览行情数据" },
  backtest: { title: "回测实验室", desc: "配置策略参数，运行事件驱动回测" },
  strategies: { title: "策略库", desc: "内置策略模板与参数说明" },
  settings: { title: "系统设置", desc: "风控参数与系统配置" },
};

// ── Utilities ──────────────────────────────────────────────

function showLoading(show = true) {
  document.getElementById("loading").classList.toggle("hidden", !show);
}

function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function fmtPct(v, digits = 2) {
  if (v == null || isNaN(v)) return "-";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtNum(v, digits = 2) {
  if (v == null || isNaN(v)) return "-";
  return Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function setMetricColor(el, value) {
  el.classList.remove("positive", "negative");
  if (value > 0) el.classList.add("positive");
  else if (value < 0) el.classList.add("negative");
}

// ── Navigation ─────────────────────────────────────────────

function navigateTo(page) {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === page);
  });
  document.querySelectorAll(".page").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `page-${page}`);
  });
  const meta = PAGE_META[page];
  document.getElementById("page-title").textContent = meta.title;
  document.getElementById("page-desc").textContent = meta.desc;
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => navigateTo(btn.dataset.page));
});

// ── Charts ─────────────────────────────────────────────────

function destroyChart(id) {
  if (charts[id]) {
    charts[id].destroy();
    delete charts[id];
  }
}

function renderEquityChart(canvasId, equityCurve, label = "权益") {
  destroyChart(canvasId);
  const ctx = document.getElementById(canvasId);
  if (!ctx || !equityCurve?.length) return;

  const labels = equityCurve.map((p) => p.timestamp?.slice(0, 10) || "");
  const values = equityCurve.map((p) => p.equity);

  charts[canvasId] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59, 130, 246, 0.08)",
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }],
    },
    options: chartOptions("权益"),
  });
}

function renderPriceChart(bars) {
  destroyChart("price-chart");
  const ctx = document.getElementById("price-chart");
  if (!ctx || !bars?.length) return;

  charts["price-chart"] = new Chart(ctx, {
    type: "line",
    data: {
      labels: bars.map((b) => b.timestamp.slice(0, 10)),
      datasets: [{
        label: "收盘价",
        data: bars.map((b) => b.close),
        borderColor: "#22c55e",
        backgroundColor: "rgba(34, 197, 94, 0.06)",
        fill: true,
        tension: 0.2,
        pointRadius: 0,
        borderWidth: 1.5,
      }],
    },
    options: chartOptions("价格"),
  });
}

function chartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#1a2230",
        borderColor: "#2a3548",
        borderWidth: 1,
        titleFont: { family: "JetBrains Mono" },
        bodyFont: { family: "JetBrains Mono" },
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(42, 53, 72, 0.5)" },
        ticks: { color: "#8b9ab5", maxTicksLimit: 8, font: { size: 10 } },
      },
      y: {
        grid: { color: "rgba(42, 53, 72, 0.5)" },
        ticks: { color: "#8b9ab5", font: { family: "JetBrains Mono", size: 10 } },
        title: { display: true, text: yLabel, color: "#8b9ab5", font: { size: 11 } },
      },
    },
  };
}

// ── Dashboard ──────────────────────────────────────────────

function updateDashboard() {
  if (!systemInfo) return;
  document.getElementById("kpi-instruments").textContent = systemInfo.instrument_count;
  document.getElementById("kpi-strategies").textContent = systemInfo.strategies.length;
  const cap = systemInfo.backtest_defaults.initial_capital;
  document.getElementById("kpi-capital").textContent = cap >= 10000 ? `${fmtNum(cap / 10000, 0)}万` : fmtNum(cap, 0);
  document.getElementById("kpi-exchanges").textContent = systemInfo.exchanges.length;
  document.getElementById("version-badge").textContent = `v${systemInfo.version}`;

  if (lastBacktestResult?.equity_curve) {
    renderEquityChart("dashboard-equity-chart", lastBacktestResult.equity_curve);
  }
}

// ── Data Page ──────────────────────────────────────────────

async function loadInstruments() {
  const data = await api("/data/instruments");
  const list = document.getElementById("instrument-list");
  document.getElementById("instrument-count").textContent = data.count;

  if (!data.instruments.length) {
    list.innerHTML = '<div class="empty-state">暂无数据，请先获取行情</div>';
    return;
  }

  list.innerHTML = data.instruments
    .map((sym) => `<div class="instrument-item" data-symbol="${sym}">${sym}<span>→</span></div>`)
    .join("");

  list.querySelectorAll(".instrument-item").forEach((el) => {
    el.addEventListener("click", () => previewBars(el.dataset.symbol, el));
  });

  previewBars(data.instruments[0]);
}

async function previewBars(symbol, activeEl) {
  document.querySelectorAll(".instrument-item").forEach((el) => el.classList.remove("active"));
  if (activeEl) activeEl.classList.add("active");

  try {
    const data = await api(`/data/bars/${encodeURIComponent(symbol)}?limit=200`);
    renderPriceChart(data.bars);
  } catch {
    renderPriceChart([]);
  }
}

document.getElementById("fetch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  showLoading(true);
  try {
    const result = await api("/data/fetch", {
      method: "POST",
      body: JSON.stringify({
        symbol: fd.get("symbol"),
        start: fd.get("start"),
        end: fd.get("end") || null,
        interval: fd.get("interval"),
        provider: fd.get("provider"),
      }),
    });
    toast(`成功获取 ${result.bar_count} 条 K 线: ${result.symbol}`, "success");
    await loadInstruments();
    await refreshSystemInfo();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

// ── Backtest Page ──────────────────────────────────────────

function renderStrategyParams(strategyId) {
  const container = document.getElementById("strategy-params");
  const meta = strategiesMeta[strategyId];
  if (!meta?.params) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = Object.entries(meta.params)
    .map(([key, spec]) => `
      <div class="form-row">
        <label>${spec.label || key}</label>
        <input type="${spec.type === 'float' ? 'number' : spec.type === 'int' ? 'number' : 'text'}"
               name="param_${key}"
               value="${spec.default ?? ''}"
               step="${spec.type === 'float' ? '0.1' : '1'}" />
      </div>`)
    .join("");
}

function populateStrategySelect() {
  const select = document.getElementById("strategy-select");
  select.innerHTML = Object.entries(strategiesMeta)
    .map(([id, meta]) => `<option value="${id}">${meta.name} (${id})</option>`)
    .join("");

  select.addEventListener("change", () => renderStrategyParams(select.value));
  renderStrategyParams(select.value);
}

function updateMetrics(metrics) {
  const fields = {
    "m-total-return": [fmtPct(metrics.total_return), metrics.total_return],
    "m-annual-return": [fmtPct(metrics.annual_return), metrics.annual_return],
    "m-sharpe": [fmtNum(metrics.sharpe_ratio, 3), metrics.sharpe_ratio],
    "m-sortino": [fmtNum(metrics.sortino_ratio, 3), metrics.sortino_ratio],
    "m-maxdd": [fmtPct(metrics.max_drawdown), -metrics.max_drawdown],
    "m-calmar": [fmtNum(metrics.calmar_ratio, 3), metrics.calmar_ratio],
    "m-winrate": [fmtPct(metrics.win_rate, 1), metrics.win_rate],
    "m-pf": [fmtNum(metrics.profit_factor, 2), metrics.profit_factor],
    "m-trades": [metrics.total_trades, null],
    "m-final": [fmtNum(metrics.final_capital, 0), metrics.final_capital - metrics.initial_capital],
  };

  for (const [id, [text, colorVal]] of Object.entries(fields)) {
    const el = document.getElementById(id);
    el.textContent = text;
    if (colorVal != null) setMetricColor(el, colorVal);
  }
}

function updateTradesTable(trades) {
  const tbody = document.querySelector("#trades-table tbody");
  if (!trades?.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无交易记录</td></tr>';
    return;
  }

  tbody.innerHTML = trades
    .map((t) => {
      const pnlClass = t.pnl >= 0 ? "positive" : "negative";
      return `<tr>
        <td>${t.instrument_id}</td>
        <td>${t.side}</td>
        <td>${t.entry_time?.slice(0, 10)} @ ${fmtNum(t.entry_price)}</td>
        <td>${t.exit_time?.slice(0, 10)} @ ${fmtNum(t.exit_price)}</td>
        <td>${t.quantity}</td>
        <td class="${pnlClass}">${fmtNum(t.pnl)}</td>
        <td class="${pnlClass}">${fmtPct(t.return_pct)}</td>
      </tr>`;
    })
    .join("");
}

document.getElementById("backtest-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);

  const params = {};
  for (const [key, val] of fd.entries()) {
    if (key.startsWith("param_")) {
      const pkey = key.replace("param_", "");
      const num = Number(val);
      params[pkey] = isNaN(num) ? val : num;
    }
  }

  showLoading(true);
  try {
    const result = await api("/backtest/run", {
      method: "POST",
      body: JSON.stringify({
        strategy: fd.get("strategy"),
        symbol: fd.get("symbol"),
        start: fd.get("start"),
        end: fd.get("end") || null,
        capital: Number(fd.get("capital")),
        params,
        use_demo_data: fd.get("use_demo_data") === "on",
      }),
    });

    lastBacktestResult = result;
    updateMetrics(result.metrics);
    renderEquityChart("equity-chart", result.equity_curve);
    renderDrawdownChart(result.equity_curve);
    updateTradesTable(result.trades);
    updateDashboard();

    const mode = result.used_demo_data ? "（演示数据）" : "";
    toast(`回测完成${mode}: 收益率 ${fmtPct(result.metrics.total_return)}`, "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

// ── Drawdown Chart ──────────────────────────────────────────

function renderDrawdownChart(equityCurve) {
  destroyChart("drawdown-chart");
  const ctx = document.getElementById("drawdown-chart");
  if (!ctx || !equityCurve?.length) return;

  const equities = equityCurve.map((p) => p.equity);
  const labels = equityCurve.map((p) => p.timestamp?.slice(0, 10) || "");
  const drawdowns = [];
  let peak = equities[0];
  for (const eq of equities) {
    if (eq > peak) peak = eq;
    drawdowns.push(((eq - peak) / peak) * 100);
  }

  charts["drawdown-chart"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "回撤 %",
        data: drawdowns,
        borderColor: "#ef4444",
        backgroundColor: "rgba(239, 68, 68, 0.12)",
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 1.5,
      }],
    },
    options: chartOptions("回撤 (%)"),
  });
}

// ── Strategy Comparison ─────────────────────────────────────

document.getElementById("run-compare-btn").addEventListener("click", async () => {
  const symbol = document.querySelector('#backtest-form [name="symbol"]').value || "600519.SSE";
  const start = document.querySelector('#backtest-form [name="start"]').value || "2023-01-01";
  const end = document.querySelector('#backtest-form [name="end"]').value || null;
  const capital = Number(document.querySelector('#backtest-form [name="capital"]').value) || 1000000;

  showLoading(true);
  try {
    const data = await api("/backtest/compare", {
      method: "POST",
      body: JSON.stringify({ strategy: "dual_ma", symbol, start, end, capital, use_demo_data: true }),
    });

    renderCompareChart(data.results);
    renderCompareTable(data.results);
    toast(`策略对比完成: ${Object.keys(data.results).length} 个策略`, "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

const COMPARE_COLORS = [
  "#3b82f6", "#22c55e", "#f59e0b", "#ef4444",
  "#a855f7", "#ec4899", "#06b6d4", "#84cc16",
];

function renderCompareChart(results) {
  destroyChart("compare-equity-chart");
  const ctx = document.getElementById("compare-equity-chart");
  if (!ctx) return;

  const datasets = [];
  let i = 0;
  for (const [sid, result] of Object.entries(results)) {
    const name = strategiesMeta[sid]?.name || sid;
    datasets.push({
      label: name,
      data: result.equity_curve.map((p) => p.equity),
      borderColor: COMPARE_COLORS[i % COMPARE_COLORS.length],
      fill: false,
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2,
    });
    i++;
  }

  const firstResult = Object.values(results)[0];
  const labels = firstResult?.equity_curve.map((p) => p.timestamp?.slice(0, 10)) || [];

  charts["compare-equity-chart"] = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      ...chartOptions("权益"),
      plugins: {
        legend: { display: true, position: "top", labels: { color: "#8b9ab5", font: { size: 11 } } },
        tooltip: {
          backgroundColor: "#1a2230",
          borderColor: "#2a3548",
          borderWidth: 1,
          mode: "index",
          intersect: false,
        },
      },
    },
  });
}

function renderCompareTable(results) {
  const tbody = document.querySelector("#compare-table tbody");
  const rows = Object.entries(results).map(([sid, result]) => {
    const m = result.metrics;
    const name = strategiesMeta[sid]?.name || sid;
    const retClass = m.total_return >= 0 ? "positive" : "negative";
    return `<tr>
      <td>${name}</td>
      <td class="${retClass}">${fmtPct(m.total_return)}</td>
      <td>${fmtNum(m.sharpe_ratio, 3)}</td>
      <td>${fmtPct(m.max_drawdown)}</td>
      <td>${m.total_trades}</td>
      <td>${fmtPct(m.win_rate, 1)}</td>
    </tr>`;
  });
  tbody.innerHTML = rows.join("") || '<tr><td colspan="6" class="empty-state">暂无数据</td></tr>';
}

// ── Strategies Page ────────────────────────────────────────

function renderStrategyCards() {
  const container = document.getElementById("strategy-cards");
  container.innerHTML = Object.entries(strategiesMeta)
    .map(([id, meta]) => {
      const paramList = Object.entries(meta.params || {})
        .map(([k, v]) => `${v.label || k}: ${v.default}`)
        .join(" · ");
      return `
        <div class="strategy-card">
          <span class="tag">${id}</span>
          <h4>${meta.name}</h4>
          <p>${meta.description}</p>
          <p style="font-size:0.75rem;color:var(--text-muted);font-family:var(--mono)">${paramList}</p>
          <button class="btn btn-sm btn-primary" onclick="useStrategy('${id}')">使用此策略</button>
        </div>`;
    })
    .join("");
}

function useStrategy(id) {
  navigateTo("backtest");
  document.getElementById("strategy-select").value = id;
  renderStrategyParams(id);
}

// ── Settings Page ──────────────────────────────────────────

function renderSettings() {
  if (!systemInfo) return;

  const riskEl = document.getElementById("risk-settings");
  riskEl.innerHTML = Object.entries(systemInfo.risk)
    .map(([k, v]) => `<div class="setting-item"><div class="key">${k}</div><div class="val">${v}</div></div>`)
    .join("");

  const btEl = document.getElementById("backtest-settings");
  btEl.innerHTML = Object.entries(systemInfo.backtest_defaults)
    .map(([k, v]) => `<div class="setting-item"><div class="key">${k}</div><div class="val">${v}</div></div>`)
    .join("");

  document.getElementById("system-info-block").textContent = JSON.stringify(systemInfo, null, 2);
}

// ── Init ───────────────────────────────────────────────────

async function refreshSystemInfo() {
  systemInfo = await api("/system/info");
  const stratData = await api("/strategies");
  strategiesMeta = {};
  for (const s of stratData.strategies) {
    strategiesMeta[s.id] = s;
  }
  updateDashboard();
  renderSettings();
  renderStrategyCards();
  populateStrategySelect();
}

async function init() {
  showLoading(true);
  try {
    await api("/health");
    await refreshSystemInfo();
    await loadInstruments();
    document.getElementById("system-status").textContent = "系统就绪";
  } catch (err) {
    document.getElementById("system-status").textContent = "API 未连接";
    toast("无法连接后端 API，请启动: uv run quant-web", "error");
  } finally {
    showLoading(false);
  }
}

document.getElementById("refresh-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await refreshSystemInfo();
    await loadInstruments();
    toast("已刷新", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

init();
