import { Suspense, lazy, type ComponentType } from "react";
import { createBrowserRouter } from "react-router";
import { basePublicPaths } from "./lib/publicRoutes";
import { RootLayout } from "./components/RootLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";

const LandingPage = lazy(async () => {
  const mod = await import("./pages/LandingPage");
  return { default: mod.LandingPage };
});

const LegalPage = lazy(async () => {
  const mod = await import("./pages/LegalPage");
  return { default: mod.LegalPage };
});

const FAQPage = lazy(async () => {
  const mod = await import("./pages/FAQPage");
  return { default: mod.FAQPage };
});

const PricingPage = lazy(async () => {
  const mod = await import("./pages/PricingPage");
  return { default: mod.PricingPage };
});

const ExamplesPage = lazy(async () => {
  const mod = await import("./pages/ExamplesPage");
  return { default: mod.ExamplesPage };
});

const HowItWorksPage = lazy(async () => {
  const mod = await import("./pages/HowItWorksPage");
  return { default: mod.HowItWorksPage };
});

const GuideDesignPhotoPage = lazy(async () => {
  const mod = await import("./pages/GuideDesignPhotoPage");
  return { default: mod.GuideDesignPhotoPage };
});

const GuideFurnitureSearchPage = lazy(async () => {
  const mod = await import("./pages/GuideFurnitureSearchPage");
  return { default: mod.GuideFurnitureSearchPage };
});

const GuideReferencePage = lazy(async () => {
  const mod = await import("./pages/GuideReferencePage");
  return { default: mod.GuideReferencePage };
});

const InteriorDesignPage = lazy(async () => {
  const mod = await import("./pages/UseCasePages");
  return { default: mod.InteriorDesignPage };
});

const DesignByReferencePage = lazy(async () => {
  const mod = await import("./pages/UseCasePages");
  return { default: mod.DesignByReferencePage };
});

const FurnitureSearchPage = lazy(async () => {
  const mod = await import("./pages/UseCasePages");
  return { default: mod.FurnitureSearchPage };
});

const AppLayout = lazy(async () => {
  const mod = await import("./pages/app/AppLayout");
  return { default: mod.AppLayout };
});

const HomePage = lazy(async () => {
  const mod = await import("./pages/app/HomePage");
  return { default: mod.HomePage };
});

const WorkspacePage = lazy(async () => {
  const mod = await import("./pages/app/WorkspacePage");
  return { default: mod.WorkspacePage };
});

const BillingPage = lazy(async () => {
  const mod = await import("./pages/app/BillingPage");
  return { default: mod.BillingPage };
});

const ResultPage = lazy(async () => {
  const mod = await import("./pages/app/ResultPage");
  return { default: mod.ResultPage };
});

const ProfilePage = lazy(async () => {
  const mod = await import("./pages/app/ProfilePage");
  return { default: mod.ProfilePage };
});

const LoginPage = lazy(async () => {
  const mod = await import("./pages/auth/LoginPage");
  return { default: mod.LoginPage };
});

const NotFoundPage = lazy(async () => {
  const mod = await import("./pages/NotFoundPage");
  return { default: mod.NotFoundPage };
});

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center px-6 py-16 text-center text-[#5A6B3A]">
      Загружаем страницу...
    </div>
  );
}

function withSuspense(Component: ComponentType) {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Component />
    </Suspense>
  );
}

function ProtectedApp() {
  return (
    <ProtectedRoute>
      <AppLayout />
    </ProtectedRoute>
  );
}

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <RouteErrorBoundary />,
    children: [
      ...buildPublicRoutes(),
      {
        path: "/auth/login",
        element: withSuspense(LoginPage),
      },
      {
        path: "/login",
        element: withSuspense(LoginPage),
      },
      {
        path: "/app",
        element: withSuspense(ProtectedApp),
        children: [
          {
            index: true,
            element: withSuspense(HomePage),
          },
          {
            path: "workspace",
            element: withSuspense(WorkspacePage),
          },
          {
            path: "workspace/result/:id",
            element: withSuspense(ResultPage),
          },
          {
            path: "billing",
            element: withSuspense(BillingPage),
          },
          {
            path: "profile",
            element: withSuspense(ProfilePage),
          },
        ],
      },
      {
        path: "*",
        element: withSuspense(NotFoundPage),
      },
    ],
  },
]);

function buildPublicRoutes() {
  const publicComponentMap: Record<(typeof basePublicPaths)[number], ReturnType<typeof withSuspense>> = {
    "/": withSuspense(LandingPage),
    "/faq": withSuspense(FAQPage),
    "/pricing": withSuspense(PricingPage),
    "/examples": withSuspense(ExamplesPage),
    "/how-it-works": withSuspense(HowItWorksPage),
    "/how-to-find-furniture-by-photo": withSuspense(GuideFurnitureSearchPage),
    "/how-to-design-by-photo": withSuspense(GuideDesignPhotoPage),
    "/how-to-design-by-reference": withSuspense(GuideReferencePage),
    "/interior-design-from-photo": withSuspense(InteriorDesignPage),
    "/design-by-reference": withSuspense(DesignByReferencePage),
    "/furniture-search-by-photo": withSuspense(FurnitureSearchPage),
    "/legal": withSuspense(LegalPage),
  };

  return basePublicPaths.flatMap((path) => [
    { path, element: publicComponentMap[path] },
    { path: path === "/" ? "/en" : `/en${path}`, element: publicComponentMap[path] },
  ]);
}
