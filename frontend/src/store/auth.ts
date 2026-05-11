import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../types";

type AuthState = {
  token: string;
  user: User | null;
  login: (token: string, user: User) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: "",
      user: null,
      login: (token, user) => set({ token, user }),
      logout: () => set({ token: "", user: null }),
    }),
    {
      name: "pypmis_auth",
      partialize: (state) => ({ token: state.token, user: state.user }),
    },
  ),
);
