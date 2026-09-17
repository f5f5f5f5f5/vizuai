from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs" / "legal"
PUBLIC_DIR = ROOT / "site" / "legal" / "public"

DOCS = [
    {
        "source": DOCS_DIR / "privacy_policy.md",
        "slug": "privacy-policy",
        "nav_title": "Политика конфиденциальности",
        "page_title": "Политика обработки персональных данных",
    },
    {
        "source": DOCS_DIR / "pd_consent.md",
        "slug": "pd-consent",
        "nav_title": "Согласие на ПД",
        "page_title": "Согласие на обработку персональных данных",
    },
    {
        "source": DOCS_DIR / "offer.md",
        "slug": "offer",
        "nav_title": "Публичная оферта",
        "page_title": "Публичная оферта",
    },
    {
        "source": DOCS_DIR / "refund_policy.md",
        "slug": "refund-policy",
        "nav_title": "Политика возвратов",
        "page_title": "Политика возвратов",
    },
    {
        "source": DOCS_DIR / "service_pricing.md",
        "slug": "service-pricing",
        "nav_title": "Цены и услуги",
        "page_title": "Описание услуг и ценообразование",
    },
    {
        "source": DOCS_DIR / "contacts.md",
        "slug": "contacts",
        "nav_title": "Контакты",
        "page_title": "Контакты и реквизиты",
    },
    {
        "source": DOCS_DIR / "affiliate_disclosure.md",
        "slug": "affiliate-disclosure",
        "nav_title": "Партнёрские ссылки",
        "page_title": "Дисклеймер о партнёрских ссылках",
    },
]


DOC_LINKS = {
    "docs/legal/privacy_policy.md": "/privacy-policy",
    "docs/legal/pd_consent.md": "/pd-consent",
    "docs/legal/offer.md": "/offer",
    "docs/legal/refund_policy.md": "/refund-policy",
    "docs/legal/service_pricing.md": "/service-pricing",
    "docs/legal/contacts.md": "/contacts",
    "docs/legal/affiliate_disclosure.md": "/affiliate-disclosure",
}


URL_RE = re.compile(r"(https?://[^\s)]+)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
CODE_RE = re.compile(r"`([^`]+)`")
ORDERED_RE = re.compile(r"^\d+\.\s+")


def _render_inline(text: str) -> str:
    rendered = html.escape(text.strip())

    def repl_code(match: re.Match[str]) -> str:
        value = match.group(1)
        href = DOC_LINKS.get(value)
        if href:
            return f'<a href="{href}"><code>{html.escape(value)}</code></a>'
        return f"<code>{html.escape(value)}</code>"

    rendered = CODE_RE.sub(repl_code, rendered)
    rendered = BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", rendered)
    rendered = URL_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', rendered)
    return rendered


def _render_markdown(md_text: str) -> str:
    lines = md_text.splitlines()
    parts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            parts.append(f"<h{level}>{_render_inline(text)}</h{level}>")
            i += 1
            continue

        if ORDERED_RE.match(stripped):
            items: list[str] = []
            while i < len(lines):
                current = lines[i].strip()
                if not current or not ORDERED_RE.match(current):
                    break
                item = ORDERED_RE.sub("", current, count=1)
                items.append(f"<li>{_render_inline(item)}</li>")
                i += 1
            parts.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue

        if stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines):
                current = lines[i].strip()
                if not current or not current.startswith("- "):
                    break
                item = current[2:].strip()
                items.append(f"<li>{_render_inline(item)}</li>")
                i += 1
            parts.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            current = lines[i].strip()
            if not current:
                break
            if current.startswith("#") or ORDERED_RE.match(current) or current.startswith("- "):
                break
            paragraph_lines.append(current)
            i += 1
        parts.append(f"<p>{_render_inline(' '.join(paragraph_lines))}</p>")

    return "\n".join(parts)


def _nav() -> str:
    links = ['<a href="/">VizuAI Legal</a>']
    for item in DOCS:
        links.append(f'<a href="/{item["slug"]}">{item["nav_title"]}</a>')
    return "\n".join(links)


def _page_layout(*, title: str, body: str, active_slug: str | None = None) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} | VizuAI</title>
  <meta name="description" content="Юридические документы VizuAI">
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <header class="site-header">
    <div class="wrap">
      <div class="brand">VizuAI</div>
      <nav class="top-nav">
        {_nav()}
      </nav>
    </div>
  </header>
  <main class="wrap">
    <article class="legal-card{' active-' + active_slug if active_slug else ''}">
      {body}
    </article>
  </main>
</body>
</html>
"""


def _build_index() -> str:
    cards = []
    for item in DOCS:
        cards.append(
            f"""
            <a class="doc-link-card" href="/{item["slug"]}">
              <h2>{html.escape(item["nav_title"])}</h2>
              <p>Открыть документ</p>
            </a>
            """.strip()
        )
    body = f"""
    <section class="hero">
      <h1>Юридические документы VizuAI</h1>
      <p>Публичные документы VizuAI для сайта, приложения, платёжных сценариев и legacy-канала в Telegram.</p>
    </section>
    <section class="cards">
      {' '.join(cards)}
    </section>
    """
    return _page_layout(title="Юридические документы", body=body)


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "index.html").write_text(_build_index(), encoding="utf-8")
    for item in DOCS:
        md_text = item["source"].read_text(encoding="utf-8")
        body = _render_markdown(md_text)
        page = _page_layout(
            title=item["page_title"],
            body=body,
            active_slug=item["slug"],
        )
        (PUBLIC_DIR / f'{item["slug"]}.html').write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
