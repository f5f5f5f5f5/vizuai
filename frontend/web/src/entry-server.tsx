import { renderToString } from "react-dom/server";
import { Route, Routes, StaticRouter } from "react-router";

import { RootLayout } from "@/app/components/RootLayout";
import { publicPrerenderPaths, publicPrerenderRoutes } from "@/app/publicPrerenderRoutes";
import { getRouteSeoMetadata } from "@/app/lib/seo/metadata";

export { getRouteSeoMetadata, publicPrerenderPaths };

export function renderPublicRoute(pathname: string) {
  const route = publicPrerenderRoutes.find((item) => item.path === pathname);

  if (!route) {
    throw new Error(`Route is not configured for prerender: ${pathname}`);
  }

  return renderToString(
    <StaticRouter location={pathname}>
      <Routes>
        <Route element={<RootLayout />}>
          {publicPrerenderRoutes.map(({ path, Component }) => (
            <Route key={path} path={path} element={<Component />} />
          ))}
        </Route>
      </Routes>
    </StaticRouter>,
  );
}
