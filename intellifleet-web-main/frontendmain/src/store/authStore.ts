import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types/api';

// This is only a client-side expiry check; protected APIs verify JWT signatures.
export function isTokenUnexpired(token: string | null): boolean {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' && payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      setAuth: (user, token) => {
        localStorage.setItem('authToken', token);
        set({ user, token, isAuthenticated: true });
      },
      clearAuth: () => {
        localStorage.removeItem('authToken');
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
      merge: (persisted, current) => {
        const saved = persisted as Partial<AuthState> | undefined;
        const token = localStorage.getItem('authToken');
        const valid = isTokenUnexpired(token) && !!saved?.user;
        return {...current, user: valid ? saved!.user! : null,
          token: valid ? token : null, isAuthenticated: valid};
      },
    }
  )
);
