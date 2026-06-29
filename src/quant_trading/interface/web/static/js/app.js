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
  optimize: { title: "参数优化", desc: "网格搜索最优策略参数" },
  monitor: { title: "监控告警", desc: "系统告警与异常监控" },
  paper: { title: "模拟盘", desc: "虚拟资金实时交易模拟" },
  risk: { title: "风控中心", desc: "紧急冻结、策略暂停、一键清仓" },
  live: { title: "实时策略", desc: "实时策略运行、行情推送与监控" },
  ailab: { title: "AI 实验室", desc: "特征工程、模型训练与预测" },
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
        enable_t1: fd.get("enable_t1") === "on",
        adjust: fd.get("adjust") || "none",
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

// ── Parameter Optimization ──────────────────────────────────

const DEFAULT_GRIDS = {
  dual_ma: { fast_period: [5, 10, 15, 20], slow_period: [20, 30, 40, 60] },
  bollinger: { period: [10, 15, 20, 30], num_std: [1.5, 2.0, 2.5, 3.0] },
  rsi: { rsi_period: [7, 14, 21], oversold: [20, 25, 30], overbought: [70, 75, 80] },
  macd: { fast_period: [8, 12, 16], slow_period: [20, 26, 30], signal_period: [7, 9, 12] },
  turtle: { entry_period: [10, 15, 20, 30], exit_period: [5, 10, 15] },
  grid: { grid_count: [5, 8, 10, 15, 20] },
};

function populateOptStrategySelect() {
  const select = document.getElementById("opt-strategy-select");
  select.innerHTML = Object.entries(strategiesMeta)
    .map(([id, meta]) => `<option value="${id}">${meta.name} (${id})</option>`)
    .join("");
  select.addEventListener("change", () => renderOptParamGrid(select.value));
  renderOptParamGrid(select.value);
}

function renderOptParamGrid(strategyId) {
  const container = document.getElementById("opt-param-grid");
  const grid = DEFAULT_GRIDS[strategyId];
  const meta = strategiesMeta[strategyId];
  if (!grid || !meta) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--text-muted)">该策略暂无预设参数范围</p>';
    return;
  }
  container.innerHTML = Object.entries(grid)
    .map(([key, vals]) => {
      const label = meta.params?.[key]?.label || key;
      return `<div class="form-row">
        <label>${label}（搜索值，逗号分隔）</label>
        <input type="text" name="grid_${key}" value="${vals.join(", ")}" />
      </div>`;
    })
    .join("");
}

