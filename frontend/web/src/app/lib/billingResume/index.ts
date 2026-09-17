export type BillingResumeMode = "design" | "reference" | "furniture";

export type BillingResumeContext = {
  draftId: string;
  mode: BillingResumeMode;
};

const STORAGE_KEY = "vizuai.billing.resume";

export function saveBillingResume(context: BillingResumeContext) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(context));
}

export function loadBillingResume(): BillingResumeContext | null {
  if (typeof window === "undefined") {
    return null;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY) || window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as BillingResumeContext;
    if (!parsed?.draftId || !parsed?.mode) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearBillingResume() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
  window.sessionStorage.removeItem(STORAGE_KEY);
}
