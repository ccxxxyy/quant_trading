# 功能测试清单 & 功能展示手册

本文档包含两部分：
1. **功能测试清单**：逐项验证系统所有功能是否正常
2. **功能展示手册**：演示系统所有可展示的功能和效果

---

## 第一部分：功能测试清单

### 一、核心框架层

#### 1.1 事件总线（EventBus）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| C-01 | 事件发布与订阅 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_subscribe_and_publish` | 订阅者收到发布的事件 |
| C-02 | 多处理器订阅 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_multiple_handlers` | 同一事件类型多个处理器都被调用 |
| C-03 | 取消订阅 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_unsubscribe` | 取消后不再接收事件 |
| C-04 | 全局订阅 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_subscribe_all` | 接收所有类型的事件 |
| C-05 | 事件计数 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_event_count` | 正确统计已发布事件数 |
| C-06 | 处理器异常隔离 | `uv run pytest tests/unit/test_event_bus.py::TestEventBus::test_handler_error_does_not_stop_others` | 一个处理器抛异常不影响其他处理器 |

#### 1.2 时钟（Clock）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| C-07 | 模拟时钟推进 | `uv run python -c "from quant_trading.core.clock import SimulatedClock; c=SimulatedClock(); print(c.now()); c.advance_seconds(60); print(c.now())"` | 时间正确推进 60 秒 |
| C-08 | 实盘时钟 | `uv run python -c "from quant_trading.core.clock import LiveClock; c=LiveClock(); print(c.now())"` | 返回当前真实时间 |

#### 1.3 配置系统（Settings）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| C-09 | YAML 配置加载 | `uv run python -c "from quant_trading.core.config import Settings; s=Settings.load(); print(s.system.name, s.risk.max_position_pct)"` | 输出 `QuantTrading 0.25` |
| C-10 | 默认配置 | `uv run python -c "from quant_trading.core.config import Settings; s=Settings(); print(s.backtest.initial_capital)"` | 输出 `1000000.0` |

#### 1.4 主引擎（MainEngine）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| C-11 | 引擎初始化 | `uv run python -c "from quant_trading.core.engine import MainEngine; e=MainEngine(); print(e.mode)"` | 输出引擎模式 |

---

### 二、领域模型层

#### 2.1 交易标的（Instrument）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| M-01 | 标的 ID 解析 | `uv run pytest tests/unit/test_models.py::TestInstrumentId::test_from_str` | `600519.SSE` 解析为 symbol=600519, exchange=SSE |
| M-02 | 标的 ID 序列化 | `uv run pytest tests/unit/test_models.py::TestInstrumentId::test_to_str` | InstrumentId 正确转为字符串 |
| M-03 | 标的 ID 往返 | `uv run pytest tests/unit/test_models.py::TestInstrumentId::test_roundtrip` | 序列化 → 解析 → 再序列化结果一致 |

#### 2.2 K线数据（Bar）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| M-04 | 阳线判断 | `uv run pytest tests/unit/test_models.py::TestBar::test_is_bullish` | close >= open 时返回 True |
| M-05 | 阴线判断 | `uv run pytest tests/unit/test_models.py::TestBar::test_is_bearish` | close < open 时返回 True |

#### 2.3 持仓（Position）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| M-06 | 开多仓 | `uv run pytest tests/unit/test_models.py::TestPosition::test_open_long` | 成交后持仓数量和均价正确 |
| M-07 | 平多仓 | `uv run pytest tests/unit/test_models.py::TestPosition::test_close_long` | 平仓后数量归零，已实现盈亏正确 |
| M-08 | 浮动盈亏 | `uv run pytest tests/unit/test_models.py::TestPosition::test_unrealized_pnl` | (当前价 - 均价) × 数量 |

#### 2.4 订单（Order）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| M-09 | 订单生命周期 | `uv run pytest tests/unit/test_models.py::TestOrder::test_order_lifecycle` | PENDING → SUBMITTED → FILLED 状态流转正确 |

#### 2.5 订单状态机（OrderStateMachine）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| M-10 | 合法状态转换 | `uv run python -c "from quant_trading.model.order_state import OrderStateMachine; sm=OrderStateMachine(); print(sm.can_transition('pending','submitted'))"` | 输出 `True` |
| M-11 | 非法状态转换 | `uv run python -c "from quant_trading.model.order_state import OrderStateMachine; sm=OrderStateMachine(); print(sm.can_transition('filled','pending'))"` | 输出 `False` |

---

### 三、数据引擎层

#### 3.1 本地存储（DataStore）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| D-01 | 保存和加载 | `uv run pytest tests/unit/test_data_store.py::TestDataStore::test_save_and_load` | Parquet 文件正确读写 |
| D-02 | 标的列表 | `uv run pytest tests/unit/test_data_store.py::TestDataStore::test_list_instruments` | 列出已存储的所有标的 |
| D-03 | 日期范围过滤 | `uv run pytest tests/unit/test_data_store.py::TestDataStore::test_load_with_date_range` | 只返回指定日期范围内的数据 |
| D-04 | 空数据保存 | `uv run pytest tests/unit/test_data_store.py::TestDataStore::test_save_empty_bars` | 不报错，不创建空文件 |
| D-05 | DataFrame 加载 | `uv run pytest tests/unit/test_data_store.py::TestDataStore::test_load_df` | 返回 Polars DataFrame |

#### 3.2 数据清洗管道（DataPipeline）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| D-06 | 数据清洗全流程 | `uv run python -c "from quant_trading.data.pipeline import DataPipeline; p=DataPipeline(); print(p)"` | 管道对象创建成功 |
| D-07 | 去重 + 无效过滤 + OHLC 修正 | `uv run python scripts/test_new_modules.py` (DataPipeline 部分) | 输出清洗统计信息 |

#### 3.3 数据源（需要网络）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| D-08 | AkShare A股数据 | `uv run quant data fetch 600519.SSE --start 2024-01-01 --provider akshare` | 下载贵州茅台日线数据并保存 |
| D-09 | AkShare 期货数据 | `uv run quant data fetch AU2412.SHFE --start 2024-01-01 --provider akshare` | 下载黄金期货数据 |
| D-10 | yfinance 美股数据 | `uv run quant data fetch AAPL.NASDAQ --start 2024-01-01 --provider yfinance` | 下载苹果股票数据 |
| D-11 | 列出本地数据 | `uv run quant data list` | 列出已下载的所有标的和条数 |
| D-12 | 前复权加载 | `uv run python -c "from quant_trading.data.adjust import AdjustType, adjust_bars, detect_adjust_factors; from quant_trading.model.market import Bar, BarInterval; from quant_trading.model.instrument import InstrumentId, Exchange; from datetime import datetime; from decimal import Decimal; inst=InstrumentId('TEST',Exchange.SSE); bars=[Bar(inst,datetime(2024,1,i),BarInterval.DAILY,Decimal('10'),Decimal('11'),Decimal('9'),Decimal('10'),1000) for i in range(1,6)]; bars[2]=Bar(inst,datetime(2024,1,3),BarInterval.DAILY,Decimal('7'),Decimal('8'),Decimal('6.5'),Decimal('7.5'),1000); f=detect_adjust_factors(bars); adj=adjust_bars(bars,f,AdjustType.FORWARD); print(len(f), float(adj[0].close))"` | 检测到跳变并输出调整后的收盘价 |
| D-13 | DataStore 复权参数 | `uv run python -c "from quant_trading.data.store import DataStore; from quant_trading.data.adjust import AdjustType; s=DataStore(); print(hasattr(s.load_bars,'__call__'), AdjustType.FORWARD.value)"` | load_bars 支持 adjust 参数 |

---

### 四、回测引擎

#### 4.1 回测核心
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-01 | 基础回测 | `uv run pytest tests/unit/test_backtest.py::TestBacktestEngine::test_basic_backtest` | 回测正常完成，生成指标 |
| B-02 | 无数据回测 | `uv run pytest tests/unit/test_backtest.py::TestBacktestEngine::test_no_data_returns_empty_metrics` | 返回空指标不报错 |
| B-03 | 买卖产生盈亏 | `uv run pytest tests/unit/test_backtest.py::TestBacktestEngine::test_buy_and_sell_produces_pnl` | 最终资金 ≠ 初始资金 |

