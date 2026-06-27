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

#### 4.3 绩效分析
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-09 | 基础指标计算 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_compute_basic_metrics` | 夏普、回撤等指标正确 |
| B-10 | 含交易的分析 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_with_trades` | 胜率、盈亏比等交易指标正确 |
| B-11 | 报告格式化 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_format_report` | 输出可读的文本报告 |
| B-12 | 空曲线处理 | `uv run pytest tests/unit/test_analyzer.py::TestBacktestAnalyzer::test_empty_curve` | 不报错返回默认值 |

#### 4.4 回测集成测试
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| B-13 | 双均线策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_full_backtest_with_demo_data` | 完整回测流程通过 |
| B-14 | RSI 策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_rsi_strategy_backtest` | 通过 |
| B-15 | MACD 策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_macd_strategy_backtest` | 通过 |
| B-16 | 海龟策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_turtle_strategy_backtest` | 通过 |
| B-17 | 布林带策略端到端 | `uv run pytest tests/integration/test_backtest_flow.py::TestBacktestIntegration::test_bollinger_strategy_backtest` | 通过 |

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

#### 6.2 投资组合管理
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-06 | 初始权益 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_initial_equity` | 等于初始余额 |
| R-07 | 加仓后权益 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_add_position_and_equity` | 权益 = 现金 + 持仓市值 |
| R-08 | 持仓集中度 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_concentration` | 百分比计算正确 |
| R-09 | 组合摘要 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_summary` | 返回完整字段 |
| R-10 | 净敞口 | `uv run pytest tests/unit/test_portfolio.py::TestPortfolioManager::test_net_exposure_long_short` | 多头 - 空头 = 净值 |

#### 6.3 执行算法
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-11 | TWAP 拆单 | `uv run python -c "from quant_trading.execution.algorithms.twap import TWAPAlgorithm; from quant_trading.model.instrument import InstrumentId, Exchange; from quant_trading.model.order import OrderSide; t=TWAPAlgorithm(InstrumentId('TEST',Exchange.SSE), OrderSide.BUY, 1000, num_slices=5, interval_seconds=60); print(f'Slices: {t._num_slices}, Qty per slice: {t._slice_quantity}')"` | 1000 股拆成 5 份每份 200 |
| R-12 | VWAP 拆单 | `uv run python scripts/test_new_modules.py` (VWAP 部分) | 按成交量比例分配子单 |

#### 6.4 监控告警
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| R-13 | 回撤告警 | `uv run python scripts/test_new_modules.py` (AlertManager 部分) | 超阈值时触发告警 |
| R-14 | 告警计数和查询 | 同上 | `alert_count > 0`，`get_recent_alerts()` 返回告警列表 |

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

#### 10.6 Web UI 页面（基础）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-23 | 总览页加载 | 浏览器打开首页 | 显示 4 个 KPI 卡片（标的数、策略数、资金、交易所） |
| W-24 | KPI 可点击 | 点击任一 KPI 卡片 | 跳转到对应页面 |
| W-25 | 数据管理页 | 点击"数据管理" | 显示数据源选择、标的输入、获取按钮 |
| W-26 | 回测实验室 | 点击"回测实验室" | 显示策略选择、参数配置、运行按钮 |
| W-27 | 回测运行 | 选择策略 → 运行回测 | 显示权益曲线、回撤图、指标面板、交易记录 |
| W-28 | 策略对比 | 点击"策略对比" | 同时回测所有策略并显示对比表和图表 |
| W-29 | 策略库页 | 点击"策略库" | 以卡片形式展示 7 个策略，每张有说明和参数 |
| W-30 | 设置页 | 点击"系统设置" | 显示风控参数、回测配置、系统信息 |
| W-31 | 初始资金自定义 | 在回测页修改资金为任意值（如 12345） | 回测使用自定义资金 |
| W-32 | 演示数据开关 | 勾选/取消"使用演示数据" | 勾选时无需下载数据即可回测 |

#### 10.7 Web UI 页面（参数优化）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-33 | 参数优化页导航 | 点击侧栏"参数优化" | 显示优化配置表单和结果面板 |
| W-34 | 策略选择 → 参数范围自动生成 | 切换策略下拉 | 表单中自动出现该策略的参数搜索范围 |
| W-35 | 运行优化 | 填写参数范围 → 点击"开始优化" | 结果表格显示参数组合排名（按 Sharpe 降序） |
| W-36 | 最优 KPI 展示 | 优化完成后 | 顶部 KPI 显示最优 Sharpe、最优收益率、组合总数 |

#### 10.8 Web UI 页面（监控告警）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-37 | 告警页导航 | 点击侧栏"监控告警" | 显示 4 个告警统计 KPI + 阈值配置 + 告警记录表 |
| W-38 | 刷新告警 | 点击"刷新告警"按钮 | 告警列表重新加载 |
| W-39 | 测试告警 | 点击"发送测试告警" | 告警表格新增一条 info 级别记录 |
| W-40 | 告警级别徽章 | 查看告警记录 | critical 红色、warning 黄色、info 蓝色徽章 |

#### 10.9 Web UI 页面（模拟盘）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-41 | 模拟盘页导航 | 点击侧栏"模拟盘" | 显示 4 个账户 KPI + 下单面板 + 持仓/挂单表 |
| W-42 | 重置模拟盘 | 点击"重置模拟盘" | 账户回到初始资金，持仓清空 |
| W-43 | 市价买入 | 输入标的 → 买入 100 股 → 提交 | 持仓表出现该标的，可用资金减少 |
| W-44 | 市价卖出 | 选择卖出 → 提交 | 持仓表更新，已实现盈亏显示 |
| W-45 | 下单表单验证 | 切换市价/限价单类型 | 限价单时价格输入框可用 |

#### 10.10 Web UI 页面（AI 实验室）
| 编号 | 测试项 | 验证方法 | 预期结果 |
|------|--------|---------|---------|
| W-46 | AI 实验室导航 | 点击侧栏"AI 实验室" | 显示因子表格 + 模型卡片 + 特征计算面板 |
| W-47 | 因子列表 | 进入 AI 实验室 | 表格展示 7 个因子（momentum、volatility、rsi、volume_ratio） |
| W-48 | 模型卡片 | 进入 AI 实验室 | 显示 LightGBM 模型卡片及"available"状态 |
| W-49 | 特征计算 | 输入标的 → 点击"计算特征" | 表格展示最近 20 行数据，包含所有因子列 |
| W-50 | 导航栏完整 | 查看侧栏 | 9 个导航按钮（总览/数据/回测/参数优化/监控告警/模拟盘/AI实验室/策略库/设置） |

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

### 展示九：Web API 接口

```bash
# 启动 Web 服务后，在另一个终端运行：

