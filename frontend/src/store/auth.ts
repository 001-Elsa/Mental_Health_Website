import { create } from "zustand";
import type { User } from "../types";

type AuthState = {
  token: string | null;
  user: User | null;
  initialized: boolean;
  setAuth: (token: string, user: User) => void;
  setToken: (token: string) => void;
  setInitialized: (initialized: boolean) => void;
  setUser: (user: User) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>()(
    (set) => ({
      token: null,
      user: null,
      initialized: false,
      setAuth: (token, user) => set({ token, user, initialized: true }),
      setToken: (token) => set({ token }),
      setInitialized: (initialized) => set({ initialized }),
      setUser: (user) => set({ user }),
      logout: () => {
        void fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
        set({ token: null, user: null, initialized: true });
      },
    }),
);
