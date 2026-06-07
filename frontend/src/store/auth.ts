import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  access_token: string | null;
  refresh_token: string | null;
  email: string | null;
  role: string | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (email: string, role: string) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      access_token: null,
      refresh_token: null,
      email: null,
      role: null,
      setTokens: (access, refresh) => set({ access_token: access, refresh_token: refresh }),
      setUser: (email, role) => set({ email, role }),
      logout: () => set({ access_token: null, refresh_token: null, email: null, role: null }),
      isAuthenticated: () => !!get().access_token,
    }),
    { name: "gold-ai-auth" }
  )
);
