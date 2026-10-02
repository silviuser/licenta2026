import { useEffect } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { UNAUTHORIZED_EVENT } from './api/client';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { Layout } from './components/Layout';
import { useToast } from './components/toastContext';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { JdDetailPage } from './pages/JdDetailPage';
import { JdEditPage } from './pages/JdEditPage';
import { LoginPage } from './pages/LoginPage';
import { MatchResultPage } from './pages/MatchResultPage';
import { PublicApplyPage } from './pages/PublicApplyPage';
import { RegisterPage } from './pages/RegisterPage';
import { ROUTES } from './lib/constants';

export default function App() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  // Global 401 handling: the axios interceptor fires this event (§5).
  useEffect(() => {
    const handler = () => {
      showToast('Your session expired. Please sign in again.', 'warning');
      navigate(ROUTES.login, { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [navigate, showToast]);

  return (
    <Routes>
      <Route path={ROUTES.login} element={<LoginPage />} />
      <Route path={ROUTES.register} element={<RegisterPage />} />

      {/* Public candidate apply page — outside the auth guard and app layout (REWORK 3 D32). */}
      <Route path="/apply/:token" element={<PublicApplyPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          {/* Landing = dashboard — REWORK 2 D30. */}
          <Route path={ROUTES.dashboard} element={<DashboardPage />} />
          <Route path={ROUTES.jdNew} element={<JdEditPage />} />
          <Route path="/jds/:id" element={<JdDetailPage />} />
          <Route path="/match/:jobId" element={<MatchResultPage />} />
          <Route path={ROUTES.history} element={<HistoryPage />} />
        </Route>
      </Route>

      {/* Legacy routes removed in REWORK 2 (D31) → dashboard. More specific
          /jds/new and /jds/:id above win for those paths. */}
      <Route path={ROUTES.cvs} element={<Navigate to={ROUTES.dashboard} replace />} />
      <Route path={ROUTES.jds} element={<Navigate to={ROUTES.dashboard} replace />} />
      <Route path="*" element={<Navigate to={ROUTES.dashboard} replace />} />
    </Routes>
  );
}
