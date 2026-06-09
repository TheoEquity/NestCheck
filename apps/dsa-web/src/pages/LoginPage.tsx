import type React from 'react';
import { useState, useEffect } from 'react';
import { motion } from "motion/react";
import { Lock, Loader2, ShieldCheck, KeyRound, ArrowLeft } from "lucide-react";
import { Button, Input } from '../components/common';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ParsedApiError } from '../api/error';
import { isParsedApiError } from '../api/error';
import { useAuth } from '../hooks';
import { SettingsAlert } from '../components/settings';
import { apiRequest } from '../api';

type LoginMode = 'login' | 'setup' | 'setup-question' | 'forgot-question' | 'forgot-reset';

const SECURITY_QUESTIONS = [
  "你的出生年份是多少？",
  "你母亲的姓名是什么？",
  "你小学的名字是什么？",
  "你最好的朋友叫什么？",
  "你的第一只宠物名字是什么？",
  "你出生城市的名字是什么？",
  "你的生日（月日）是什么？",
  "你的工牌号是多少？",
  "你最喜欢的球队是哪个？",
  "你第一次旅行的目的地是哪里？",
];

const LoginPage: React.FC = () => {
  const { login, passwordSet, setupState } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = '登录 - NestCheck';
  }, []);

  const [searchParams] = useSearchParams();
  const rawRedirect = searchParams.get('redirect') ?? '';
  const redirect =
    rawRedirect.startsWith('/') && !rawRedirect.startsWith('//') ? rawRedirect : '/';

  const [mode, setMode] = useState<LoginMode>(setupState === 'no_password' || !passwordSet ? 'setup' : 'login');

  // Login/Setup fields
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');

  // Security question for setup
  const [setupQuestionIndex, setSetupQuestionIndex] = useState(0);
  const [setupAnswer, setSetupAnswer] = useState('');

  // Forgot password fields
  const [forgotQuestionIndex, setForgotQuestionIndex] = useState(0);
  const [forgotAnswer, setForgotAnswer] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('');

  // Common
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    if (mode === 'setup' && password !== passwordConfirm) {
      setError('两次输入的密码不一致');
      return;
    }
    if (mode === 'setup-question' && !setupAnswer.trim()) {
      setError('请设置安全问题答案');
      return;
    }
    setIsSubmitting(true);
    try {
      const result = await login(
        password,
        (mode === 'setup' || mode === 'setup-question') ? passwordConfirm : undefined,
        mode === 'setup-question' ? setupQuestionIndex : undefined,
        mode === 'setup-question' ? setupAnswer : undefined,
      );
      if (result.success) {
        navigate(redirect, { replace: true });
      } else {
        setError(result.error ?? '登录失败');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCheckAnswer = async () => {
    setError(null);
    setSuccessMsg(null);
    if (!forgotAnswer.trim()) {
      setError('请输入答案');
      return;
    }
    setIsSubmitting(true);
    try {
      await apiRequest('/auth/check-security-answer', {
        method: 'POST',
        body: JSON.stringify({
          questionIndex: forgotQuestionIndex,
          answer: forgotAnswer,
        }),
      });
      setMode('forgot-reset');
    } catch (err: any) {
      setError(err?.message ?? '答案不正确');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword !== newPasswordConfirm) {
      setError('两次输入的新密码不一致');
      return;
    }
    if (!newPassword.trim()) {
      setError('请输入新密码');
      return;
    }
    setIsSubmitting(true);
    try {
      await apiRequest('/auth/reset-password-by-answer', {
        method: 'POST',
        body: JSON.stringify({
          questionIndex: forgotQuestionIndex,
          answer: forgotAnswer,
          newPassword,
          newPasswordConfirm,
        }),
      });
      setSuccessMsg('密码已重置，请使用新密码登录');
      setMode('login');
      setPassword('');
      setPasswordConfirm('');
      setNewPassword('');
      setNewPasswordConfirm('');
      setForgotAnswer('');
    } catch (err: any) {
      setError(err?.message ?? '重置密码失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderForm = () => {
    if (mode === 'forgot-question') {
      return (
        <div className="space-y-5">
          <div className="mb-2">
            <h2 className="text-xl font-semibold text-gray-900">忘记密码</h2>
            <p className="mt-2 text-sm text-gray-500">
              选择您设置的安全问题并回答。
            </p>
          </div>
          <div className="space-y-4">
            <div>
              <label htmlFor="forgot-question-select" className="block mb-2 text-sm font-medium text-gray-700">
                安全问题
              </label>
              <select
                id="forgot-question-select"
                value={forgotQuestionIndex}
                onChange={(e) => setForgotQuestionIndex(Number(e.target.value))}
                disabled={isSubmitting}
                className="h-11 w-full rounded-xl border bg-white px-4 text-sm focus:outline-none focus:ring-2 focus:ring-[hsl(200,70%,40%)] focus:border-[hsl(200,70%,40%)] transition-all"
              >
                {SECURITY_QUESTIONS.map((q, i) => (
                  <option key={i} value={i}>{q}</option>
                ))}
              </select>
            </div>
            <Input
              id="forgot-answer"
              type="text"
              appearance="login"
              iconType="key"
              label="答案"
              placeholder="请输入您的答案"
              value={forgotAnswer}
              onChange={(e) => setForgotAnswer(e.target.value)}
              disabled={isSubmitting}
              autoFocus
            />
          </div>
          {error && (
            <SettingsAlert title="验证失败" message={isParsedApiError(error) ? error.message : error} variant="error" className="!border-[hsl(0,70%,45%)] !bg-[hsl(0,60%,12%/0.5)] !text-[hsl(0,70%,70%)]" />
          )}
          <div className="flex gap-3">
            <Button type="button" variant="outline" size="lg" className="h-12 w-24 rounded-xl" onClick={() => setMode('login')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="primary" size="lg" className="h-12 flex-1 rounded-xl" onClick={handleCheckAnswer} disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              <span>{isSubmitting ? '验证中...' : '验证答案'}</span>
            </Button>
          </div>
        </div>
      );
    }

    if (mode === 'forgot-reset') {
      return (
        <form onSubmit={handleResetPassword} className="space-y-5">
          <div className="mb-2">
            <h2 className="text-xl font-semibold text-gray-900">设置新密码</h2>
            <p className="mt-2 text-sm text-gray-500">
              验证通过，请设置新密码。
            </p>
          </div>
          <div className="space-y-4">
            <Input
              id="new-password"
              type="password"
              appearance="login"
              iconType="password"
              label="新密码"
              placeholder="请设置 6 位以上密码"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={isSubmitting}
              autoFocus
              autoComplete="new-password"
            />
            <Input
              id="new-password-confirm"
              type="password"
              appearance="login"
              iconType="password"
              label="确认新密码"
              placeholder="再次确认新密码"
              value={newPasswordConfirm}
              onChange={(e) => setNewPasswordConfirm(e.target.value)}
              disabled={isSubmitting}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <SettingsAlert title="重置失败" message={isParsedApiError(error) ? error.message : error} variant="error" className="!border-[hsl(0,70%,45%)] !bg-[hsl(0,60%,12%/0.5)] !text-[hsl(0,70%,70%)]" />
          )}
          <Button type="submit" variant="primary" size="lg" className="h-12 w-full rounded-xl" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            <span>{isSubmitting ? '重置中...' : '重置密码'}</span>
          </Button>
        </form>
      );
    }

    if (mode === 'setup') {
      return (
        <form onSubmit={(e) => {
          e.preventDefault();
          if (password !== passwordConfirm) {
            setError('两次输入的密码不一致');
            return;
          }
          setMode('setup-question');
        }} className="space-y-5">
          <div className="mb-2">
            <h2 className="text-xl font-semibold text-gray-900">设置初始密码</h2>
            <p className="mt-2 text-sm text-gray-500">
              首次启用认证，请为系统设置管理员密码。
            </p>
          </div>
          <div className="space-y-4">
            <Input
              id="password"
              type="password"
              appearance="login"
              iconType="password"
              label="管理员密码"
              placeholder="请设置 6 位以上密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              autoFocus
              autoComplete="new-password"
            />
            <Input
              id="passwordConfirm"
              type="password"
              appearance="login"
              iconType="password"
              label="确认密码"
              placeholder="再次确认管理员密码"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              disabled={isSubmitting}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <SettingsAlert title="输入有误" message={isParsedApiError(error) ? error.message : error} variant="error" className="!border-[hsl(0,70%,45%)] !bg-[hsl(0,60%,12%/0.5)] !text-[hsl(0,70%,70%)]" />
          )}
          <Button type="submit" variant="primary" size="lg" className="h-12 w-full rounded-xl" disabled={isSubmitting}>
            <span>下一步：设置安全问题</span>
          </Button>
        </form>
      );
    }

    if (mode === 'setup-question') {
      return (
        <form onSubmit={handleLoginSubmit} className="space-y-5">
          <div className="mb-2">
            <h2 className="text-xl font-semibold text-gray-900">设置安全问题</h2>
            <p className="mt-2 text-sm text-gray-500">
              选择一个安全问题并设置答案，用于忘记密码时验证身份。答案不区分大小写。
            </p>
          </div>
          <div className="space-y-4">
            <div>
              <label htmlFor="setup-question-select" className="block mb-2 text-sm font-medium text-gray-700">
                安全问题
              </label>
              <select
                id="setup-question-select"
                value={setupQuestionIndex}
                onChange={(e) => setSetupQuestionIndex(Number(e.target.value))}
                disabled={isSubmitting}
                className="h-11 w-full rounded-xl border bg-white px-4 text-sm focus:outline-none focus:ring-2 focus:ring-[hsl(200,70%,40%)] focus:border-[hsl(200,70%,40%)] transition-all"
              >
                {SECURITY_QUESTIONS.map((q, i) => (
                  <option key={i} value={i}>{q}</option>
                ))}
              </select>
            </div>
            <Input
              id="setup-answer"
              type="text"
              appearance="login"
              iconType="key"
              label="答案"
              placeholder="请输入您的答案"
              value={setupAnswer}
              onChange={(e) => setSetupAnswer(e.target.value)}
              disabled={isSubmitting}
              autoFocus
            />
          </div>
          {error && (
            <SettingsAlert title="配置失败" message={isParsedApiError(error) ? error.message : error} variant="error" className="!border-[hsl(0,70%,45%)] !bg-[hsl(0,60%,12%/0.5)] !text-[hsl(0,70%,70%)]" />
          )}
          <Button type="submit" variant="primary" size="lg" className="h-12 w-full rounded-xl border-0 bg-gradient-to-r from-[hsl(200_70%_40%)] to-[hsl(180_60%_35%)] font-medium text-white shadow-lg shadow-[hsla(200,70%,30%,0.25)] hover:from-[hsl(200_70%_45%)] hover:to-[hsl(180_60%_40%)] transition-all duration-200" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>初始化中...</span>
              </>
            ) : (
              <>
                <ShieldCheck className="h-4 w-4" />
                <span>完成设置并登录</span>
              </>
            )}
          </Button>
        </form>
      );
    }

    // Login mode
    return (
      <form onSubmit={handleLoginSubmit} className="space-y-5">
        <div className="space-y-4">
          <Input
            id="password"
            type="password"
            appearance="login"
            iconType="password"
            label="登录密码"
            placeholder="请输入密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={isSubmitting}
            autoFocus
            autoComplete="current-password"
          />
        </div>

        {error && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="overflow-hidden">
            <SettingsAlert title="验证未通过" message={isParsedApiError(error) ? error.message : error} variant="error" className="!border-[hsl(0,70%,45%)] !bg-[hsl(0,60%,12%/0.5)] !text-[hsl(0,70%,70%)]" />
          </motion.div>
        )}

        {successMsg && (
          <SettingsAlert title="操作成功" message={successMsg} variant="success" className="!border-[hsl(160,60%,40%)] !bg-[hsl(160,50%,90%/0.5)] !text-[hsl(160,60%,30%)]" />
        )}

        <Button type="submit" variant="primary" size="lg" className="h-12 w-full rounded-xl border-0 bg-gradient-to-r from-[hsl(200_70%_40%)] to-[hsl(180_60%_35%)] font-medium text-white shadow-lg shadow-[hsla(200,70%,30%,0.25)] hover:from-[hsl(200_70%,45%)] hover:to-[hsl(180,60%,40%)] transition-all duration-200" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>正在验证...</span>
            </>
          ) : (
            <>
              <Lock className="h-4 w-4" />
              <span>登录</span>
            </>
          )}
        </Button>

        {/* Forgot password link */}
        <p className="mt-4 text-center">
          <button type="button" className="text-sm text-gray-400 hover:text-gray-600 transition-colors" onClick={() => setMode('forgot-question')}>
            忘记密码？通过安全问题找回
          </button>
        </p>
      </form>
    );
  };

  return (
    <div className="flex min-h-screen overflow-hidden bg-[hsl(220_15%_8%)] font-sans">
      {/* Left: Branding Panel */}
      <div className="hidden lg:flex lg:w-[40%] relative flex-col justify-center overflow-hidden bg-gradient-to-br from-[hsl(220_50%_6%)] via-[hsl(210_60%_10%)] to-[hsl(200_55%_8%)]">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,hsla(220,60%,80%,0.03)_1px,transparent_1px),linear-gradient(to_bottom,hsla(220,60%,80%,0.03)_1px,transparent_1px)] bg-[size:40px_40px]" />
        <motion.div animate={{ scale: [1, 1.08, 1], opacity: [0.12, 0.18, 0.12] }} transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }} className="pointer-events-none absolute -right-20 -top-20 h-[600px] w-[600px] rounded-full bg-[hsla(200_80%_50%/0.15)] blur-[120px]" />
        <motion.div animate={{ scale: [1, 1.12, 1], opacity: [0.08, 0.14, 0.08] }} transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", delay: 2 }} className="pointer-events-none absolute -bottom-32 -left-32 h-[500px] w-[500px] rounded-full bg-[hsla(160_70%_45%/0.10)] blur-[100px]" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <motion.div animate={{ rotate: 360 }} transition={{ duration: 120, repeat: Infinity, ease: "linear" }} className="h-[500px] w-[500px] rounded-full border border-[hsla(200_50%_60%/0.06)]" />
        </div>
        <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <motion.div animate={{ rotate: -360 }} transition={{ duration: 90, repeat: Infinity, ease: "linear" }} className="h-[350px] w-[350px] rounded-full border border-[hsla(200_50%_60%/0.04)]" />
        </div>
        <div className="relative z-10 px-16 xl:px-24">
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: "easeOut" }}>
            <div className="flex items-baseline gap-3">
              <h1 className="text-7xl font-black tracking-tight text-white">
                Nest<span className="bg-gradient-to-r from-[hsl(200_80%_55%)] to-[hsl(160_70%_50%)] bg-clip-text text-transparent">Check</span>
              </h1>
            </div>
            <h2 className="mt-3 text-3xl font-bold tracking-[0.2em] text-[hsla(200,50%,80%,0.7)]">稳巢</h2>
            <div className="mt-8 h-px w-16 bg-gradient-to-r from-[hsla(200_70%_55%/0.5)] to-transparent" />
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-[hsla(210,30%,75%,0.8)]">给个人投资者的资产体检与价值配置助手</p>
            <p className="mt-2 max-w-lg text-base leading-relaxed text-[hsla(210,25%,60%,0.6)]">不为你交易，只帮你把"巢"搭稳。</p>
          </motion.div>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.5 }} className="absolute bottom-16 left-16 xl:left-24 flex gap-10">
            <div>
              <div className="text-xs uppercase tracking-wider text-[hsla(210,25%,50%,0.5)]">资产体检</div>
              <div className="mt-1 text-sm font-medium text-[hsla(200,50%,65%,0.7)]">实时监控持仓健康</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-[hsla(210,25%,50%,0.5)]">价值配置</div>
              <div className="mt-1 text-sm font-medium text-[hsla(200,50%,65%,0.7)]">理性构建资产组合</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-[hsla(210,25%,50%,0.5)]">数据决策</div>
              <div className="mt-1 text-sm font-medium text-[hsla(200,50%,65%,0.7)]">告别情绪化投资</div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Right: Form Panel */}
      <div className="flex w-full flex-col items-center justify-center bg-white lg:w-[60%]">
        <div className="mb-10 text-center lg:hidden">
          <h1 className="text-5xl font-black tracking-tight text-gray-900">
            Nest<span className="bg-gradient-to-r from-[hsl(200_80%_55%)] to-[hsl(160_70%_50%)] bg-clip-text text-transparent">Check</span>
          </h1>
          <h2 className="mt-2 text-xl font-bold tracking-[0.2em] text-gray-500">稳巢</h2>
        </div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: "easeOut" }} className="w-full max-w-md px-6 sm:px-8">
          {renderForm()}
        </motion.div>

        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="absolute bottom-8 text-center text-xs text-[hsla(210,20%,40%,0.4)]">
          {setupState === 'no_password' ? '首次设置密码后将启用登录保护' : '稳巢 · NestCheck'}
        </motion.p>
      </div>
    </div>
  );
};

export default LoginPage;
