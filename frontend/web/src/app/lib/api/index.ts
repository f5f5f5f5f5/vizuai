const rawApiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "");
const isBrowser = typeof window !== "undefined";
const isLocalHost =
  isBrowser &&
  ["localhost", "127.0.0.1"].includes(window.location.hostname);

if (!rawApiBaseUrl && isBrowser && !isLocalHost) {
  throw new Error("VITE_API_BASE_URL is required for non-local frontend builds");
}

const API_BASE_URL = rawApiBaseUrl || "http://127.0.0.1:8080/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

type ApiEnvelope<T> = {
  ok?: boolean;
  data?: T;
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  let body = options.body;

  if (body !== undefined && body !== null && !(body instanceof FormData) && !(body instanceof Blob)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: "include",
      ...options,
      headers,
      body: body as BodyInit | null | undefined,
    });
  } catch (error) {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "Не удалось связаться с сервером. Проверьте соединение и попробуйте снова.",
      error instanceof Error ? { cause: error.message, path } : { path },
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? ((await response.json()) as ApiEnvelope<T>)
    : undefined;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code || "API_ERROR",
      payload?.error?.message || `Request failed with status ${response.status}`,
      payload?.error?.details,
    );
  }

  if (payload && Object.prototype.hasOwnProperty.call(payload, "data")) {
    return payload.data as T;
  }

  return payload as T;
}

async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: "include",
      ...options,
    });
  } catch (error) {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "Не удалось связаться с сервером. Проверьте соединение и попробуйте снова.",
      error instanceof Error ? { cause: error.message, path } : { path },
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? ((await response.json()) as ApiEnvelope<unknown>)
    : undefined;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code || "API_ERROR",
      payload?.error?.message || `Request failed with status ${response.status}`,
      payload?.error?.details,
    );
  }

  return response.blob();
}

export type AuthMeResponse = {
  account: {
    id: string;
    email: string;
    display_name: string | null;
    locale: string | null;
    timezone: string | null;
    created_at: string;
    last_seen_at: string | null;
  };
  balance: {
    credits: number;
  };
};

export type BillingPlan = {
  provider: string;
  credits: number;
  currency: string;
  amount: string;
};

export type BillingCheckout = {
  id: string;
  provider: string;
  status: string;
  credits_amount: number;
  currency: string;
  amount_original: string | null;
  discount_amount: string | null;
  amount_final: string | null;
  provider_checkout_id: string | null;
  checkout_url: string | null;
  promocode_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  expires_at: string | null;
  payment: BillingPayment | null;
};

export type BillingPayment = {
  id: string;
  provider: string | null;
  status: string;
  credits_amount: number;
  currency: string;
  price_original: string;
  discount_amount: string;
  price_final: string;
  provider_payment_id: string | null;
  checkout_session_id: string | null;
  promocode_code: string | null;
  created_at: string;
  paid_at: string | null;
  refunded_at: string | null;
};

export type BillingPromocodePreview = {
  code: string;
  discount_type: string;
  discount_value: string;
  credits_amount: number;
  currency: string;
  amount_original: string;
  discount_amount: string;
  amount_final: string;
  code_left: number | null;
};

export type UploadIntent = {
  upload: {
    upload_id: string;
    upload_url: string;
    storage_key: string;
    method: string;
    headers: Record<string, string>;
    expires_at: string;
  };
};

export type UploadedFile = {
  file: {
    file_id: string;
    url: string;
    content_type: string;
    size_bytes: number;
  };
};

export type DesignDraft = {
  id: string;
  status: string;
  source_file_id: string | null;
  source_image_url: string;
  style_reference_file_id: string | null;
  style_reference_image_url: string | null;
  style_reference_enabled: boolean;
  user_request: string;
  estimated_units: number | null;
  created_at: string;
  updated_at: string;
};

export type FurnitureDraft = {
  id: string;
  status: string;
  source_file_id: string | null;
  source_image_url: string;
  user_request: string | null;
  estimated_units: number | null;
  created_at: string;
  updated_at: string;
};

export type JobSnapshot = {
  id: string;
  account_id: string;
  job_type: string;
  status: string;
  draft_id: string | null;
  draft_type: string | null;
  result_ref_id: string | null;
  result_ref_type: string | null;
  units_reserved: number;
  units_final: number | null;
  error_code: string | null;
  error_message: string | null;
  error_stage: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  progress: Record<string, unknown>;
  provider_meta: Record<string, unknown>;
};

export type HistoryItem = {
  id: string;
  mode: string;
  status: string;
  title: string | null;
  preview_image_url: string | null;
  original_image_url: string | null;
  user_request: string | null;
  units_spent: number | null;
  error_message: string | null;
  error_stage: string | null;
  retry_eligible: boolean;
  created_at: string;
  ended_at: string | null;
};

