import type { SystemConfigCategory } from '../types/systemConfig';

const categoryTitleMap: Record<SystemConfigCategory, string> = {
  data_source: '数据源',
  ai_model: 'AI 模型',
  system: '系统设置',
  agent: 'Agent 设置',
  backtest: '回测配置',
  scheduler: '定时管理',
  uncategorized: '其他',
};

const categoryDescriptionMap: Partial<Record<SystemConfigCategory, string>> = {
  data_source: '管理行情数据源与优先级策略。',
  ai_model: '管理模型服务、模型名称与推理参数。',
  system: '管理调度、日志、端口等系统级参数。',
  agent: '管理 Agent 模式、策略与多 Agent 编排配置。',
  backtest: '管理回测开关、评估窗口和引擎参数。',
  scheduler: '管理定时任务的执行时间、频率和执行状态。',
  uncategorized: '其他未归类的配置项。',
};

const fieldTitleMap: Record<string, string> = {
  TUSHARE_TOKEN: 'Tushare Token',
  REALTIME_SOURCE_PRIORITY: '实时数据源优先级',
  LITELLM_MODEL: '主模型',
  AGENT_LITELLM_MODEL: 'Agent 主模型',
  LITELLM_FALLBACK_MODELS: '备选模型',
  LLM_CHANNELS: 'LLM 渠道列表',
  LLM_TEMPERATURE: '采样温度',
  AIHUBMIX_KEY: 'AIHubmix Key',
  DEEPSEEK_API_KEY: 'DeepSeek API Key',
  GEMINI_API_KEY: 'Gemini API Key',
  GEMINI_MODEL: 'Gemini 模型',
  GEMINI_TEMPERATURE: 'Gemini 温度参数',
  OPENAI_API_KEY: 'OpenAI API Key',
  OPENAI_BASE_URL: 'OpenAI Base URL',
  OPENAI_MODEL: 'OpenAI 模型',
  REPORT_TYPE: '报告类型',
  REPORT_LANGUAGE: '报告语言',
  REPORT_TEMPLATES_DIR: '报告模板目录',
  REPORT_INTEGRITY_ENABLED: '报告完整性检查',
  REPORT_RENDERER_ENABLED: '报告渲染器',
  REPORT_INTEGRITY_RETRY: '报告完整性重试次数',
  REPORT_HISTORY_COMPARE_N: '历史对比期数',
  REPORT_SUMMARY_ONLY: '仅分析结果摘要',
  REPORT_SHOW_LLM_MODEL: '显示分析模型',
  MAX_WORKERS: '最大并发线程数',
  TRADING_DAY_CHECK_ENABLED: '启用交易日检查',
  WEBUI_HOST: 'WebUI 监听地址',
  ADMIN_AUTH_ENABLED: '启用后台登录鉴权',
  TRUST_X_FORWARDED_FOR: '信任 X-Forwarded-For',
  RUN_IMMEDIATELY: '启动后立即运行',
  MARKET_REVIEW_ENABLED: '启用大盘复盘',
  MARKET_REVIEW_REGION: '大盘复盘市场',
  MARKET_REVIEW_COLOR_SCHEME: '大盘复盘涨跌颜色',
  ANALYSIS_DELAY: '分析启动延迟（秒）',
  DEBUG: '调试模式',
  HTTP_PROXY: 'HTTP 代理',
  LOG_LEVEL: '日志级别',
  WEBUI_PORT: 'WebUI 端口',
  AGENT_MODE: '启用 Agent 策略问股',
  AGENT_MAX_STEPS: 'Agent 最大步数',
  AGENT_SKILLS: 'Agent 激活策略',
  AGENT_SKILL_DIR: 'Agent 策略目录',
  AGENT_ARCH: 'Agent 架构模式',
  AGENT_ORCHESTRATOR_MODE: '编排模式',
  AGENT_ORCHESTRATOR_TIMEOUT_S: 'Agent 超时（秒）',
  AGENT_RISK_OVERRIDE: '风控 Agent 否决',
  AGENT_SKILL_AUTOWEIGHT: '策略自动加权',
  AGENT_SKILL_ROUTING: '策略路由模式',
  AGENT_MEMORY_ENABLED: '记忆与校准',
  AGENT_NL_ROUTING: '自然语言路由',
  AGENT_DEEP_RESEARCH_BUDGET: 'Deep Research 预算',
  AGENT_DEEP_RESEARCH_TIMEOUT: 'Deep Research 超时（秒）',
  AGENT_CONTEXT_COMPRESSION_ENABLED: '上下文压缩',
  AGENT_CONTEXT_COMPRESSION_PROFILE: '上下文压缩策略',
  AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS: '压缩触发阈值（tokens）',
  AGENT_CONTEXT_PROTECTED_TURNS: '原文保护轮次',
  BACKTEST_ENABLED: '启用回测',
  BACKTEST_EVAL_WINDOW_DAYS: '回测评估窗口（交易日）',
  BACKTEST_MIN_AGE_DAYS: '回测最小历史天数',
  BACKTEST_ENGINE_VERSION: '回测引擎版本',
  BACKTEST_NEUTRAL_BAND_PCT: '回测中性区间阈值（%）',
};

