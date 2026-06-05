import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '../utils/cn';
import { agentApi } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Badge, Button, ConfirmDialog, EmptyState, InlineAlert, ScrollArea } from '../components/common';
import { getParsedApiError } from '../api/error';
import type { SkillInfo } from '../api/agent';
import { DashboardStateBlock } from '../components/dashboard';
import {
  useAgentChatStore,
  type Message,
  type ProgressStep,
} from '../stores/agentChatStore';
import type { ChatFollowUpContext } from '../utils/chatFollowUp';
import {
  buildFollowUpPrompt,
  parseFollowUpRecordId,
  resolveChatFollowUpContext,
  sanitizeFollowUpStockCode,
  sanitizeFollowUpStockName,
} from '../utils/chatFollowUp';
import { isNearBottom } from '../utils/chatScroll';
import { getReportText } from '../utils/reportLanguage';

// Quick question examples shown on empty state
const QUICK_QUESTIONS = [
  { label: '解释当前风险和估值位置', skill: 'bull_trend' },
  { label: '最近新闻有什么影响', skill: 'bull_trend' },
  { label: '当前适合加仓还是等待', skill: 'box_oscillation' },
  { label: '说明主要风险点', skill: 'bull_trend' },
  { label: '结合技术面看支撑位', skill: 'emotion_cycle' },
  { label: '给出下一步观察清单', skill: 'bull_trend' },
];

const MAX_SELECTED_SKILLS = 3;
const CONTEXT_COMPRESSION_CONFIG_KEY = 'AGENT_CONTEXT_COMPRESSION_ENABLED';
const DEFAULT_CHAT_PROFILE_ID = 'stock_chat_auto';
const FUND_CHAT_PROFILE_ID = 'fund_analysis';
const STOCK_SPECIALIST_PROFILE_ID = 'stock_specialist';
const STOCK_SPECIALIST_PROMPT = '请对当前个股进行专家分析，结合已选策略技能，覆盖行情位置、技术结构、情报风险、策略条件和操作建议。';

export const getDefaultChatProfileId = (assetType?: string | null) => (
  assetType === 'fund' ? FUND_CHAT_PROFILE_ID : DEFAULT_CHAT_PROFILE_ID
);

type ActiveChatTopic = { market: string; assetType: string; code: string; name: string; sessionId: string };

export const buildChatTopicContext = (
  topic: ActiveChatTopic,
  followUpContext?: ChatFollowUpContext | null,
) => ({
  ...(followUpContext ?? {}),
  agent_chat_mode: true,
  stock_code: topic.assetType === 'stock' ? topic.code : undefined,
  stock_name: topic.assetType === 'stock' ? topic.name || undefined : undefined,
  fund_code: topic.assetType === 'fund' ? topic.code : undefined,
  fund_name: topic.assetType === 'fund' ? topic.name || undefined : undefined,
  asset_code: topic.code,
  asset_name: topic.name || undefined,
  market: topic.market,
  asset_type: topic.assetType,
});

const MARKET_OPTIONS = [
  { value: 'cn', label: 'A股' },
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
];

const ASSET_TYPE_OPTIONS = [
  { value: 'stock', label: '股票' },
  { value: 'fund', label: '基金' },
  { value: 'index', label: '指数' },
  { value: 'bond', label: '债券' },
];

const getMessageSkillNames = (msg: Message): string[] => {
  if (msg.skillNames?.length) return msg.skillNames;
  if (msg.skillName) return [msg.skillName];
  if (msg.skills?.length) return msg.skills;
  if (msg.skill) return [msg.skill];
  return [];
};

const getMessageSkillLabel = (msg: Message): string => getMessageSkillNames(msg).join('、');

const ChatPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [input, setInput] = useState('');
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [showSkillDesc, setShowSkillDesc] = useState<string | null>(null);
  const [expandedThinking, setExpandedThinking] = useState<Set<string>>(new Set());
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isFollowUpContextLoading, setIsFollowUpContextLoading] = useState(false);
  const [contextCompressionEnabled, setContextCompressionEnabled] = useState(false);
  const [contextCompressionLoaded, setContextCompressionLoaded] = useState(false);
  const [contextCompressionSaving, setContextCompressionSaving] = useState(false);
  const [contextCompressionConfigVersion, setContextCompressionConfigVersion] = useState('');
  const [contextCompressionMaskToken, setContextCompressionMaskToken] = useState('******');
  const [copiedMessages, setCopiedMessages] = useState<Set<string>>(new Set());
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [topicForm, setTopicForm] = useState({ market: 'cn', assetType: 'stock', code: '', name: '' });
  const [activeTopic, setActiveTopic] = useState<ActiveChatTopic | null>(null);
  const [topicError, setTopicError] = useState<string | null>(null);
  const [topicResolving, setTopicResolving] = useState(false);
  const copyResetTimerRef = useRef<Partial<Record<string, number>>>({});
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isMountedRef = useRef(true);
  const followUpHydrationTokenRef = useRef(0);
  const followUpContextRef = useRef<ChatFollowUpContext | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const pendingScrollBehaviorRef = useRef<ScrollBehavior>('auto');

  // Get localized text (default to Chinese)
  const text = getReportText('zh');

  // Cleanup timers on unmount
  useEffect(() => {
    const timers = copyResetTimerRef.current;
    return () => {
      Object.values(timers).forEach((timerId) => {
        if (timerId !== undefined) {
          window.clearTimeout(timerId);
        }
      });
    };
  }, []);

  // Set page title
  useEffect(() => {
    document.title = 'AI问答 - NestCheck';
  }, []);

  const {
    messages,
    loading,
    progressSteps,
    sessionId,
    sessions,
    sessionsLoading,
    chatError,
    loadSessions,
    loadInitialSession,
    switchSession,
    startStream,
    clearCompletionBadge,
  } = useAgentChatStore();

  const syncScrollState = useCallback(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    const nearBottom = isNearBottom({
      scrollTop: viewport.scrollTop,
      clientHeight: viewport.clientHeight,
      scrollHeight: viewport.scrollHeight,
    });
    shouldStickToBottomRef.current = nearBottom;
    setShowJumpToBottom((prev) => (nearBottom ? false : prev));
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  const requestScrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    shouldStickToBottomRef.current = true;
    pendingScrollBehaviorRef.current = behavior;
    setShowJumpToBottom(false);
  }, []);

  const handleMessagesScroll = useCallback(() => {
    syncScrollState();
  }, [syncScrollState]);

  useEffect(() => {
    syncScrollState();
  }, [syncScrollState, sessionId]);

  useEffect(() => {
    const behavior = pendingScrollBehaviorRef.current;
    const shouldAutoScroll = shouldStickToBottomRef.current;
    if (!shouldAutoScroll) {
      if (messages.length > 0 || progressSteps.length > 0 || loading) {
        setShowJumpToBottom(true);
      }
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      scrollToBottom(behavior);
      pendingScrollBehaviorRef.current = loading ? 'auto' : 'smooth';
    });

    return () => window.cancelAnimationFrame(frame);
  }, [messages, progressSteps, loading, sessionId, scrollToBottom]);

  useEffect(() => {
    if (!loading) {
      pendingScrollBehaviorRef.current = 'smooth';
    }
  }, [loading]);

  useEffect(() => {
    clearCompletionBadge();
  }, [clearCompletionBadge]);

  useEffect(() => {
    loadInitialSession();
  }, [loadInitialSession]);

  useEffect(() => {
    agentApi.getSkills()
      .then((res) => {
        setSkills(res.skills);
        const defaultId =
          res.default_skill_id ||
          res.skills[0]?.id ||
          '';
        setSelectedSkillIds(defaultId ? [defaultId] : []);
      })
      .catch((error) => {
        console.error('Failed to load chat skills:', error);
      });
  }, []);

  useEffect(() => {
    let active = true;

    void systemConfigApi.getConfig(false)
      .then((config) => {
        if (!active) {
          return;
        }
        const enabledItem = config.items.find((item) => item.key === CONTEXT_COMPRESSION_CONFIG_KEY);
        setContextCompressionEnabled(String(enabledItem?.value ?? '').trim().toLowerCase() === 'true');
        setContextCompressionConfigVersion(config.configVersion);
        setContextCompressionMaskToken(config.maskToken || '******');
        setContextCompressionLoaded(true);
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        setContextCompressionLoaded(false);
        console.error('Failed to load context compression setting:', error);
      });

    return () => {
      active = false;
    };
  }, []);

  const updateContextCompressionEnabled = useCallback(
    async (nextEnabled: boolean) => {
      if (!contextCompressionLoaded || contextCompressionSaving) {
        return;
      }

      const previousEnabled = contextCompressionEnabled;
      setContextCompressionEnabled(nextEnabled);
      setContextCompressionSaving(true);

      try {
        const result = await systemConfigApi.update({
          configVersion: contextCompressionConfigVersion,
          maskToken: contextCompressionMaskToken,
          reloadNow: true,
          items: [
            {
              key: CONTEXT_COMPRESSION_CONFIG_KEY,
              value: nextEnabled ? 'true' : 'false',
            },
          ],
        });
        setContextCompressionConfigVersion(result.configVersion || contextCompressionConfigVersion);
      } catch {
        setContextCompressionEnabled(previousEnabled);
      } finally {
        setContextCompressionSaving(false);
      }
    },
    [
      contextCompressionConfigVersion,
      contextCompressionEnabled,
      contextCompressionLoaded,
      contextCompressionMaskToken,
      contextCompressionSaving,
    ],
  );

  const availableSkillIds = new Set(skills.map((skill) => skill.id));
  const quickQuestions = QUICK_QUESTIONS.filter((question) => availableSkillIds.size === 0 || availableSkillIds.has(question.skill));

  const canStartTopic = Boolean(topicForm.market && topicForm.assetType && topicForm.code.trim());
  const canSendMessage = Boolean(activeTopic && input.trim() && !loading);
  const buildTopicContext = useCallback((topic: ActiveChatTopic) => (
    buildChatTopicContext(topic, followUpContextRef.current)
  ), []);

  const applyTopicSelection = useCallback((topic: { market?: string | null; asset_type?: string | null; code?: string | null; name?: string | null; session_id?: string | null }) => {
    if (!topic.session_id || !topic.market || !topic.asset_type || !topic.code) return;
    const nextTopic = {
      market: topic.market,
      assetType: topic.asset_type,
      code: topic.code,
      name: topic.name || '',
      sessionId: topic.session_id,
    };
    setTopicForm({
      market: nextTopic.market,
      assetType: nextTopic.assetType,
      code: nextTopic.code,
      name: nextTopic.name,
    });
    setActiveTopic(nextTopic);
    setTopicError(null);
  }, []);

  const handleStartTopicChat = useCallback(async () => {
    if (!canStartTopic || topicResolving) return;
    setTopicResolving(true);
    setTopicError(null);
    const code = topicForm.code.trim();
    const name = topicForm.name.trim();
    try {
      const topic = await agentApi.resolveChatTopic(code, name || undefined, {
        market: topicForm.market,
        assetType: topicForm.assetType,
      });
      if (!topic.found || !topic.session_id || !topic.market || !topic.asset_type || !topic.code) {
        setTopicError('无法识别该标的，请检查市场、大类和代码。');
        return;
      }
      applyTopicSelection(topic);
      await switchSession(topic.session_id);
      await loadSessions();
    } catch (error) {
      console.error('Failed to start topic chat:', error);
      setTopicError(getParsedApiError(error).message || '开始问答失败');
    } finally {
      setTopicResolving(false);
    }
  }, [applyTopicSelection, canStartTopic, loadSessions, switchSession, topicForm, topicResolving]);
  const selectedSkillIdSet = new Set(selectedSkillIds);
  const skillLimitReached = selectedSkillIds.length >= MAX_SELECTED_SKILLS;

  const getSkillNames = useCallback(
    (skillIds: string[]) => skillIds.map((id) => skills.find((s) => s.id === id)?.name || id),
    [skills],
  );

  const normalizeSelectedSkillIds = useCallback((skillIds: string[]) => {
    const normalized: string[] = [];
    for (const skillId of skillIds) {
      const cleaned = skillId.trim();
      if (cleaned && !normalized.includes(cleaned)) {
        normalized.push(cleaned);
      }
    }
    return normalized.slice(0, MAX_SELECTED_SKILLS);
  }, []);

  const toggleSkillSelection = useCallback((skillId: string) => {
    setSelectedSkillIds((prev) => {
      if (prev.includes(skillId)) {
        return prev.filter((id) => id !== skillId);
      }
      if (prev.length >= MAX_SELECTED_SKILLS) {
        return prev;
      }
      return [...prev, skillId];
    });
  }, []);

  const handleStartNewChat = useCallback(() => {
    followUpContextRef.current = null;
    requestScrollToBottom('auto');
    useAgentChatStore.getState().startNewChat();
    setSidebarOpen(false);
  }, [requestScrollToBottom]);

  const confirmDelete = useCallback(() => {
    if (!deleteConfirmId) return;
    agentApi.deleteChatSession(deleteConfirmId)
      .then(() => {
        loadSessions();
        if (deleteConfirmId === sessionId) {
          handleStartNewChat();
        }
      })
      .catch((error) => {
        console.error('Failed to delete chat session:', error);
      });
    setDeleteConfirmId(null);
  }, [deleteConfirmId, sessionId, loadSessions, handleStartNewChat]);

  // Handle follow-up from report page: ?stock=600519&name=贵州茅台&recordId=xxx
  useEffect(() => {
    const stock = sanitizeFollowUpStockCode(searchParams.get('stock'));
    const name = sanitizeFollowUpStockName(searchParams.get('name'));
    const recordId = parseFollowUpRecordId(searchParams.get('recordId'));

    if (!stock) {
      setSearchParams({}, { replace: true });
      return;
    }

    const hydrationToken = ++followUpHydrationTokenRef.current;
    void agentApi.resolveChatTopic(stock, name ?? undefined).then((topic) => {
      if (!isMountedRef.current || followUpHydrationTokenRef.current !== hydrationToken) {
        return;
      }
      if (topic.found && topic.session_id) {
        applyTopicSelection(topic);
        void switchSession(topic.session_id);
        if (topic.has_messages) {
          setInput('');
          return;
        }
      }
      setInput(buildFollowUpPrompt(stock, name));
    }).catch((error) => {
      console.error('Failed to resolve chat topic:', error);
      if (isMountedRef.current && followUpHydrationTokenRef.current === hydrationToken) {
        setInput(buildFollowUpPrompt(stock, name));
      }
    });
    followUpContextRef.current = {
      stock_code: stock,
      stock_name: name,
    };
    if (recordId !== undefined) {
      setIsFollowUpContextLoading(true);
    }
    void resolveChatFollowUpContext({
      stockCode: stock,
      stockName: name,
      recordId,
    }).then((context) => {
      if (!isMountedRef.current || followUpHydrationTokenRef.current !== hydrationToken) {
        return;
      }
      followUpContextRef.current = context;
    }).finally(() => {
      if (isMountedRef.current && followUpHydrationTokenRef.current === hydrationToken) {
        setIsFollowUpContextLoading(false);
      }
    });
    setSearchParams({}, { replace: true });
  }, [applyTopicSelection, searchParams, setSearchParams, switchSession]);

  const handleSend = useCallback(
    async (overrideMessage?: string, overrideSkillIds?: string[], overrideProfileId?: string) => {
      const msgText = (overrideMessage ?? input).trim();
      if (!msgText || loading || !activeTopic) return;
      const usedSkillIds = activeTopic.assetType === 'fund'
        ? []
        : normalizeSelectedSkillIds(overrideSkillIds ?? selectedSkillIds);
      const usedSkillNames = activeTopic.assetType === 'fund'
        ? ['基金问答']
        : usedSkillIds.length > 0 ? getSkillNames(usedSkillIds) : ['通用'];

      const payload = {
        message: msgText,
        session_id: activeTopic.sessionId,
        profile_id: overrideProfileId ?? getDefaultChatProfileId(activeTopic.assetType),
        ...(activeTopic.assetType === 'fund' || usedSkillIds.length > 0 ? { skills: usedSkillIds } : {}),
        context: buildTopicContext(activeTopic),
      };
      followUpHydrationTokenRef.current += 1;
      followUpContextRef.current = null;
      setIsFollowUpContextLoading(false);

      setInput('');
      requestScrollToBottom('smooth');
      await startStream(payload, {
        skillNames: usedSkillNames,
        skillName: usedSkillNames.join('、'),
      });
    },
    [activeTopic, buildTopicContext, getSkillNames, input, loading, normalizeSelectedSkillIds, requestScrollToBottom, selectedSkillIds, startStream],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSwitchSession = useCallback((targetSessionId: string) => {
    const target = sessions.find((item) => item.session_id === targetSessionId);
    if (target?.market && target.asset_type && target.code) {
      applyTopicSelection({
        session_id: target.session_id,
        market: target.market,
        asset_type: target.asset_type,
        code: target.code,
        name: target.name,
      });
    } else {
      setActiveTopic(null);
    }
    requestScrollToBottom('auto');
    void switchSession(targetSessionId);
    setSidebarOpen(false);
  }, [applyTopicSelection, requestScrollToBottom, sessions, switchSession]);

  const handleQuickQuestion = (q: (typeof QUICK_QUESTIONS)[0]) => {
    setSelectedSkillIds([q.skill]);
    handleSend(q.label, [q.skill]);
  };

  const handleStockSpecialistAnalysis = useCallback(() => {
    void handleSend(STOCK_SPECIALIST_PROMPT, selectedSkillIds, STOCK_SPECIALIST_PROFILE_ID);
  }, [handleSend, selectedSkillIds]);

  const toggleThinking = (msgId: string) => {
    setExpandedThinking((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  const copyMessageToClipboard = async (msgId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessages((prev) => new Set(prev).add(msgId));
      const existingTimer = copyResetTimerRef.current[msgId];
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }
      copyResetTimerRef.current[msgId] = window.setTimeout(() => {
        setCopiedMessages((prev) => {
          const next = new Set(prev);
          next.delete(msgId);
          return next;
        });
        delete copyResetTimerRef.current[msgId];
      }, 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  const downloadMessageAsMarkdown = useCallback((msg: Message) => {
    const skillLabel = getMessageSkillLabel(msg);
    const heading = msg.role === 'user' ? '# 用户消息' : `# AI 回复${skillLabel ? ` · ${skillLabel}` : ''}`;
    const content = [heading, '', msg.content].join('\n');
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${msg.role === 'user' ? 'user' : 'assistant'}-message-${msg.id}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, []);

  const getCurrentStage = (steps: ProgressStep[]): string => {
    if (steps.length === 0) return '正在连接...';
    const last = steps[steps.length - 1];
    if (last.type === 'thinking') return last.message || 'AI 正在思考...';
    if (last.type === 'tool_start')
      return `${last.display_name || last.tool}...`;
    if (last.type === 'tool_done')
      return `${last.display_name || last.tool} 完成`;
    if (last.type === 'generating')
      return last.message || '正在生成最终分析...';
    return '处理中...';
  };

  const renderThinkingBlock = (msg: Message) => {
    if (!msg.thinkingSteps || msg.thinkingSteps.length === 0) return null;
    const isExpanded = expandedThinking.has(msg.id);
    const toolSteps = msg.thinkingSteps.filter((s) => s.type === 'tool_done');
    const totalDuration = toolSteps.reduce(
      (sum, s) => sum + (s.duration || 0),
      0,
    );
    const summary = `${toolSteps.length} 个工具调用 · ${totalDuration.toFixed(1)}s`;

    return (
      <button
        onClick={() => toggleThinking(msg.id)}
        className="flex items-center gap-2 text-xs text-muted-text hover:text-secondary-text transition-colors mb-2 w-full text-left"
      >
        <svg
          className={`w-3 h-3 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span className="flex items-center gap-1.5">
          <span className="opacity-60">思考过程</span>
          <span className="text-muted-text/50">·</span>
          <span className="opacity-50">{summary}</span>
        </span>
      </button>
    );
  };

  const renderThinkingDetails = (steps: ProgressStep[]) => (
    <div className="mb-3 pl-5 border-l border-border/40 space-y-1.5 animate-fade-in">
      {steps.map((step, idx) => {
        let statusClass = 'chat-progress-item-muted';
        let iconClass = 'chat-progress-dot-muted';
        let text = '';
        if (step.type === 'thinking') {
          text = step.message || `第 ${step.step} 步：思考`;
          statusClass = 'chat-progress-item-thinking';
          iconClass = 'chat-progress-dot-thinking';
        } else if (step.type === 'tool_start') {
          text = `${step.display_name || step.tool}...`;
          statusClass = 'chat-progress-item-tool';
          iconClass = 'chat-progress-dot-tool';
        } else if (step.type === 'tool_done') {
          text = `${step.display_name || step.tool} (${step.duration}s)`;
          statusClass = step.success ? 'chat-progress-item-success' : 'chat-progress-item-danger';
          iconClass = step.success ? 'chat-progress-dot-success' : 'chat-progress-dot-danger';
        } else if (step.type === 'generating') {
          text = step.message || '生成分析';
          statusClass = 'chat-progress-item-generating';
          iconClass = 'chat-progress-dot-generating';
        }
        return (
          <div
            key={idx}
            className={cn('chat-progress-item', statusClass)}
          >
            <span className={cn('chat-progress-dot', iconClass)} />
            <span className="leading-relaxed">{text}</span>
          </div>
        );
      })}
    </div>
  );

  const sidebarContent = (
    <>
      <div className="flex items-center justify-between border-b border-white/5 bg-white/2 p-3.5">
        <h2 className="text-sm font-semibold text-cyan uppercase tracking-[0.2em] flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          历史对话
        </h2>
      </div>
      <ScrollArea testId="chat-session-list-scroll" viewportClassName="p-3">
        {sessionsLoading ? (
          <DashboardStateBlock
            loading
            compact
            title="加载对话中..."
            className="rounded-2xl border border-dashed border-border/50 bg-surface/30"
          />
        ) : sessions.length === 0 ? (
          <DashboardStateBlock
            compact
            title="暂无历史对话"
            description="开始提问后，这里会保留会话记录。"
            className="rounded-2xl border border-dashed border-border/50 bg-surface/30"
          />
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-item-row">
                <button
                  type="button"
                  onClick={() => handleSwitchSession(s.session_id)}
                  className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                  aria-label={`切换到对话 ${s.title}`}
                  aria-current={s.session_id === sessionId ? 'page' : undefined}
                >
                  <div className="indicator" />
                  <div className="content">
                    <span className="title">{s.title}</span>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="meta">
                        {s.message_count} 条对话
                      </span>
                      {s.last_active && (
                        <>
                          <span className="separator" />
                          <span className="meta">
                            {new Date(s.last_active).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  className="delete-btn"
                  onClick={() => {
                    setDeleteConfirmId(s.session_id);
                  }}
                  aria-label={`删除对话 ${s.title}`}
                >
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </>
  );

  return (
    <div
      data-testid="chat-workspace"
      className="flex h-[calc(100vh-5rem)] w-full gap-4 overflow-hidden px-3 sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)] lg:px-4"
    >
      {/* Desktop sidebar */}
      <div className="hidden h-full w-64 flex-shrink-0 flex-col overflow-hidden rounded-[1.25rem] border border-white/8 bg-card/82 shadow-soft-card md:flex">
        {sidebarContent}
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <div className="page-drawer-overlay absolute inset-0" />
          <div
            className="absolute left-0 top-0 bottom-0 w-72 flex flex-col glass-card overflow-hidden border-r border-white/10 bg-card/90 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={Boolean(deleteConfirmId)}
        title="删除对话"
        message="删除后，该对话将不可恢复，确认删除吗？"
        confirmText="删除"
        cancelText="取消"
        isDanger
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirmId(null)}
      />

      {/* Main chat area */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="mb-4 flex-shrink-0 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen(true)}
                className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-hover transition-colors text-secondary-text hover:text-foreground"
                aria-label="历史对话"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 6h16M4 12h16M4 18h16"
                  />
                </svg>
              </button>
              <svg
                className="w-6 h-6 text-cyan"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
              AI问答
              {activeTopic ? (
                <span className="ml-3 inline-flex items-center gap-1 rounded-lg bg-white/5 px-2 py-0.5 text-xs text-secondary-text">
                  <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  {activeTopic.code} {activeTopic.name}
                </span>
              ) : null}
            </h1>
          </div>
          <p className="text-secondary-text text-sm">
            先明确市场和资产类型，再让 AI 基于数据做知识解释和风险参考。
          </p>
        </header>

        <section className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-white/8 bg-card/82 px-3 py-2.5 shadow-soft-card">
          <label className="flex items-center gap-1.5 text-xs font-medium text-secondary-text">
            市场
            <select
              value={topicForm.market}
              onChange={(event) => setTopicForm((prev) => ({ ...prev, market: event.target.value }))}
              className="input-surface input-focus-glow h-8 rounded-lg border bg-transparent px-2 text-sm text-foreground"
            >
              {MARKET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-elevated text-foreground">{option.label}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs font-medium text-secondary-text">
            大类
            <select
              value={topicForm.assetType}
              onChange={(event) => setTopicForm((prev) => ({ ...prev, assetType: event.target.value }))}
              className="input-surface input-focus-glow h-8 rounded-lg border bg-transparent px-2 text-sm text-foreground"
            >
              {ASSET_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value} className="bg-elevated text-foreground">{option.label}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs font-medium text-secondary-text">
            代码
            <input
              value={topicForm.code}
              onChange={(event) => setTopicForm((prev) => ({ ...prev, code: event.target.value.trim() }))}
              placeholder="600519 / 00700 / AAPL"
              className="input-surface input-focus-glow h-8 w-[130px] rounded-lg border bg-transparent px-2 text-sm text-foreground"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs font-medium text-secondary-text">
            名称
            <input
              value={topicForm.name}
              onChange={(event) => setTopicForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="可选"
              className="input-surface input-focus-glow h-8 w-[110px] rounded-lg border bg-transparent px-2 text-sm text-foreground"
            />
          </label>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleStartTopicChat()}
            disabled={!canStartTopic || topicResolving}
            isLoading={topicResolving}
            className="h-8 whitespace-nowrap"
          >
            开始问答
          </Button>
          {topicError ? (
            <p className="ml-auto text-xs text-danger">{topicError}</p>
          ) : (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleStockSpecialistAnalysis}
                disabled={loading || !activeTopic || activeTopic.assetType !== 'stock'}
                className="ml-auto h-8 whitespace-nowrap"
              >
                个股专家分析
              </Button>
            <label
              className={cn(
                'inline-flex items-center gap-1.5 text-xs',
                contextCompressionLoaded && !contextCompressionSaving
                  ? 'cursor-pointer text-secondary-text'
                  : 'cursor-not-allowed text-muted-text',
              )}
            >
              <input
                type="checkbox"
                checked={contextCompressionEnabled}
                disabled={!contextCompressionLoaded || contextCompressionSaving}
                onChange={(event) => void updateContextCompressionEnabled(event.target.checked)}
                className="chat-skill-checkbox"
              />
              <span>上下文压缩</span>
              <span className="text-[10px] text-muted-text">
                {contextCompressionSaving ? '保存中…' : contextCompressionEnabled ? '已启用' : '未启用'}
              </span>
            </label>
            </>
          )}
        </section>

        <div className="relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden border border-white/6 bg-card/78 glass-card">
          {/* Messages */}
          <ScrollArea
            className="relative z-10 flex-1"
            viewportRef={messagesViewportRef}
            onScroll={handleMessagesScroll}
            viewportClassName="space-y-6 p-4 md:p-6"
            testId="chat-message-scroll"
          >
            {messages.length === 0 && !loading ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState
                  title="选择标的后开始AI问答"
                  description="先在上方填写市场、大类和代码并点击开始问答。系统会按代码和名称固定归集历史对话。"
                  className="max-w-2xl border-dashed bg-card/55"
                  icon={(
                    <svg
                      className="h-8 w-8"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  )}
                  action={(
                    <div className="flex max-w-lg flex-wrap justify-center gap-2">
                      {quickQuestions.map((q, i) => (
                        <button
                          key={i}
                          onClick={() => handleQuickQuestion(q)}
                          disabled={!activeTopic}
                          className="quick-question-btn"
                        >
                          {q.label}
                        </button>
                      ))}
                    </div>
                  )}
                />
              </div>
            ) : (
              messages.map((msg) => {
                const skillLabel = getMessageSkillLabel(msg);
                return (
                <div
                  key={msg.id}
                  className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold shadow-sm transition-all',
                      msg.role === 'user' ? 'chat-avatar-user' : 'chat-avatar-ai'
                    )}
                  >
                    {msg.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div
                    className={cn(
                      'group/message min-w-0 w-fit max-w-[90%] overflow-hidden px-5 py-3.5 transition-colors',
                      msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'
                    )}
                  >
                    {msg.role === 'assistant' && skillLabel && (
                      <div className="mb-2">
                        <Badge variant="info" className="chat-skill-badge shadow-none" aria-label={`技能 ${skillLabel}`}>
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M13 10V3L4 14h7v7l9-11h-7z"
                            />
                          </svg>
                          {skillLabel}
                        </Badge>
                      </div>
                    )}
                    {msg.role === 'assistant' && renderThinkingBlock(msg)}
                    {msg.role === 'assistant' &&
                      expandedThinking.has(msg.id) &&
                      msg.thinkingSteps &&
                      renderThinkingDetails(msg.thinkingSteps)}
                    {msg.role === 'assistant' ? (
                      <div className="relative">
                        <div className="chat-message-actions">
                          <button
                            type="button"
                            onClick={() => copyMessageToClipboard(msg.id, msg.content)}
                            className="chat-copy-btn"
                            aria-label={copiedMessages.has(msg.id) ? text.copied : text.copy}
                          >
                            {copiedMessages.has(msg.id) ? text.copied : text.copy}
                          </button>
                          <button
                            type="button"
                            onClick={() => downloadMessageAsMarkdown(msg)}
                            className="chat-copy-btn"
                            aria-label="导出此条消息为 Markdown"
                          >
                            导出
                          </button>
                        </div>
                        <div className="chat-prose pr-20 sm:pr-24">
                          <Markdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </Markdown>
                        </div>
                      </div>
                    ) : (
                      msg.content
                        .split('\n')
                        .map((line, i) => (
                          <p
                            key={i}
                            className="mb-1 last:mb-0 leading-relaxed"
                          >
                            {line || '\u00A0'}
                          </p>
                        ))
                    )}
                  </div>
                </div>
                );
              })
            )}

            {loading && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-elevated text-foreground flex items-center justify-center flex-shrink-0 text-xs font-bold">
                  AI
                </div>
                <div className="min-w-[200px] max-w-[90%] overflow-hidden rounded-2xl rounded-tl-sm border border-white/6 bg-card/72 px-5 py-4">
                  <div className="flex items-center gap-2.5 text-sm text-secondary-text">
                    <div className="relative w-4 h-4 flex-shrink-0">
                      <div className="absolute inset-0 rounded-full border-2 border-cyan/20" />
                      <div className="absolute inset-0 rounded-full border-2 border-cyan border-t-transparent animate-spin" />
                    </div>
                    <span className="text-secondary-text">
                      {getCurrentStage(progressSteps)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </ScrollArea>

          {showJumpToBottom && (
            <div className="pointer-events-none absolute bottom-[5.75rem] right-4 z-20 md:bottom-24 md:right-6">
              <button
                type="button"
                className="pointer-events-auto chat-copy-btn shadow-soft-card"
                onClick={() => {
                  requestScrollToBottom('smooth');
                  scrollToBottom('smooth');
                }}
                aria-label="查看最新消息"
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 14l-7 7m0 0l-7-7m7 7V3"
                  />
                </svg>
                有新消息
              </button>
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-white/6 bg-card/88 p-4 md:p-6 relative z-20">
            <div className="space-y-3">
              {chatError ? <ApiErrorAlert error={chatError} /> : null}
              {isFollowUpContextLoading ? (
                <InlineAlert
                  variant="info"
                  title="追问上下文加载中"
                  message="正在加载历史分析上下文；现在可直接发送追问。"
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              ) : null}
              {skills.length > 0 && (
              <div className="flex flex-wrap items-start gap-x-5 gap-y-2">
                <span className="text-xs text-muted-text font-medium uppercase tracking-wider flex-shrink-0 mt-1">
                  策略
                </span>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer group mt-0.5">
                  <input
                    type="checkbox"
                    name="general-analysis"
                    value=""
                    checked={selectedSkillIds.length === 0}
                    onChange={() => setSelectedSkillIds([])}
                    className="chat-skill-checkbox"
                  />
                  <span
                    className={`transition-colors text-sm ${selectedSkillIds.length === 0 ? 'text-foreground font-medium' : 'text-secondary-text group-hover:text-foreground'}`}
                  >
                    通用分析
                  </span>
                </label>
                {skills.map((s) => {
                  const checked = selectedSkillIdSet.has(s.id);
                  const disabled = !checked && skillLimitReached;
                  return (
                    <label
                      key={s.id}
                      className={`flex items-center gap-1.5 cursor-pointer group relative mt-0.5 ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
                      onMouseEnter={() => setShowSkillDesc(s.id)}
                      onMouseLeave={() => setShowSkillDesc(null)}
                    >
                      <input
                        type="checkbox"
                        name="skills"
                        value={s.id}
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggleSkillSelection(s.id)}
                        className="chat-skill-checkbox"
                      />
                      <span
                        className={`transition-colors text-sm ${checked ? 'text-foreground font-medium' : 'text-secondary-text group-hover:text-foreground'}`}
                      >
                        {s.name}
                      </span>
                      {showSkillDesc === s.id && s.description && (
                        <div className="skill-desc-tooltip">
                          <p className="skill-title">{s.name}</p>
                          <p>{s.description}</p>
                        </div>
                      )}
                    </label>
                  );
                })}
              </div>
            )}

              <div className="flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="围绕当前标的提问；如需询问其他标的，请从对应标的入口重新进入。 (Enter 发送, Shift+Enter 换行)"
                  disabled={loading || !activeTopic}
                  rows={1}
                  className="input-surface input-focus-glow flex-1 min-h-[44px] max-h-[200px] rounded-xl border bg-transparent px-4 py-2.5 text-sm transition-all focus:outline-none resize-none disabled:cursor-not-allowed disabled:opacity-60"
                  style={{ height: 'auto' }}
                  onInput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = 'auto';
                    t.style.height = `${Math.min(t.scrollHeight, 200)}px`;
                  }}
                />
                <Button
                  variant="primary"
                  onClick={() => handleSend()}
                  disabled={!canSendMessage}
                  isLoading={loading}
                  className="btn-primary flex-shrink-0"
                >
                  发送
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
