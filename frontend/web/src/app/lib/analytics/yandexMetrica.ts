import { hasAnalyticsConsent } from "./consent";

const YANDEX_METRICA_ID = Number(import.meta.env.VITE_YANDEX_METRICA_ID || 0);
const ANALYTICS_HOSTNAMES = String(import.meta.env.VITE_ANALYTICS_HOSTNAMES || "")
  .split(",")
  .map((hostname) => hostname.trim().toLowerCase())
  .filter(Boolean);
const YANDEX_METRICA_SRC = "https://mc.yandex.ru/metrika/tag.js";

type YandexGoalName =
  | "open_app"
  | "start_login"
  | "open_pricing"
  | "open_billing"
  | "purchase";

type YmFunction = {
  (...args: unknown[]): void;
  a?: IArguments[];
  l?: number;
};

declare global {
  interface Window {
    ym?: YmFunction;
  }
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function isProductionHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return ANALYTICS_HOSTNAMES.includes(normalized);
}

export function isYandexMetricaEnabled(): boolean {
  if (!isBrowser() || !Number.isSafeInteger(YANDEX_METRICA_ID) || YANDEX_METRICA_ID <= 0) {
    return false;
  }
  if (!hasAnalyticsConsent()) {
    return false;
  }
  return isProductionHostname(window.location.hostname);
}

export function ensureYandexMetrica(): void {
  if (!isYandexMetricaEnabled()) {
    return;
  }

  const win = window as Window & { __vizuaiYmInitialized?: boolean };
  if (win.__vizuaiYmInitialized) {
    return;
  }

  win.ym =
    win.ym ||
    function (...args: unknown[]) {
      ((win.ym as YmFunction).a = (win.ym as YmFunction).a || []).push(arguments);
    };
  win.ym.l = Date.now();

  const scriptAlreadyPresent = Array.from(document.scripts).some((script) => script.src === YANDEX_METRICA_SRC);
  if (!scriptAlreadyPresent) {
    const script = document.createElement("script");
    script.async = true;
    script.src = YANDEX_METRICA_SRC;
    const firstScript = document.getElementsByTagName("script")[0];
    if (firstScript?.parentNode) {
      firstScript.parentNode.insertBefore(script, firstScript);
    } else {
      document.head.appendChild(script);
    }
  }

  win.ym(YANDEX_METRICA_ID, "init", {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
  });
  win.__vizuaiYmInitialized = true;
}

export function trackYandexPageHit(path: string): void {
  if (!isYandexMetricaEnabled()) {
    return;
  }
  ensureYandexMetrica();
  window.ym?.(YANDEX_METRICA_ID, "hit", path);
}

export function reachYandexGoal(goal: YandexGoalName, params?: Record<string, unknown>): void {
  if (!isYandexMetricaEnabled()) {
    return;
  }
  ensureYandexMetrica();
  if (params && Object.keys(params).length > 0) {
    window.ym?.(YANDEX_METRICA_ID, "reachGoal", goal, params);
    return;
  }
  window.ym?.(YANDEX_METRICA_ID, "reachGoal", goal);
}

export function reachYandexGoalOnce(
  goal: YandexGoalName,
  onceKey: string,
  params?: Record<string, unknown>,
): boolean {
  if (!isYandexMetricaEnabled()) {
    return false;
  }
  const storageKey = `vizuai_ym_goal_once:${goal}:${onceKey}`;
  try {
    if (window.sessionStorage.getItem(storageKey) === "1") {
      return false;
    }
    window.sessionStorage.setItem(storageKey, "1");
  } catch {
    // Ignore storage failures and still emit the goal.
  }
  reachYandexGoal(goal, params);
  return true;
}
