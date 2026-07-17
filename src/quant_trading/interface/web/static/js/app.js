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
  risk: { title: "风控中心", desc: "紧急冻结、策略暂停、一键清仓、浮亏减仓、仓位管理" },
  live: { title: "实时策略", desc: "实时策略运行、行情推送与监控" },
  ailab: { title: "AI 实验室", desc: "特征工程、模型训练与预测" },
  strategies: { title: "策略库", desc: "内置策略模板与参数说明" },
  ops: { title: "运维中心", desc: "定时任务调度、进程守护与崩溃重启" },
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

async function loadInstruments(focusSymbol) {
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

  const target = focusSymbol && data.instruments.includes(focusSymbol)
    ? focusSymbol
    : data.instruments[0];
  previewBars(target);
}

async function previewBars(symbol, activeEl) {
  document.querySelectorAll(".instrument-item").forEach((el) => el.classList.remove("active"));
  if (activeEl) activeEl.classList.add("active");

  try {
    const data = await api(`/data/bars/${encodeURIComponent(symbol)}?limit=200`);
    if (!data.bars || data.bars.length === 0) {
      destroyChart("price-chart");
      const ctx = document.getElementById("price-chart");
      if (ctx) {
        const parent = ctx.parentElement;
        const hint = parent.querySelector(".empty-hint");
        if (!hint) {
          const el = document.createElement("div");
          el.className = "empty-state empty-hint";
          el.textContent = "该标的暂无 K 线数据，请在左侧选择日期范围并点击「获取并存储」";
          parent.appendChild(el);
        }
      }
    } else {
      const parent = document.getElementById("price-chart")?.parentElement;
      if (parent) parent.querySelector(".empty-hint")?.remove();
      renderPriceChart(data.bars);
    }
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
    const count = result.bar_count ?? result.tick_count ?? 0;
    if (count === 0) {
      toast(`获取 0 条数据（${result.symbol}）——可能原因：① 代理/VPN 软件拦截了东方财富 API（请关闭 Clash/V2Ray 的 TUN 模式或添加 eastmoney.com 到直连规则）② 标的代码或日期有误 ③ 东方财富限频`, "error");
    } else {
      toast(`成功获取 ${count} 条 K 线: ${result.symbol}`, "success");
    }
    await loadInstruments(result.symbol);
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
    "m-winning": [metrics.winning_trades ?? "-", metrics.winning_trades],
    "m-losing": [metrics.losing_trades ?? "-", -(metrics.losing_trades ?? 0)],
    "m-avg-win": [fmtNum(metrics.avg_win, 2), metrics.avg_win],
    "m-avg-loss": [fmtNum(metrics.avg_loss, 2), metrics.avg_loss],
    "m-volatility": [fmtPct(metrics.volatility), -Math.abs(metrics.volatility ?? 0)],
    "m-avg-dur": [metrics.avg_trade_duration_days != null ? fmtNum(metrics.avg_trade_duration_days, 1) + " 天" : "-", null],
    "m-dd-days": [metrics.max_drawdown_duration_days != null ? metrics.max_drawdown_duration_days + " 天" : "-", -(metrics.max_drawdown_duration_days ?? 0)],
    "m-initial": [fmtNum(metrics.initial_capital, 0), null],
  };

  for (const [id, [text, colorVal]] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (!el) continue;
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
        transfer_fee_rate: (Number(fd.get("transfer_fee_rate")) || 0.2) / 10000,
      }),
    });

    lastBacktestResult = result;
    updateMetrics(result.metrics);
    renderEquityChart("equity-chart", result.equity_curve);
    renderDrawdownChart(result.equity_curve);
    renderKlineWithTrades(result.equity_curve, result.trades);
    updateTradesTable(result.trades);
    updateDashboard();

    document.getElementById("run-montecarlo-btn").disabled = false;
    document.getElementById("run-review-btn").disabled = false;

    const mode = result.used_demo_data ? "（演示数据）" : "（真实数据）";
    toast(`回测完成${mode}: 收益率 ${fmtPct(result.metrics.total_return)}`, "success");
  } catch (err) {
    let msg = err.message;
    if (msg.includes("No data") || msg.includes("Fetch data first")) {
      msg += " —— 提示：勾选下方「无本地数据时使用模拟数据（演示模式）」可使用模拟数据回测；如需真实数据请先在数据管理页获取";
    }
    toast(msg, "error");
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

// ── K-line with Trade Markers ───────────────────────────────

function renderKlineWithTrades(equityCurve, trades) {
  destroyChart("kline-trades-chart");
  const emptyEl = document.getElementById("kline-trades-empty");
  const ctx = document.getElementById("kline-trades-chart");
  if (!ctx || !equityCurve?.length) { if (emptyEl) emptyEl.style.display = "block"; return; }
  if (emptyEl) emptyEl.style.display = "none";

  const labels = equityCurve.map(p => p.timestamp?.slice(0, 10) || "");
  const prices = equityCurve.map(p => p.equity);

  const buyPoints = new Array(labels.length).fill(null);
  const sellPoints = new Array(labels.length).fill(null);

  for (const t of (trades || [])) {
    const entryDate = t.entry_time?.slice(0, 10);
    const exitDate = t.exit_time?.slice(0, 10);
    const entryIdx = labels.indexOf(entryDate);
    const exitIdx = labels.indexOf(exitDate);
    if (entryIdx >= 0) buyPoints[entryIdx] = prices[entryIdx];
    if (exitIdx >= 0) sellPoints[exitIdx] = prices[exitIdx];
  }

  charts["kline-trades-chart"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "权益", data: prices, borderColor: "#3b82f6", borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false },
        { label: "买入 ▲", data: buyPoints, borderColor: "#22c55e", backgroundColor: "#22c55e", pointRadius: 7, pointStyle: "triangle", showLine: false },
        { label: "卖出 ▼", data: sellPoints, borderColor: "#ef4444", backgroundColor: "#ef4444", pointRadius: 7, pointStyle: "triangle", rotation: 180, showLine: false },
      ],
    },
    options: { ...chartOptions("权益 + 买卖点"), plugins: { ...chartOptions("").plugins, legend: { display: true, labels: { color: "#94a3b8", font: { size: 11 } } } } },
  });
}

