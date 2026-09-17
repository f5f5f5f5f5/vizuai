export const basePublicPaths = [
  "/",
  "/faq",
  "/pricing",
  "/examples",
  "/how-it-works",
  "/how-to-find-furniture-by-photo",
  "/how-to-design-by-photo",
  "/how-to-design-by-reference",
  "/interior-design-from-photo",
  "/design-by-reference",
  "/furniture-search-by-photo",
  "/legal",
] as const;

export function expandLocalizedPublicPaths(paths: readonly string[]) {
  return paths.flatMap((path) => [path, path === "/" ? "/en" : `/en${path}`]);
}
