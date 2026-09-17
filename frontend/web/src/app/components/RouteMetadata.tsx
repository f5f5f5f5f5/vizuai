import { useEffect } from "react";
import { useLocation } from "react-router";

import { getRouteSeoMetadata } from "@/app/lib/seo/metadata";

function ensureMetaTag(attributeName: "name" | "property", attributeValue: string) {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[${attributeName}="${attributeValue}"]`);
  if (!tag) {
    tag = document.createElement("meta");
    tag.setAttribute(attributeName, attributeValue);
    document.head.appendChild(tag);
  }
  return tag;
}

function ensureCanonicalLink() {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!link) {
    link = document.createElement("link");
    link.setAttribute("rel", "canonical");
    document.head.appendChild(link);
  }
  return link;
}

function syncAlternateLinks(alternates: Array<{ hrefLang: string; href: string }>) {
  const existing = document.head.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][data-vizuai-alt="true"]');
  existing.forEach((link) => link.remove());

  alternates.forEach((alternate) => {
    const link = document.createElement("link");
    link.setAttribute("rel", "alternate");
    link.setAttribute("hreflang", alternate.hrefLang);
    link.setAttribute("href", alternate.href);
    link.setAttribute("data-vizuai-alt", "true");
    document.head.appendChild(link);
  });
}

export function RouteMetadata() {
  const location = useLocation();

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    const metadata = getRouteSeoMetadata(location.pathname);

    document.title = metadata.title;

    const descriptionTag = ensureMetaTag("name", "description");
    descriptionTag.setAttribute("content", metadata.description);

    const robotsTag = ensureMetaTag("name", "robots");
    robotsTag.setAttribute("content", metadata.robots);

    const ogTitleTag = ensureMetaTag("property", "og:title");
    ogTitleTag.setAttribute("content", metadata.title);

    const ogDescriptionTag = ensureMetaTag("property", "og:description");
    ogDescriptionTag.setAttribute("content", metadata.description);

    const ogTypeTag = ensureMetaTag("property", "og:type");
    ogTypeTag.setAttribute("content", metadata.ogType ?? "website");

    const ogUrlTag = ensureMetaTag("property", "og:url");
    if (metadata.canonical) {
      ogUrlTag.setAttribute("content", metadata.canonical);
    } else {
      ogUrlTag.remove();
    }

    const canonicalLink = ensureCanonicalLink();
    if (metadata.canonical) {
      canonicalLink.setAttribute("href", metadata.canonical);
    } else {
      canonicalLink.remove();
    }

    syncAlternateLinks(metadata.alternates || []);
  }, [location.pathname]);

  return null;
}
