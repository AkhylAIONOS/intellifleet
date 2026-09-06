import { useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { authApi } from '../api/auth';
import { isTokenUnexpired, useAuthStore } from '../store/authStore';
import { useAppStore } from '../store/appStore';

export function DemoLandingPage() {
  const [loading, setLoading] = useState(false);
  const pending = useRef(false);
  const navigate = useNavigate();
  const {isAuthenticated, token, setAuth} = useAuthStore();

  if (isAuthenticated && isTokenUnexpired(token)) {
    return <Navigate to="/dashboard" replace />;
  }

  const enter = async () => {
    if (pending.current) return;
    pending.current = true;
    setLoading(true);
    try {
      const response = await authApi.demoAccess();
      if (!response.success || !response.data?.user || !isTokenUnexpired(response.data.token)) {
        throw new Error('Demo entry failed');
      }
      // Avoid carrying another signed-in user's cached network into demo entry.
      useAppStore.getState().resetStore();
      setAuth(response.data.user, response.data.token);
      navigate('/dashboard', {replace: true});
    } catch {
      // Stay on the welcome page and allow retry without showing auth errors.
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  return <AuthLayout type="demo">
    <button type="button" className="auth-submit-btn" disabled={loading} onClick={enter}>
      {loading ? 'Entering UniFleet...' : 'Enter UniFleet'}
    </button>
  </AuthLayout>;
}
