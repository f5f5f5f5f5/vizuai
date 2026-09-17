export type RouteSeoMetadata = {
  title: string;
  description: string;
  robots: string;
  canonical: string | null;
  locale: "ru" | "en";
  alternates?: Array<{ hrefLang: string; href: string }>;
  ogType?: "website";
};

const PUBLIC_SITE_BASE_URL = "https://vizuai.example";
import { getPathLocale, stripLocalePrefix, type AppLocale } from "@/app/i18n";

const indexableRoutes: Record<string, Record<AppLocale, Omit<RouteSeoMetadata, "robots" | "alternates">>> = {
  "/": {
    ru: {
      title: "Дизайн интерьера по фото с помощью ИИ | VizuAI",
      description:
        "VizuAI помогает создавать новый интерьер по фото, переносить стиль по референсу и находить похожую мебель на маркетплейсах.",
      canonical: `${PUBLIC_SITE_BASE_URL}/`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "AI Interior Design from Photo | VizuAI",
      description:
        "VizuAI helps you redesign interiors from photos, apply style references, and find matching furniture from marketplace listings.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en`,
      locale: "en",
      ogType: "website",
    },
  },
  "/faq": {
    ru: {
      title: "FAQ VizuAI | Ответы про дизайн, мебель и оплату",
      description:
        "Ответы на вопросы о VizuAI: как работает дизайн по фото, сценарий по референсу, поиск мебели, пакеты запросов, оплата и поддержка.",
      canonical: `${PUBLIC_SITE_BASE_URL}/faq`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "VizuAI FAQ | Design, Furniture, and Billing Answers",
      description:
        "Answers about VizuAI: interior design from photo, reference-based redesign, furniture search, pricing, payments, and support.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/faq`,
      locale: "en",
      ogType: "website",
    },
  },
  "/pricing": {
    ru: {
      title: "Цены VizuAI | Пакеты запросов и оплата",
      description:
        "Стоимость VizuAI без подписки: пакеты запросов, единый баланс для всех сценариев и промокоды для покупки внутри приложения.",
      canonical: `${PUBLIC_SITE_BASE_URL}/pricing`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "VizuAI Pricing | Request Packs and Payments",
      description:
        "VizuAI pricing with no subscription: request packs, one shared balance for all scenarios, and promo codes applied inside the app.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/pricing`,
      locale: "en",
      ogType: "website",
    },
  },
  "/examples": {
    ru: {
      title: "Примеры работ VizuAI | Дизайн интерьера по фото",
      description:
        "Подборка примеров работ VizuAI: реальные before/after визуализации, чтобы оценить характер результата и качество AI-рендера.",
      canonical: `${PUBLIC_SITE_BASE_URL}/examples`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "VizuAI Examples | AI Interior Design Results",
      description:
        "A curated set of VizuAI examples with real before/after visualizations so you can evaluate result style and render quality.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/examples`,
      locale: "en",
      ogType: "website",
    },
  },
  "/how-it-works": {
    ru: {
      title: "Как работает VizuAI | AI-дизайн и поиск мебели",
      description:
        "Объясняем, как VizuAI создаёт интерьерные рендеры, переносит стиль по референсу и ищет похожую мебель по фото.",
      canonical: `${PUBLIC_SITE_BASE_URL}/how-it-works`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "How VizuAI Works | AI Design and Furniture Search",
      description:
        "A plain-language overview of how VizuAI renders interiors, applies style references, and finds similar furniture from photos.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/how-it-works`,
      locale: "en",
      ogType: "website",
    },
  },
  "/how-to-find-furniture-by-photo": {
    ru: {
      title: "Как искать мебель по фото интерьера | VizuAI",
      description:
        "Пошаговый guide по поиску мебели в VizuAI: какое фото загрузить, как запустить поиск и что вы получите на выходе.",
      canonical: `${PUBLIC_SITE_BASE_URL}/how-to-find-furniture-by-photo`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "How to Find Furniture by Photo | VizuAI",
      description:
        "A step-by-step guide to furniture search in VizuAI: what image to upload, how to run the search, and what results you get.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/how-to-find-furniture-by-photo`,
      locale: "en",
      ogType: "website",
    },
  },
  "/how-to-design-by-photo": {
    ru: {
      title: "Как сделать дизайн интерьера по фото | VizuAI",
      description:
        "Пошаговый guide по сценарию дизайна интерьера в VizuAI: какое фото выбрать, как написать запрос и как выглядит готовый результат.",
      canonical: `${PUBLIC_SITE_BASE_URL}/how-to-design-by-photo`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "How to Design an Interior from a Photo | VizuAI",
      description:
        "A step-by-step guide to interior design in VizuAI: which photo to use, how to write the request, and what the final result looks like.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/how-to-design-by-photo`,
      locale: "en",
      ogType: "website",
    },
  },
  "/how-to-design-by-reference": {
    ru: {
      title: "Как сделать дизайн по референсу | VizuAI",
      description:
        "Пошаговый guide по сценарию дизайна по референсу в VizuAI: как загрузить помещение, выбрать референс и получить готовый результат.",
      canonical: `${PUBLIC_SITE_BASE_URL}/how-to-design-by-reference`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "How to Redesign by Reference | VizuAI",
      description:
        "A step-by-step guide to reference-based redesign in VizuAI: upload your room, add a reference image, and get a finished result.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/how-to-design-by-reference`,
      locale: "en",
      ogType: "website",
    },
  },
  "/interior-design-from-photo": {
    ru: {
      title: "Дизайн интерьера по фото | VizuAI",
      description:
        "Загрузите фото комнаты и получите новый вариант интерьера с помощью ИИ. Подходит для быстрого поиска стиля и визуального направления.",
      canonical: `${PUBLIC_SITE_BASE_URL}/interior-design-from-photo`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "Interior Design from Photo | VizuAI",
      description:
        "Upload a room photo and get a new interior concept with AI. Useful for quickly exploring style direction and visual ideas.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/interior-design-from-photo`,
      locale: "en",
      ogType: "website",
    },
  },
  "/design-by-reference": {
    ru: {
      title: "Дизайн по референсу | VizuAI",
      description:
        "Перенесите стиль, настроение и материалы с понравившегося изображения на своё помещение с помощью сценария по референсу от VizuAI.",
      canonical: `${PUBLIC_SITE_BASE_URL}/design-by-reference`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "Design by Reference | VizuAI",
      description:
        "Transfer style, mood, and materials from an inspiration image to your own room with VizuAI reference-based redesign.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/design-by-reference`,
      locale: "en",
      ogType: "website",
    },
  },
  "/furniture-search-by-photo": {
    ru: {
      title: "Подбор мебели по фото | VizuAI",
      description:
        "Найдите похожую мебель и предметы интерьера по фото. VizuAI выделяет объекты и собирает ссылки на маркетплейсы по каждому предмету.",
      canonical: `${PUBLIC_SITE_BASE_URL}/furniture-search-by-photo`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "Furniture Search by Photo | VizuAI",
      description:
        "Find similar furniture and decor from a photo. VizuAI identifies objects and groups marketplace links for each item separately.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/furniture-search-by-photo`,
      locale: "en",
      ogType: "website",
    },
  },
  "/legal": {
    ru: {
      title: "Юридическая информация | VizuAI",
      description:
        "Юридические документы, оферта, политика конфиденциальности и другие материалы по работе сервиса VizuAI.",
      canonical: `${PUBLIC_SITE_BASE_URL}/legal`,
      locale: "ru",
      ogType: "website",
    },
    en: {
      title: "Legal Information | VizuAI",
      description:
        "Legal documents, public offer, privacy materials, and other service information for VizuAI.",
      canonical: `${PUBLIC_SITE_BASE_URL}/en/legal`,
      locale: "en",
      ogType: "website",
    },
  },
};

