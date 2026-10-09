import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryProvider } from './providers/QueryProvider';
import { ProtectedRoute } from './components/ProtectedRoute';
import { DashboardPage } from './pages/DashboardPage';
import { DemoLandingPage } from './pages/DemoLandingPage';
import './App.css';
import {AdminUsersPage} from './pages/AdminUsersPage';

function App() {
  return (
    <QueryProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<DemoLandingPage />} />
          <Route path="/signup" element={<DemoLandingPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          {['/planning','/live-operations'].map(path=><Route key={path} path={path} element={<ProtectedRoute><DashboardPage/></ProtectedRoute>}/>)}
          <Route path="/plan" element={<Navigate to="/planning" replace/>}/>
          <Route path="/schedules" element={<Navigate to="/planning?section=schedules" replace/>}/>
          <Route path="/schedule" element={<Navigate to="/planning?section=schedules" replace/>}/>
          <Route path="/network" element={<Navigate to="/planning?section=network" replace/>}/>
          <Route path="/ai-chat" element={<Navigate to="/dashboard?chat=open" replace/>}/>
          <Route path="/internal/users" element={<ProtectedRoute><AdminUsersPage /></ProtectedRoute>} />
          <Route path="/" element={<DemoLandingPage />} />
        </Routes>
      </BrowserRouter>
    </QueryProvider>
  );
}

export default App;