export type HistoryListResponse = {
  items: HistoryItem[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_more: boolean;
  };
  filters: {
    mode: string | null;
    status: string | null;
    query: string | null;
  };
};

export type DesignResult = {
  id: string;
  mode: string;
  status: string;
  original_image_url: string;
  prepared_image_url: string | null;
  render_image_url: string | null;
  fix_image_url: string | null;
  final_image_url: string | null;
  style_reference_image_url: string | null;
  style_reference_used: boolean;
  style_reference_status: string | null;
  selected_image: string | null;
  user_request: string;
  error_message: string | null;
  error_stage: string | null;
  units_spent: number | null;
  cost_usd: number | null;
  created_at: string;
  ended_at: string | null;
  retry_eligible: boolean;
  metadata: Record<string, unknown>;
  debug: Record<string, unknown>;
};

export type FurnitureResult = {
  id: string;
  mode: string;
  status: string;
  original_image_url: string;
  final_image_url: string | null;
  user_request: string;
  error_message: string | null;
  error_stage: string | null;
  units_spent: number | null;
  created_at: string;
  ended_at: string | null;
  retry_eligible: boolean;
  summary_text: string | null;
  object_cards: Array<Record<string, unknown>>;
  products_count: number;
  metadata: Record<string, unknown>;
};

export type AccountResponse = {
  account: {
    id: string;
    email: string | null;
    display_name: string | null;
    locale: string | null;
    timezone: string | null;
    marketing_opt_in: boolean;
    created_at: string;
    last_seen_at: string | null;
  };
};

export type AccountUsageResponse = {
  usage: {
    total_runs: number;
    completed_runs: number;
    failed_runs: number;
    design_runs: number;
    furniture_runs: number;
    credits_spent: number;
  };
};

export type AnalyticsEventPayload = {
  event_type: string;
  screen_key?: string | null;
  action_key?: string | null;
  source?: string | null;
  path?: string | null;
  referrer?: string | null;
  anon_id?: string | null;
  meta?: Record<string, unknown> | null;
};

export type ReuseSeed = {
  source_file_id: string;
  source_image_url: string;
  style_reference_file_id?: string | null;
  style_reference_image_url?: string | null;
  style_reference_enabled?: boolean;
  user_request: string;
  estimated_units?: number | null;
};

