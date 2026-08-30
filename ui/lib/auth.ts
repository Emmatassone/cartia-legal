import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { TokenPair } from "./types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  setTokens: (tokens: TokenPair) => void;
  clear: () => void;
}

// Nota de seguridad: los tokens viven en localStorage, que queda expuesto a XSS. Para
// producción conviene migrar a cookies httpOnly emitidas por el backend; el store ya está
// aislado detrás de esta interfaz para que el cambio no toque los componentes.
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      setTokens: (tokens) =>
        set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token }),
      clear: () => set({ accessToken: null, refreshToken: null }),
    }),
    { name: "cartia-auth" },
  ),
);
