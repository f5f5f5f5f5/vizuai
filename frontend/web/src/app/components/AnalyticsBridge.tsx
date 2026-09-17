import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { useAuth } from "@/app/contexts/AuthContext";
import {
  primeVisitorAnalyticsContext,
  trackAppPageView,
  trackPublicPageView,
} from "@/app/lib/analytics/client";
import {
  ANALYTICS_CONSENT_CHANGED_EVENT,
  getAnalyticsConsent,
  hasAnalyticsConsent,
  type AnalyticsConsentStatus,
} from "@/app/lib/analytics/consent";

function resolvePublicScreen(pathname: string): string | null {
  if (pathname === "/") {
    return "landing";
  }
  if (pathname === "/faq") {
    return "faq";
  }
  if (pathname === "/pricing") {
    return "pricing";
  }
  if (pathname === "/examples") {
    return "examples";
  }
  if (pathname === "/how-it-works") {
    return "how_it_works";
  }
  if (pathname === "/how-to-design-by-photo") {
    return "guide_design_photo";
  }
  if (pathname === "/how-to-design-by-reference") {
    return "guide_reference";
  }
  if (pathname === "/how-to-find-furniture-by-photo") {
    return "guide_furniture";
  }
  if (pathname === "/interior-design-from-photo") {
    return "use_case_interior";
  }
  if (pathname === "/design-by-reference") {
    return "use_case_reference";
  }
  if (pathname === "/furniture-search-by-photo") {
    return "use_case_furniture";
  }
  if (pathname === "/legal") {
    return "legal";
  }
  if (pathname === "/login" || pathname === "/auth/login") {
    return "login";
  }
  return null;
}

function resolveAppScreen(pathname: string): string | null {
  if (pathname === "/app") {
    return "home";
  }
  if (pathname === "/app/workspace") {
    return "workspace";
  }
  if (pathname.startsWith("/app/workspace/result/")) {
    return "result";
  }
  if (pathname === "/app/billing") {
    return "billing";
  }
  if (pathname === "/app/profile") {
    return "profile";
  }
  return null;
}

export function AnalyticsBridge() {
  const location = useLocation();
  const { isAuthenticated, isLoading } = useAuth();
  const lastTrackedRef = useRef<string | null>(null);
  const [analyticsEnabled, setAnalyticsEnabled] = useState(() => hasAnalyticsConsent());

  useEffect(() => {
    primeVisitorAnalyticsContext();
  }, []);

  useEffect(() => {
    const handleConsentChange = (event: Event) => {
      const detail = (event as CustomEvent<AnalyticsConsentStatus>).detail ?? getAnalyticsConsent();
      setAnalyticsEnabled(detail === "accepted");
      if (detail === "accepted") {
        lastTrackedRef.current = null;
      }
    };
    window.addEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, handleConsentChange);
    return () => {
      window.removeEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, handleConsentChange);
    };
  }, []);

  useEffect(() => {
    if (!analyticsEnabled) {
      return;
    }
    const publicScreen = resolvePublicScreen(location.pathname);
    if (publicScreen) {
      const key = `public:${location.pathname}:${location.search}`;
      if (lastTrackedRef.current === key) {
        return;
      }
      lastTrackedRef.current = key;
      void trackPublicPageView(publicScreen);
      return;
    }

    const appScreen = resolveAppScreen(location.pathname);
    if (!appScreen || isLoading || !isAuthenticated) {
      return;
    }
    const key = `app:${location.pathname}:${location.search}`;
    if (lastTrackedRef.current === key) {
      return;
    }
    lastTrackedRef.current = key;
    void trackAppPageView(appScreen);
  }, [analyticsEnabled, location.pathname, location.search, isAuthenticated, isLoading]);

  return null;
}
