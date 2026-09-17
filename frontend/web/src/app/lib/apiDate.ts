const API_DATE_WITH_TIMEZONE_RE = /(?:Z|[+-]\d{2}:\d{2})$/;

export function parseApiDate(value: string): Date {
  const normalized = API_DATE_WITH_TIMEZONE_RE.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}
