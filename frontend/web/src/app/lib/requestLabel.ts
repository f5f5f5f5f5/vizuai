import type { AppLocale } from "@/app/i18n";

export function formatRequestLabel(count: number, locale: AppLocale): string {
  if (locale === "en") {
    return `${count} ${count === 1 ? "request" : "requests"}`;
  }

  const absCount = Math.abs(count);
  const mod10 = absCount % 10;
  const mod100 = absCount % 100;

  if (mod10 === 1 && mod100 !== 11) {
    return `${count} запрос`;
  }

  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} запроса`;
  }

  return `${count} запросов`;
}

export function requestWord(count: number, locale: AppLocale): string {
  return formatRequestLabel(count, locale).replace(/^\d+\s*/, "");
}