document.getElementById("optimize-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const paramGrid = {};
  for (const [key, val] of fd.entries()) {
    if (key.startsWith("grid_")) {
      const pkey = key.replace("grid_", "");
      paramGrid[pkey] = val.split(",").map((v) => {
        const n = Number(v.trim());
        return isNaN(n) ? v.trim() : n;
      });
    }
  }

  showLoading(true);
  try {
    const result = await api("/optimize/run", {
      method: "POST",
      body: JSON.stringify({
        strategy: fd.get("strategy"),
        symbol: fd.get("symbol"),
        start: fd.get("start"),
        end: fd.get("end") || null,
        capital: Number(fd.get("capital")),
        param_grid: paramGrid,
        use_demo_data: fd.get("use_demo_data") === "on",
      }),
    });

    document.getElementById("opt-result-count").textContent = result.total;
    const summary = document.getElementById("opt-summary");
    summary.style.display = "block";

    if (result.results.length > 0) {
      const best = result.results[0];
      document.getElementById("opt-best-sharpe").textContent = fmtNum(best.sharpe_ratio, 3);
      document.getElementById("opt-best-return").textContent = fmtPct(best.total_return);
      document.getElementById("opt-total").textContent = result.total;
    }

    const tbody = document.querySelector("#opt-results-table tbody");
    tbody.innerHTML = result.results
      .slice(0, 30)
      .map((r, i) => {
        const params = Object.entries(r.params)
          .map(([k, v]) => `${k}=${v}`)
          .join(", ");
        const retClass = r.total_return >= 0 ? "positive" : "negative";
        const rowClass = i === 0 ? "opt-rank-1" : "";
        return `<tr class="${rowClass}">
          <td>${i + 1}</td>
          <td style="font-size:0.7rem">${params}</td>
          <td class="${retClass}">${fmtPct(r.total_return)}</td>
          <td>${fmtNum(r.sharpe_ratio, 3)}</td>
          <td>${fmtPct(r.max_drawdown)}</td>
          <td>${fmtPct(r.win_rate, 1)}</td>
          <td>${r.total_trades}</td>
        </tr>`;
      })
      .join("");

    toast(`优化完成: ${result.total} 种参数组合`, "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

// ── Monitor & Alerts ────────────────────────────────────────

async function loadAlerts() {
  try {
    const data = await api("/monitor/alerts?limit=100");
    const alerts = data.alerts || [];

    document.getElementById("mon-total").textContent = alerts.length;
    document.getElementById("mon-critical").textContent = alerts.filter((a) => a.level === "critical").length;
    document.getElementById("mon-warning").textContent = alerts.filter((a) => a.level === "warning").length;
    document.getElementById("mon-info").textContent = alerts.filter((a) => a.level === "info").length;

    const tbody = document.querySelector("#alerts-table tbody");
    if (!alerts.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">暂无告警记录</td></tr>';
    } else {
      tbody.innerHTML = alerts
        .reverse()
        .map((a) => `<tr>
          <td>${a.timestamp?.slice(0, 19).replace("T", " ") || "-"}</td>
          <td><span class="alert-badge ${a.level}">${a.level}</span></td>
          <td>${a.type}</td>
          <td>${a.message}</td>
        </tr>`)
        .join("");
    }
  } catch {
    /* silent */
  }
}

async function loadMonitorConfig() {
  try {
    const data = await api("/monitor/config");
    const el = document.getElementById("mon-thresholds");
    el.innerHTML = Object.entries(data.thresholds)
      .map(([k, v]) => `<div class="setting-item"><div class="key">${k}</div><div class="val">${v}</div></div>`)
      .join("");
  } catch {
    /* silent */
  }
}

document.getElementById("mon-refresh-btn").addEventListener("click", async () => {
  await loadAlerts();
  await loadMonitorConfig();
  toast("告警已刷新", "success");
});

document.getElementById("mon-test-btn").addEventListener("click", async () => {
  try {
    await api("/monitor/test", { method: "POST" });
    await loadAlerts();
    toast("测试告警已发送", "info");
  } catch (err) {
    toast(err.message, "error");
  }
});

// ── Paper Trading ───────────────────────────────────────────

function updatePaperAccount(account) {
  if (!account) return;
  document.getElementById("paper-balance").textContent = fmtNum(account.balance, 2);
  document.getElementById("paper-available").textContent = fmtNum(account.available, 2);
  document.getElementById("paper-commission").textContent = fmtNum(account.commission, 2);
}

function updatePaperPositions(positions) {
  document.getElementById("paper-pos-count").textContent = positions?.length || 0;
  const tbody = document.querySelector("#paper-positions-table tbody");
  if (!positions?.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">暂无持仓</td></tr>';
    return;
  }
  tbody.innerHTML = positions
    .map((p) => {
      const pnlClass = p.realized_pnl >= 0 ? "positive" : "negative";
      return `<tr>
        <td>${p.instrument_id}</td>
        <td>${p.side}</td>
        <td>${Math.abs(p.quantity)}</td>
        <td>${fmtNum(p.avg_price)}</td>
        <td class="${pnlClass}">${fmtNum(p.realized_pnl)}</td>
      </tr>`;
    })
    .join("");
}

function updatePaperOrders(orders) {
  const tbody = document.querySelector("#paper-orders-table tbody");
  if (!orders?.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">暂无挂单</td></tr>';
    return;
  }
  tbody.innerHTML = orders
    .map((o) => `<tr>
      <td style="font-size:0.7rem">${o.order_id.slice(0, 8)}...</td>
      <td>${o.instrument_id}</td>
      <td>${o.side}</td>
      <td>${o.order_type}</td>
      <td>${o.quantity}</td>
      <td>${o.price || "-"}</td>
      <td>${o.status}</td>
    </tr>`)
    .join("");
}

async function refreshPaperState() {
  try {
    const [accData, posData, orderData] = await Promise.all([
      api("/paper/account"),
      api("/paper/positions"),
      api("/paper/orders"),
    ]);
    updatePaperAccount(accData.account);
    updatePaperPositions(posData.positions);
    updatePaperOrders(orderData.orders);
  } catch {
    /* gateway not initialized yet */
  }
}

document.getElementById("paper-connect-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    const result = await api("/paper/connect", { method: "POST", body: "{}" });
    updatePaperAccount(result.account);
    updatePaperPositions([]);
    updatePaperOrders([]);
    toast("模拟盘已重置", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

document.getElementById("paper-order-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  showLoading(true);
  try {
    const result = await api("/paper/order", {
      method: "POST",
      body: JSON.stringify({
        symbol: fd.get("symbol"),
        side: fd.get("side"),
        order_type: fd.get("order_type"),
        quantity: Number(fd.get("quantity")),
        price: fd.get("price") ? Number(fd.get("price")) : null,
      }),
    });
    updatePaperAccount(result.account);
    updatePaperPositions(result.positions);
    toast(`订单已提交: ${result.status}`, "success");
    const orderData = await api("/paper/orders");
    updatePaperOrders(orderData.orders);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

// ── AI Lab ──────────────────────────────────────────────────

async function loadAIFeatures() {
  try {
    const data = await api("/alpha/features");
    const tbody = document.querySelector("#ai-features-table tbody");
    tbody.innerHTML = data.features
      .map((f) => `<tr>
        <td>${f.name}</td>
        <td><span class="badge">${f.type}</span></td>
        <td style="font-size:0.75rem">${f.dependencies.join(", ")}</td>
      </tr>`)
      .join("");
  } catch {
    /* silent */
  }
}

async function loadAIModels() {
  try {
    const data = await api("/alpha/models");
    const container = document.getElementById("ai-models-cards");
    container.innerHTML = data.models
      .map((m) => `<div class="model-card">
        <h4>${m.name}</h4>
        <p>${m.description}</p>
        <span class="status-tag">${m.status}</span>
      </div>`)
      .join("");
  } catch {
    /* silent */
  }
}

document.getElementById("ai-compute-btn").addEventListener("click", async () => {
  const symbol = document.getElementById("ai-compute-symbol").value || "DEMO.SSE";
  showLoading(true);
  try {
    const data = await api(`/alpha/compute?symbol=${encodeURIComponent(symbol)}`, { method: "POST" });
    const thead = document.querySelector("#ai-compute-table thead tr");
    thead.innerHTML = data.columns.map((c) => `<th>${c}</th>`).join("");

    const tbody = document.querySelector("#ai-compute-table tbody");
    tbody.innerHTML = data.rows
      .map((row) => `<tr>${data.columns.map((c) => {
        let v = row[c];
        if (typeof v === "number") v = v.toFixed(4);
        return `<td>${v ?? ""}</td>`;
      }).join("")}</tr>`)
      .join("");

    toast(`特征计算完成: ${data.total_rows} 行 × ${data.columns.length} 列`, "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

// ── Risk Control Center ─────────────────────────────────────

async function loadRiskStatus() {
  try {
    const data = await api("/risk/status");
    const status = data.status || data;

    const frozenEl = document.getElementById("risk-frozen-status");
    if (status.frozen) {
      frozenEl.textContent = "已冻结";
      frozenEl.className = "kpi-value negative";
    } else {
      frozenEl.textContent = "正常";
      frozenEl.className = "kpi-value positive";
    }

    const haltEl = document.getElementById("risk-halt-status");
    if (status.strategies_halted) {
      haltEl.textContent = "已暂停";
      haltEl.className = "kpi-value negative";
    } else {
      haltEl.textContent = "运行中";
      haltEl.className = "kpi-value positive";
    }

    const pnlEl = document.getElementById("risk-daily-pnl");
    const pnl = status.daily_pnl ?? 0;
    pnlEl.textContent = fmtNum(pnl, 2);
    setMetricColor(pnlEl, pnl);

    document.getElementById("risk-order-count").textContent = status.order_count ?? "-";

    const detailEl = document.getElementById("risk-status-detail");
    const displayMap = {
      frozen: "账户冻结",
      strategies_halted: "策略暂停",
      enabled: "风控启用",
      daily_pnl: "当日盈亏",
      order_count: "下单笔数",
      max_position_pct: "最大持仓比例",
      max_single_order_pct: "最大单笔比例",
      max_daily_loss_pct: "最大日亏损比例",
      max_order_frequency: "最大下单频率",
    };
    detailEl.innerHTML = Object.entries(status)
      .map(([k, v]) => {
        const label = displayMap[k] || k;
        let display = v;
        if (typeof v === "boolean") display = v ? "是" : "否";
        if (typeof v === "number" && v < 1 && v > 0) display = fmtPct(v);
        return `<div class="setting-item"><div class="key">${label}</div><div class="val">${display}</div></div>`;
      })
      .join("");
  } catch {
    /* risk engine may not be initialized */
  }
}

document.getElementById("risk-freeze-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/risk/freeze", { method: "POST" });
    toast("已紧急冻结 — 所有新订单将被拒绝", "error");
    await loadRiskStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("risk-unfreeze-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/risk/unfreeze", { method: "POST" });
    toast("已解除冻结 — 恢复正常下单", "success");
    await loadRiskStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("risk-halt-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/risk/halt", { method: "POST" });
    toast("策略已暂停 — 不再产生新信号", "info");
    await loadRiskStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("risk-resume-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/risk/resume", { method: "POST" });
    toast("策略已恢复运行", "success");
    await loadRiskStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("risk-closeall-btn").addEventListener("click", async () => {
  if (!confirm("确认一键清仓？将平掉所有模拟盘持仓并冻结账户。")) return;
  showLoading(true);
  try {
    const result = await api("/risk/close-all", { method: "POST" });
    const el = document.getElementById("risk-closeall-result");
    el.innerHTML = `
      <div style="padding:0.75rem">
        <p style="color:var(--red);font-weight:600;margin-bottom:0.5rem">清仓完成</p>
        <p>平仓笔数：<strong>${result.closed ?? 0}</strong></p>
        <p>账户余额：<strong>${fmtNum(result.account?.balance, 2)}</strong></p>
        <p>账户已自动冻结</p>
      </div>`;
    toast(`一键清仓完成: 平仓 ${result.closed ?? 0} 笔`, "error");
    await loadRiskStatus();
    await refreshPaperState();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("risk-refresh-btn").addEventListener("click", async () => {
  await loadRiskStatus();
  toast("风控状态已刷新", "success");
});

// ── Live Strategy Runner ────────────────────────────────────

let liveFeedLog = [];

function populateLiveStrategySelect() {
  const select = document.getElementById("live-strategy-select");
  if (!select || !Object.keys(strategiesMeta).length) return;
  select.innerHTML = Object.entries(strategiesMeta)
    .map(([id, meta]) => `<option value="${id}">${meta.name} (${id})</option>`)
    .join("");
}

async function loadLiveStatus() {
  try {
    const data = await api("/live/status");
    const status = data.status || data;

    const runEl = document.getElementById("live-running-status");
    if (status.running) {
      runEl.textContent = "运行中";
      runEl.className = "kpi-value positive";
    } else {
      runEl.textContent = "停止";
      runEl.className = "kpi-value";
    }
    document.getElementById("live-strategy-id").textContent = status.strategy_id || "-";
    document.getElementById("live-symbol").textContent = status.symbol || "-";
    document.getElementById("live-bars-count").textContent = status.bars_received ?? 0;
  } catch {
    /* live runner may not exist yet */
  }
}

document.getElementById("live-start-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  showLoading(true);
  try {
    const strategyId = fd.get("strategy_id");
    const symbol = fd.get("symbol");
    await api(`/live/start?strategy_id=${encodeURIComponent(strategyId)}&symbol=${encodeURIComponent(symbol)}`, {
      method: "POST",
    });
    toast(`实时策略已启动: ${strategyId} → ${symbol}`, "success");
    liveFeedLog = [];
    await loadLiveStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("live-stop-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/live/stop", { method: "POST" });
    toast("实时策略已停止", "info");
    await loadLiveStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("live-feed-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const symbol = fd.get("symbol");
  const price = Number(fd.get("price"));
  const volume = Number(fd.get("volume"));

  try {
    await api(`/live/feed?symbol=${encodeURIComponent(symbol)}&price=${price}&volume=${volume}`, {
      method: "POST",
    });
    const now = new Date().toLocaleTimeString("zh-CN");
    liveFeedLog.unshift({ time: now, symbol, price, volume });
    if (liveFeedLog.length > 20) liveFeedLog.length = 20;

    const logEl = document.getElementById("live-feed-log");
    logEl.innerHTML = liveFeedLog
      .map((l) => `<div class="feed-item">
        <span class="feed-time">${l.time}</span>
        <span class="feed-symbol">${l.symbol}</span>
        <span class="feed-price">¥${fmtNum(l.price, 2)}</span>
        <span class="feed-vol">Vol: ${fmtNum(l.volume, 0)}</span>
      </div>`)
      .join("");

    toast(`K 线已推送: ${symbol} @ ¥${price}`, "success");
    await loadLiveStatus();
  } catch (err) { toast(err.message, "error"); }
});

document.getElementById("live-refresh-btn").addEventListener("click", async () => {
  await loadLiveStatus();
  toast("状态已刷新", "success");
});

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
  populateOptStrategySelect();
  populateLiveStrategySelect();
}

async function init() {
  showLoading(true);
  try {
    await api("/health");
    await refreshSystemInfo();
    await Promise.all([
      loadInstruments(),
      loadAlerts(),
      loadMonitorConfig(),
      refreshPaperState(),
      loadRiskStatus(),
      loadLiveStatus(),
      loadAIFeatures(),
      loadAIModels(),
    ]);
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
    await Promise.all([
      loadInstruments(),
      loadAlerts(),
      loadMonitorConfig(),
      refreshPaperState(),
      loadRiskStatus(),
      loadLiveStatus(),
      loadAIFeatures(),
      loadAIModels(),
    ]);
    toast("已刷新", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

init();