const defaultMetadata: RouteSeoMetadata = {
  title: "VizuAI",
  description:
    "VizuAI помогает создавать дизайн интерьера по фото, работать со стилевыми референсами и искать похожую мебель по изображению.",
  robots: "noindex,nofollow",
  canonical: null,
  locale: "ru",
  ogType: "website",
};

export function getRouteSeoMetadata(pathname: string): RouteSeoMetadata {
  const normalizedPath = normalizePathname(stripLocalePrefix(pathname));
  const locale = getPathLocale(pathname) || "ru";

  const exactIndexable = indexableRoutes[normalizedPath];
  if (exactIndexable) {
    const localizedMetadata = exactIndexable[locale];
    return {
      ...localizedMetadata,
      robots: "index,follow",
      alternates: buildAlternates(normalizedPath),
    };
  }

  if (
    normalizedPath === "/login" ||
    normalizedPath === "/auth/login" ||
    normalizedPath === "/app" ||
    normalizedPath.startsWith("/app/")
  ) {
    return {
      title: "VizuAI",
      description: defaultMetadata.description,
      robots: "noindex,nofollow",
      canonical: null,
      locale,
      ogType: "website",
    };
  }

  return {
    ...defaultMetadata,
    locale,
    title: locale === "en" ? "Page not found | VizuAI" : "Страница не найдена | VizuAI",
    description:
      locale === "en"
        ? "VizuAI helps redesign interiors from photos, work with style references, and find similar furniture."
        : defaultMetadata.description,
  };
}

function buildAlternates(pathname: string) {
  const ruPath = pathname === "/" ? "/" : pathname;
  const enPath = pathname === "/" ? "/en" : `/en${pathname}`;
  return [
    { hrefLang: "ru", href: `${PUBLIC_SITE_BASE_URL}${ruPath}` },
    { hrefLang: "en", href: `${PUBLIC_SITE_BASE_URL}${enPath}` },
    { hrefLang: "x-default", href: `${PUBLIC_SITE_BASE_URL}${ruPath}` },
  ];
}

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === "/") {
    return "/";
  }

  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}
