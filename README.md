# NestCheck

NestCheck 是面向个人投资者的资产智能工作台，用 FastAPI、React 和 SQLite 把资产台账、内部组合净值、关注标的红绿灯、AI 问答与 Agent 配置收敛到一个本地优先的系统里。

[产品预览](#产品预览) · [核心能力](#核心能力) · [系统架构](#系统架构) · [快速开始](#快速开始) · [文档中心](docs/INDEX.md) · [完整指南](docs/full-guide.md)

简体中文 | [English](docs/README_EN.md) | [繁體中文](docs/README_CHT.md)

## 产品预览

<p align="center">
  <img src="docs/assets/readme_workspace_tour_20260510.gif" alt="NestCheck Web 工作台演示" width="720">
</p>

## 项目定位

NestCheck 当前主线是“稳巢基金”资产管理工作台。系统把个人持仓、现金流水、交易事件、市场行情和 AI 分析统一到一套可本地运行的服务里，核心目标是快速回答三类问题：

- 我的内部组合今天净值、收益、回撤和波动如何。
- 我的资产分布、账户敞口、开放日和持仓收益是否清楚。
- 我关注的股票、基金和市场标的是否触发了红绿灯信号或告警规则。

## 核心能力

| 模块 | 说明 |
| --- | --- |
| 稳巢基金 | 展示内部组合单位净值、年化收益、年化波动、最大回撤、夏普比率、卡玛比率，并对比 `沪深300指数 50% + 十年国债ETF 50%` 业绩基准。 |
| 资产管理 | 管理账户、资产初始化、交易事件、资金流水、现金分红、送股除权、开放日跟踪和持仓收益。 |
| 关注标的 | 管理股票和基金关注列表，展示 5 灯红绿灯、行业 ETF 温度、行情缓存、告警规则摘要和触发历史。 |
| AI 问答 | 支持股票、基金和市场问答，按标的大类自动选择合适 profile，并可调用轻量或深度分析 Agent。 |
| Agent 管理 | 在 Web 中查看和编辑 profiles、专业 Agent、tools 与 skills，配置来源统一到 `agent_configs/catalog.yaml`。 |
| 设置中心 | 管理模型、数据源、通知、系统运行时、报告、Agent、回测等配置项。 |
| API / CLI | FastAPI 提供资产、行情、关注、告警、Agent、回测等接口；CLI 保留批处理分析和后台能力。 |

## 极速特点

- 本地优先：默认使用 SQLite，适合个人电脑、Docker、桌面端和轻量云服务器部署。
- 启动简单：后端服务可直接通过 `python main.py --serve-only` 拉起，Web 构建产物由同一服务承载。
- 页面按需加载：Web 路由采用 lazy loading，减少首屏包体积。
- 数据缓存明确：行情、基金净值、汇率、关注标的快照和内部基金净值按业务表持久化，减少重复拉取。
- API 优先：Web、桌面端、Bot 和自动任务共用 FastAPI 契约。
- V1.0 聚焦：前端主线收敛到资产驾驶舱、稳巢基金、资产管理、关注标的、AI 问答和系统设置。

## 系统架构

| 层级 | 目录 / 入口 | 职责 |
| --- | --- | --- |
| Web 前端 | `apps/dsa-web/` | React + Vite 工作台，覆盖资产、关注、问答、Agent 管理和设置。 |
| API 服务 | `api/`、`server.py` | FastAPI 路由、认证、Web 静态资源、SSE 和业务接口。 |
| 业务服务 | `src/services/` | 资产组合、内部基金净值、市场缓存、关注标的、Agent runtime、告警等核心逻辑。 |
| 数据访问 | `src/repositories/`、`src/storage.py` | SQLite 表结构、仓储封装和业务数据读写。 |
| 数据源 | `data_provider/` | AkShare、Tushare、TickFlow、YFinance、Baostock、Pytdx 等行情与基础数据适配。 |
| 自动化 | `scripts/`、`.github/workflows/` | 本地脚本、CI、发布、诊断、数据初始化和构建辅助。 |
| 桌面端 | `apps/dsa-desktop/` | Electron 客户端打包与桌面运行入口。 |

核心数据默认写入 `data/stock_analysis.db`。主要业务表包括资产持仓、账户、交易事件、现金台账、市场日线、行情缓存、关注标的快照和内部基金净值记录。

## 快速开始

### 个人电脑生产使用

Windows 个人电脑推荐优先走两条路径：

1. 已安装 Docker Desktop：使用 Docker 一键部署。
2. 没有 Docker Desktop：直接用 Python 运行现成的 Web/API 服务。

Tailscale 用于后续跨设备访问；首次本机部署可先完成服务启动，再决定是否接入 Tailscale。开发模式的 `npm run dev` 仅用于前端开发调试。

#### 第 1 步：配置 Tailscale

需要在外出笔记本、手机或平板访问家里电脑时，推荐使用 Tailscale 私有网络。这样无需路由器端口转发，也避免把 NestCheck 直接暴露到公网。

1. 在 Windows 电脑安装 Tailscale：<https://tailscale.com/download/windows>
2. 在访问设备上也安装 Tailscale，并登录同一个账号。
3. 在 Windows PowerShell 查看这台电脑的 Tailscale IP：

```powershell
tailscale ip -4
```

4. 后续在其他已登录 Tailscale 的设备访问：

```text
http://你的Tailscale-IP:8000
```

例如：

```text
http://100.88.12.34:8000
```

#### 路径 A：Windows + Docker 一键部署

适合希望运行环境更干净、升级更稳定的 Windows 个人电脑部署。

1. 打开 Windows PowerShell，直接运行一键安装命令：

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/TheoEquity/NestCheck/main/scripts/install-nestcheck-docker.ps1 -OutFile $env:TEMP\install-nestcheck-docker.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\install-nestcheck-docker.ps1
```

默认会把项目下载到：

```text
%USERPROFILE%\NestCheck
```

2. 需要脚本协助安装 Docker Desktop 时，运行：

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/TheoEquity/NestCheck/main/scripts/install-nestcheck-docker.ps1 -OutFile $env:TEMP\install-nestcheck-docker.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\install-nestcheck-docker.ps1 -InstallDocker
```

Docker Desktop 首次安装后需要手动打开一次，并等待 Docker Engine 进入运行状态，再重新执行第 1 条安装命令。

已有源码目录时，也可以在项目目录内运行：

```powershell
cd $env:USERPROFILE\NestCheck
powershell -ExecutionPolicy Bypass -File scripts\install-nestcheck-docker.ps1
```

脚本会自动完成：

- 创建 `.env` 并开启 `ADMIN_AUTH_ENABLED=true`
- 设置 `API_PORT=8000` 与 `WEBUI_HOST=0.0.0.0`
- 创建 `data/`、`logs/`、`reports/`、`strategies/` 目录
- 添加 Windows 专用网络防火墙规则
- 执行 `docker compose -f docker/docker-compose.yml up -d --build server`

本机浏览器访问：

```text
http://127.0.0.1:8000
```

生产数据默认保存在本机项目目录下：

```text
.env
data/stock_analysis.db
logs/
reports/
```

停止服务：

```powershell
docker compose -f docker/docker-compose.yml stop server
```

再次启动：

```powershell
docker compose -f docker/docker-compose.yml start server
```

关闭并移除容器：

```powershell
docker compose -f docker/docker-compose.yml down
```

`down` 只移除容器，保留本机 `.env`、`data/`、`logs/` 和 `reports/`。

升级时执行：

```powershell
git pull
powershell -ExecutionPolicy Bypass -File scripts\install-nestcheck-docker.ps1
```

临时断开 Tailscale：

```powershell
tailscale down
```

恢复 Tailscale：

```powershell
tailscale up
```

安全建议：保持 `ADMIN_AUTH_ENABLED=true`，设置强管理员密码和安全问题；路由器不配置端口转发；Tailscale 中不启用 Exit Node 时，普通网页、微信、邮箱和券商软件仍按原网络访问。

#### 路径 B：Windows + Python 直接运行

适合没有 Docker Desktop，或希望先在本机快速跑起来的个人电脑部署。

1. 安装 Python 3.11，并确认 PowerShell 中能执行：

```powershell
python --version
```

2. 准备源码目录。

可以用 `git clone`，也可以直接下载并解压源码 zip 到 `C:\Users\你的用户名\NestCheck`。

3. 在项目目录中创建虚拟环境并安装依赖：

也可以直接运行一键脚本：

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/TheoEquity/NestCheck/main/scripts/install-nestcheck-python.ps1 -OutFile $env:TEMP\install-nestcheck-python.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\install-nestcheck-python.ps1
```

如果本机还没有 Python 3.11，可以运行：

```powershell
iwr -UseBasicParsing https://raw.githubusercontent.com/TheoEquity/NestCheck/main/scripts/install-nestcheck-python.ps1 -OutFile $env:TEMP\install-nestcheck-python.ps1; powershell -ExecutionPolicy Bypass -File $env:TEMP\install-nestcheck-python.ps1 -InstallPython
```

脚本会自动下载源码、创建虚拟环境、处理 UTF-8、安装依赖、生成 `.env`，并在完成后直接启动服务。

```powershell
cd C:\Users\你的用户名\NestCheck

python -m venv .venv
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果遇到 `UnicodeDecodeError` 或 `gbk` 解码错误，先执行：

```powershell
chcp 65001
$env:PYTHONUTF8=1
```

再重新运行依赖安装命令。

4. 启动服务：

```powershell
.\.venv\Scripts\python.exe main.py --serve-only --host 127.0.0.1 --port 8000
```

服务启动后，当前 PowerShell 会被前台进程占用，这是正常状态。保持该窗口打开，然后在浏览器访问：

```text
http://127.0.0.1:8000
```

停止服务时，在该窗口按 `Ctrl + C`。

5. 如果 `pip install -r requirements.txt` 长时间卡住，可以先安装核心运行依赖，再启动服务：

一键脚本也支持只安装核心依赖：

```powershell
powershell -ExecutionPolicy Bypass -File $env:TEMP\install-nestcheck-python.ps1 -CoreOnly
```

```powershell
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-cache-dir python-dotenv pandas fastapi uvicorn[standard]
```

然后再次执行启动命令。

6. 常见问题：

- `py` 命令不存在：直接使用 `python`。
- `No module named 'dotenv'`：执行 `.\.venv\Scripts\python.exe -m pip install python-dotenv`。
- `No module named 'pandas'`：重新执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。
- 首次登录密码框输入不顺畅：切换到英文半角输入法，直接粘贴密码也可完成初始化。

`static/` 目录中已经包含 Web 构建产物时，直接运行 `main.py --serve-only` 即可，无需额外执行 `npm run build`。

### 本地运行

```bash
# 克隆项目
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git

# 进入项目目录
cd daily_stock_analysis

# 安装 Python 依赖
pip install -r requirements.txt

# 准备配置文件
cp .env.example .env

# 启动 FastAPI 与 Web 工作台
python main.py --serve-only
```

服务启动后访问 `http://127.0.0.1:8000`。

### Web 前端开发

```bash
# 进入 Web 应用
cd apps/dsa-web

# 安装依赖
npm ci

# 启动 Vite 开发服务
npm run dev

# 构建生产产物
npm run build
```

前端开发服务需要配合后端 API 使用。完整代理、认证和部署说明见 [完整配置与部署指南](docs/full-guide.md)。

### 常用命令

```bash
# 启动 Web/API 服务
python main.py --serve-only

# 执行一次分析任务
python main.py

# 调试模式
python main.py --debug

# Dry-run 验证配置
python main.py --dry-run

# 指定股票分析
python main.py --stocks 600519,hk00700,AAPL

# 大盘复盘
python main.py --market-review
```

## 配置概览

至少准备一个可用的大模型渠道，AI 问答和 Agent 分析即可工作。行情和新闻源按需增强，系统会按可用来源执行 fallback。

| 类型 | 常见配置 |
| --- | --- |
| 大模型 | Anspire、AIHubMix、OpenAI-compatible、DeepSeek、通义千问、Claude、Gemini、Ollama |
| 行情数据 | AkShare、Tushare、TickFlow、Baostock、Pytdx、YFinance、Longbridge |
| 新闻搜索 | Anspire AI Search、SerpAPI、Tavily、Bocha、Brave、MiniMax、SearXNG |
| 通知渠道 | 企业微信、飞书、Telegram、Discord、Slack、邮件、ntfy、Gotify |

详细配置、优先级、失败降级、Docker、桌面端和云服务器部署见 [完整配置与部署指南](docs/full-guide.md)。

## DSA Agent 参考

NestCheck 继承 Daily Stock Analysis 的多市场数据、报告生成和 Agent 编排能力。当前 Web 主线把问股入口升级为统一资产问答，股票、基金和市场会话会根据大类选择对应 profile；后台仍保留 DSA 的分析任务、报告、通知、Bot、回测 API/CLI 与多 Agent runtime。

Agent 配置重点入口：

- Web：`/agent-management` 管理 profiles、专业 Agent、tools 与 skills。
- 配置文件：`agent_configs/catalog.yaml`。
- 详细文档：[LLM 配置指南](docs/LLM_CONFIG_GUIDE.md)、[完整指南](docs/full-guide.md)。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [文档中心](docs/INDEX.md) | 项目文档导航。 |
| [完整配置与部署指南](docs/full-guide.md) | 环境、配置、运行、部署、Web、API 和排障。 |
| [LLM 配置指南](docs/LLM_CONFIG_GUIDE.md) | 大模型渠道、路由和 Web 设置页说明。 |
| [V1.0 测试计划](docs/v1-test-plan.md) | 稳巢基金、资产和关注标的相关测试计划。 |
| [告警文档](docs/alerts.md) | Alert API、规则、触发历史和通知结果。 |
| [更新日志](docs/CHANGELOG.md) | 版本变化和迁移说明。 |

## 相关项目

| 项目 | 定位 |
| --- | --- |
| [AlphaSift](https://github.com/ZhuLinsen/alphasift) | 多因子选股与全市场扫描，用于从股票池中提取候选标的。 |
| [AlphaEvo](https://github.com/ZhuLinsen/alphaevo) | 策略回测与自我进化，用于验证策略规则，并通过迭代探索策略参数与组合。 |

## 联系与合作

<table>
  <tr>
    <td width="92" valign="top"><strong>合作邮箱</strong></td>
    <td valign="top">
      <a href="mailto:zhuls345@gmail.com">zhuls345@gmail.com</a><br>
      项目咨询、部署支持与功能扩展
    </td>
    <td align="center" rowspan="3" valign="middle" width="148">
      <a href="http://xhslink.com/m/tU520DWCKT" target="_blank"><img src="./docs/assets/xiaohongshu_tick.jpg" width="112" alt="小红书二维码"></a><br>
      <sub>扫码关注小红书</sub>
    </td>
  </tr>
  <tr>
    <td width="92" valign="top"><strong>小红书</strong></td>
    <td valign="top"><a href="http://xhslink.com/m/tU520DWCKT">欢迎关注小红书</a></td>
  </tr>
  <tr>
    <td width="92" valign="top"><strong>问题反馈</strong></td>
    <td valign="top"><a href="https://github.com/ZhuLinsen/daily_stock_analysis/issues">提交 Issue</a></td>
  </tr>
</table>

## License

[MIT License](LICENSE) © 2026 ZhuLinsen

本项目仅供学习和研究使用，不构成投资建议。市场有风险，投资需谨慎。
