import { useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { authApi } from '../api/auth';
import { isTokenUnexpired, useAuthStore } from '../store/authStore';
import { useAppStore } from '../store/appStore';

export function DemoLandingPage() {
  const [name,setName]=useState(''),[email,setEmail]=useState(''),[error,setError]=useState('');
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
    setLoading(true);setError('');
    try {
      const response = await authApi.demoAccess({name:name.trim(),email:email.trim().toLowerCase()});
      if (!response.success || !response.data?.user || !response.data?.token) {
        throw new Error('Demo entry failed');
      }
      // Avoid carrying another signed-in user's cached network into demo entry.
      useAppStore.getState().resetStore();
      setAuth(response.data.user, response.data.token);
      navigate('/dashboard', {replace: true});
    } catch (err: any) {
      const detail=err.response?.data?.detail;
      setError(typeof detail==='string'?detail:'Enter a valid email and a name for a new account.');
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  return <AuthLayout type="demo">
    <form onSubmit={e=>{e.preventDefault();void enter();}}>
      <div className="form-group"><label htmlFor="demo-name">Name</label><input id="demo-name" name="name" autoComplete="name" maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></div>
      <div className="form-group"><label htmlFor="demo-email">Email</label><input id="demo-email" name="email" type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)}/></div>
      {error&&<p role="alert">{error}</p>}
      <button type="submit" className="auth-submit-btn" disabled={loading}>{loading?'Entering UniFleet...':'Continue to UniFleet'}</button>
      <p>Temporary demo login using email identity; not production-secure authentication.</p>
    </form>
  </AuthLayout>;
}
