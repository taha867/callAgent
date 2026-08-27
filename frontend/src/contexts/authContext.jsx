import { createContext, useContext } from "react";

const AuthContext = createContext({ user: null, isAuthenticated: false });

export function AuthProvider({ children }) {
  // Replaced once src/auth/ exists on the backend — see phase-0-frontend-spec.md decision 1.
  return <AuthContext.Provider value={{ user: null, isAuthenticated: false }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
