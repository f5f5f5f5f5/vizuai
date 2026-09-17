import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/app/components/ui/button";
import { useTheme } from "@/app/contexts/ThemeContext";
import { primeVisitorAnalyticsContext } from "@/app/lib/analytics/client";
import {
  ANALYTICS_CONSENT_CHANGED_EVENT,
  getAnalyticsConsent,
  setAnalyticsConsent,
  type AnalyticsConsentStatus,
} from "@/app/lib/analytics/consent";
import { clearVisitorAnalyticsStorage } from "@/app/lib/analytics/visitor";

const ANALYTICS_BANNER_DISMISSED_KEY = "vizuai_analytics_banner_dismissed";

function isBannerDismissed(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.sessionStorage.getItem(ANALYTICS_BANNER_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function dismissBannerForSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(ANALYTICS_BANNER_DISMISSED_KEY, "1");
  } catch {
    // Ignore session persistence failures.
  }
}

export function AnalyticsConsentBanner() {
  const { isDarkMode } = useTheme();
  const [isMounted, setIsMounted] = useState(false);
  const [consent, setConsent] = useState<AnalyticsConsentStatus | null>(() => getAnalyticsConsent());
  const [dismissed, setDismissed] = useState(() => isBannerDismissed());

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    const handleConsentChange = (event: Event) => {
      const detail = (event as CustomEvent<AnalyticsConsentStatus>).detail ?? getAnalyticsConsent();
      setConsent(detail);
    };
    window.addEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, handleConsentChange);
    return () => {
      window.removeEventListener(ANALYTICS_CONSENT_CHANGED_EVENT, handleConsentChange);
    };
  }, []);

  if (!isMounted || consent || dismissed) {
    return null;
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-[100] px-4 pb-4 sm:px-6 sm:pb-6">
      <div
        className={`mx-auto max-w-xl rounded-[24px] border px-4 py-3 shadow-2xl backdrop-blur-sm sm:px-5 sm:py-4 ${
          isDarkMode
            ? "border-gray-800 bg-[#111111]/95 text-gray-100"
            : "border-[#E7E2CC] bg-white/95 text-[#2C3419]"
        }`}
      >
        <div className="mb-2 flex items-start justify-between gap-3">
          <div className="min-w-0 pr-1">
            <p className={`text-sm leading-6 sm:text-[15px] ${isDarkMode ? "text-gray-300" : "text-[#5A6B3A]"}`}>
              Мы используем Cookies для улучшения работы сайта
            </p>
          </div>
          <button
            type="button"
            aria-label="Закрыть уведомление о cookies"
            className={`inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full transition-colors ${
              isDarkMode
                ? "text-gray-400 hover:bg-gray-900 hover:text-white"
                : "text-[#5A6B3A] hover:bg-[#F5F3E7] hover:text-[#2C3419]"
            }`}
            onClick={() => {
              dismissBannerForSession();
              setDismissed(true);
            }}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            type="button"
            className="h-10 bg-[#7A8B4A] text-white hover:bg-[#6B7B3F] sm:h-9 sm:flex-1"
            onClick={() => {
              setAnalyticsConsent("accepted");
              primeVisitorAnalyticsContext();
            }}
          >
            Принять все
          </Button>
          <Button
            type="button"
            variant="outline"
            className={
              isDarkMode
                ? "h-10 border-gray-700 bg-transparent text-gray-200 hover:bg-gray-900 hover:text-white sm:h-9 sm:flex-1"
                : "h-10 border-[#D8D0B2] bg-white text-[#2C3419] hover:bg-[#F5F3E7] sm:h-9 sm:flex-1"
            }
            onClick={() => {
              clearVisitorAnalyticsStorage();
              setAnalyticsConsent("rejected");
            }}
          >
            Только необходимые
          </Button>
        </div>
      </div>
    </div>
  );
}
