import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const distDir = path.join(webRoot, "dist");
const serverEntryPath = path.join(webRoot, ".prerender", "server", "entry-server.js");

const { getRouteSeoMetadata, publicPrerenderPaths, renderPublicRoute } = await import(
  pathToFileURL(serverEntryPath).href
);

function escapeHtmlAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function stripManagedHeadTags(html) {
  return html
    .replace(/<title>[\s\S]*?<\/title>\s*/gi, "")
    .replace(/<meta\s+[^>]*name=["']description["'][^>]*>\s*/gi, "")
    .replace(/<meta\s+[^>]*name=["']robots["'][^>]*>\s*/gi, "")
    .replace(/<link\s+[^>]*rel=["']canonical["'][^>]*>\s*/gi, "")
    .replace(/<meta\s+[^>]*property=["']og:(title|description|type|url)["'][^>]*>\s*/gi, "");
}

function buildManagedHeadTags(metadata) {
  const tags = [
    `<title>${escapeHtmlAttribute(metadata.title)}</title>`,
    `<meta name="description" content="${escapeHtmlAttribute(metadata.description)}">`,
    `<meta name="robots" content="${escapeHtmlAttribute(metadata.robots)}">`,
    `<meta property="og:title" content="${escapeHtmlAttribute(metadata.title)}">`,
    `<meta property="og:description" content="${escapeHtmlAttribute(metadata.description)}">`,
    `<meta property="og:type" content="${escapeHtmlAttribute(metadata.ogType ?? "website")}">`,
  ];

  if (metadata.canonical) {
    tags.push(`<link rel="canonical" href="${escapeHtmlAttribute(metadata.canonical)}">`);
    tags.push(`<meta property="og:url" content="${escapeHtmlAttribute(metadata.canonical)}">`);
  }

  for (const alternate of metadata.alternates || []) {
    tags.push(
      `<link rel="alternate" hreflang="${escapeHtmlAttribute(alternate.hrefLang)}" href="${escapeHtmlAttribute(alternate.href)}">`,
    );
  }

  return tags.map((tag) => `      ${tag}`).join("\n");
}

function routeOutputPath(routePath) {
  if (routePath === "/") {
    return path.join(distDir, "index.html");
  }

  return path.join(distDir, routePath.slice(1), "index.html");
}

function renderHtml(template, routePath) {
  const metadata = getRouteSeoMetadata(routePath);
  const appHtml = renderPublicRoute(routePath);
  const htmlWithoutManagedHead = stripManagedHeadTags(template);
  const htmlWithLang = htmlWithoutManagedHead.replace(
    /<html\s+lang=["'][^"']*["']/i,
    `<html lang="${escapeHtmlAttribute(metadata.locale)}"`,
  );
  const htmlWithHead = htmlWithLang.replace(
    "</head>",
    `${buildManagedHeadTags(metadata)}\n    </head>`,
  );

  if (!htmlWithHead.includes('<div id="root"></div>')) {
    throw new Error("Cannot find empty #root placeholder in built index.html");
  }

  return htmlWithHead.replace('<div id="root"></div>', `<div id="root">${appHtml}</div>`);
}

const templatePath = path.join(distDir, "index.html");
const template = await fs.readFile(templatePath, "utf8");
const spaTemplatePath = path.join(distDir, "spa.html");

if (!template.includes('<div id="root"></div>')) {
  throw new Error("Cannot find empty #root placeholder in built index.html template");
}

await fs.writeFile(spaTemplatePath, template, "utf8");

for (const routePath of publicPrerenderPaths) {
  const outputPath = routeOutputPath(routePath);
  const html = renderHtml(template, routePath);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, html, "utf8");
}

console.log(`Prerendered ${publicPrerenderPaths.length} public routes.`);
