import { create } from 'zustand';

interface User {
  username: string;
  role: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  setAuth: (token, user) => {
    localStorage.setItem('skuld_token', token);
    localStorage.setItem('skuld_user', JSON.stringify(user));
    set({ token, user });
  },
  logout: () => {
    localStorage.removeItem('skuld_token');
    localStorage.removeItem('skuld_user');
    set({ token: null, user: null });
  },
  hydrate: () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('skuld_token');
    const userStr = localStorage.getItem('skuld_user');
    if (token && userStr) {
      set({ token, user: JSON.parse(userStr) });
    }
  },
}));
