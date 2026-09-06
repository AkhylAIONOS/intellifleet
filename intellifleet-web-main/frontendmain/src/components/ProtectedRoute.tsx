import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { isTokenUnexpired, useAuthStore } from '../store/authStore';

interface ProtectedRouteProps {
  children: ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { isAuthenticated, token } = useAuthStore();

  if (!isAuthenticated || !isTokenUnexpired(token)) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};
