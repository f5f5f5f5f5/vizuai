const ANALYTICS_CONSENT_STORAGE_KEY = "vizuai_analytics_consent";
const ANALYTICS_CONSENT_COOKIE = "vizuai_analytics_consent";
const ONE_YEAR_SECONDS = 365 * 24 * 60 * 60;

export const ANALYTICS_CONSENT_CHANGED_EVENT = "vizuai:analytics-consent-changed";

export type AnalyticsConsentStatus = "accepted" | "rejected";

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function getCookieDomain(): string | undefined {
  if (!isBrowser()) {
    return undefined;
  }
  const hostname = window.location.hostname.toLowerCase();
  if (hostname === "vizuai.example" || hostname.endsWith(".vizuai.example")) {
    return ".vizuai.example";
  }
  return undefined;
}

function readCookie(name: string): string | null {
  if (!isBrowser()) {
    return null;
  }
  const encoded = `${encodeURIComponent(name)}=`;
  const match = document.cookie
    .split("; ")
    .find((chunk) => chunk.startsWith(encoded));
  if (!match) {
    return null;
  }
  return decodeURIComponent(match.slice(encoded.length));
}

function writeCookie(name: string, value: string, maxAgeSeconds = ONE_YEAR_SECONDS): void {
  if (!isBrowser()) {
    return;
  }
  const parts = [
    `${encodeURIComponent(name)}=${encodeURIComponent(value)}`,
    "Path=/",
    `Max-Age=${maxAgeSeconds}`,
    "SameSite=Lax",
  ];
  const domain = getCookieDomain();
  if (domain) {
    parts.push(`Domain=${domain}`);
  }
  if (window.location.protocol === "https:") {
    parts.push("Secure");
  }
  document.cookie = parts.join("; ");
}

function writeLocalStorage(key: string, value: string): void {
  if (!isBrowser()) {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore persistence failures.
  }
}

export function getAnalyticsConsent(): AnalyticsConsentStatus | null {
  if (!isBrowser()) {
    return null;
  }
  const cookieValue = readCookie(ANALYTICS_CONSENT_COOKIE);
  if (cookieValue === "accepted" || cookieValue === "rejected") {
    return cookieValue;
  }
  try {
    const storageValue = window.localStorage.getItem(ANALYTICS_CONSENT_STORAGE_KEY);
    if (storageValue === "accepted" || storageValue === "rejected") {
      return storageValue;
    }
  } catch {
    // Ignore storage failures.
  }
  return null;
}

export function hasAnalyticsConsent(): boolean {
  return getAnalyticsConsent() === "accepted";
}

export function setAnalyticsConsent(status: AnalyticsConsentStatus): void {
  if (!isBrowser()) {
    return;
  }
  writeLocalStorage(ANALYTICS_CONSENT_STORAGE_KEY, status);
  writeCookie(ANALYTICS_CONSENT_COOKIE, status);
  window.dispatchEvent(
    new CustomEvent<AnalyticsConsentStatus>(ANALYTICS_CONSENT_CHANGED_EVENT, {
      detail: status,
    }),
  );
}