// ── Monte Carlo Stress Test ────────────────────────────────

document.getElementById("run-montecarlo-btn").addEventListener("click", async () => {
  if (!lastBacktestResult) { toast("请先运行回测", "error"); return; }
  const bt = document.getElementById("backtest-form");
  const fd = new FormData(bt);
  const params = {};
  for (const [key, val] of fd.entries()) {
    if (key.startsWith("param_")) { params[key.replace("param_", "")] = isNaN(Number(val)) ? val : Number(val); }
  }
  showLoading(true);
  try {
    const data = await api("/backtest/montecarlo", {
      method: "POST",
      body: JSON.stringify({
        strategy: fd.get("strategy"), symbol: fd.get("symbol"),
        start: fd.get("start"), end: fd.get("end") || null,
        capital: Number(fd.get("capital")), params,
        use_demo_data: fd.get("use_demo_data") === "on",
        enable_t1: fd.get("enable_t1") === "on",
        adjust: fd.get("adjust") || "none",
        transfer_fee_rate: (Number(fd.get("transfer_fee_rate")) || 0.2) / 10000,
      }),
    });
    document.getElementById("mc-stats").style.display = "block";
    document.getElementById("mc-empty").style.display = "none";
    document.getElementById("mc-base-final").textContent = fmtNum(data.base_final);
    document.getElementById("mc-p5").textContent = fmtNum(data.stats.p5_final);
    document.getElementById("mc-p50").textContent = fmtNum(data.stats.p50_final);
    document.getElementById("mc-p95").textContent = fmtNum(data.stats.p95_final);
    document.getElementById("mc-avg-dd").textContent = fmtPct(data.stats.mean_max_dd);
    document.getElementById("mc-p95-dd").textContent = fmtPct(data.stats.p95_max_dd);
    document.getElementById("mc-worst-dd").textContent = fmtPct(data.stats.worst_max_dd);
    renderMCPercentileChart(data.percentile_curves);
    renderMCDistributionChart(data.distribution);
    toast(`Monte Carlo 完成: ${data.n_simulations} 次模拟, ${data.n_trades} 笔交易`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

function renderMCPercentileChart(curves) {
  destroyChart("mc-percentile-chart");
  const ctx = document.getElementById("mc-percentile-chart");
  if (!ctx) return;
  const len = curves.p50.length;
  const labels = Array.from({ length: len }, (_, i) => `T${i}`);
  charts["mc-percentile-chart"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "95% 最优路径", data: curves.p95, borderColor: "#22c55e", borderWidth: 1.2, pointRadius: 0, tension: 0.3, fill: false },
        { label: "50% 中位路径", data: curves.p50, borderColor: "#3b82f6", borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
        { label: "5% 最差路径", data: curves.p5, borderColor: "#ef4444", borderWidth: 1.2, pointRadius: 0, tension: 0.3, fill: false },
      ],
    },
    options: { ...chartOptions("Monte Carlo 权益分布带"), plugins: { legend: { display: true, labels: { color: "#94a3b8", font: { size: 11 } } } } },
  });
}

function renderMCDistributionChart(dist) {
  destroyChart("mc-distribution-chart");
  const ctx = document.getElementById("mc-distribution-chart");
  if (!ctx) return;
  const labels = dist.finals.map((_, i) => `${i * 5}%`);
  charts["mc-distribution-chart"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "最终资金分布", data: dist.finals, backgroundColor: "rgba(59,130,246,0.6)", borderColor: "#3b82f6", borderWidth: 1 }],
    },
    options: { ...chartOptions("最终资金 (按百分位)"), plugins: { legend: { display: false } } },
  });
}

// ── Review Report ──────────────────────────────────────────