#### 4.2 撮合引擎
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-04 | 市价单撮合 | `uv run pytest tests/unit/test_matching.py::TestMatchingEngine::test_market_order_fills_at_open` | 以开盘价 + 滑点成交 |
| B-05 | 限价买入成交 | `uv run pytest tests/unit/test_matching.py::TestMatchingEngine::test_limit_buy_fills_when_price_drops` | 价格跌到限价时成交 |
| B-06 | 限价买入未成交 | `uv run pytest tests/unit/test_matching.py::TestMatchingEngine::test_limit_buy_no_fill_when_price_high` | 价格未到限价不成交 |
| B-07 | 撤单 | `uv run pytest tests/unit/test_matching.py::TestMatchingEngine::test_cancel_order` | 成功撤销未成交订单 |
| B-08 | 手续费计算 | `uv run pytest tests/unit/test_matching.py::TestMatchingEngine::test_commission_applied` | 成交回报包含正确手续费 |
| B-09 | T+1 当日卖拒 | `uv run python -c "from quant_trading.backtest.matching import MatchingEngine; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import Order, OrderSide, OrderType; from quant_trading.model.market import Bar, BarInterval; from datetime import datetime; from decimal import Decimal; m=MatchingEngine(enable_t1=True); inst=InstrumentId('600519',Exchange.SSE); bar=Bar(inst,datetime(2024,6,1),BarInterval.DAILY,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100.5'),1000); buy=Order(inst,OrderSide.BUY,OrderType.MARKET,100); m.submit_order(buy); m.on_bar(bar); sell=Order(inst,OrderSide.SELL,OrderType.MARKET,100); m.submit_order(sell); m.on_bar(bar); print(buy.status.value, sell.status.value)"` | 买入成交、当日卖出被拒绝 |
| B-10 | 卖出印花税 | `uv run python -c "from quant_trading.backtest.matching import MatchingEngine; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import Order, OrderSide, OrderType; from quant_trading.model.market import Bar, BarInterval; from datetime import datetime; from decimal import Decimal; m=MatchingEngine(stamp_tax_rate=0.0005); inst=InstrumentId('600519',Exchange.SSE); bar=Bar(inst,datetime(2024,6,1),BarInterval.DAILY,Decimal('100'),Decimal('101'),Decimal('99'),Decimal('100'),1000); o=Order(inst,OrderSide.SELL,OrderType.MARKET,100); m.submit_order(o); m.on_bar(bar); print(float(o.commission))"` | 卖出手续费含印花税 |
| B-11 | 涨跌停过滤 | `uv run python -c "from quant_trading.backtest.matching import MatchingEngine; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import Order, OrderSide, OrderType; from quant_trading.model.market import Bar, BarInterval; from datetime import datetime; from decimal import Decimal; m=MatchingEngine(price_limit_pct=0.10); inst=InstrumentId('600519',Exchange.SSE); bar=Bar(inst,datetime(2024,6,1),BarInterval.DAILY,Decimal('100'),Decimal('110'),Decimal('100'),Decimal('110'),1000); buy=Order(inst,OrderSide.BUY,OrderType.MARKET,100); m.submit_order(buy); m.on_bar(bar); print(buy.status.value)"` | 涨停封板时买单不成交 |

#### 4.3 绩效分析
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-12 | 基础指标计算 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_compute_basic_metrics` | 夏普、回撤等指标正确 |
| B-13 | 含交易的分析 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_with_trades` | 胜率、盈亏比等交易指标正确 |
| B-14 | 报告格式化 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_format_report` | 输出可读的文本报告 |
| B-15 | 空曲线处理 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_empty_curve` | 不报错返回默认值 |

#### 4.4 回测集成测试
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-16 | 双均线策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_full_backtest_with_demo_data` | 完整回测流程通过 |
| B-17 | RSI 策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_rsi_strategy_backtest` | 通过 |
| B-18 | MACD 策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_macd_strategy_backtest` | 通过 |
| B-19 | 海龟策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_turtle_strategy_backtest` | 通过 |
| B-20 | 布林带策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_bollinger_strategy_backtest` | 通过 |
| B-21 | A股增强回测 API | `POST /api/backtest/run` body 含 `"enable_t1":true,"adjust":"forward"` | 正常返回 metrics，无报错 |
| B-22 | 过户费计算 | 卖出+买入时 commission 均含 transfer_fee（默认万分之0.2） | 双向收取过户费 |
| B-23 | 追踪止损单 | 提交 TRAILING_STOP 订单，推入多根K线后回落触发 | 止损价跟随最高价浮动，回落达阈值后成交 |
| B-24 | 条件单 | 提交 CONDITIONAL 订单（condition_expr="close > 105"），推入 close=110 的K线 | 条件满足后自动市价成交 |

---

### 五、策略框架

#### 5.1 策略单元测试
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| S-01 | RSI 无报错运行 | `uv run pytest tests/unit/test_strategies.py::TestRSIReversionStrategy::test_rsi_strategy_runs_without_error` | 通过 |
| S-02 | RSI 指标计算 | `uv run pytest tests/unit/test_strategies.py::TestRSIReversionStrategy::test_rsi_computes_correctly` | RSI 值在 0-100 范围 |
| S-03 | RSI 全跌数据 | `uv run pytest tests/unit/test_strategies.py::TestRSIReversionStrategy::test_rsi_all_down` | 不崩溃，RSI 趋近 0 |
| S-04 | MACD 趋势数据 | `uv run pytest tests/unit/test_strategies.py::TestMACDStrategy::test_macd_on_trending_data` | 通过 |
| S-05 | MACD 触发交易 | `uv run pytest tests/unit/test_strategies.py::TestMACDStrategy::test_macd_triggers_trades_on_trend` | 产生交易活动 |
| S-06 | 海龟趋势数据 | `uv run pytest tests/unit/test_strategies.py::TestTurtleTradingStrategy::test_turtle_on_trending_data` | 通过 |
| S-07 | 海龟突破交易 | `uv run pytest tests/unit/test_strategies.py::TestTurtleTradingStrategy::test_turtle_enters_on_breakout` | 突破时产生交易 |
| S-08 | 双均线震荡数据 | `uv run pytest tests/unit/test_strategies.py::TestDualMovingAverageIntegration::test_dual_ma_on_oscillating_data` | 通过 |

#### 5.2 策略参数优化
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| S-09 | 网格搜索优化 | `uv run python scripts/test_new_modules.py` (StrategyOptimizer 部分) | 输出参数组合排名 |

---

### 六、风控与执行

#### 6.1 风控引擎
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-01 | 正常订单通过 | `uv run pytest tests/unit/test_risk_engine.py::TestRiskEngine::test_order_passes_normal_check` | 通过风控检查 |
| R-02 | 单笔超限拦截 | `uv run pytest tests/unit/test_risk_engine.py::TestRiskEngine::test_order_rejected_exceeds_size_limit` | 订单被拒绝 |
| R-03 | 集中度超限拦截 | `uv run pytest tests/unit/test_risk_engine.py::TestRiskEngine::test_order_rejected_position_concentration` | 订单被拒绝 |
| R-04 | 风控禁用 | `uv run pytest tests/unit/test_risk_engine.py::TestRiskEngine::test_disabled_engine_passes_all` | 禁用后所有订单通过 |
| R-05 | 下单频率限制 | `uv run pytest tests/unit/test_risk_engine.py::TestRiskEngine::test_order_frequency_limit` | 超频后被拒绝 |
| R-06 | 紧急冻结拦截 | `uv run python -c "from quant_trading.risk.engine import RiskEngine; from quant_trading.model.account import Account; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import Order, OrderSide, OrderType; from decimal import Decimal; a=Account('d',Decimal('100000'),Decimal('100000')); e=RiskEngine(a); e.emergency_freeze(); o=Order(InstrumentId('600519',Exchange.SSE),OrderSide.BUY,OrderType.MARKET,10,Decimal('100')); r=e.pre_trade_check(o,{}); print(r.approved, e.get_status()['frozen'])"` | approved=False，frozen=True |
| R-07 | 解除冻结 | 同上续接 `e.emergency_unfreeze(); print(e.get_status()['frozen'])` | frozen=False |
| R-08 | 策略暂停 | `uv run python -c "from quant_trading.risk.engine import RiskEngine; from quant_trading.model.account import Account; from decimal import Decimal; e=RiskEngine(Account('d',Decimal('100000'),Decimal('100000'))); e.halt_strategies(); print(e.get_status()['strategies_halted'])"` | strategies_halted=True |
| R-09 | 一键清仓信号 | `uv run python -c "from quant_trading.risk.engine import RiskEngine; from quant_trading.model.account import Account; from quant_trading.model.instrument import InstrumentId, Exchange; from decimal import Decimal; e=RiskEngine(Account('d',Decimal('100000'),Decimal('100000'))); pos={InstrumentId('600519',Exchange.SSE): type('P',(),{'quantity':100})()}; orders=e.close_all_positions(pos); print(len(orders), orders[0].side.value if orders else 'none')"` | 返回 sell 平仓订单列表 |

| R-10a | 浮亏自动减仓 | 调用 `check_unrealized_loss()`，传入浮亏超阈值的持仓 | 返回减仓市价订单列表 |
| R-10b | 仓位管理-等权 | `PositionSizer(EQUAL_WEIGHT).calculate(...)` 传入 3 个标的 | 三者权重均为 1/3，数量按100股对齐 |
| R-10c | 仓位管理-凯利 | `PositionSizer(KELLY).calculate(...)` 传入胜率和盈亏比 | 权重 = Kelly fraction，不超过 cap |

#### 6.2 投资组合管理
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-10 | 初始权益 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_initial_equity` | 等于初始余额 |
| R-11 | 加仓后权益 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_add_position_and_equity` | 权益 = 现金 + 持仓市值 |
| R-12 | 持仓集中度 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_concentration` | 百分比计算正确 |
| R-13 | 组合摘要 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_summary` | 返回完整字段 |
| R-14 | 净敞口 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_net_exposure_long_short` | 多头 - 空头 = 净值 |

