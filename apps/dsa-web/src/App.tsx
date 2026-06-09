import type React from 'react';
import { lazy, useEffect } from 'react';
import { BrowserRouter as Router, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { ApiErrorAlert, Shell } from './components/common';
import {
  PageLoadingFallback,
  RouteOutletBoundary,
  StandaloneRouteBoundary,
} from './components/layout/RouteBoundary';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { useAgentChatStore } from './stores/agentChatStore';
import './App.css';

const AssetDashboardPage = lazy(() => import('./pages/AssetDashboardPage'));
const AssetManagementPage = lazy(() => import('./pages/AssetManagementPage'));
const AssetOpenDatesPage = lazy(() => import('./pages/AssetOpenDatesPage'));
const AssetDiagnosisPage = lazy(() => import('./pages/AssetDiagnosisPage'));
const AssetAllocationPage = lazy(() => import('./pages/AssetAllocationPage'));
const AssetInitializationPage = lazy(() => import('./pages/AssetInitializationPage'));
const AssetEventsPage = lazy(() => import('./pages/AssetEventsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'));
const AgentManagementPage = lazy(() => import('./pages/AgentManagementPage'));

const AppContent: React.FC = () => {
  const location = useLocation();
  const { authEnabled, loggedIn, isLoading, loadError, refreshStatus } = useAuth();

  useEffect(() => {
    useAgentChatStore.getState().setCurrentRoute(location.pathname);
  }, [location.pathname]);

  if (isLoading) {
    return <PageLoadingFallback />;
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-base px-4">
        <div className="w-full max-w-lg">
          <ApiErrorAlert error={loadError} />
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={() => void refreshStatus()}
        >
          重试
        </button>
      </div>
    );
  }

  if (authEnabled && !loggedIn) {
    if (location.pathname === '/login') {
      return (
        <StandaloneRouteBoundary>
          <LoginPage />
        </StandaloneRouteBoundary>
      );
    }
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }

  if (location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }

  return (
    <Routes>
      <Route
        element={(
          <Shell>
            <RouteOutletBoundary />
          </Shell>
        )}
      >
        <Route path="/" element={<AssetDashboardPage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/analysis" element={<Navigate to="/watchlist" replace />} />
        <Route path="/assets/manage" element={<AssetManagementPage />} />
        <Route path="/assets/open-dates" element={<AssetOpenDatesPage />} />
        <Route path="/assets/diagnosis" element={<AssetDiagnosisPage />} />
        <Route path="/assets/allocation" element={<AssetAllocationPage />} />
        <Route path="/assets/init" element={<AssetInitializationPage />} />
        <Route path="/assets/events" element={<AssetEventsPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/funds" element={<Navigate to="/chat" replace />} />
        <Route path="/agents" element={<AgentManagementPage />} />
        <Route path="/portfolio" element={<AssetInitializationPage />} />
        <Route path="/backtest" element={<Navigate to="/assets/diagnosis" replace />} />
        <Route path="/alerts" element={<Navigate to="/watchlist" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </Router>
  );
};

export default App;
