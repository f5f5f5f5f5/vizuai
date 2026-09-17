import { faqByLocale } from "@/app/lib/content/faq";
import { getPathLocale, stripLocalePrefix } from "@/app/i18n";

const PUBLIC_SITE_BASE_URL = "https://vizuai.example";
const APP_URL = "https://app.vizuai.example";
const TELEGRAM_SUPPORT_URL = "https://example.com/support";

type JsonLdNode = Record<string, unknown>;

export function getStructuredDataNodes(pathname: string): JsonLdNode[] {
  const normalizedPath = normalizePathname(stripLocalePrefix(pathname));
  const locale = getPathLocale(pathname) || "ru";
  const nodes: JsonLdNode[] = [];

  if (isIndexablePublicRoute(normalizedPath)) {
    nodes.push(buildOrganizationNode(locale));
  }

  if (isProductVisibilityRoute(normalizedPath)) {
    nodes.push(buildSoftwareApplicationNode(locale));
  }

  if (normalizedPath === "/faq") {
    nodes.push(buildFaqPageNode(locale));
  }

  return nodes;
}

function buildOrganizationNode(locale: "ru" | "en"): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "VizuAI",
    url: PUBLIC_SITE_BASE_URL,
    logo: `${PUBLIC_SITE_BASE_URL}/apple-touch-icon.png`,
    email: "owner@vizuai.example",
    contactPoint: [
      {
        "@type": "ContactPoint",
        contactType: "customer support",
        email: "owner@vizuai.example",
        url: TELEGRAM_SUPPORT_URL,
        availableLanguage: locale === "en" ? ["en", "ru"] : ["ru", "en"],
      },
    ],
    sameAs: [TELEGRAM_SUPPORT_URL],
  };
}

function buildSoftwareApplicationNode(locale: "ru" | "en"): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "VizuAI",
    applicationCategory: "DesignApplication",
    operatingSystem: "Web",
    url: PUBLIC_SITE_BASE_URL,
    downloadUrl: APP_URL,
    description:
      locale === "en"
        ? "VizuAI is a web app for interior redesign from photos, reference-based styling, and similar furniture search."
        : "VizuAI — веб-сервис для дизайна интерьера по фото, работы со стилевыми референсами и поиска похожей мебели по изображению.",
    inLanguage: locale,
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "RUB",
      lowPrice: "199",
      highPrice: "1599",
      offerCount: "3",
    },
    featureList: [
      ...(locale === "en"
        ? [
            "Interior design from photo",
            "Design by reference",
            "Furniture search by photo",
            "History and repeat runs",
          ]
        : [
            "Дизайн интерьера по фото",
            "Дизайн по референсу",
            "Подбор мебели по фото",
            "История запусков и повторные сценарии",
          ]),
    ],
    provider: {
      "@type": "Organization",
      name: "VizuAI",
      url: PUBLIC_SITE_BASE_URL,
    },
  };
}

function buildFaqPageNode(locale: "ru" | "en"): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqByLocale[locale].map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
}

function isIndexablePublicRoute(pathname: string) {
  return (
    pathname === "/" ||
    pathname === "/faq" ||
    pathname === "/pricing" ||
    pathname === "/examples" ||
    pathname === "/how-it-works" ||
    pathname === "/how-to-find-furniture-by-photo" ||
    pathname === "/how-to-design-by-photo" ||
    pathname === "/how-to-design-by-reference" ||
    pathname === "/interior-design-from-photo" ||
    pathname === "/design-by-reference" ||
    pathname === "/furniture-search-by-photo" ||
    pathname === "/legal"
  );
}

function isProductVisibilityRoute(pathname: string) {
  return (
    pathname === "/" ||
    pathname === "/faq" ||
    pathname === "/pricing" ||
    pathname === "/examples" ||
    pathname === "/how-it-works" ||
    pathname === "/how-to-find-furniture-by-photo" ||
    pathname === "/how-to-design-by-photo" ||
    pathname === "/how-to-design-by-reference" ||
    pathname === "/interior-design-from-photo" ||
    pathname === "/design-by-reference" ||
    pathname === "/furniture-search-by-photo"
  );
}

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === "/") {
    return "/";
  }

  return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}
