import type { ComponentType } from "react";

import { FAQPage } from "@/app/pages/FAQPage";
import { ExamplesPage } from "@/app/pages/ExamplesPage";
import { GuideDesignPhotoPage } from "@/app/pages/GuideDesignPhotoPage";
import { GuideFurnitureSearchPage } from "@/app/pages/GuideFurnitureSearchPage";
import { GuideReferencePage } from "@/app/pages/GuideReferencePage";
import { HowItWorksPage } from "@/app/pages/HowItWorksPage";
import { LandingPage } from "@/app/pages/LandingPage";
import { LegalPage } from "@/app/pages/LegalPage";
import { PricingPage } from "@/app/pages/PricingPage";
import {
  DesignByReferencePage,
  FurnitureSearchPage,
  InteriorDesignPage,
} from "@/app/pages/UseCasePages";
import { basePublicPaths, expandLocalizedPublicPaths } from "@/app/lib/publicRoutes";

type PublicPrerenderRoute = {
  path: string;
  Component: ComponentType;
};

const publicComponentMap: Record<(typeof basePublicPaths)[number], ComponentType> = {
  "/": LandingPage,
  "/faq": FAQPage,
  "/pricing": PricingPage,
  "/examples": ExamplesPage,
  "/how-it-works": HowItWorksPage,
  "/how-to-find-furniture-by-photo": GuideFurnitureSearchPage,
  "/how-to-design-by-photo": GuideDesignPhotoPage,
  "/how-to-design-by-reference": GuideReferencePage,
  "/interior-design-from-photo": InteriorDesignPage,
  "/design-by-reference": DesignByReferencePage,
  "/furniture-search-by-photo": FurnitureSearchPage,
  "/legal": LegalPage,
};

export const publicPrerenderRoutes: PublicPrerenderRoute[] = expandLocalizedPublicPaths(basePublicPaths).map((path) => {
  const basePath = path === "/en" ? "/" : path.startsWith("/en/") ? path.slice(3) : path;
  return {
    path,
    Component: publicComponentMap[basePath as (typeof basePublicPaths)[number]],
  };
});

export const publicPrerenderPaths = publicPrerenderRoutes.map((route) => route.path);