const fieldDescriptionMap: Record<string, string> = {
  TUSHARE_TOKEN: '用于接入 Tushare Pro 数据服务的凭据。',
  REALTIME_SOURCE_PRIORITY: '按逗号分隔填写数据源调用优先级。',
  LITELLM_MODEL: '主模型，格式 provider/model（如 gemini/gemini-2.5-flash）。配置渠道后自动推断。',
  AGENT_LITELLM_MODEL: 'Agent 专用主模型。留空时继承主模型；无 provider 前缀时会按 openai/<model> 解析。',
  LITELLM_FALLBACK_MODELS: '备选模型，逗号分隔，主模型失败时按序尝试。',
  LLM_CHANNELS: '渠道名称列表（逗号分隔）。推荐使用上方渠道编辑器管理。',
  LLM_TEMPERATURE: '控制模型输出随机性，0 为确定性输出，2 为最大随机性，推荐 0.7。',
  AIHUBMIX_KEY: 'AIHubmix 一站式密钥，自动指向 aihubmix.com/v1。',
  DEEPSEEK_API_KEY: 'DeepSeek 官方 API 密钥。填写后自动使用 deepseek-chat 模型。',
  GEMINI_API_KEY: '用于 Gemini 服务调用的密钥。',
  GEMINI_MODEL: '设置 Gemini 分析模型名称。',
  GEMINI_TEMPERATURE: '控制模型输出随机性，范围通常为 0.0 到 2.0。',
  OPENAI_API_KEY: '用于 OpenAI 兼容服务调用的密钥。',
  OPENAI_BASE_URL: 'OpenAI 兼容 API 地址，例如 https://api.deepseek.com/v1。',
  OPENAI_MODEL: 'OpenAI 兼容模型名称，例如 gpt-4o-mini、deepseek-chat。',
  REPORT_TYPE: '通知报告展示粒度（如 simple/full/brief）。',
  REPORT_LANGUAGE: '通知报告语言（zh/en）。',
  REPORT_TEMPLATES_DIR: '自定义报告模板目录路径。',
  REPORT_INTEGRITY_ENABLED: '启用报告完整性检查，避免发送缺字段或异常内容。',
  REPORT_RENDERER_ENABLED: '启用报告渲染器，将结构化数据渲染为最终通知内容。',
  REPORT_INTEGRITY_RETRY: '报告完整性检查失败时的重试次数。',
  REPORT_HISTORY_COMPARE_N: '通知中引用历史报告做对比时的回看期数。',
  REPORT_SUMMARY_ONLY: '仅推送分析结果摘要，不包含个股详情。多股时适合快速浏览。',
  REPORT_SHOW_LLM_MODEL: '在通知报告底部显示本次分析使用的 LLM 模型名称；关闭后隐藏运行时模型信息。仅影响展示，不会影响 provider/model/Base URL、运行时模型保存、迁移或清理。',
  MAX_WORKERS: '异步任务队列最大并发数。配置保存后，队列空闲时会自动应用；繁忙时延后生效。',
  TRADING_DAY_CHECK_ENABLED: '启用交易日校验，非交易日自动跳过定时分析。',
  WEBUI_HOST: 'WebUI 服务监听地址（默认通常为 0.0.0.0）。',
  ADMIN_AUTH_ENABLED: '启用 Web 管理端账号密码登录校验。',
  TRUST_X_FORWARDED_FOR: '启用后信任反向代理透传的 X-Forwarded-For 源 IP。',
  RUN_IMMEDIATELY: '程序启动后立即执行一次分析任务。',
  MARKET_REVIEW_ENABLED: '是否启用大盘复盘流程。',
  MARKET_REVIEW_REGION: '大盘复盘默认市场区域（如 cn/us/hk）。',
  MARKET_REVIEW_COLOR_SCHEME: '控制大盘复盘指数涨跌幅图标颜色：green_up 为绿涨红跌，red_up 为红涨绿跌。',
  ANALYSIS_DELAY: '启动任务前的延迟秒数，可用于等待依赖服务就绪。',
  DEBUG: '启用调试模式，输出更多诊断日志。',
  HTTP_PROXY: '网络代理地址，可留空。',
  LOG_LEVEL: '设置日志输出级别。',
  WEBUI_PORT: 'Web 页面服务监听端口。',
  AGENT_MODE: '是否启用 ReAct Agent 策略问股。对外文案仍叫“策略”，内部配置字段统一使用 skill。',
  AGENT_MAX_STEPS: 'Agent 最大推理步数上限。保持默认 10 时，各子 Agent 按自身预设步数运行；调高到高于默认值时，所有子 Agent 统一采用该值；调低到低于某子 Agent 默认值时，该 Agent 会被封顶。',
  AGENT_SKILLS: '逗号分隔的交易策略列表。留空时使用 metadata 里声明的主默认策略 skill（内置默认是 bull_trend）；也可填写 all 启用全部策略。',
  AGENT_SKILL_DIR: '存放 Agent 策略定义文件的目录路径，支持 YAML 与 SKILL.md bundle。',
  AGENT_ARCH: "选择 Agent 执行架构。single 为经典单 Agent；multi 为多 Agent 编排（实验性）。",
  AGENT_ORCHESTRATOR_MODE: "Multi-Agent 编排深度。quick（技术→决策）、standard（技术→情报→决策）、full（含风控）、specialist（含策略专家评估）。",
  AGENT_ORCHESTRATOR_TIMEOUT_S: "Agent 执行总超时预算（秒）。single-agent 用作整体 ReAct 循环预算，multi-agent 用作协作编排预算；0 表示不限制。",
  AGENT_RISK_OVERRIDE: "允许风控 Agent 在发现关键风险时否决买入信号。",
  AGENT_SKILL_AUTOWEIGHT: "根据回测表现自动调整策略权重。",
  AGENT_SKILL_ROUTING: "策略选择方式。auto 按市场状态自动选择，manual 使用 AGENT_SKILLS 列表。",
  AGENT_MEMORY_ENABLED: "启用记忆与校准系统，追踪历史分析准确率并自动调节置信度。",
  AGENT_NL_ROUTING: '启用自然语言路由，让 Agent 自动识别意图并选择执行路径。',
  AGENT_DEEP_RESEARCH_BUDGET: 'Deep Research 预算上限，用于限制深度调研阶段的资源消耗。',
  AGENT_DEEP_RESEARCH_TIMEOUT: 'Deep Research 超时秒数，超过后自动结束深度调研。',
  AGENT_CONTEXT_COMPRESSION_ENABLED: "开启后，问股会在长会话中压缩可见历史上下文，减少重复 token 消耗；默认关闭。",
  AGENT_CONTEXT_COMPRESSION_PROFILE: "选择问股长会话上下文压缩策略。cost 偏省 token，balanced 均衡推荐、兼顾保真与成本，long_context_raw_first 优先保留更多原文。",
  AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS: "估算历史 token 超过该值时触发摘要；留空则跟随当前上下文压缩策略 profile 默认值。",
  AGENT_CONTEXT_PROTECTED_TURNS: "压缩时最近 N 个用户轮次及其后的回复保持原文；留空则跟随当前上下文压缩策略 profile 默认值。",
  BACKTEST_ENABLED: '是否启用回测功能（true/false）。',
  BACKTEST_EVAL_WINDOW_DAYS: '回测评估窗口长度，单位为交易日。',
  BACKTEST_MIN_AGE_DAYS: '仅回测早于该天数的分析记录。',
  BACKTEST_ENGINE_VERSION: '回测引擎版本标识，用于区分结果版本。',
  BACKTEST_NEUTRAL_BAND_PCT: '中性区间阈值百分比，例如 2 表示 -2%~+2%。',
};