#### 6.3 执行算法
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-15 | TWAP 拆单 | `uv run python -c "from quant_trading.execution.algorithms.twap import TWAPAlgorithm; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import OrderSide; t=TWAPAlgorithm(InstrumentId('TEST',Exchange.SSE), OrderSide.BUY, 1000, num_slices=5, interval_seconds=60); print(f'Slices: {t._num_slices}, Qty per slice: {t._slice_quantity}')"` | 1000 股拆成 5 份每份 200 |
| R-16 | VWAP 拆单 | `uv run python scripts/test_new_modules.py` (VWAP 部分) | 按成交量比例分配子单 |

#### 6.4 监控告警
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-17 | 回撤告警 | `uv run python scripts/test_new_modules.py` (AlertManager 部分) | 超阈值时触发告警 |
| R-18 | 告警计数和查询 | 同上 | `alert_count > 0`，`get_recent_alerts()` 返回告警列表 |

#### 6.5 实时策略运行器
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-19 | 运行器启停 | `uv run python -c "from quant_trading.strategy.runner import LiveStrategyRunner; r=LiveStrategyRunner(); print(r.is_running)"` | 初始 is_running=False |
| R-20 | Web 启停 API | `POST /api/live/start` → `GET /api/live/status` → `POST /api/live/stop` | running 状态随操作切换 |
| R-21 | WebSocket 行情源初始化 | `uv run python -c "from quant_trading.data.websocket_feed import WebSocketFeed, ConnectionState; f=WebSocketFeed(); assert f.state==ConnectionState.DISCONNECTED; print('OK')"` | 初始状态为 disconnected |
| R-22 | Runner WS 集成 | `uv run python -c "from quant_trading.strategy.runner import LiveStrategyRunner; r=LiveStrategyRunner(); s=r.get_status(); assert 'feed_state' in s; print('OK')"` | get_status 包含 feed_state 和 websocket 字段 |
| R-23 | 订单回调链路 | 注册 order callback → 发送 on_order_update(FILLED) | 回调被触发，completed 后自动清理 |
| R-24 | 行情缺失检测 | 设置 gap_timeout=5 → 订阅标的 → 超时不推送 | on_gap_detected 回调触发 |

---

### 七、交易网关

#### 7.1 模拟网关
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| G-01 | 模拟网关初始化 | `uv run python -c "from quant_trading.gateway.simulated import SimulatedGateway; g=SimulatedGateway(); print(g.name, g.is_connected)"` | 输出 `simulated False` |

#### 7.2 模拟盘网关
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| G-02 | 模拟盘初始化 | `uv run python -c "from quant_trading.gateway.paper import PaperTradingGateway; g=PaperTradingGateway(); print(g.name, g.is_connected)"` | 输出 `paper False` |

#### 7.3 CTP 期货网关
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| G-03 | CTP 桩模式连接 | `uv run python -c "import asyncio; from quant_trading.gateway.ctp import CTPGateway; gw=CTPGateway.create_simnow('test','pwd'); asyncio.run(gw.connect()); print(f'connected={gw.is_connected} stub={gw._stub_mode}')"` | `connected=True stub=True` |
| G-04 | CTP 桩模式下单 | `uv run python -c "import asyncio; from quant_trading.gateway.ctp import CTPGateway; from quant_trading.model.instrument import *; from quant_trading.model.order import *; from decimal import Decimal; gw=CTPGateway.create_simnow('t','p'); asyncio.run(gw.connect()); o=Order(InstrumentId('au2412',Exchange.SHFE),OrderSide.BUY,OrderType.LIMIT,1,Decimal('500')); oid=asyncio.run(gw.submit_order(o)); print(f'status={o.status.value}')"` | `status=submitted` |
| G-05 | CTP 桩模式撤单 | 同上续接 `cancel_order` | 订单状态变为 cancelled |
| G-06 | CTP 桩模式查持仓 | 同上续接 `query_positions` | 返回空列表 |
| G-07 | CTP 桩模式查账户 | 同上续接 `query_account` | 返回 Account 对象 |

#### 7.4 IB 网关
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| G-08 | IB 网关导入 | `uv run python -c "from quant_trading.gateway.ibkr import IBGateway; print('OK')"` | 输出 `OK` |

---

### 八、AI/机器学习模块

| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| A-01 | 因子引擎 | `uv run python -c "from quant_trading.alpha.feature import FeatureEngine; e=FeatureEngine(); e.register_defaults(); print(e.factor_names())"` | 输出已注册因子名列表 |
| A-02 | 预测服务 | `uv run python scripts/test_new_modules.py` (PredictService 部分) | 服务初始化成功 |
| A-03 | Walk-Forward 验证 | `uv run python scripts/test_new_modules.py` (WalkForwardValidator 部分) | 验证器创建成功 |

---

### 九、CLI 命令行

| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| L-01 | 系统信息 | `uv run quant info` | 输出版本号、Python 版本、配置信息 |
| L-02 | 回测（演示数据） | `uv run quant backtest dual_ma --symbol TEST.SSE --start 2024-01-01` | 输出绩效报告（使用内置演示数据） |
| L-03 | RSI 策略回测 | `uv run quant backtest rsi --symbol TEST.SSE --start 2024-01-01` | 输出绩效报告 |
| L-04 | MACD 策略回测 | `uv run quant backtest macd --symbol TEST.SSE --start 2024-01-01` | 输出绩效报告 |
| L-05 | 海龟策略回测 | `uv run quant backtest turtle --symbol TEST.SSE --start 2024-01-01` | 输出绩效报告 |
| L-06 | 自定义资金回测 | `uv run quant backtest dual_ma --symbol TEST.SSE --start 2024-01-01 --capital 50000` | 初始资金为 50000 |
| L-07 | 自定义参数回测 | `uv run quant backtest dual_ma --symbol TEST.SSE --start 2024-01-01 --params fast_period=5,slow_period=20` | 使用自定义均线参数 |
| L-08 | 数据列表 | `uv run quant data list` | 列出本地数据（可能为空） |

---

### 十、Web 仪表盘

> 启动命令：`uv run quant-web`，然后浏览器访问 `http://127.0.0.1:8888`

#### 10.1 API 接口（基础）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-01 | 健康检查 | `GET /api/health` | `{"status":"ok","version":"0.1.0"}` |
| W-02 | 系统信息 | `GET /api/system/info` | 返回版本、策略数、交易所数等 |
| W-03 | 策略列表 | `GET /api/strategies` | 返回 7 个内置策略及其参数 |
| W-04 | 本地数据列表 | `GET /api/data/instruments` | 返回已存储标的列表 |
| W-05 | 回测运行 | `POST /api/backtest/run` body: `{"strategy":"dual_ma","symbol":"TEST.SSE","start":"2024-01-01","use_demo_data":true}` | 返回 metrics、equity_curve、trades |
| W-06 | 自定义资金回测 | `POST /api/backtest/run` body: `{"strategy":"dual_ma","symbol":"TEST.SSE","start":"2024-01-01","capital":50000,"use_demo_data":true}` | initial_capital = 50000 |
| W-07 | 策略对比 | `POST /api/backtest/compare` | 返回多策略回测结果对比 |
| W-08 | 告警查询 | `GET /api/monitor/alerts` | 返回告警列表 |
| W-09 | AI 因子列表 | `GET /api/alpha/features` | 返回因子名、类型、依赖数据 |
| W-10 | K线预览 | `GET /api/data/bars/TEST.SSE` | 返回柱状数据（若有） |

