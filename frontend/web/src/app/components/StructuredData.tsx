import { useLocation } from "react-router";

import { getStructuredDataNodes } from "@/app/lib/seo/structuredData";

export function StructuredData() {
  const location = useLocation();
  const nodes = getStructuredDataNodes(location.pathname);

  if (!nodes.length) {
    return null;
  }

  return (
    <>
      {nodes.map((node, index) => (
        <script
          key={`${location.pathname}-jsonld-${index}`}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(node) }}
        />
      ))}
    </>
  );
}
