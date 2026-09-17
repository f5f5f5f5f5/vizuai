import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { ApiError, api, type AuthMeResponse } from "@/app/lib/api";

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  authError: string | null;
  login: (email: string, locale?: string | null) => Promise<void>;
  verify: (
    token: string,
    options?: {
      anon_id?: string | null;
      acquisition?: Record<string, unknown> | null;
      locale?: string | null;
    },
  ) => Promise<void>;
  logout: () => Promise<void>;
  userEmail: string | null;
  user: AuthMeResponse["account"] | null;
  balance: number;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [user, setUser] = useState<AuthMeResponse["account"] | null>(null);
  const [balance, setBalance] = useState(0);

  useEffect(() => {
    void refreshSession();
  }, []);

  const applySession = (payload: AuthMeResponse | null) => {
    if (payload?.account?.email) {
      setIsAuthenticated(true);
      setAuthError(null);
      setUserEmail(payload.account.email);
      setUser(payload.account);
      setBalance(Number(payload.balance?.credits || 0));
      return;
    }

    setIsAuthenticated(false);
    setAuthError(null);
    setUserEmail(null);
    setUser(null);
    setBalance(0);
  };

  const refreshSession = async () => {
    try {
      const payload = await api.authMe();
      applySession(payload);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        applySession(null);
      } else {
        console.error("Auth bootstrap failed:", error);
        setAuthError("Не удалось проверить сессию. Проверьте соединение и попробуйте снова.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, locale?: string | null) => {
    setAuthError(null);
    await api.authStart(email, locale);
  };

  const verify = async (
    token: string,
    options?: {
      anon_id?: string | null;
      acquisition?: Record<string, unknown> | null;
      locale?: string | null;
    },
  ) => {
    setAuthError(null);
    await api.authVerify(token, options);
    const payload = await api.authMe();
    applySession(payload);
  };

  const logout = async () => {
    try {
      await api.authLogout();
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      applySession(null);
      window.location.assign("/");
    }
  };

  const value = useMemo(
    () => ({
      isAuthenticated,
      isLoading,
      authError,
      login,
      verify,
      logout,
      userEmail,
      user,
      balance,
      refreshSession,
    }),
    [isAuthenticated, isLoading, authError, userEmail, user, balance],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
