# 用户指令记忆

本文件记录了用户的指令、偏好和教导，用于在未来的交互中提供参考。

**每次执行任务时，必须先读取本文件，了解用户要求和偏好后再行动。**

## 系统环境

- 内存：8G，不可扩容
- 硬盘：20G，不可扩容
- 访问方式：仅通过预览端口访问，不可本地访问。每次服务启动后必须主动开放预览链接

## 开发工作流规范

1. **任务启动**：每次执行任务时，先读取本文件（`.monkeycode/MEMORY.md`）了解用户要求和偏好
2. **测试出错**：发现错误后必须先分析根因，提出解决方案，经用户批准后方可修改部署，不可擅自变更
3. **修改范围**：仅修改当前错误涉及的代码范围，严禁修改无关代码
4. **系统操作**：原定系统操作出现问题时，先分析原因，经用户确认后再进行，不得自行绕路解决或降低标准
5. **开发完成交付标准**：
   - 自行充分测试，确认无误
   - 检查前后端情况，确认是否需要编译/构建才能生效
   - 确认所有准备工作就绪后，再通知用户测试
   - 每次服务启动后主动开放预览端口链接
6. **沟通语气**：用确定的语气与用户说话。不使用"可能"、"也许"、"大概"等不确定词汇。不清楚的问题必须先自行检查清楚

## 关键技术资产

### 数据库
- 类型：SQLite，路径 `/workspace/NestCheck/data/stock_analysis.db`
- 主要表：`portfolio_positions`（持仓主数据）、`portfolio_accounts`（账户）、`portfolio_trades`（交易记录）、`portfolio_cash_ledgers`（现金台账）、`stock_daily`（日线数据）、`market_quotes`（行情缓存）、`watchlist_indicator_snapshot`（关注列表指标快照）

### 关键字段：风险等级
- `asset_risk_class` 字段（R1-R5）：资产初始化录入时的分类，存主数据，用于资产配置
- `getPositionRiskLevel()` 动态计算（高/中/低）：基于价格波动实时计算，用于止盈止损
- 台账表格只显示 R1-R5（asset_risk_class），不与动态评估混用

### 关键方案
- 价格缓存：`portfolio_positions.last_price` 字段，`refresh_all_prices()` 后台任务每 5 分钟更新
- 名称字段：`portfolio_positions.name`，随价格刷新任务从行情源获取并持久化
- 基金净值：`watchlist_indicator_snapshot.price` 字段，`_build_fund_indicator()` 从 akshare 获取并保存（使用前一天数据）

## 运行时要求

### 北京时间使用
- 系统运行在 UTC 环境，但 A 股交易时间判断必须使用北京时间（UTC+8）
- `api/app.py` 中 `_daily_portfolio_price_refresh()` 和 `_daily_market_cache_refresh_loop()` 都已改用北京时间
- 启动补执行逻辑：启动时检查当前北京时间，如果已过 20:30 且今天未执行过，立即补执行（解决个人电脑不 24 小时运行的场景）

### Watchlist 基金净值数据流
- Watchlist 基金净值独立存储于 `watchlist_indicator_snapshot` 表，与持仓资产的 `FundDailyNav` 分离
- 三个场景统一使用该表：
  1. **新增 Watchlist 基金**：`WatchlistService.create_item()` → `refresh_item()` → `_save_indicator_and_signal()` → 写入 `WatchlistIndicatorSnapshot`
  2. **定时任务刷新**：`market_cache_refresh` (5 分钟) → `WatchlistSignalService().refresh_enabled_funds()` → 写入 `WatchlistIndicatorSnapshot`
  3. **前端展示读取**：`quote_summary_for_items()` → 从 `WatchlistIndicatorSnapshot` 读取（而非 `FundDailyNav`）
- 字段：`price`（净值）、`price_change_pct`（涨跌幅%）、`change_amount`（涨跌额）、`as_of_date`（数据日期）

## 条目格式

### 用户指令条目
[用户指令摘要]
- Date: [YYYY-MM-DD]
- Context: [提及的场景或时间]
- Instructions:
  - [用户教导或指示的内容，逐行描述]

## 条目

### 改代码前先分析确认
- Date: 2026-05-27
- Context: 资产台账页面调整列名时，混淆了两套风险等级概念导致多次返工
- Instructions:
  - 修改代码前必须先分析清楚系统现状、涉及的字段、关联的影响面
  - 将分析结果反馈给用户确认后，再动手改代码
  - 不要理解不清楚就盲目修改

### 后台任务必须使用北京时间
- Date: 2026-06-05
- Context: 后台定时任务（市场数据刷新、持仓价格刷新）没有执行，数据停留在昨天
- Instructions:
  - 系统运行在 UTC 环境，但 A 股交易时间判断必须使用北京时间（UTC+8）
  - `api/app.py` 中的 `_daily_market_cache_refresh_loop()` 和 `_daily_portfolio_price_refresh()` 必须使用 `datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))` 获取北京时间
  - 交易时间判断：周一至周五 9:00-15:00（北京时间）
  - 持仓价格刷新：每天 20:30（北京时间）
  - 使用 `--serve-only` 模式启动服务时，lifespan 后台任务才能正确执行。不能用后台线程方式启动 uvicorn
  - **个人电脑不会 24 小时运行**：`_daily_portfolio_price_refresh()` 在启动时会检查当前北京时间，如果已经过了 20:30 且今天还没执行过，会立即补执行一次

### 远程历史分支来源
- Date: 2026-06-05
- Context: 用户说明仓库远程分支来源
- Instructions:
  - 远程大量 `autocode/*`、`codex/*`、`copilot/*`、`fix/*`、`feat/*` 等历史分支，是从 DSA 开源项目克隆时一并带入的上游遗留分支
  - 分支清理时优先按上游遗留分支处理，当前项目主线以 `main` 为准
