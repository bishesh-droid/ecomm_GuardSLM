import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getToken, setToken } from "./api";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [cartCount, setCartCount] = useState(0);

  const refreshCart = useCallback(async () => {
    try { setCartCount((await api("/cart")).count); } catch { setCartCount(0); }
  }, []);

  useEffect(() => {
    (async () => {
      if (getToken()) {
        try {
          const me = await api("/auth/me");
          setUser(me);
          if (me.role === "CUSTOMER") refreshCart();
        } catch { setToken(null); }
      }
      setReady(true);
    })();
  }, [refreshCart]);

  const login = async (username, password) => {
    const res = await api("/auth/login", { method: "POST", body: { username, password } });
    setToken(res.access_token);
    setUser(res.user);
    if (res.user.role === "CUSTOMER") refreshCart();
    return res.user;
  };
  const logout = () => { setToken(null); setUser(null); setCartCount(0); };

  return <Ctx.Provider value={{ user, ready, login, logout, cartCount, refreshCart }}>{children}</Ctx.Provider>;
}

export const homeFor = (role) =>
  ({ ADMIN: "/admin", SELLER: "/seller", WAREHOUSE: "/warehouse", SUPPORT: "/support", CUSTOMER: "/" })[role] || "/";