document.getElementById("run-review-btn").addEventListener("click", async () => {
  if (!lastBacktestResult) { toast("请先运行回测", "error"); return; }
  const bt = document.getElementById("backtest-form");
  const fd = new FormData(bt);
  const params = {};
  for (const [key, val] of fd.entries()) {
    if (key.startsWith("param_")) { params[key.replace("param_", "")] = isNaN(Number(val)) ? val : Number(val); }
  }
  showLoading(true);
  try {
    const data = await api("/backtest/review", {
      method: "POST",
      body: JSON.stringify({
        strategy: fd.get("strategy"), symbol: fd.get("symbol"),
        start: fd.get("start"), end: fd.get("end") || null,
        capital: Number(fd.get("capital")), params,
        use_demo_data: fd.get("use_demo_data") === "on",
        enable_t1: fd.get("enable_t1") === "on",
        adjust: fd.get("adjust") || "none",
        transfer_fee_rate: (Number(fd.get("transfer_fee_rate")) || 0.2) / 10000,
      }),
    });
    document.getElementById("review-stats").style.display = "block";
    document.getElementById("review-empty").style.display = "none";
    document.getElementById("rv-streak-win").textContent = data.streaks.max_consecutive_wins;
    document.getElementById("rv-streak-lose").textContent = data.streaks.max_consecutive_losses;
    document.getElementById("rv-largest-win").textContent = fmtNum(data.trade_analysis.largest_win);
    document.getElementById("rv-largest-loss").textContent = fmtNum(data.trade_analysis.largest_loss);
    document.getElementById("rv-avg-dur").textContent = data.trade_analysis.avg_duration_days + " 天";
    document.getElementById("rv-avg-win").textContent = fmtNum(data.trade_analysis.avg_win);
    document.getElementById("rv-avg-loss").textContent = fmtNum(data.trade_analysis.avg_loss);
    renderReviewMonthlyChart(data.monthly);
    renderReviewMonthlyTable(data.monthly);
    toast(`复盘报表生成完成: ${data.monthly.length} 个月`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

function renderReviewMonthlyChart(monthly) {
  destroyChart("review-monthly-chart");
  const ctx = document.getElementById("review-monthly-chart");
  if (!ctx || !monthly?.length) return;
  charts["review-monthly-chart"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: monthly.map(m => m.month),
      datasets: [{
        label: "月度盈亏",
        data: monthly.map(m => m.pnl),
        backgroundColor: monthly.map(m => m.pnl >= 0 ? "rgba(34,197,94,0.7)" : "rgba(239,68,68,0.7)"),
        borderColor: monthly.map(m => m.pnl >= 0 ? "#22c55e" : "#ef4444"),
        borderWidth: 1,
      }],
    },
    options: { ...chartOptions("盈亏 (元)"), plugins: { legend: { display: false } } },
  });
}

function renderReviewMonthlyTable(monthly) {
  const tbody = document.querySelector("#review-monthly-table tbody");
  if (!tbody) return;
  tbody.innerHTML = monthly.map(m => {
    const cls = m.pnl >= 0 ? "positive" : "negative";
    return `<tr><td>${m.month}</td><td class="${cls}">${fmtNum(m.pnl)}</td><td>${m.trades}</td><td>${fmtPct(m.win_rate)}</td></tr>`;
  }).join("") || '<tr><td colspan="4" class="empty-state">无数据</td></tr>';
}

// ── Parameter Heatmap ──────────────────────────────────────

let lastOptimizeResults = null;

function renderHeatmap(results) {
  destroyChart("heatmap-chart");
  const emptyEl = document.getElementById("heatmap-empty");
  const ctx = document.getElementById("heatmap-chart");
  if (!ctx || !results?.length) { if (emptyEl) emptyEl.style.display = "block"; return; }

  const paramKeys = Object.keys(results[0].params || {});
  if (paramKeys.length < 2) { if (emptyEl) emptyEl.style.display = "block"; return; }
  if (emptyEl) emptyEl.style.display = "none";

  const xKey = paramKeys[0], yKey = paramKeys[1];
  const xVals = [...new Set(results.map(r => r.params[xKey]))].sort((a, b) => a - b);
  const yVals = [...new Set(results.map(r => r.params[yKey]))].sort((a, b) => a - b);

  const grid = {};
  for (const r of results) {
    const key = `${r.params[xKey]}_${r.params[yKey]}`;
    grid[key] = r.metrics?.sharpe_ratio ?? 0;
  }

  const allSharpes = Object.values(grid);
  const minS = Math.min(...allSharpes), maxS = Math.max(...allSharpes);

  const data = [];
  for (let yi = 0; yi < yVals.length; yi++) {
    for (let xi = 0; xi < xVals.length; xi++) {
      const s = grid[`${xVals[xi]}_${yVals[yi]}`] ?? 0;
      data.push({ x: xi, y: yi, v: s });
    }
  }

  const container = document.getElementById("heatmap-container");
  container.innerHTML = "";
  const table = document.createElement("table");
  table.className = "data-table";
  table.style.fontSize = "0.8rem";
  table.style.textAlign = "center";

  let html = `<thead><tr><th>${xKey} \\ ${yKey}</th>`;
  for (const y of yVals) html += `<th>${y}</th>`;
  html += "</tr></thead><tbody>";

  for (let xi = 0; xi < xVals.length; xi++) {
    html += `<tr><td><strong>${xVals[xi]}</strong></td>`;
    for (let yi = 0; yi < yVals.length; yi++) {
      const s = grid[`${xVals[xi]}_${yVals[yi]}`] ?? 0;
      const norm = maxS > minS ? (s - minS) / (maxS - minS) : 0.5;
      const r = Math.round(239 * (1 - norm) + 34 * norm);
      const g = Math.round(68 * (1 - norm) + 197 * norm);
      const b = Math.round(68 * (1 - norm) + 94 * norm);
      const bg = `rgba(${r},${g},${b},0.7)`;
      html += `<td style="background:${bg};color:#fff;font-weight:600">${s.toFixed(2)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody>";
  table.innerHTML = html;
  container.appendChild(table);
}

// ── Strategy Comparison ─────────────────────────────────────

document.getElementById("run-compare-btn").addEventListener("click", async () => {
  const symbol = document.querySelector('#backtest-form [name="symbol"]').value || "600519.SSE";
  const fallbackStart = new Date(new Date().getFullYear() - 1, 0, 1).toISOString().slice(0, 10);
  const start = document.querySelector('#backtest-form [name="start"]').value || fallbackStart;
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
  document.getElementById("system-info-block").textContent = JSON.stringify(systemInfo, null, 2);
  loadConfigEditor();
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

    lastOptimizeResults = result.results;
    renderHeatmap(result.results);
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

// 告警推送通道切换
document.getElementById("push-channel-select").addEventListener("change", (e) => {
  const isEmail = e.target.value === "email";
  document.getElementById("push-webhook-fields").style.display = isEmail ? "none" : "block";
  document.getElementById("push-email-fields").style.display = isEmail ? "block" : "none";
});

// 告警推送配置提交
document.getElementById("push-config-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const channel = fd.get("channel");
  const params = new URLSearchParams();
  params.set("channel", channel);
  if (channel === "webhook") {
    params.set("url", fd.get("url"));
    params.set("platform", fd.get("platform"));
  } else {
    params.set("smtp_host", fd.get("smtp_host"));
    params.set("smtp_port", fd.get("smtp_port"));
    params.set("username", fd.get("username"));
    params.set("password", fd.get("password"));
    params.set("sender", fd.get("sender"));
    params.set("recipients", fd.get("recipients"));
  }
  showLoading(true);
  try {
    const r = await api(`/monitor/push-config?${params.toString()}`, { method: "POST" });
    toast(`推送通道已配置并测试成功（${r.channel}）`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
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
    const payload = {
      symbol: fd.get("symbol"),
      side: fd.get("side"),
      order_type: fd.get("order_type"),
      quantity: Number(fd.get("quantity")),
      price: fd.get("price") ? Number(fd.get("price")) : null,
    };
    if (fd.get("order_type") === "trailing_stop") {
      payload.trail_offset = fd.get("trail_offset") ? Number(fd.get("trail_offset")) : null;
      payload.trigger_price = fd.get("trigger_price") ? Number(fd.get("trigger_price")) : null;
    }
    if (fd.get("order_type") === "conditional") {
      payload.cond_price = fd.get("cond_price") ? Number(fd.get("cond_price")) : null;
      payload.cond_direction = fd.get("cond_direction") || "above";
    }
    const result = await api("/paper/order", {
      method: "POST",
      body: JSON.stringify(payload),
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

// ── Auto Reduce & Position Sizer ─────────────────────────────

document.getElementById("auto-reduce-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const threshold = Number(fd.get("threshold")) / 100;
  const reduceRatio = Number(fd.get("reduce_ratio")) / 100;
  showLoading(true);
  try {
    const data = await api(`/risk/auto-reduce?threshold=${threshold}&reduce_ratio=${reduceRatio}`);
    const el = document.getElementById("auto-reduce-result");
    if (!data.orders?.length) {
      el.innerHTML = '<div class="empty-state">当前无需减仓（所有持仓浮亏在阈值内）</div>';
      toast("检测完成，无需减仓", "success");
    } else {
      el.innerHTML = `
        <div style="padding:0.75rem">
          <p style="color:var(--amber);font-weight:600;margin-bottom:0.5rem">发现 ${data.orders.length} 笔需减仓</p>
          ${data.orders.map((o) => `<p>${o.instrument_id}: ${o.side} ${o.quantity} 股</p>`).join("")}
        </div>`;
      toast(`浮亏减仓建议: ${data.orders.length} 笔`, "warning");
    }
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("position-sizer-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const mode = fd.get("mode");
  const symbols = fd.get("symbols");
  showLoading(true);
  try {
    const data = await api(`/position-sizer/calculate?mode=${encodeURIComponent(mode)}&symbols=${encodeURIComponent(symbols)}`, {
      method: "POST",
    });
    const tbody = document.querySelector("#position-sizer-table tbody");
    if (!data.results?.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">无数据</td></tr>';
    } else {
      tbody.innerHTML = data.results.map((r) => `<tr>
        <td>${r.instrument}</td>
        <td>${fmtPct(r.weight, 1)}</td>
        <td>${fmtNum(r.target_value, 0)}</td>
        <td>${fmtNum(r.target_quantity, 0)}</td>
      </tr>`).join("");
    }
    toast(`仓位计算完成 (${mode}): ${data.results.length} 个标的`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
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
    const strats = status.strategies || [];
    document.getElementById("live-strategy-id").textContent = strats.length ? strats.map(s => s.id).join(", ") : "-";
    const syms = strats.flatMap(s => s.instruments || []);
    document.getElementById("live-symbol").textContent = syms.length ? syms.join(", ") : "-";
    document.getElementById("live-bars-count").textContent = status.bar_count ?? 0;
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
  await loadWsStatus();
  toast("状态已刷新", "success");
});

// ── WebSocket Feed Controls ─────────────────────────────────

async function loadWsStatus() {
  try {
    const data = await api("/live/ws-status");
    const stateEl = document.getElementById("ws-state");
    const state = data.feed_state || "disconnected";
    stateEl.textContent = state === "connected" ? "已连接" : state === "reconnecting" ? "重连中" : "未连接";
    stateEl.className = "kpi-value" + (state === "connected" ? " positive" : state === "reconnecting" ? " negative" : "");
    document.getElementById("ws-reconnects").textContent = data.websocket?.reconnect_count ?? 0;
  } catch { /* silent */ }
}

document.getElementById("ws-connect-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const url = fd.get("ws_url");
  const symbols = fd.get("ws_symbols") || "";
  showLoading(true);
  try {
    await api(`/live/ws-connect?url=${encodeURIComponent(url)}&symbols=${encodeURIComponent(symbols)}`, {
      method: "POST",
    });
    toast("WebSocket 行情源已连接（含自动重连）", "success");
    await loadWsStatus();
    await loadLiveStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("ws-disconnect-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/live/ws-disconnect", { method: "POST" });
    toast("WebSocket 行情源已断开", "info");
    await loadWsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

// ── Ops Center (Scheduler + Guardian) ────────────────────────

async function loadOpsStatus() {
  try {
    const [sched, guard] = await Promise.all([
      api("/scheduler/status"),
      api("/guardian/status"),
    ]);

    const sr = document.getElementById("ops-scheduler-running");
    sr.textContent = sched.running ? "运行中" : "停止";
    sr.className = "kpi-value" + (sched.running ? " positive" : "");
    document.getElementById("ops-task-count").textContent = sched.task_count ?? 0;

    const gr = document.getElementById("ops-guardian-running");
    gr.textContent = guard.running ? "运行中" : "停止";
    gr.className = "kpi-value" + (guard.running ? " positive" : "");
    document.getElementById("ops-process-count").textContent = guard.process_count ?? 0;

    // task table
    const taskTb = document.querySelector("#ops-task-table tbody");
    const tasks = sched.tasks || [];
    taskTb.innerHTML = tasks.length === 0
      ? '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">暂无定时任务</td></tr>'
      : tasks.map(t => `<tr>
          <td>${t.name}</td>
          <td><span class="badge">${t.type}</span></td>
          <td>${t.run_time || (t.interval ? t.interval + "s 间隔" : "-")}</td>
          <td>${t.run_count}</td>
          <td>${t.error_count > 0 ? '<span class="negative">' + t.error_count + "</span>" : "0"}</td>
          <td>${t.enabled ? "✅ 启用" : "⏸ 禁用"}</td>
          <td><button class="btn btn-ghost" style="padding:2px 8px;font-size:0.75rem" onclick="runTaskNow('${t.name}')">立即执行</button></td>
        </tr>`).join("");

    // process table
    const procTb = document.querySelector("#ops-process-table tbody");
    const procs = guard.processes || [];
    const stateMap = { stopped: "已停止", running: "运行中", crashed: "已崩溃", restarting: "重启中", max_restarts_reached: "已放弃" };
    procTb.innerHTML = procs.length === 0
      ? '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">暂无被守护进程</td></tr>'
      : procs.map(p => `<tr>
          <td>${p.name}</td>
          <td><span class="${p.state === "running" ? "positive" : p.state === "crashed" ? "negative" : ""}">${stateMap[p.state] || p.state}</span></td>
          <td>${p.pid || "-"}</td>
          <td>${p.uptime_seconds > 0 ? fmtNum(p.uptime_seconds, 0) + "s" : "-"}</td>
          <td>${p.restart_count} / ${p.max_restarts}</td>
          <td>${p.last_crash || "-"}</td>
          <td><button class="btn btn-ghost" style="padding:2px 8px;font-size:0.75rem" onclick="restartProcess('${p.name}')">重启</button></td>
        </tr>`).join("");
  } catch { /* page not active yet */ }
}

async function runTaskNow(name) {
  showLoading(true);
  try {
    const r = await api(`/scheduler/run?task_name=${encodeURIComponent(name)}`, { method: "POST" });
    toast(`任务 "${name}" 执行${r.status === "success" ? "成功" : "失败"}`, r.status === "success" ? "success" : "error");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
}

async function restartProcess(name) {
  showLoading(true);
  try {
    await api(`/guardian/restart?name=${encodeURIComponent(name)}`, { method: "POST" });
    toast(`进程 "${name}" 正在重启`, "success");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
}

document.getElementById("ops-scheduler-start-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/scheduler/start", { method: "POST" });
    toast("定时任务调度器已启动", "success");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("ops-scheduler-stop-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/scheduler/stop", { method: "POST" });
    toast("定时任务调度器已停止", "info");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("ops-guardian-start-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/guardian/start", { method: "POST" });
    toast("进程守护器已启动", "success");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("ops-guardian-stop-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    await api("/guardian/stop", { method: "POST" });
    toast("进程守护器已停止（所有子进程已终止）", "info");
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("ops-refresh-btn").addEventListener("click", async () => {
  await loadOpsStatus();
  toast("运维状态已刷新", "success");
});

// ── Walk-Forward ───────────────────────────────────────────

document.getElementById("walkforward-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const bt = document.getElementById("backtest-form");
  const btFd = new FormData(bt);
  const params = new URLSearchParams();
  params.set("strategy", btFd.get("strategy"));
  params.set("symbol", btFd.get("symbol"));
  params.set("start", btFd.get("start") || new Date(new Date().getFullYear() - 1, 0, 1).toISOString().slice(0, 10));
  params.set("end", btFd.get("end") || new Date().toISOString().slice(0, 10));
  params.set("capital", btFd.get("capital") || "1000000");
  params.set("train_days", fd.get("in_sample_days"));
  params.set("test_days", fd.get("out_sample_days"));
  params.set("use_demo_data", btFd.get("use_demo_data") === "on" ? "true" : "false");
  showLoading(true);
  try {
    const data = await api(`/walkforward/run?${params.toString()}`, { method: "POST" });
    const resEl = document.getElementById("walkforward-result");
    resEl.innerHTML = `<div style="padding:0.75rem">
      <p>窗口数: <strong>${data.num_windows}</strong> | 平均测试 Sharpe: <strong>${fmtNum(data.avg_test_sharpe, 3)}</strong> | 一致性: <strong>${fmtPct(data.consistency_ratio)}</strong></p>
      <p style="font-size:0.8rem;color:var(--text-muted)">一致性比率 = 盈利窗口数 / 总窗口数，> 50% 表示较稳健</p>
    </div>`;

    const tbody = document.querySelector("#walkforward-table tbody");
    tbody.innerHTML = (data.windows || []).map((w, i) => {
      const cls = w.return >= 0 ? "positive" : "negative";
      return `<tr>
        <td>${w.id || i + 1}</td>
        <td>-</td>
        <td>${fmtNum(w.sharpe, 3)}</td>
        <td class="${cls}">${fmtPct(w.return)}</td>
        <td>-</td>
      </tr>`;
    }).join("") || '<tr><td colspan="5" class="empty-state">无数据</td></tr>';
    toast(`Walk-Forward 完成: ${data.num_windows} 窗口`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

// ── TWAP / VWAP 执行算法预览 ────────────────────────────────

document.getElementById("algo-preview-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams();
  params.set("algorithm", fd.get("algorithm"));
  params.set("symbol", fd.get("symbol"));
  params.set("side", fd.get("side"));
  params.set("total_quantity", fd.get("total_quantity"));
  params.set("num_slices", fd.get("num_slices"));
  params.set("interval_seconds", fd.get("interval_seconds"));
  showLoading(true);
  try {
    const data = await api(`/algo/preview?${params.toString()}`, { method: "POST" });
    const tbody = document.querySelector("#algo-slices-table tbody");
    tbody.innerHTML = (data.slices || []).map((s) => {
      const extra = s.time_offset != null ? s.time_offset + "s" : (s.volume_pct != null ? fmtPct(s.volume_pct) : "-");
      return `<tr>
        <td>${s.index + 1}</td>
        <td>${fmtNum(s.quantity, 0)}</td>
        <td>${extra}</td>
      </tr>`;
    }).join("");
    toast(`${data.algorithm.toUpperCase()} 拆单: ${data.num_slices} 切片`, "success");
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

// ── 追踪止损 / 条件单字段切换 ──────────────────────────────

document.querySelector('#paper-order-form [name="order_type"]').addEventListener("change", (e) => {
  const v = e.target.value;
  document.getElementById("trailing-stop-fields").style.display = v === "trailing_stop" ? "block" : "none";
  document.getElementById("conditional-fields").style.display = v === "conditional" ? "block" : "none";
});

// ── 活跃订单（实时策略页）──────────────────────────────────

async function loadActiveOrders() {
  try {
    const data = await api("/live/orders");
    const tbody = document.querySelector("#live-orders-table tbody");
    const emptyEl = document.getElementById("live-orders-empty");
    if (!data.orders?.length) {
      tbody.innerHTML = "";
      emptyEl.style.display = "block";
    } else {
      emptyEl.style.display = "none";
      tbody.innerHTML = data.orders.map((o) => `<tr>
        <td style="font-size:0.75rem;font-family:var(--mono)">${o.order_id}</td>
        <td>${o.symbol}</td>
        <td>${o.side}</td>
        <td>${o.type}</td>
        <td>${o.quantity}</td>
        <td>${o.price}</td>
        <td>${o.status}</td>
      </tr>`).join("");
    }
  } catch { /* silent */ }
}

document.getElementById("live-orders-refresh-btn").addEventListener("click", async () => {
  await loadActiveOrders();
  toast("订单状态已刷新", "success");
});

// ── 券商网关 ──────────────────────────────────────────────

async function loadGateways() {
  try {
    const data = await api("/gateway/list");
    const tbody = document.querySelector("#gateway-table tbody");
    tbody.innerHTML = (data.gateways || []).map((gw) => {
      const statusCls = gw.status === "connected" ? "positive" : gw.status === "not_configured" ? "" : "negative";
      const statusText = gw.status === "connected" ? "已连接" : gw.status === "not_configured" ? "未配置" : "未连接";
      const canConnect = gw.type === "paper" || gw.status !== "not_configured";
      return `<tr>
        <td>${gw.display}</td>
        <td><span class="badge">${gw.type}</span></td>
        <td class="${statusCls}">${statusText}</td>
        <td style="font-size:0.75rem;color:var(--text-muted)">${gw.note || "-"}</td>
        <td>${canConnect ? `<button class="btn btn-ghost" style="padding:2px 8px;font-size:0.75rem" onclick="connectGateway('${gw.name}')">连接</button>` : "-"}</td>
      </tr>`;
    }).join("");
  } catch { /* silent */ }
}

async function connectGateway(name) {
  showLoading(true);
  try {
    const r = await api(`/gateway/connect?name=${encodeURIComponent(name)}`, { method: "POST" });
    toast(`网关 ${name} ${r.status === "connected" ? "连接成功" : "连接失败: " + (r.error || "")}`, r.status === "connected" ? "success" : "error");
    await loadGateways();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
}

document.getElementById("gateway-refresh-btn").addEventListener("click", async () => {
  await loadGateways();
  toast("网关状态已刷新", "success");
});

// ── 事前四重风控规则 ─────────────────────────────────────

async function loadRiskRules() {
  try {
    const data = await api("/risk/rules");
    const tbody = document.querySelector("#risk-rules-table tbody");
    tbody.innerHTML = (data.rules || []).map((r) => {
      const displayVal = typeof r.value === "number" && r.value < 1 && r.value > 0 ? fmtPct(r.value) : r.value;
      return `<tr>
        <td><strong>${r.name}</strong></td>
        <td>${displayVal}</td>
        <td style="font-size:0.8rem;color:var(--text-muted)">${r.desc}</td>
        <td>
          <input type="number" step="any" value="${r.value}" style="width:80px;padding:3px 6px;background:var(--bg-elevated);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:0.8rem"
                 onchange="updateRiskRule('${r.key}', this.value)" />
        </td>
      </tr>`;
    }).join("");
    const statusEl = document.getElementById("risk-rules-status");
    statusEl.innerHTML = `冻结: ${data.frozen ? '<span class="negative">是</span>' : '否'} | 策略暂停: ${data.strategies_halted ? '<span class="negative">是</span>' : '否'}`;
  } catch { /* silent */ }
}

async function updateRiskRule(key, value) {
  showLoading(true);
  try {
    const params = new URLSearchParams();
    params.set(key, value);
    await api(`/risk/rules/update?${params.toString()}`, { method: "POST" });
    toast(`风控规则 ${key} 已更新为 ${value}`, "success");
    await loadRiskRules();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
}

document.getElementById("risk-rules-refresh-btn").addEventListener("click", async () => {
  await loadRiskRules();
  toast("风控规则已刷新", "success");
});

// ── 添加定时任务 / 添加被守护进程 ──────────────────────────

document.getElementById("add-task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams();
  params.set("name", fd.get("name"));
  params.set("task_type", fd.get("task_type"));
  params.set("run_time", fd.get("run_time"));
  params.set("interval", fd.get("interval"));
  showLoading(true);
  try {
    await api(`/scheduler/add?${params.toString()}`, { method: "POST" });
    toast(`定时任务 "${fd.get("name")}" 已添加`, "success");
    e.target.reset();
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

document.getElementById("add-process-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams();
  params.set("name", fd.get("name"));
  params.set("command", fd.get("command"));
  params.set("max_restarts", fd.get("max_restarts"));
  showLoading(true);
  try {
    await api(`/guardian/add?${params.toString()}`, { method: "POST" });
    toast(`被守护进程 "${fd.get("name")}" 已添加`, "success");
    e.target.reset();
    await loadOpsStatus();
  } catch (err) { toast(err.message, "error"); }
  finally { showLoading(false); }
});

// ── Blacklist Management (P2-7) ─────────────────────────────

async function loadBlacklist() {
  try {
    const data = await api("/risk/blacklist");
    const container = document.getElementById("blacklist-list");
    if (!data.blacklist.length) {
      container.innerHTML = '<div class="empty-state">黑名单为空</div>';
      return;
    }
    container.innerHTML = data.blacklist
      .map(
        (s) =>
          `<div class="instrument-item" style="margin-bottom:0.2rem">
            <span>${s}</span>
            <button class="btn btn-sm btn-danger-outline blacklist-rm-btn" data-symbol="${s}">移除</button>
          </div>`,
      )
      .join("");
    container.querySelectorAll(".blacklist-rm-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/risk/blacklist/remove?symbol=${encodeURIComponent(btn.dataset.symbol)}`, { method: "POST" });
        toast(`${btn.dataset.symbol} 已从黑名单移除`, "success");
        await loadBlacklist();
      });
    });
  } catch {
    /* silent */
  }
}