# 1. 健康检查
curl http://127.0.0.1:8888/api/health

# 2. 查看所有策略
curl http://127.0.0.1:8888/api/strategies

# 3. 运行回测
curl -X POST http://127.0.0.1:8888/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"strategy":"dual_ma","symbol":"TEST.SSE","start":"2024-01-01","use_demo_data":true}'

# 4. 参数优化
curl -X POST http://127.0.0.1:8888/api/optimize/run \
  -H "Content-Type: application/json" \
  -d '{"strategy":"dual_ma","symbol":"TEST.SSE","start":"2023-01-01","param_grid":{"fast_period":[5,10],"slow_period":[20,30]},"use_demo_data":true}'

# 5. 模拟盘下单
curl -X POST http://127.0.0.1:8888/api/paper/connect -H "Content-Type: application/json" -d '{}'
curl -X POST http://127.0.0.1:8888/api/paper/order \
  -H "Content-Type: application/json" \
  -d '{"symbol":"600519.SSE","side":"buy","order_type":"market","quantity":100}'

# 6. AI 特征计算
curl -X POST "http://127.0.0.1:8888/api/alpha/compute?symbol=DEMO.SSE"

# 7. 监控告警
curl http://127.0.0.1:8888/api/monitor/config
curl -X POST http://127.0.0.1:8888/api/monitor/test
```

**展示效果**：全部 20 个 API 端点返回 JSON 格式数据，可被任何前端/脚本调用。

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

**展示效果**：直观演示风控引擎如何自动拦截超限订单。

---

### 展示十一：CTP 期货网关演示

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

### 展示十二：数据清洗管道演示

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

### 展示十三：55 项自动化测试

```bash
uv run pytest tests/ -v --tb=short
```

**展示效果**：55 个测试用例全部通过（绿色），覆盖事件总线、模型、回测、撮合、绩效分析、数据存储、投资组合、风控引擎、4 种策略的完整测试矩阵。

---

### 展示十四：GitHub Actions CI/CD

**展示位置**：GitHub 仓库 → Actions 标签页

**展示效果**：
- **test** Job：在 ubuntu + windows × Python 3.12 + 3.13（4 种组合）上自动运行 pytest
- **lint** Job：ruff 代码检查 + 格式检查
- **import-check** Job：验证 50+ 模块的导入链完整性

---

### 功能总览数字

| 维度 | 数量 |
|------|------|
| 源代码模块 | 50+ 个 `.py` 文件 |
| 内置策略 | 7 种（双均线、布林带、RSI、MACD、海龟、网格、配对交易） |
| 支持交易所 | 10 个（SSE、SZSE、CFFEX、SHFE、DCE、CZCE、NYSE、NASDAQ、BINANCE、IB） |
| 交易网关 | 4 个（模拟、模拟盘、CTP、IB） |
| 绩效指标 | 10 项（收益率、年化、夏普、最大回撤、Calmar、胜率、盈亏比等） |
| 风控检查 | 4 重（单笔限额、集中度、日亏损、频率） |
| 执行算法 | 2 种（TWAP、VWAP） |
| AI 因子 | 4 类 7 个（动量×3、波动率×2、RSI、量比） |
| Web API | 20 个端点 |
| Web 页面 | 9 个（总览、数据、回测、参数优化、监控告警、模拟盘、AI实验室、策略库、设置） |
| CLI 命令 | 4 个（info、data fetch、data list、backtest） |
| 单元测试 | 55 个用例 |
| 功能测试项 | 50 项 Web 测试 + 80+ 项全系统测试 |
| 展示场景 | 14 个（含 4 个新增 Web 交互场景） |
| CI 矩阵 | 4 种环境（2 OS × 2 Python） |