const fieldOptionLabelMap: Record<string, Record<string, string>> = {
  REPORT_TYPE: {
    simple: '简洁',
    full: '完整',
    brief: '简报',
  },
  REPORT_LANGUAGE: {
    zh: '中文',
    en: '英文',
    chinese: '中文',
    english: '英文',
  },
  MARKET_REVIEW_COLOR_SCHEME: {
    green_up: '绿涨红跌',
    red_up: '红涨绿跌',
    'green up / red down': '绿涨红跌',
    'red up / green down': '红涨绿跌',
  },
  LOG_LEVEL: {
    debug: '调试',
    info: '信息',
    warning: '警告',
    error: '错误',
    critical: '严重',
  },
  MARKET_REVIEW_REGION: {
    cn: 'A 股',
    hk: '港股',
    us: '美股',
    both: '全部市场',
  },
  AGENT_ARCH: {
    single: '单 Agent',
    multi: '多 Agent（编排）',
    'single agent': '单 Agent',
    'multi agent (orchestrator)': '多 Agent（编排）',
  },
  AGENT_ORCHESTRATOR_MODE: {
    quick: '快速',
    standard: '标准',
    full: '完整',
    specialist: '专家',
  },
  AGENT_SKILL_ROUTING: {
    auto: '自动（按市场状态）',
    manual: '手动（使用 AGENT_SKILLS）',
    'auto (regime-based)': '自动（按市场状态）',
    'manual (use agent_skills)': '手动（使用 AGENT_SKILLS）',
  },
};

function normalizeOptionToken(raw: string): string {
  return raw.trim().toLowerCase();
}

export function getCategoryTitleZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryTitleMap[category] || fallback || category;
}

export function getCategoryDescriptionZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryDescriptionMap[category] || fallback || '';
}

export function getFieldTitleZh(key: string, fallback?: string): string {
  return fieldTitleMap[key] || fallback || key;
}

export function getFieldDescriptionZh(key: string, fallback?: string): string {
  return fieldDescriptionMap[key] || fallback || '';
}

export function getFieldOptionLabelZh(key: string, value: string, fallbackLabel?: string): string {
  const map = fieldOptionLabelMap[key];
  if (!map) {
    return fallbackLabel ?? value;
  }

  const byValue = map[normalizeOptionToken(value)];
  if (byValue) {
    return byValue;
  }

  if (fallbackLabel) {
    const byLabel = map[normalizeOptionToken(fallbackLabel)];
    if (byLabel) {
      return byLabel;
    }
  }

  return fallbackLabel ?? value;
}
