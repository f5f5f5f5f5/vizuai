import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useLocation } from "react-router";

import { useAuth } from "@/app/contexts/AuthContext";

export type AppLocale = "ru" | "en";

const LOCALE_STORAGE_KEY = "vizuai.locale";
const PUBLIC_EN_PREFIX = "/en";

type LocaleContextValue = {
  locale: AppLocale;
  setLocale: (nextLocale: AppLocale) => void;
  publicPath: (path: string) => string;
  publicPathForLocale: (path: string, locale: AppLocale) => string;
  loginPath: string;
  isEnglish: boolean;
};

const LocaleContext = createContext<LocaleContextValue | undefined>(undefined);

function normalizeLocale(value: string | null | undefined): AppLocale | null {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("en")) {
    return "en";
  }
  if (normalized.startsWith("ru")) {
    return "ru";
  }
  return null;
}

function detectBrowserLocale(): AppLocale {
  if (typeof navigator === "undefined") {
    return "ru";
  }
  return normalizeLocale(navigator.language) || "ru";
}

export function getPathLocale(pathname: string): AppLocale | null {
  const normalizedPath = pathname || "/";
  if (normalizedPath === PUBLIC_EN_PREFIX || normalizedPath.startsWith(`${PUBLIC_EN_PREFIX}/`)) {
    return "en";
  }
  return null;
}

export function stripLocalePrefix(pathname: string): string {
  const normalizedPath = pathname || "/";
  if (normalizedPath === PUBLIC_EN_PREFIX) {
    return "/";
  }
  if (normalizedPath.startsWith(`${PUBLIC_EN_PREFIX}/`)) {
    return normalizedPath.slice(PUBLIC_EN_PREFIX.length) || "/";
  }
  return normalizedPath;
}

export function localizePublicPath(path: string, locale: AppLocale): string {
  const normalizedPath = path === "/" ? "/" : path.replace(/\/$/, "");
  if (locale === "en") {
    return normalizedPath === "/" ? PUBLIC_EN_PREFIX : `${PUBLIC_EN_PREFIX}${normalizedPath}`;
  }
  return normalizedPath;
}

function readStoredLocale(): AppLocale | null {
  if (typeof window === "undefined") {
    return null;
  }
  return normalizeLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY));
}

function writeStoredLocale(locale: AppLocale) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
}

function isAppScopedPath(pathname: string): boolean {
  return pathname.startsWith("/app");
}

function isAuthScopedPath(pathname: string): boolean {
  return pathname.startsWith("/login") || pathname.startsWith("/auth");
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { user } = useAuth();
  const pathLocale = getPathLocale(location.pathname);
  const appScopedPath = isAppScopedPath(location.pathname);
  const authScopedPath = isAuthScopedPath(location.pathname);
  const queryLocale = useMemo(
    () => normalizeLocale(new URLSearchParams(location.search).get("lang")),
    [location.search],
  );
  const accountLocale = normalizeLocale(user?.locale);
  const [storedLocale, setStoredLocale] = useState<AppLocale>(() => readStoredLocale() || detectBrowserLocale());

  useEffect(() => {
    if (!queryLocale || pathLocale) {
      return;
    }
    writeStoredLocale(queryLocale);
    setStoredLocale(queryLocale);
  }, [pathLocale, queryLocale]);

  useEffect(() => {
    if (!accountLocale) {
      return;
    }
    writeStoredLocale(accountLocale);
    setStoredLocale(accountLocale);
  }, [accountLocale]);

  const locale = authScopedPath
    ? queryLocale || storedLocale || accountLocale || detectBrowserLocale() || "ru"
    : appScopedPath
      ? queryLocale || accountLocale || storedLocale || detectBrowserLocale() || "ru"
      : pathLocale || "ru";

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      setLocale: (nextLocale) => {
        writeStoredLocale(nextLocale);
        setStoredLocale(nextLocale);
      },
      publicPath: (path) => localizePublicPath(path, locale),
      publicPathForLocale: (path, nextLocale) => localizePublicPath(path, nextLocale),
      loginPath: locale === "en" ? "/login?lang=en" : "/login?lang=ru",
      isEnglish: locale === "en",
    }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return context;
}