#### 10.2 API 接口（参数优化）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-11 | 网格搜索 | `POST /api/optimize/run` body: `{"strategy":"dual_ma","symbol":"TEST.SSE","start":"2023-01-01","param_grid":{"fast_period":[5,10],"slow_period":[20,30]},"use_demo_data":true}` | 返回 results 数组（按 Sharpe 排序）和 total 数量 |
| W-12 | 跳过无效组合 | 同上，包含 fast_period > slow_period 的组合 | 无效组合被自动跳过 |

#### 10.3 API 接口（监控告警）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-13 | 告警阈值配置 | `GET /api/monitor/config` | 返回 thresholds 字典（max_drawdown, max_daily_loss 等） |
| W-14 | 发送测试告警 | `POST /api/monitor/test` | 返回 alerts 列表，count > 0 |

#### 10.4 API 接口（模拟盘）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-15 | 初始化模拟盘 | `POST /api/paper/connect` body: `{}` | status=connected，account.balance=1000000 |
| W-16 | 查询账户 | `GET /api/paper/account` | 返回 account 对象（balance, available, commission, currency） |
| W-17 | 查询持仓 | `GET /api/paper/positions` | 返回 positions 数组 |
| W-18 | 市价买入 | `POST /api/paper/order` body: `{"symbol":"600519.SSE","side":"buy","order_type":"market","quantity":100}` | status=filled，positions 含该标的，available 减少 |
| W-19 | 查询挂单 | `GET /api/paper/orders` | 返回 orders 数组 |
| W-20 | 重置模拟盘 | `POST /api/paper/connect` body: `{"initial_capital":500000}` | balance=500000，持仓清空 |

#### 10.5 API 接口（AI 实验室）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-21 | 特征计算 | `POST /api/alpha/compute?symbol=DEMO.SSE` | 返回 rows（最近 20 行）和 columns（含 momentum_5 等因子列） |
| W-22 | 可用模型 | `GET /api/alpha/models` | 返回 models 列表，包含 lightgbm |

#### 10.6 API 接口（紧急风控）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-23 | 风控状态 | `GET /api/risk/status` | 返回 frozen、strategies_halted、daily_pnl 等字段 |
| W-24 | 紧急冻结 | `POST /api/risk/freeze` | status.frozen=true |
| W-25 | 解除冻结 | `POST /api/risk/unfreeze` | status.frozen=false |
| W-26 | 暂停策略 | `POST /api/risk/halt` | status.strategies_halted=true |
| W-27 | 恢复策略 | `POST /api/risk/resume` | status.strategies_halted=false |
| W-28 | 一键清仓 | `POST /api/risk/close-all`（需先模拟盘持仓） | 返回 closed 数量，并自动冻结 |

#### 10.7 API 接口（实时策略）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-29 | 运行器状态 | `GET /api/live/status` | 返回 running、strategy_id、symbol |
| W-30 | 启动运行 | `POST /api/live/start?strategy_id=ma_cross&symbol=DEMO.SSE` | running=true |
| W-31 | 推送测试 K 线 | `POST /api/live/feed?symbol=DEMO.SSE&price=105&volume=2000` | 返回 fed=true |
| W-32 | 停止运行 | `POST /api/live/stop` | running=false |

#### 10.8 API 接口（A 股增强回测）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-33 | T+1 回测 | `POST /api/backtest/run` body 含 `"enable_t1":true,"use_demo_data":true` | 正常返回 metrics |
| W-34 | 前复权回测 | 同上 body 含 `"adjust":"forward"` | 正常返回 metrics |

#### 10.9 Web UI 页面（基础）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-35 | 总览页加载 | 浏览器打开首页 | 显示 4 个 KPI 卡片（标的数、策略数、资金、交易所） |
| W-36 | KPI 可点击 | 点击任一 KPI 卡片 | 跳转到对应页面 |
| W-37 | 数据管理页 | 点击"数据管理" | 显示数据源选择、标的输入、获取按钮 |
| W-38 | 回测实验室 | 点击"回测实验室" | 显示策略选择、参数配置、运行按钮 |
| W-39 | 回测运行 | 选择策略 → 运行回测 | 显示权益曲线、回撤图、指标面板、交易记录 |
| W-40 | 策略对比 | 点击"策略对比" | 同时回测所有策略并显示对比表和图表 |
| W-41 | 策略库页 | 点击"策略库" | 以卡片形式展示 7 个策略，每张有说明和参数 |
| W-42 | 设置页 | 点击"系统设置" | 显示风控参数、回测配置、系统信息 |
| W-43 | 初始资金自定义 | 在回测页修改资金为任意值（如 12345） | 回测使用自定义资金 |
| W-44 | 演示数据开关 | 勾选/取消"使用演示数据" | 勾选时无需下载数据即可回测 |
| W-45 | 复权模式选择 | 回测页"复权模式"下拉切换 | 可选不复权/前复权/后复权 |
| W-46 | T+1 开关 | 回测页勾选"T+1" | 勾选后当日买入次日才能卖出 |

#### 10.10 Web UI 页面（参数优化）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-47 | 参数优化页导航 | 点击侧栏"参数优化" | 显示优化配置表单和结果面板 |
| W-48 | 策略选择 → 参数范围自动生成 | 切换策略下拉 | 表单中自动出现该策略的参数搜索范围 |
| W-49 | 运行优化 | 填写参数范围 → 点击"开始优化" | 结果表格显示参数组合排名（按 Sharpe 降序） |
| W-50 | 最优 KPI 展示 | 优化完成后 | 顶部 KPI 显示最优 Sharpe、最优收益率、组合总数 |

#### 10.11 Web UI 页面（监控告警）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-51 | 告警页导航 | 点击侧栏"监控告警" | 显示 4 个告警统计 KPI + 阈值配置 + 告警记录表 |
| W-52 | 刷新告警 | 点击"刷新告警"按钮 | 告警列表重新加载 |
| W-53 | 测试告警 | 点击"发送测试告警" | 告警表格新增一条 info 级别记录 |
| W-54 | 告警级别徽章 | 查看告警记录 | critical 红色、warning 黄色、info 蓝色徽章 |

#### 10.12 Web UI 页面（模拟盘）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-55 | 模拟盘页导航 | 点击侧栏"模拟盘" | 显示 4 个账户 KPI + 下单面板 + 持仓/挂单表 |
| W-56 | 重置模拟盘 | 点击"重置模拟盘" | 账户回到初始资金，持仓清空 |
| W-57 | 市价买入 | 输入标的 → 买入 100 股 → 提交 | 持仓表出现该标的，可用资金减少 |
| W-58 | 市价卖出 | 选择卖出 → 提交 | 持仓表更新，已实现盈亏显示 |
| W-59 | 下单表单验证 | 切换市价/限价单类型 | 限价单时价格输入框可用 |

#### 10.13 Web UI 页面（风控中心）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-60 | 风控中心导航 | 点击侧栏"风控中心" | 显示 4 个状态 KPI + 紧急操作按钮 + 风控详情 |
| W-61 | 紧急冻结 | 点击"紧急冻结"按钮 | 账户状态变为"已冻结"（红色），toast 提示 |
| W-62 | 解除冻结 | 点击"解除冻结"按钮 | 账户状态恢复"正常"（绿色） |
| W-63 | 暂停策略 | 点击"暂停策略"按钮 | 策略状态变为"已暂停"（红色） |
| W-64 | 恢复策略 | 点击"恢复策略"按钮 | 策略状态恢复"运行中"（绿色） |
| W-65 | 一键清仓 | 点击"一键清仓" → 确认弹窗 | 显示清仓结果（平仓笔数、余额），自动冻结 |
| W-66 | 风控状态详情 | 查看详情面板 | 展示 frozen、strategies_halted、enabled、daily_pnl 等字段 |
| W-67 | 刷新状态 | 点击"刷新"按钮 | 所有 KPI 和详情面板数据更新 |

