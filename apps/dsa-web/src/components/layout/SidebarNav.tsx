import React, { useState } from 'react';
import { motion } from 'motion/react';
import { BarChart3, Bell, Bot, BriefcaseBusiness, Database, Eye, Home, Landmark, LogOut, MessageSquareQuote, PieChart, Settings2 } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
  orientation?: 'vertical' | 'horizontal';
};

type NavItem = {
  key: string;
  label: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: 'completion';
};

const NAV_ITEMS: NavItem[] = [
  { key: 'home', label: '首页', to: '/', icon: Home, exact: true },
  { key: 'watchlist', label: '关注标的', to: '/watchlist', icon: Eye },
  { key: 'asset-manage', label: '资产管理', to: '/assets/manage', icon: Landmark },
  { key: 'asset-allocation', label: '资产配置', to: '/assets/allocation', icon: BarChart3 },
  { key: 'asset-init', label: '资产初始化', to: '/assets/init', icon: BriefcaseBusiness },
  { key: 'asset-events', label: '资产事件', to: '/assets/events', icon: Database },
  { key: 'analysis', label: '分析台', to: '/analysis', icon: BarChart3 },
  { key: 'chat', label: '问股', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'funds', label: '基金', to: '/funds', icon: PieChart },
  { key: 'agents', label: 'Agent 管理', to: '/agents', icon: Bot },
  { key: 'backtest', label: '回测', to: '/backtest', icon: BarChart3 },
  { key: 'alerts', label: '告警', to: '/alerts', icon: Bell },
  { key: 'settings', label: '设置', to: '/settings', icon: Settings2 },
];

export const SidebarNav: React.FC<SidebarNavProps> = ({ collapsed = false, onNavigate, orientation = 'vertical' }) => {
  const { authEnabled, logout } = useAuth();
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const isHorizontal = orientation === 'horizontal';

  return (
    <div className={cn('flex', isHorizontal ? 'w-full items-center gap-3' : 'h-full flex-col')}>
      <div className={cn('flex items-center gap-2 px-1', isHorizontal ? 'shrink-0 pr-3' : 'mb-4', collapsed ? 'justify-center' : '')}>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-gradient text-[hsl(var(--primary-foreground))] shadow-[0_12px_28px_var(--nav-brand-shadow)]">
          <BarChart3 className="h-5 w-5" />
        </div>
        {!collapsed ? (
          <p className="min-w-0 truncate text-sm font-semibold text-foreground">NestCheck</p>
        ) : null}
      </div>

      <nav className={cn('flex flex-1', isHorizontal ? 'min-w-0 flex-row flex-wrap items-center gap-1.5' : 'flex-col gap-1')} aria-label="主导航">
        {NAV_ITEMS.map(({ key, label, to, icon: Icon, exact, badge }) => (
          <NavLink
            key={key}
            to={to}
            end={exact}
            onClick={onNavigate}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center text-sm transition-all',
                isHorizontal ? 'h-10 gap-2 rounded-xl border border-transparent px-3' : 'h-[var(--nav-item-height)] gap-2.5 border-y border-x-0',
                collapsed ? 'justify-center px-0' : isHorizontal ? '' : 'px-[var(--nav-item-padding-x)]',
                isActive
                  ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-[hsl(var(--primary))] font-medium'
                  : 'border-transparent text-secondary-text hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div 
                    layoutId="activeIndicator"
                    className={cn(
                      'absolute bg-[var(--nav-indicator-bg)] shadow-[0_0_10px_var(--nav-indicator-shadow)]',
                      isHorizontal ? 'inset-x-3 bottom-0 h-0.5 rounded-full' : 'top-0 bottom-0 left-0 w-[var(--nav-indicator-width)]'
                    )}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2 }}
                  />
                )}
                <Icon className={cn(isHorizontal ? 'h-4.5 w-4.5 shrink-0' : 'ml-0.5 h-5 w-5 shrink-0', isActive ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
                {!collapsed ? <span className="min-w-0 flex-1 truncate">{label}</span> : null}
                {badge === 'completion' && completionBadge ? (
                  <StatusDot
                    tone="info"
                    data-testid="chat-completion-badge"
                    className={cn(
                      'absolute border-2 border-background shadow-[0_0_10px_var(--nav-indicator-shadow)]',
                      isHorizontal ? 'right-1.5 top-1.5' : 'right-3',
                      collapsed ? 'right-2 top-2' : ''
                    )}
                    aria-label="问股有新消息"
                  />
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className={cn(isHorizontal ? 'ml-auto' : 'mt-4 mb-2')}>
        <ThemeToggle variant="nav" collapsed={collapsed} />
      </div>

      {authEnabled ? (
        <button
          type="button"
          onClick={() => setShowLogoutConfirm(true)}
          className={cn(
            'flex h-11 cursor-pointer select-none items-center gap-3 rounded-2xl border border-transparent px-3 text-sm text-secondary-text transition-all hover:border-border/70 hover:bg-hover hover:text-foreground',
            isHorizontal ? 'ml-1 shrink-0' : 'mt-5 w-full',
            collapsed ? 'justify-center px-2' : ''
          )}
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed ? <span>退出</span> : null}
        </button>
      ) : null}

      <ConfirmDialog
        isOpen={showLogoutConfirm}
        title="退出登录"
        message="确认退出当前登录状态吗？退出后需要重新输入密码。"
        confirmText="确认退出"
        cancelText="取消"
        isDanger
        onConfirm={() => {
          setShowLogoutConfirm(false);
          onNavigate?.();
          void logout();
        }}
        onCancel={() => setShowLogoutConfirm(false)}
      />
    </div>
  );
};
