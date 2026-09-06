import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryProvider } from './providers/QueryProvider';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { DashboardPage } from './pages/DashboardPage';
import { DemoLandingPage } from './pages/DemoLandingPage';
import { DEMO_ACCESS_ENABLED } from './config/env';
import './App.css';

function App() {
  return (
    <QueryProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={DEMO_ACCESS_ENABLED ? <DemoLandingPage /> : <LoginPage />} />
          <Route path="/signup" element={DEMO_ACCESS_ENABLED ? <DemoLandingPage /> : <SignupPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={DEMO_ACCESS_ENABLED ? <DemoLandingPage /> : <Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryProvider>
  );
}

export default App;