#### 10.14 Web UI 页面（实时策略）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-68 | 实时策略导航 | 点击侧栏"实时策略" | 显示 4 个 KPI + 启动面板 + K 线推送面板 |
| W-69 | 启动策略 | 选择策略、输入标的 → 点击"启动运行" | 运行状态变为"运行中"（绿色），显示策略名和标的 |
| W-70 | 停止策略 | 点击"停止运行" | 运行状态变为"停止" |
| W-71 | 推送 K 线 | 输入价格和成交量 → 点击"推送 K 线" | 推送记录列表新增一条，已接收 K 线数+1 |
| W-72 | 推送记录滚动 | 连续推送多次 | 最新记录在最上方，最多显示 20 条 |
| W-73 | 刷新状态 | 点击"刷新状态" | 所有 KPI 更新 |

#### 10.15 Web UI 页面（AI 实验室）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-74 | AI 实验室导航 | 点击侧栏"AI 实验室" | 显示因子表格 + 模型卡片 + 特征计算面板 |
| W-75 | 因子列表 | 进入 AI 实验室 | 表格展示 7 个因子（momentum、volatility、rsi、volume_ratio） |
| W-76 | 模型卡片 | 进入 AI 实验室 | 显示 LightGBM 模型卡片及"available"状态 |
| W-77 | 特征计算 | 输入标的 → 点击"计算特征" | 表格展示最近 20 行数据，包含所有因子列 |
| W-78 | 导航栏完整 | 查看侧栏 | 12 个导航按钮（总览/数据/回测/参数优化/监控告警/模拟盘/风控中心/实时策略/AI实验室/策略库/运维中心/设置） |
| W-79 | 回测过户费率 | 回测表单内修改"过户费率"字段 → 运行回测 | 手续费中包含过户费 |
| W-80 | 浮亏减仓表单 | 风控中心 → 设置阈值和减仓比例 → 点击"检测浮亏" | 返回减仓建议或"无需减仓" |
| W-81 | 仓位管理器 | 风控中心 → 选择模式 + 输入标的 → 点击"计算目标仓位" | 表格显示各标的权重/金额/股数 |
| W-82 | 仓位管理模式切换 | 依次选择等权/风险平价/凯利/固定金额 | 计算结果随模式变化 |
| W-83 | WebSocket 行情源面板 | 实时策略页 → 查看 WebSocket 行情源区域 | 显示 URL 输入、标的输入、连接/断开按钮、连接状态和重连次数 |
| W-84 | 连接 WebSocket | 启动策略后 → 输入 URL → 点击"连接行情源" | 提示"已连接"，状态显示"已连接" |
| W-85 | 断开 WebSocket | 点击"断开行情源" | 提示"已断开"，状态回到"未连接" |
| W-86 | WebSocket API: ws-connect | `POST /api/live/ws-connect?url=ws://...&symbols=X.SSE` | 返回 ws_connected + 完整 status |
| W-87 | WebSocket API: ws-disconnect | `POST /api/live/ws-disconnect` | 返回 ws_disconnected |
| W-88 | WebSocket API: ws-status | `GET /api/live/ws-status` | 返回 feed_state、websocket、active_orders |

#### 10.19 Web UI 页面（P1 补齐项）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-89 | Walk-Forward 面板 | 回测实验室 → 设置训练/测试窗口 → 运行 Walk-Forward | 显示窗口数、平均 Sharpe、一致性比率及窗口明细表 |
| W-90 | Walk-Forward API | `POST /api/walkforward/run?strategy=dual_ma&symbol=TEST.SSE&train_days=180&test_days=30&use_demo_data=true` | 返回 num_windows、avg_test_sharpe、windows 数组 |
| W-91 | TWAP 拆单预览 | 模拟盘 → TWAP/VWAP 面板 → 预览拆单 | 表格显示各切片数量与时间偏移 |
| W-92 | VWAP 拆单预览 | 同上，算法选 VWAP | 表格显示各切片数量与成交量权重 |
| W-93 | 追踪止损下单 | 模拟盘 → 类型选「追踪止损」→ 填写追踪距离 → 提交 | 订单进入挂单列表，status=submitted |
| W-94 | 条件单下单 | 模拟盘 → 类型选「条件单」→ 填写触发价 → 提交 | 订单进入挂单列表，等待价格触发 |
| W-95 | 活跃订单监控 | 实时策略 → 活跃订单面板 → 刷新 | 显示 order_id、标的、方向、类型、状态 |
| W-96 | 活跃订单 API | `GET /api/live/orders` | 返回 orders 数组和 count |
| W-97 | 事前风控规则展示 | 风控中心 → 事前四重风控规则表格 | 显示 4 条规则当前阈值 |
| W-98 | 事前风控规则修改 | 表格内修改阈值 → 自动提交 | toast 提示已更新，刷新后值生效 |
| W-99 | 风控规则 API | `GET /api/risk/rules` + `POST /api/risk/rules/update?max_position_pct=0.2` | 返回/更新 4 条规则 |
| W-100 | 添加定时任务 | 运维中心 → 添加定时任务表单 → 提交 | 任务列表新增一条，task_count+1 |
| W-101 | 添加被守护进程 | 运维中心 → 添加被守护进程表单 → 提交 | 进程列表新增一条，process_count+1 |
| W-102 | 券商网关列表 | 模拟盘 → 券商网关连接面板 | 显示 paper/ctp/ib 网关及状态 |
| W-103 | 连接模拟盘网关 | 点击 paper 网关「连接」按钮 | 状态变为已连接 |
| W-104 | 网关 API | `GET /api/gateway/list` + `POST /api/gateway/connect?name=paper` | 返回 gateways 列表及连接结果 |
| W-105 | 告警推送 Web 配置 | 监控告警 → 告警推送配置 → 保存并测试 | toast 提示配置成功 |

#### 10.17 数据中心扩展
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| D-10 | 指数代码识别 | `AkShareFeed._is_index("000001")` | 返回 True（上证指数） |
| D-11 | 可转债代码识别 | `AkShareFeed._is_convertible_bond("113050")` | 返回 True（南银转债） |
| D-12 | Tick 数据存储 | `DataStore.save_ticks()` → `load_ticks()` | 写入/读取 Tick Parquet 文件一致 |
| D-13 | Tick 数据回放 | `DataEngine.replay_ticks()` | 逐条发送 Tick 事件到事件总线 |
| D-14 | 数据源 Tick 接口 | `AkShareFeed.get_ticks()` | 返回 Tick 列表（实时快照） |

#### 10.18 运维支撑
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| O-01 | 调度器初始化 | `TaskScheduler()` + `get_status()` | running=False, task_count=0 |
| O-02 | 添加盘前任务 | `add_pre_market("test", handler, time(9,15))` | task_count=1, type=pre_market |
| O-03 | 添加盘后任务 | `add_post_market("test", handler, time(15,30))` | task_count 增加 |
| O-04 | 间隔任务 | `add_interval("check", handler, interval=60)` | interval_seconds=60 |
| O-05 | 手动执行任务 | `run_task_now("test")` | 返回 status=success, run_count=1 |
| O-06 | 进程守护器初始化 | `ProcessGuardian()` + `get_status()` | running=False, process_count=0 |
| O-07 | 注册被守护进程 | `add_process("web", ["echo","hi"])` | process_count=1, state=stopped |
| O-08 | 调度器 API | `GET /api/scheduler/status` | 返回 running、task_count、tasks 列表 |
| O-09 | 守护器 API | `GET /api/guardian/status` | 返回 running、process_count、processes 列表 |

