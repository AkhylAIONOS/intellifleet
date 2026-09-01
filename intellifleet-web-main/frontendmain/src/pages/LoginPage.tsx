import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api';
import { AuthLayout } from '../components/AuthLayout';
import './Auth.css';
import { useAppStore } from '../store/appStore';

export const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authApi.signin({ email, password });
      console.log(response);
      if (response.success && response.data) {
        console.log(response.data);

        // Create a complete User object
        const user = {
          id: 0,
          first_name: (response as any).user || 'User',
          last_name: '',
          email: email
        };

        // Restore user-specific state from localStorage
        const userStorageKey = `intellifleet-storage-${email}`;
        const savedState = localStorage.getItem(userStorageKey);

        if (savedState) {
          const parsedState = JSON.parse(savedState);
          // Restore the user's previous state
          useAppStore.setState({
            warehouses: parsedState.warehouses || [],
            vehicles: parsedState.vehicles || [],
            activeRoutes: parsedState.activeRoutes || {},
            //chatHistory: parsedState.chatHistory || [],
          });
        } else {
          // New user - start fresh
          useAppStore.getState().resetStore();
        }

        setAuth(user, response.data.token);
        navigate('/dashboard');
      } else {
        setError(response.message || 'Login failed');
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout type="signin">
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Email Address</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="Enter your email"
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="Enter your password"
          />
        </div>
        {error && <div className="error-message">{error}</div>}
        <button type="submit" disabled={loading} className="auth-submit-btn">
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </AuthLayout>
  );
};
