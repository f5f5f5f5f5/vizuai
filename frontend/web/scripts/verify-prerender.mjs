import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const distDir = path.join(webRoot, "dist");
const sitemapPath = path.join(distDir, "sitemap.xml");
const publicSiteBaseUrl = "https://vizuai.example";
const spaShellPath = path.join(distDir, "spa.html");

function routeFromUrl(url) {
  const parsed = new URL(url);
  return parsed.pathname === "/" ? "/" : parsed.pathname.replace(/\/$/, "");
}

function routeOutputPath(routePath) {
  if (routePath === "/") {
    return path.join(distDir, "index.html");
  }

  return path.join(distDir, routePath.slice(1), "index.html");
}

function countMatches(html, regex) {
  return [...html.matchAll(regex)].length;
}

function stripTags(html) {
  return html.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<[^>]+>/g, " ");
}

function canonicalForRoute(routePath) {
  return routePath === "/" ? `${publicSiteBaseUrl}/` : `${publicSiteBaseUrl}${routePath}`;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const sitemap = await fs.readFile(sitemapPath, "utf8");
const routes = [...sitemap.matchAll(/<loc>(.*?)<\/loc>/g)].map((match) => routeFromUrl(match[1]));

assert(routes.length === 24, `Expected 24 public sitemap routes, got ${routes.length}`);

const spaShellHtml = await fs.readFile(spaShellPath, "utf8");
assert(spaShellHtml.includes('<div id="root"></div>'), "spa.html: expected empty #root app shell");
assert(!spaShellHtml.includes("<h1"), "spa.html: app shell must not contain prerendered page h1");
assert(!spaShellHtml.includes('href="https://vizuai.example/"'), "spa.html: app shell must not contain public canonical");
assert(!spaShellHtml.includes("Дизайн интерьера по фото с помощью ИИ | VizuAI"), "spa.html: app shell must not contain RU landing title");
assert(!spaShellHtml.includes("AI Interior Design from Photo | VizuAI"), "spa.html: app shell must not contain EN landing title");

for (const routePath of routes) {
  const htmlPath = routeOutputPath(routePath);
  const html = await fs.readFile(htmlPath, "utf8");
  const canonical = canonicalForRoute(routePath);
  const text = stripTags(html).replace(/\s+/g, " ").trim();

  assert(!html.includes('<div id="root"></div>'), `${routePath}: #root is still empty`);
  assert(!html.includes("Загружаем страницу..."), `${routePath}: prerendered Suspense fallback instead of page content`);
  assert(/<h1[\s>]/i.test(html), `${routePath}: missing h1 in prerendered HTML`);
  assert(text.length > 500, `${routePath}: prerendered text content is unexpectedly short`);
  assert(countMatches(html, /<title>/gi) === 1, `${routePath}: expected exactly one title`);
  assert(countMatches(html, /<meta\s+[^>]*name=["']description["'][^>]*>/gi) === 1, `${routePath}: expected exactly one meta description`);
  assert(countMatches(html, /<meta\s+[^>]*name=["']robots["'][^>]*>/gi) === 1, `${routePath}: expected exactly one meta robots`);
  assert(countMatches(html, /<link\s+[^>]*rel=["']canonical["'][^>]*>/gi) === 1, `${routePath}: expected exactly one canonical link`);
  assert(countMatches(html, /<meta\s+[^>]*property=["']og:url["'][^>]*>/gi) === 1, `${routePath}: expected exactly one og:url`);
  assert(html.includes(`href="${canonical}"`), `${routePath}: canonical does not match ${canonical}`);
  assert(html.includes(`content="${canonical}"`), `${routePath}: og:url does not match ${canonical}`);
  assert(/<script\s+[^>]*type=["']application\/ld\+json["'][^>]*>/i.test(html), `${routePath}: missing JSON-LD`);
}

for (const privateRoutePath of ["/app", "/login", "/auth/login"]) {
  try {
    await fs.access(routeOutputPath(privateRoutePath));
    throw new Error(`${privateRoutePath}: private route must not have prerendered HTML`);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      continue;
    }
    throw error;
  }
}

console.log(`Verified prerendered HTML for ${routes.length} public routes.`);