#### 10.19 Web UI 页面（P1 补齐项）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-89 | Walk-Forward 面板 | 回测实验室 → 设置训练/测试窗口 → 运行 Walk-Forward | 显示窗口数、平均 Sharpe、一致性比率及窗口明细表 |
| W-90 | Walk-Forward API | `POST /api/walkforward/run?strategy=dual_ma&symbol=TEST.SSE&train_days=180&test_days=30&use_demo_data=true` | 返回 num_windows、windows 数组 |
| W-91 | TWAP 拆单预览 | 模拟盘 → TWAP/VWAP 面板 → 预览拆单 | 表格显示各切片数量与时间偏移 |
| W-92 | VWAP 拆单预览 | 同上，算法选 VWAP | 表格显示各切片数量与成交量权重 |
| W-93 | 执行算法 API | `POST /api/algo/preview?algorithm=twap&total_quantity=10000&num_slices=5` | 返回 slices 数组 |
| W-94 | 追踪止损下单 | 模拟盘 → 类型选「追踪止损」→ 填写追踪距离 → 提交 | 订单进入挂单列表，status=submitted |
| W-95 | 条件单下单 | 模拟盘 → 类型选「条件单」→ 填写触发价 → 提交 | 订单进入挂单列表，等待价格触发 |
| W-96 | 活跃订单面板 | 实时策略页 → 查看「活跃订单」表格 → 刷新 | 显示 order_id、标的、方向、类型、状态 |
| W-97 | 活跃订单 API | `GET /api/live/orders` | 返回 orders 数组和 count |
| W-98 | 事前风控规则 | 风控中心 → 查看「事前四重风控规则」表格 | 显示 4 条规则当前值，可在线修改 |
| W-99 | 风控规则 API | `GET /api/risk/rules` + `POST /api/risk/rules/update?max_position_pct=0.2` | 返回 4 条规则，修改后实时生效 |
| W-100 | 添加定时任务 | 运维中心 → 填写任务名/类型/时间 → 添加 | 任务列表新增一条，task_count+1 |
| W-101 | 添加被守护进程 | 运维中心 → 填写进程名/命令 → 添加 | 进程列表新增一条，process_count+1 |
| W-102 | 调度器添加 API | `POST /api/scheduler/add?name=测试任务&task_type=interval&interval=60` | status=added |
| W-103 | 守护器添加 API | `POST /api/guardian/add?name=测试进程&command=echo hi` | status=added |
| W-104 | 券商网关面板 | 模拟盘 → 查看「券商网关连接」表格 | 显示 paper/ctp/ibkr 状态及连接按钮 |
| W-105 | 网关连接 | 点击模拟盘网关「连接」 | status=connected，toast 提示成功 |
| W-106 | 网关 API | `GET /api/gateway/list` + `POST /api/gateway/connect?name=paper` | 返回 gateways 列表，连接后 status=connected |
| W-107 | 告警推送 Web 配置 | 监控告警 → 选择 Webhook/Email → 保存并测试 | toast 提示配置成功 |
| W-108 | Tick Web 拉取 | 数据管理 → 周期选「Tick 逐笔」→ 获取 | 成功返回 tick 数据并存储 |

#### 10.21 P2 可视化增强

| ID | 测试项 | 操作步骤 | 预期结果 |
|----|--------|---------|---------|
| W-109 | K线叠加买卖点 | 回测实验室 → 运行回测 → 查看「K 线叠加买卖点」面板 | 权益曲线上用 ▲/▼ 标注买入/卖出位置 |
| W-110 | Monte Carlo 运行 | 回测实验室 → 运行回测 → 「Monte Carlo 压力测试」→ 运行模拟 | KPI 显示 5%/50%/95% 分位，两张图表渲染 |
| W-111 | Monte Carlo API | `POST /api/backtest/montecarlo`（同回测参数） | 返回 n_simulations=500, stats, distribution, percentile_curves |
| W-112 | 复盘报表运行 | 回测实验室 → 运行回测 → 「复盘报表」→ 生成报表 | KPI 显示连胜/连亏/单笔盈亏，月度柱状图渲染 |
| W-113 | 复盘报表 API | `POST /api/backtest/review`（同回测参数） | 返回 monthly[], streaks, trade_analysis |
| W-114 | 参数热力图 | 参数优化 → 运行优化 → 回测页查看「参数优化热力图」 | 颜色矩阵表格，绿=高Sharpe，红=低Sharpe |
| W-115 | 黑名单添加 | 风控中心 → 「标的黑名单」→ 输入代码 → 加入黑名单 | 黑名单列表更新，标的显示「移除」按钮 |
| W-116 | 黑名单移除 | 风控中心 → 「标的黑名单」→ 点击标的旁「移除」 | 标的从黑名单消失 |
| W-117 | 黑名单拦截 | 加入黑名单后尝试对该标的下单 | 事前检查自动拒绝 |
| W-118 | 流动性过滤设置 | 风控中心 → 「流动性过滤」→ 设置阈值 → 保存 | 状态文字更新显示当前配置 |
| W-119 | 流动性过滤开关 | 取消「启用流动性过滤」复选框 → 保存 | 状态显示「已关闭」 |
| W-120 | 风控日报生成 | 风控中心 → 「风控日报」→ 点击「生成日报」 | 显示账户余额/盈亏/下单数/持仓/连亏统计 |
| W-121 | 连续亏损阈值 | 「连续亏损暂停阈值」输入框改值 → 保存阈值 | toast 提示保存成功 |
| W-122 | 连续亏损检测 | 点击「手动检测」 | 显示当前连亏笔数和是否触发暂停 |
| W-123 | 配置在线编辑 | 系统设置 → 修改某项配置值 → 保存全部修改 | toast 提示已保存 N 项，settings.yaml 已更新 |
| W-124 | 配置恢复默认 | 系统设置 → 点击「恢复默认」 | 所有配置恢复初始值 |
| W-125 | 风控日报 API | `GET /api/risk/daily-report` | 返回 account/risk_status/positions/consecutive_loss |
| W-126 | 黑名单 API | `GET /api/risk/blacklist` → `POST /api/risk/blacklist/add?symbol=X` | 黑名单列表包含 X |
| W-127 | 配置 API | `GET /api/config` → `POST /api/config/update?section=risk&key=max_position_pct&value=0.3` | settings.yaml 更新 |

---

### 十一、代码质量

| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| Q-01 | 全量单元测试 | `uv run pytest tests/ -v` | 55/55 通过 |
| Q-02 | Ruff 代码检查 | `uv run ruff check src/ tests/` | 无错误 |
| Q-03 | Ruff 格式检查 | `uv run ruff format --check src/ tests/` | 85 files already formatted |
| Q-04 | 全模块导入检查 | `uv run python -c "from quant_trading.core.event import EventBus; ..."` (见 ci.yml) | All imports OK |
| Q-05 | GitHub Actions CI | 推送到 dev/main 分支 | test、lint、import-check 三个 Job 全绿 |

---

### 十二、一键全量测试

```bash
# 运行所有自动化测试（约 3 秒）
uv run pytest tests/ -v --tb=short

# 运行代码质量检查
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 运行模块功能验证脚本
uv run python scripts/test_new_modules.py

# 运行多策略回测对比脚本
uv run python scripts/demo_backtest.py

# 启动 Web 仪表盘后运行 API 测试
uv run quant-web &
uv run python scripts/test_api.py
uv run python scripts/test_compare_api.py
```

---

## 第二部分：功能展示手册

### 展示一：系统总览

```bash
uv run quant info
```

**展示效果**：输出系统版本、Python 版本、配置路径、风控参数、支持的交易所列表。

---

### 展示二：一键回测

```bash
# 双均线策略回测（使用内置演示数据，无需网络）
uv run quant backtest dual_ma --symbol DEMO.SSE --start 2024-01-01

# RSI 反转策略回测
uv run quant backtest rsi --symbol DEMO.SSE --start 2024-01-01

# 海龟策略回测，自定义初始资金 50 万
uv run quant backtest turtle --symbol DEMO.SSE --start 2024-01-01 --capital 500000

# 双均线策略，自定义参数
uv run quant backtest dual_ma --symbol DEMO.SSE --start 2024-01-01 --params fast_period=5,slow_period=20,quantity=200
```

**展示效果**：每次输出完整的绩效报告，包括总收益率、年化收益率、夏普比率、最大回撤、胜率、盈亏比等 10 项指标。

---

### 展示三：多策略对比

```bash
uv run python scripts/demo_backtest.py
```

**展示效果**：同时回测 5 种策略（双均线、RSI、MACD、海龟、布林带），输出格式化对比表格，一目了然哪个策略历史表现最好。

---

### 展示四：Web 仪表盘

```bash
uv run quant-web
# 浏览器打开 http://127.0.0.1:8888
```

**展示流程**：

1. **总览页**
   - 4 个 KPI 卡片显示系统概况
   - 点击"内置策略"卡片 → 跳转策略库

2. **策略库**
   - 以卡片展示 7 种策略：双均线、布林带、RSI、MACD、海龟、网格、配对交易
   - 每张卡片有策略类型标签、参数说明、"使用此策略"按钮