document.getElementById("blacklist-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const symbol = fd.get("symbol").trim();
  if (!symbol) return;
  try {
    await api(`/risk/blacklist/add?symbol=${encodeURIComponent(symbol)}`, { method: "POST" });
    toast(`${symbol} 已加入黑名单`, "success");
    e.target.reset();
    await loadBlacklist();
  } catch (err) {
    toast(err.message, "error");
  }
});

// ── Liquidity Filter (P2-7) ─────────────────────────────────

async function loadLiquidityConfig() {
  try {
    const data = await api("/risk/liquidity");
    const form = document.getElementById("liquidity-form");
    form.querySelector('[name="min_volume"]').value = data.min_volume;
    form.querySelector('[name="min_turnover"]').value = data.min_turnover;
    form.querySelector('[name="enabled"]').checked = data.enabled;
    const statusEl = document.getElementById("liquidity-status");
    statusEl.textContent = data.enabled
      ? `已启用 — 最低量 ${data.min_volume.toLocaleString()} 股 / 最低额 ¥${data.min_turnover.toLocaleString()}`
      : "已关闭";
  } catch {
    /* silent */
  }
}

document.getElementById("liquidity-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const params = new URLSearchParams();
  params.set("min_volume", fd.get("min_volume"));
  params.set("min_turnover", fd.get("min_turnover"));
  params.set("enabled", fd.has("enabled") ? "true" : "false");
  try {
    await api(`/risk/liquidity/update?${params}`, { method: "POST" });
    toast("流动性过滤设置已保存", "success");
    await loadLiquidityConfig();
  } catch (err) {
    toast(err.message, "error");
  }
});

