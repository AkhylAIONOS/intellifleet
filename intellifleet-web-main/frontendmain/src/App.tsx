import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryProvider } from './providers/QueryProvider';
import { ProtectedRoute } from './components/ProtectedRoute';
import { DashboardPage } from './pages/DashboardPage';
import { DemoLandingPage } from './pages/DemoLandingPage';
import './App.css';

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
          <Route path="/" element={<DemoLandingPage />} />
        </Routes>
      </BrowserRouter>
    </QueryProvider>
  );
}

export default App;