3. **回测实验室**
   - 选择"双均线"策略
   - 勾选"使用演示数据"
   - 点击"运行回测"
   - **展示效果**：
     - 权益曲线图（资金随时间变化）
     - 回撤曲线图（每个时点距最高点的跌幅）
     - 10 项绩效指标面板
     - 逐笔交易记录表
   - 修改初始资金为 `50000` → 重新回测 → 观察指标变化
   - 点击"策略对比" → 横向对比所有策略的表现

4. **数据管理**（需网络）
   - 数据源选择 "AkShare"
   - 输入标的代码 `600519.SSE`
   - 点击"获取数据"
   - **展示效果**：下载贵州茅台日线数据，显示 K 线图预览

5. **系统设置**
   - 查看风控参数（单笔限额 10%、集中度 25%、日亏损 5%、频率 100次/小时）
   - 查看回测默认配置（初始资金、手续费率、滑点）

---

### 展示五：参数优化（Web）

**展示流程**：

1. 左侧点击 **「参数优化」**
2. 策略选 **双均线**
3. 系统自动生成搜索范围（快线: 5,10,15,20 / 慢线: 20,30,40,60）
4. 点击 **「开始优化」**
5. **展示效果**：
   - 顶部 KPI 显示最优 Sharpe、最优收益率、组合总数
   - 结果表格按 Sharpe 降序排名，第一行蓝色高亮
   - 每行显示参数组合、收益率、Sharpe、最大回撤、胜率、交易数

---

### 展示六：监控告警（Web）

**展示流程**：

1. 左侧点击 **「监控告警」**
2. 查看阈值配置面板（回撤 10%、日亏损 5 万等）
3. 点击 **「发送测试告警」**
4. **展示效果**：
   - 告警统计 KPI 更新（info +1）
   - 告警记录表格新增一条记录，蓝色 info 徽章
5. 点击 **「刷新告警」** 确认数据同步

---

### 展示七：模拟盘交易（Web）

**展示流程**：

1. 左侧点击 **「模拟盘」**
2. 点击 **「重置模拟盘」** → 账户初始化为 100 万
3. 下单面板输入 `600519.SSE` → 买入 → 市价 → 数量 100 → **「提交订单」**
4. **展示效果**：
   - 账户 KPI 更新：可用资金减少约 1 万元，手续费出现
   - 持仓表新增一行：600519.SSE / long / 100 / 均价约 100
5. 再次下单：卖出 100 股
6. **展示效果**：持仓清空，已实现盈亏显示

---

### 展示八：AI 实验室（Web）

**展示流程**：

1. 左侧点击 **「AI 实验室」**
2. **因子表格**：展示 7 个 Alpha 因子（momentum_5/10/20、volatility_10/20、rsi_14、volume_ratio_20）
3. **模型卡片**：LightGBM 模型（available 状态）
4. 特征计算区：输入 `DEMO.SSE` → 点击 **「计算特征」**
5. **展示效果**：
   - 表格展示 120 行 × 13 列数据（最近 20 行可见）
   - 列包括 timestamp、OHLCV 和 7 个因子值

---

### 展示九：Web 全功能演示

**所有功能均可在浏览器中完成操作**，启动后访问 http://127.0.0.1:8888 即可使用：

| 序号 | 功能 | 对应页面 | 操作说明 |
|------|------|---------|---------|
| 1 | 系统总览 | 总览 | 查看 4 个 KPI 卡片，点击任一卡片跳转 |
| 2 | 数据获取 | 数据管理 | 选数据源 → 输标的 → 点击获取 → K 线预览 |
| 3 | 运行回测 | 回测实验室 | 选策略/复权/T+1 → 运行 → 查看曲线和指标 |
| 4 | 策略对比 | 回测实验室 | 点击"策略对比" → 多策略横向比较 |
| 5 | 参数优化 | 参数优化 | 选策略 → 自动生成搜索范围 → 运行 → 排名 |
| 6 | 监控告警 | 监控告警 | 查看阈值/告警记录 → 发送测试告警 |
| 7 | 模拟盘交易 | 模拟盘 | 重置 → 下单买入 → 查看持仓/挂单 |
| 8 | 紧急风控 | 风控中心 | 冻结/解冻/暂停策略/一键清仓 |
| 9 | 实时策略 | 实时策略 | 启动策略 → 推送 K 线 → 查看状态 → 停止 |
| 10 | AI 因子 | AI 实验室 | 查看因子列表/模型 → 计算特征 |
| 11 | 策略库 | 策略库 | 卡片式展示 → 一键跳转回测 |

**展示效果**：12 个页面覆盖系统所有功能，无需任何命令行操作。

---

### 展示十：风控引擎演示

```python
# uv run python
from quant_trading.risk.engine import RiskEngine
from quant_trading.model.account import Account
from quant_trading.model.instrument import InstrumentId, Exchange, Currency
from quant_trading.model.order import Order, OrderSide, OrderType
from decimal import Decimal

account = Account(account_id="demo", balance=Decimal("100000"), available=Decimal("100000"))
engine = RiskEngine(account)

# 正常订单 → 通过
order_ok = Order(
    instrument_id=InstrumentId("600519", Exchange.SSE),
    side=OrderSide.BUY, order_type=OrderType.MARKET,
    quantity=10, price=Decimal("1800"),
)
result = engine.pre_trade_check(order_ok, {})
print(f"正常订单: {result}")  # approved=True

# 超大订单（超过总资金 10%）→ 拒绝
order_big = Order(
    instrument_id=InstrumentId("600519", Exchange.SSE),
    side=OrderSide.BUY, order_type=OrderType.MARKET,
    quantity=100, price=Decimal("1800"),
)
result = engine.pre_trade_check(order_big, {})
print(f"超大订单: {result}")  # approved=False, reason=单笔金额超限
```

**展示效果**：直观演示风控引擎如何自动拦截超限订单，以及紧急冻结如何阻断所有新订单。

---

### 展示十一：A 股增强回测（复权 / T+1 / 涨跌停 / 印花税）

**操作步骤：**

1. 左侧点击 **「回测实验室」**
2. 策略选 **双均线**，标的填 `600519.SSE`
3. **复权模式**下拉选 **「前复权（推荐 A 股）」**
4. 勾选 **「T+1（当日买入次日才能卖）」**
5. 勾选 **「使用演示数据」** → 点击 **「运行回测」**
6. 再取消 T+1 和复权，用同一策略再跑一次回测做对比

**展示效果**：同一策略在 A 股规则下交易次数、手续费（含印花税）可能与默认模式不同，回测更贴近真实 A 股环境。页面上直接可看到差异。

---

### 展示十二：紧急风控与一键清仓

**操作步骤：**

1. 先在 **「模拟盘」** 页重置并买入 100 股茅台
2. 切换到 **「风控中心」** 页
3. 查看 4 个状态 KPI：账户状态=正常、策略状态=运行中
4. 点击 **「紧急冻结」** → 账户状态变为红色"已冻结"
5. 切回模拟盘尝试下单 → 应失败（被冻结拦截）
6. 回到风控中心，点击 **「一键清仓」** → 确认弹窗 → 清仓结果面板显示平仓笔数和余额
7. 点击 **「解除冻结」** → 账户恢复正常

**展示效果**：直观演示实盘"保命"流程——异常时一键冻结 + 批量平仓，全部在界面完成，无需敲命令。

---

### 展示十三：实时策略运行器

**操作步骤：**

1. 左侧点击 **「实时策略」**
2. 策略选择 **双均线**，标的填 `DEMO.SSE`
3. 点击 **「启动运行」** → 运行状态变为绿色"运行中"
4. 在右侧 **「手动推送 K 线」** 面板，输入价格 100、成交量 1000 → 点击 **「推送 K 线」**
5. 多次推送不同价格（如 102、98、105）→ 推送记录列表实时滚动
6. 观察"已接收 K 线"KPI 数字递增
7. 点击 **「停止运行」** → 状态恢复为"停止"

**展示效果**：策略在后台持续运行，推送 K 线后自动处理信号，全过程在页面完成。

---

### 展示十三B：WebSocket 实时行情接入

**操作步骤：**

1. 先按展示十三启动策略运行器
2. 在启动面板下方找到 **「WebSocket 行情源」** 区域
3. URL 栏保持默认 `ws://127.0.0.1:9999/ws/market`（或填入实际行情源地址）
4. 标的列表栏留空（自动使用策略绑定标的）或填入 `600519.SSE`
5. 点击 **「连接行情源」** → 提示"WebSocket 行情源已连接（含自动重连）"
6. 观察连接状态变为 **"已连接"**（绿色），重连次数为 0
7. 如断线会自动重连，重连次数递增
8. 点击 **「断开行情源」** → 状态回到"未连接"