// ── Daily Report & Consecutive Loss (P2-8) ──────────────────

document.getElementById("daily-report-btn").addEventListener("click", async () => {
  showLoading(true);
  try {
    const data = await api("/risk/daily-report");
    document.getElementById("daily-report-empty").style.display = "none";
    document.getElementById("daily-report-content").style.display = "block";

    document.getElementById("dr-balance").textContent = fmtNum(data.account.balance, 0);
    const pnlEl = document.getElementById("dr-daily-pnl");
    pnlEl.textContent = fmtNum(data.order_summary.daily_pnl, 2);
    setMetricColor(pnlEl, data.order_summary.daily_pnl);
    document.getElementById("dr-orders").textContent = data.order_summary.total_orders;
    document.getElementById("dr-positions").textContent = data.positions.length;

    document.getElementById("dr-consec-current").textContent = data.consecutive_loss.current_streak;
    document.getElementById("dr-consec-max").textContent = data.consecutive_loss.max_streak;
    document.getElementById("dr-consec-threshold").textContent = data.consecutive_loss.pause_threshold;
    document.getElementById("consec-loss-threshold").value = data.consecutive_loss.pause_threshold;

    const alertEl = document.getElementById("dr-pause-alert");
    alertEl.style.display = data.consecutive_loss.should_pause ? "block" : "none";

    const tbody = document.querySelector("#dr-history-table tbody");
    if (data.order_history.length) {
      tbody.innerHTML = data.order_history
        .reverse()
        .map((h) => {
          const pnlClass = (h.pnl || 0) >= 0 ? "positive" : "negative";
          return `<tr>
            <td>${h.time ? h.time.slice(0, 19) : "-"}</td>
            <td>${h.symbol || "-"}</td>
            <td>${h.side || "-"}</td>
            <td class="${pnlClass}">${fmtNum(h.pnl, 2)}</td>
          </tr>`;
        })
        .join("");
    } else {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">暂无交易记录</td></tr>';
    }
    toast("日报已生成", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

document.getElementById("consec-loss-save-btn").addEventListener("click", async () => {
  const val = document.getElementById("consec-loss-threshold").value;
  try {
    await api(`/risk/consecutive-loss-config?threshold=${val}`, { method: "POST" });
    toast(`连续亏损阈值已设为 ${val}`, "success");
  } catch (err) {
    toast(err.message, "error");
  }
});

document.getElementById("consec-loss-check-btn").addEventListener("click", async () => {
  try {
    const data = await api("/risk/consecutive-loss-check", { method: "POST" });
    if (data.triggered) {
      toast(`连续亏损 ${data.consecutive_losses} 笔，策略已暂停！`, "error");
    } else {
      toast(`当前连续亏损 ${data.consecutive_losses} 笔，未达阈值 ${data.threshold}`, "info");
    }
    await loadRiskStatus();
  } catch (err) {
    toast(err.message, "error");
  }
});

// ── Config Management (P2-10) ───────────────────────────────

const CONFIG_LABELS = {
  system: {
    _title: "系统配置",
    name: "系统名称",
    log_level: "日志级别",
    timezone: "时区",
    data_dir: "数据目录",
  },
  data: {
    _title: "数据配置",
    default_store: "存储引擎",
    parquet_dir: "Parquet 目录",
    duckdb_path: "DuckDB 路径",
  },
  risk: {
    _title: "风控配置",
    max_position_pct: "单标的持仓上限",
    max_single_order_pct: "单笔下单上限",
    max_daily_loss_pct: "日亏损上限",
    max_order_frequency: "下单频率上限(次/时)",
  },
  backtest: {
    _title: "回测配置",
    default_commission: "默认佣金率",
    default_slippage: "默认滑点率",
    initial_capital: "默认初始资金",
  },
};

let _configCache = null;

async function loadConfigEditor() {
  try {
    const data = await api("/config");
    _configCache = data;
    const editor = document.getElementById("config-editor");
    let html = "";
    for (const [section, fields] of Object.entries(CONFIG_LABELS)) {
      const sectionData = data[section] || {};
      html += `<div style="margin-bottom:0.5rem">
        <h4 style="font-size:0.85rem;margin-bottom:0.35rem;color:var(--accent)">${fields._title}</h4>
        <div class="settings-grid">`;
      for (const [key, label] of Object.entries(fields)) {
        if (key === "_title") continue;
        const val = sectionData[key] ?? "";
        html += `<div class="setting-item">
          <div class="key">${label}</div>
          <input type="text" class="config-input" data-section="${section}" data-key="${key}"
            value="${val}"
            style="width:100%;padding:0.25rem 0.4rem;margin-top:0.15rem;background:var(--bg-base);border:1px solid var(--border);border-radius:4px;color:var(--text);font-family:var(--mono);font-size:0.8rem" />
        </div>`;
      }
      html += "</div></div>";
    }
    editor.innerHTML = html;
  } catch {
    /* silent */
  }
}

document.getElementById("config-save-all-btn").addEventListener("click", async () => {
  const inputs = document.querySelectorAll(".config-input");
  let saved = 0;
  let errors = [];
  showLoading(true);
  for (const input of inputs) {
    const section = input.dataset.section;
    const key = input.dataset.key;
    const origVal = _configCache?.[section]?.[key];
    const newVal = input.value;
    if (String(origVal) === newVal) continue;
    try {
      const params = new URLSearchParams({ section, key, value: newVal });
      await api(`/config/update?${params}`, { method: "POST" });
      saved++;
    } catch (err) {
      errors.push(`${section}.${key}: ${err.message}`);
    }
  }
  showLoading(false);
  if (errors.length) {
    toast(`保存出错: ${errors.join("; ")}`, "error");
  } else if (saved > 0) {
    toast(`已保存 ${saved} 项配置`, "success");
    await loadConfigEditor();
  } else {
    toast("无修改", "info");
  }
});

document.getElementById("config-reset-btn").addEventListener("click", async () => {
  if (!confirm("确认恢复所有配置到默认值？")) return;
  showLoading(true);
  try {
    await api("/config/reset", { method: "POST" });
    toast("配置已恢复默认值", "success");
    await loadConfigEditor();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
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

function setDefaultDates() {
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const oneYearAgo = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
  const oneYearAgoStr = oneYearAgo.toISOString().slice(0, 10);

  document.querySelectorAll('#backtest-form [name="start"]').forEach(el => { el.value = oneYearAgoStr; });
  document.querySelectorAll('#backtest-form [name="end"]').forEach(el => { el.value = todayStr; });
  document.querySelectorAll('#fetch-form [name="start"]').forEach(el => { if (!el.value) el.value = oneYearAgoStr; });
  document.querySelectorAll('#fetch-form [name="end"]').forEach(el => { if (!el.value) el.value = todayStr; });
  document.querySelectorAll('#optimize-form [name="start"]').forEach(el => { el.value = oneYearAgoStr; });
  document.querySelectorAll('#optimize-form [name="end"]').forEach(el => { el.value = todayStr; });
}

async function init() {
  setDefaultDates();
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
      loadRiskRules(),
      loadLiveStatus(),
      loadActiveOrders(),
      loadAIFeatures(),
      loadAIModels(),
      loadOpsStatus(),
      loadGateways(),
      loadBlacklist(),
      loadLiquidityConfig(),
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
      loadRiskRules(),
      loadLiveStatus(),
      loadActiveOrders(),
      loadAIFeatures(),
      loadAIModels(),
      loadOpsStatus(),
      loadGateways(),
      loadBlacklist(),
      loadLiquidityConfig(),
    ]);
    toast("已刷新", "success");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    showLoading(false);
  }
});

init();
