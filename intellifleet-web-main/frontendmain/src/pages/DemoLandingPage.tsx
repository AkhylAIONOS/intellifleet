import { useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { authApi } from '../api/auth';
import { isTokenUnexpired, useAuthStore } from '../store/authStore';
import { useAppStore } from '../store/appStore';

export function DemoLandingPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
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
    setError(false);
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
      setError(true);
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  return <AuthLayout type="demo">
    <p className="demo-description">Plan routes, optimize vehicles, manage warehouses,
      simulate disruptions and make faster logistics decisions
      from one unified planning system.</p>
    <button type="button" className="auth-submit-btn" disabled={loading} onClick={enter}>
      {loading ? 'Entering UniFleet...' : 'Enter UniFleet'}
    </button>
    <p className="demo-continue">Continue to the planning dashboard</p>
    {error && <p className="demo-entry-error" role="alert">Unable to enter UniFleet. Please try again.</p>}
  </AuthLayout>;
}