export const api = {
  authStart(email: string, locale?: string | null) {
    return request<{ status: string }>("/auth/start", {
      method: "POST",
      body: { email, locale: locale || null },
    });
  },
  authVerify(
    token: string,
    options?: {
      anon_id?: string | null;
      acquisition?: Record<string, unknown> | null;
      locale?: string | null;
    },
  ) {
    return request<{ account: AuthMeResponse["account"]; session: { expires_at: string } }>("/auth/verify", {
      method: "POST",
      body: {
        token,
        anon_id: options?.anon_id ?? null,
        acquisition: options?.acquisition ?? null,
        locale: options?.locale ?? null,
      },
    });
  },
  authMe() {
    return request<AuthMeResponse>("/auth/me");
  },
  authLogout() {
    return request<{ status: string }>("/auth/logout", { method: "POST" });
  },
  getAccount() {
    return request<AccountResponse>("/account");
  },
  updateAccount(payload: Partial<{ display_name: string; locale: string; timezone: string }>) {
    return request<AccountResponse>("/account", { method: "PATCH", body: payload });
  },
  getAccountUsage() {
    return request<AccountUsageResponse>("/account/usage");
  },
  getBalance() {
    return request<{ credits: number }>("/account/balance");
  },
  getBillingPlans() {
    return request<BillingPlan[]>("/billing/plans");
  },
  checkBillingPromocode(credits: number, promocode: string, provider = "tbank_sbp") {
    return request<BillingPromocodePreview>("/billing/promocode/check", {
      method: "POST",
      body: { credits, provider, promocode },
    });
  },
  createCheckout(credits: number, provider = "tbank_sbp", promocode?: string | null) {
    return request<BillingCheckout>("/billing/checkout", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: { credits, provider, promocode: promocode || null },
    });
  },
  getCheckout(checkoutId: string) {
    return request<BillingCheckout>(`/billing/checkout/${checkoutId}`);
  },
  getPayments() {
    return request<BillingPayment[]>("/billing/payments");
  },
  createImageUploadIntent(payload: { filename: string; content_type: string; size_bytes: number; purpose: string }) {
    return request<UploadIntent>("/uploads/image", { method: "POST", body: payload });
  },
  createStyleReferenceUploadIntent(payload: { filename: string; content_type: string; size_bytes: number; purpose: string }) {
    return request<UploadIntent>("/uploads/style-reference", { method: "POST", body: payload });
  },
  async putSignedUpload(uploadUrl: string, file: File, headers: Record<string, string>) {
    let response: Response;
    try {
      response = await fetch(uploadUrl, {
        method: "PUT",
        headers,
        body: file,
      });
    } catch (error) {
      throw new ApiError(
        0,
        "UPLOAD_NETWORK_ERROR",
        "Не удалось загрузить файл. Проверьте соединение и попробуйте снова.",
        error instanceof Error ? { cause: error.message } : undefined,
      );
    }
    if (!response.ok) {
      throw new ApiError(response.status, "UPLOAD_PUT_FAILED", "Не удалось загрузить файл.");
    }
  },
  completeUpload(uploadId: string, storageKey: string) {
    return request<UploadedFile>(`/uploads/${uploadId}/complete`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: { storage_key: storageKey },
    });
  },
  listDesignDrafts(limit = 6) {
    return request<{ items: DesignDraft[] }>(`/design/drafts?limit=${limit}`);
  },
  getDesignDraft(draftId: string) {
    return request<DesignDraft>(`/design/drafts/${draftId}`);
  },
  createDesignDraft(payload: {
    source_file_id: string;
    user_request: string;
    style_reference_file_id?: string | null;
    style_reference_enabled?: boolean;
  }) {
    return request<DesignDraft>("/design/drafts", { method: "POST", body: payload });
  },
  updateDesignDraft(draftId: string, payload: Partial<{
    user_request: string;
    style_reference_file_id: string | null;
    style_reference_enabled: boolean;
  }>) {
    return request<DesignDraft>(`/design/drafts/${draftId}`, { method: "PATCH", body: payload });
  },
  createDesignJob(draftId: string) {
    return request<JobSnapshot>("/design/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: { draft_id: draftId },
    });
  },
  getDesignResult(resultId: string) {
    return request<DesignResult>(`/design/results/${resultId}`);
  },
  downloadDesignResult(resultId: string) {
    return requestBlob(`/design/results/${resultId}/download`);
  },
  getDesignReuse(resultId: string) {
    return request<ReuseSeed>(`/design/results/${resultId}/reuse`);
  },
  getDesignEditSeed(resultId: string) {
    return request<ReuseSeed>(`/design/results/${resultId}/edit`, { method: "POST" });
  },
  getDesignFurnitureSeed(resultId: string) {
    return request<ReuseSeed>(`/design/results/${resultId}/furniture-seed`, { method: "POST" });
  },
  listFurnitureDrafts(limit = 6) {
    return request<{ items: FurnitureDraft[] }>(`/furniture/drafts?limit=${limit}`);
  },
  getFurnitureDraft(draftId: string) {
    return request<FurnitureDraft>(`/furniture/drafts/${draftId}`);
  },
  createFurnitureDraft(payload: {
    source_file_id: string;
    user_request?: string | null;
  }) {
    return request<FurnitureDraft>("/furniture/drafts", { method: "POST", body: payload });
  },
  updateFurnitureDraft(draftId: string, payload: Partial<{ user_request: string | null }>) {
    return request<FurnitureDraft>(`/furniture/drafts/${draftId}`, { method: "PATCH", body: payload });
  },
  createFurnitureJob(draftId: string) {
    return request<JobSnapshot>("/furniture/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: { draft_id: draftId },
    });
  },
  getFurnitureResult(resultId: string) {
    return request<FurnitureResult>(`/furniture/results/${resultId}`);
  },
  downloadFurnitureResult(resultId: string) {
    return requestBlob(`/furniture/results/${resultId}/download`);
  },
  getFurnitureReuse(resultId: string) {
    return request<ReuseSeed>(`/furniture/results/${resultId}/reuse`);
  },
  getJob(jobId: string) {
    return request<JobSnapshot>(`/jobs/${jobId}`);
  },
  getHistory(page = 1, pageSize = 20) {
    return request<HistoryListResponse>(`/history?page=${page}&page_size=${pageSize}`);
  },
  getHistoryItem(id: string) {
    return request<{ item: HistoryItem }>(`/history/${id}`).then((payload) => payload.item);
  },
  trackPublicEvent(payload: AnalyticsEventPayload) {
    return request<{ status: string; anon_id?: string | null }>("/public/analytics/events", {
      method: "POST",
      body: payload,
    });
  },
  trackAppEvent(payload: AnalyticsEventPayload) {
    return request<{ status: string }>("/analytics/events", {
      method: "POST",
      body: payload,
    });
  },
};
