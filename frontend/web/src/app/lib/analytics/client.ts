import { api, type AnalyticsEventPayload } from "@/app/lib/api";
import {
  captureFirstTouchSnapshot,
  getCurrentPathWithSearch,
  getVisitorContext,
} from "./visitor";
import {
  ensureYandexMetrica,
  reachYandexGoal,
  trackYandexPageHit,
} from "./yandexMetrica";
import { hasAnalyticsConsent } from "./consent";

type EventOptions = {
  screenKey?: string | null;
  actionKey?: string | null;
  path?: string | null;
  referrer?: string | null;
  meta?: Record<string, unknown> | null;
};

function buildMeta(meta?: Record<string, unknown> | null): Record<string, unknown> {
  const { anonId, acquisition } = getVisitorContext();
  return {
    ...(meta || {}),
    anon_id: anonId,
    acquisition,
  };
}

function buildPayload(
  eventType: string,
  options?: EventOptions,
): AnalyticsEventPayload {
  const { anonId } = getVisitorContext();
  return {
    event_type: eventType,
    screen_key: options?.screenKey ?? null,
    action_key: options?.actionKey ?? null,
    path: options?.path ?? getCurrentPathWithSearch(),
    referrer: options?.referrer ?? (typeof document !== "undefined" ? document.referrer || null : null),
    anon_id: anonId,
    meta: buildMeta(options?.meta),
  };
}

export function primeVisitorAnalyticsContext(): void {
  if (!hasAnalyticsConsent()) {
    return;
  }
  captureFirstTouchSnapshot();
  getVisitorContext();
  ensureYandexMetrica();
}

export async function trackPublicEvent(
  eventType: string,
  options?: EventOptions,
): Promise<void> {
  if (!hasAnalyticsConsent()) {
    return;
  }
  try {
    await api.trackPublicEvent(buildPayload(eventType, options));
  } catch (error) {
    console.debug("Public analytics event dropped:", error);
  }
}

export async function trackAppEvent(
  eventType: string,
  options?: EventOptions,
): Promise<void> {
  if (!hasAnalyticsConsent()) {
    return;
  }
  try {
    await api.trackAppEvent(buildPayload(eventType, options));
  } catch (error) {
    console.debug("App analytics event dropped:", error);
  }
}

export async function trackPublicPageView(screenKey: string, meta?: Record<string, unknown>): Promise<void> {
  trackYandexPageHit(getCurrentPathWithSearch());
  if (screenKey === "pricing") {
    reachYandexGoal("open_pricing");
  }
  await trackPublicEvent("public_page_view", { screenKey, meta });
}

export async function trackPublicClick(
  screenKey: string,
  actionKey: string,
  meta?: Record<string, unknown>,
): Promise<void> {
  if (
    actionKey === "open_app_click" ||
    actionKey === "header_login_click" ||
    actionKey === "hero_start_click" ||
    actionKey === "bottom_cta_click"
  ) {
    reachYandexGoal("open_app", {
      screen_key: screenKey,
      action_key: actionKey,
    });
  }
  if (screenKey === "login" && actionKey === "magic_link_start_submit") {
    reachYandexGoal("start_login");
  }
  await trackPublicEvent("public_cta_click", { screenKey, actionKey, meta });
}

export async function trackAppPageView(screenKey: string, meta?: Record<string, unknown>): Promise<void> {
  trackYandexPageHit(getCurrentPathWithSearch());
  if (screenKey === "billing") {
    reachYandexGoal("open_billing");
  }
  await trackAppEvent("client_page_view", { screenKey, meta });
}

export async function trackAppClick(
  screenKey: string,
  actionKey: string,
  meta?: Record<string, unknown>,
): Promise<void> {
  await trackAppEvent("client_cta_click", { screenKey, actionKey, meta });
}
