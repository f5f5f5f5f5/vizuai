import { Outlet, useLocation } from "react-router";
import { AuthProvider } from "../contexts/AuthContext";
import { ThemeProvider } from "../contexts/ThemeContext";
import { useEffect } from "react";
import { AnalyticsBridge } from "./AnalyticsBridge";
import { AnalyticsConsentBanner } from "./AnalyticsConsentBanner";
import { LocaleProvider } from "../i18n";
import { RouteMetadata } from "./RouteMetadata";
import { StructuredData } from "./StructuredData";

const ROOT_PUBLIC_HOSTS = new Set(["vizuai.example", "www.vizuai.example"]);
const APP_HOST = "app.vizuai.example";

function CanonicalDomainRedirect() {
  const location = useLocation();

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const hostname = window.location.hostname.toLowerCase();
    const isRootPublicHost = ROOT_PUBLIC_HOSTS.has(hostname);
    const needsAppHost =
      location.pathname === "/login" ||
      location.pathname === "/auth/login" ||
      location.pathname.startsWith("/app");

    if (!isRootPublicHost || !needsAppHost) {
      return;
    }

    const nextUrl = new URL(window.location.href);
    nextUrl.hostname = APP_HOST;
    window.location.replace(nextUrl.toString());
  }, [location.pathname, location.search, location.hash]);

  return null;
}

function RouteScrollReset() {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname, location.search]);

  return null;
}

export function RootLayout() {
  return (
    <AuthProvider>
      <LocaleProvider>
        <ThemeProvider>
          <CanonicalDomainRedirect />
          <RouteScrollReset />
          <RouteMetadata />
          <StructuredData />
          <AnalyticsBridge />
          <AnalyticsConsentBanner />
          <Outlet />
        </ThemeProvider>
      </LocaleProvider>
    </AuthProvider>
  );
}
