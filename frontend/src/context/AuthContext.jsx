import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authApi, tokenStore } from "../services/api.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  useEffect(() => {
    if (!tokenStore.get()) return;
    authApi.me().then((r) => setUser(r.user)).catch(() => tokenStore.clear()).finally(() => setLoading(false));
  }, []);

  const finish = useCallback((r) => { tokenStore.set(r.access_token); setUser(r.user); return r.user; }, []);
  const login = useCallback(async (b) => finish(await authApi.login(b)), [finish]);
  const register = useCallback(async (b) => finish(await authApi.register(b)), [finish]);
  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* token may already be invalid */ }
    tokenStore.clear();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, login, register, logout, setUser }}>{children}</AuthContext.Provider>;
}
