import { hasAnalyticsConsent } from "./consent";

const ANON_ID_STORAGE_KEY = "vizuai_anon_id";
const FIRST_TOUCH_STORAGE_KEY = "vizuai_first_touch";
const ANON_ID_COOKIE = "vizuai_anon_id";
const FIRST_TOUCH_COOKIE = "vizuai_first_touch";
const ONE_YEAR_SECONDS = 365 * 24 * 60 * 60;

export type AcquisitionSnapshot = {
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
  landing_host: string | null;
  landing_path: string | null;
  referrer: string | null;
  first_seen_at: string | null;
};

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

function normalizeString(value: string | null | undefined, maxLength = 255): string | null {
  if (!value) {
    return null;
  }
  const normalized = String(value).trim();
  if (!normalized) {
    return null;
  }
  return normalized.slice(0, maxLength);
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

function readLocalStorage(key: string): string | null {
  if (!isBrowser()) {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalStorage(key: string, value: string): void {
  if (!isBrowser()) {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore analytics persistence failures.
  }
}

function readStoredJson<T>(raw: string | null): T | null {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function persistFirstTouch(snapshot: AcquisitionSnapshot): AcquisitionSnapshot {
  const serialized = JSON.stringify(snapshot);
  writeLocalStorage(FIRST_TOUCH_STORAGE_KEY, serialized);
  writeCookie(FIRST_TOUCH_COOKIE, serialized);
  return snapshot;
}

export function ensureAnonVisitorId(): string {
  if (!isBrowser()) {
    return "server-render";
  }
  const cookieValue = normalizeString(readCookie(ANON_ID_COOKIE), 64);
  const storageValue = normalizeString(readLocalStorage(ANON_ID_STORAGE_KEY), 64);
  const resolved = cookieValue || storageValue || crypto.randomUUID();
  writeLocalStorage(ANON_ID_STORAGE_KEY, resolved);
  writeCookie(ANON_ID_COOKIE, resolved);
  return resolved;
}

export function getFirstTouchSnapshot(): AcquisitionSnapshot | null {
  const cookieValue = readStoredJson<AcquisitionSnapshot>(readCookie(FIRST_TOUCH_COOKIE));
  const storageValue = readStoredJson<AcquisitionSnapshot>(readLocalStorage(FIRST_TOUCH_STORAGE_KEY));
  const resolved = cookieValue || storageValue;
  if (!resolved) {
    return null;
  }
  persistFirstTouch(resolved);
  return resolved;
}

export function captureFirstTouchSnapshot(): AcquisitionSnapshot | null {
  if (!isBrowser()) {
    return null;
  }
  const existing = getFirstTouchSnapshot();
  if (existing) {
    return existing;
  }

  const url = new URL(window.location.href);
  const snapshot: AcquisitionSnapshot = {
    utm_source: normalizeString(url.searchParams.get("utm_source")),
    utm_medium: normalizeString(url.searchParams.get("utm_medium")),
    utm_campaign: normalizeString(url.searchParams.get("utm_campaign")),
    utm_content: normalizeString(url.searchParams.get("utm_content")),
    utm_term: normalizeString(url.searchParams.get("utm_term")),
    landing_host: normalizeString(url.hostname),
    landing_path: normalizeString(`${url.pathname}${url.search}`, 255),
    referrer: normalizeString(document.referrer, 1024),
    first_seen_at: new Date().toISOString(),
  };
  return persistFirstTouch(snapshot);
}

export function getCurrentPathWithSearch(): string {
  if (!isBrowser()) {
    return "/";
  }
  return normalizeString(`${window.location.pathname}${window.location.search}`, 255) || "/";
}

export function getVisitorContext(): { anonId: string; acquisition: AcquisitionSnapshot | null } {
  return {
    anonId: ensureAnonVisitorId(),
    acquisition: captureFirstTouchSnapshot(),
  };
}

export function getVisitorContextIfConsented(): { anonId: string | null; acquisition: AcquisitionSnapshot | null } {
  if (!hasAnalyticsConsent()) {
    return {
      anonId: null,
      acquisition: null,
    };
  }
  return getVisitorContext();
}

export function clearVisitorAnalyticsStorage(): void {
  if (!isBrowser()) {
    return;
  }
  try {
    window.localStorage.removeItem(ANON_ID_STORAGE_KEY);
    window.localStorage.removeItem(FIRST_TOUCH_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
  writeCookie(ANON_ID_COOKIE, "", 0);
  writeCookie(FIRST_TOUCH_COOKIE, "", 0);
}