**展示效果**：一键接入外部 WebSocket 行情源，自动维护连接（含指数退避重连、行情缺失检测），无需编写连接代码。

---

### 展示十三C：订单状态回调链路

```python
# uv run python
from quant_trading.strategy.runner import LiveStrategyRunner
from quant_trading.model.order import Order, OrderType, OrderSide, OrderStatus
from quant_trading.model.instrument import InstrumentId
from decimal import Decimal

runner = LiveStrategyRunner()
order = Order(
    instrument_id=InstrumentId.from_str("DEMO.SSE"),
    order_type=OrderType.LIMIT,
    side=OrderSide.BUY,
    quantity=Decimal("100"),
    price=Decimal("10.0"),
)

# 注册回调
runner._active_orders[order.order_id] = order
runner.register_order_callback(
    order.order_id,
    lambda o, f: print(f"回调触发: {o.order_id[:8]} → {o.status.value}")
)

# 模拟网关回报
order.status = OrderStatus.FILLED
runner.on_order_update(order)
# 输出: 回调触发: xxxxxxxx → filled
```

**展示效果**：注册回调后，网关成交回报自动分发到策略和回调函数，订单完成后自动清理。

---

### 展示十四：CTP 期货网关演示

```python
# uv run python
import asyncio
from quant_trading.gateway.ctp import CTPGateway
from quant_trading.model.instrument import InstrumentId, Exchange
from quant_trading.model.order import Order, OrderSide, OrderType
from decimal import Decimal

async def demo():
    # 创建 SimNow 模拟盘网关（桩模式，无需真实账号）
    gw = CTPGateway.create_simnow("demo_user", "demo_pwd")
    await gw.connect()
    print(f"连接状态: {gw.is_connected}, 桩模式: {gw._stub_mode}")

    # 订阅黄金期货行情
    await gw.subscribe_market_data([InstrumentId("au2412", Exchange.SHFE)])

    # 提交限价买单
    order = Order(
        instrument_id=InstrumentId("au2412", Exchange.SHFE),
        side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=1, price=Decimal("560.0"),
    )
    await gw.submit_order(order)
    print(f"订单状态: {order.status.value}")

    # 撤单
    await gw.cancel_order(order.order_id)
    print(f"撤单后: {order.status.value}")

    # 查询账户
    account = await gw.query_account()
    print(f"账户: {account.account_id}")

    await gw.disconnect()
    print("已断开")

asyncio.run(demo())
```

**展示效果**：演示 CTP 网关的完整交易流程（连接 → 订阅 → 下单 → 撤单 → 查询 → 断开）。

---

### 展示十五：数据清洗管道演示

```python
# uv run python
from quant_trading.data.pipeline import DataPipeline
from quant_trading.model.market import Bar, BarInterval
from quant_trading.model.instrument import InstrumentId, Exchange
from datetime import datetime
from decimal import Decimal

pipeline = DataPipeline()
inst = InstrumentId("TEST", Exchange.SSE)

# 构造含脏数据的 Bar 列表
bars = [
    Bar(inst, datetime(2024,1,1), BarInterval.DAILY, Decimal("100"), Decimal("110"), Decimal("95"), Decimal("105"), 10000),
    Bar(inst, datetime(2024,1,1), BarInterval.DAILY, Decimal("100"), Decimal("110"), Decimal("95"), Decimal("105"), 10000),  # 重复
    Bar(inst, datetime(2024,1,2), BarInterval.DAILY, Decimal("-1"), Decimal("110"), Decimal("95"), Decimal("105"), 10000),  # 无效价格
    Bar(inst, datetime(2024,1,3), BarInterval.DAILY, Decimal("102"), Decimal("112"), Decimal("97"), Decimal("108"), 12000),
]

cleaned, stats = pipeline.process(bars)
print(f"原始: {len(bars)} 条 → 清洗后: {len(cleaned)} 条")
print(stats.summary())
```

**展示效果**：4 条原始数据经过去重、无效过滤后剩余 2 条有效数据。

---

### 展示十六：55 项自动化测试

```bash
uv run pytest tests/ -v --tb=short
```

**展示效果**：55 个测试用例全部通过（绿色），覆盖事件总线、模型、回测、撮合、绩效分析、数据存储、投资组合、风控引擎、4 种策略的完整测试矩阵。

---

### 展示十七：GitHub Actions CI/CD

**展示位置**：GitHub 仓库 → Actions 标签页

**展示效果**：
- **test** Job：在 ubuntu + windows × Python 3.12 + 3.13（4 种组合）上自动运行 pytest
- **lint** Job：ruff 代码检查 + 格式检查
- **import-check** Job：验证 50+ 模块的导入链完整性

---

### 展示十八：标的黑名单管理

**展示位置**：Web 风控中心 → 标的黑名单面板

**操作步骤**：
1. 在输入框输入 `600519.SSE` → 点击「加入黑名单」
2. 列表出现该标的及「移除」按钮
3. 在模拟盘尝试对 `600519.SSE` 下单 → 被事前检查拒绝
4. 点击「移除」→ 标的从列表消失

**展示效果**：通过 Web 界面管理交易黑名单，黑名单内的标的在事前风控检查中被自动拦截。

---

### 展示十九：流动性过滤

**展示位置**：Web 风控中心 → 流动性过滤面板

**操作步骤**：
1. 设置最低成交量 10,000 股、最低成交额 1,000,000 元
2. 勾选「启用流动性过滤」→ 保存设置
3. 状态显示启用信息

**展示效果**：通过阈值设置自动过滤低流动性品种，避免无法成交或异常价格。

---

### 展示二十：风控日报 & 连续亏损暂停

**展示位置**：Web 风控中心 → 风控日报 & 连续亏损暂停面板

**操作步骤**：
1. 设置连续亏损阈值为 3 → 保存
2. 点击「生成日报」→ 查看 KPI 卡片（余额/盈亏/下单/持仓/连亏统计）
3. 点击「手动检测」→ 查看当前连亏状态
4. 若连续亏损达到阈值，红色警告出现且策略自动暂停

**展示效果**：一键生成当日风控日报，连续亏损超限时自动保护策略停止交易。

---

### 展示二十一：可视化配置管理

**展示位置**：Web 系统设置页面

**操作步骤**：
1. 在配置编辑器中修改风控参数（如 `max_position_pct` 从 0.25 改为 0.3）
2. 点击「保存全部修改」→ toast 提示保存成功
3. 检查 `config/settings.yaml` 文件已同步更新
4. 点击「恢复默认」→ 所有配置回到初始值

**展示效果**：无需手动编辑 YAML，通过 Web 界面在线修改系统全部配置并持久化。

---

### 功能总览数字

| 维度 | 数量 |
|------|------|
| 源代码模块 | 50+ 个 `.py` 文件 |
| 内置策略 | 7 种（双均线、布林带、RSI、MACD、海龟、网格、配对交易） |
| 支持交易所 | 10 个（SSE、SZSE、CFFEX、SHFE、DCE、CZCE、NYSE、NASDAQ、BINANCE、IB） |
| 交易网关 | 4 个（模拟、模拟盘、CTP、IB） |
| 绩效指标 | 10 项（收益率、年化、夏普、最大回撤、Calmar、胜率、盈亏比等） |
| 风控检查 | 4 重事前检查 + 紧急冻结/清仓/策略暂停 + 黑名单 + 流动性过滤 + 连续亏损暂停 |
| 执行算法 | 2 种（TWAP、VWAP） |
| AI 因子 | 4 类 7 个（动量×3、波动率×2、RSI、量比） |
| Web API | 44 个端点 |
| Web 页面 | 12 个（总览、数据、回测、参数优化、监控告警、模拟盘、风控中心、实时策略、AI实验室、策略库、运维中心、设置） |
| CLI 命令 | 4 个（info、data fetch、data list、backtest） |
| 单元测试 | 55 个用例 |
| 功能测试项 | 127 项 Web 测试 + 95+ 项全系统测试 |
| 展示场景 | 23 个（含 A 股增强、紧急风控、Monte Carlo、复盘报表、热力图、黑名单、流动性过滤、配置管理） |
| CI 矩阵 | 4 种环境（2 OS × 2 Python） |
