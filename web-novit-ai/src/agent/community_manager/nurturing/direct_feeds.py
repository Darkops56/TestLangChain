"""Direct feed fetching from vendor blogs and curated AI news sections.

Fetches the latest posts from known-good sources and returns them as
SerperResult-compatible objects so they seamlessly merge into the
existing Brave/Serper search pipeline in the researcher node.

Why this exists:
  Brave/Serper search is great but has three blind spots:
    1. Same queries return the same top-10 results for days
    2. Breaking news takes hours to index and rank
    3. Spanish queries miss English-first announcements

  By fetching directly from vendor blogs and tech media RSS/HTML,
  we catch model launches and breaking news within MINUTES of
  publication — before Brave has even indexed them.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html as lhtml

from community_manager.nurturing.tools import SerperResult

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
#  Feed source registry
# ════════════════════════════════════════════════════════════════════════════
# Each entry is (feed_name, url, source_domain).
# feed_name becomes the category tag in the extraction prompt (e.g. "feed:Anthropic").
# source_domain must be in TRUSTED_SOURCE_DOMAINS or the result will be filtered.

DIRECT_FEED_SOURCES: list[tuple[str, str, str]] = [
    # ── Vendor blogs (official announcements — fastest source) ──
    ("Anthropic",      "https://www.anthropic.com/blog",              "anthropic.com"),
    ("OpenAI",         "https://openai.com/blog",                     "openai.com"),
    ("Google AI",      "https://blog.google/technology/ai/",          "blog.google"),
    ("Meta AI",        "https://ai.meta.com/blog/",                   "meta.com"),
    ("xAI",            "https://x.ai/blog",                           "x.ai"),
    ("Mistral",        "https://mistral.ai/news/",                    "mistral.ai"),
    ("Cohere",         "https://cohere.com/blog",                     "cohere.com"),
    ("DeepSeek",       "https://api-docs.deepseek.com/news",          "deepseek.com"),
    # ── AI news sections (curated editorial coverage) ───────────
    ("TechCrunch AI",  "https://techcrunch.com/category/artificial-intelligence/", "techcrunch.com"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/",                     "venturebeat.com"),
    ("Ars Technica AI","https://arstechnica.com/ai/",                              "arstechnica.com"),
    ("The Verge AI",   "https://www.theverge.com/ai-artificial-intelligence",      "theverge.com"),
    ("Reuters AI",     "https://www.reuters.com/technology/artificial-intelligence/", "reuters.com"),
    ("Wired AI",       "https://www.wired.com/category/artificial-intelligence/",  "wired.com"),
    ("MIT Tech Rev AI","https://www.technologyreview.com/topic/artificial-intelligence/", "technologyreview.com"),
]


# ════════════════════════════════════════════════════════════════════════════
#  HTML parsing
# ════════════════════════════════════════════════════════════════════════════

def _normalize_url(href: str, base_url: str) -> str | None:
    """Resolve a potentially relative href to an absolute URL."""
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return None
    full = urljoin(base_url, href)
    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    # Skip common non-article paths
    path = parsed.path.lower()
    if any(ext in path for ext in (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".ttf")):
        return None
    return full


def _extract_date_from_element(el) -> str:
    """Try to extract a date string from an HTML element (or its children)."""
    # Check <time> tags first
    for time_el in el.xpath('.//time'):
        dt = time_el.get("datetime") or time_el.text or ""
        if dt.strip():
            return dt.strip()
    # Check data attributes
    for data_attr in ("data-date", "data-datetime", "data-timestamp"):
        val = el.get(data_attr)
        if val:
            return val.strip()
    return ""


def _clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw.strip())


def _parse_html_entries(
    page_html: str,
    source_domain: str,
    base_url: str,
    max_entries: int = 5,
) -> list[SerperResult]:
    """Parse blog/feed HTML using lxml. Returns up to ``max_entries`` entries.

    Parsing strategy (in order of preference):
      1. ``<article>`` elements — most semantic, works on WordPress/Ghost
      2. divs with role="article" or class containing "post"/"entry"/"card"
      3. Flat ``<a>`` heading combos as last-resort fallback
    """
    try:
        tree = lhtml.fromstring(page_html)
    except Exception as exc:
        logger.warning("HTML parse failed for %s: %s", source_domain, exc)
        return []

    # Remove noisy elements that contain irrelevant links
    for el in tree.xpath("//script | //style | //nav | //footer | //header | //aside"):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    candidate_els: list = tree.xpath("//article")
    if not candidate_els:
        candidate_els = tree.xpath(
            '//div[contains(@class,"post") or contains(@class,"entry") '
            'or contains(@class,"card") or contains(@class,"item") '
            'or contains(@class,"story") or @role="article"]'
        )
    if not candidate_els:
        # Last resort: treat all h2/h3 siblings as entry boundaries
        candidate_els = [tree]

    entries: list[SerperResult] = []
    seen_urls: set[str] = set()

    for container in candidate_els:
        _extract_entries_from_container(
            container, source_domain, base_url, max_entries, entries, seen_urls,
        )
        if len(entries) >= max_entries:
            break

    return entries[:max_entries]


def _extract_entries_from_container(
    container,
    source_domain: str,
    base_url: str,
    max_entries: int,
    entries: list[SerperResult],
    seen_urls: set[str],
) -> None:
    """Extract article-like entries from a container element."""

    # Use both heading-based and link-based approaches
    # Strategy A: find <a> with heading child
    for a_el in container.xpath(".//a[.//h1 or .//h2 or .//h3]"):
        href = a_el.get("href")
        url = _normalize_url(href, base_url)
        if not url or url in seen_urls:
            continue
        title = _clean_text(a_el.text_content())
        if len(title) < 10:
            continue
        seen_urls.add(url)

        snippet = ""
        date = ""

        # Try to find sibling/child <p> for snippet
        for p in container.xpath(f".//a[@href='{href}']/../p | .//a[@href='{href}']/following-sibling::p"):
            snippet = _clean_text(p.text_content())[:300]
            if snippet:
                break

        # Extract date from the container
        date = _extract_date_from_element(container)

        entries.append(SerperResult(
            title=title,
            snippet=snippet,
            url=url,
            rank=len(entries) + 1,
            source_domain=source_domain,
            is_trusted_domain=True,
            date=date,
        ))
        if len(entries) >= max_entries:
            return

    # Strategy B: find standalone <a> links with meaningful text
    for a_el in container.xpath(".//a[@href]"):
        href = a_el.get("href")
        url = _normalize_url(href, base_url)
        if not url or url in seen_urls:
            continue
        title = _clean_text(a_el.text_content())
        if len(title) < 15:
            continue
        # Skip nav links, tags, categories
        if any(skip in title.lower() for skip in ("subscribe", "sign up", "log in", "register")):
            continue
        if a_el.getparent() is not None and a_el.getparent().tag in ("nav", "footer", "header"):
            continue
        seen_urls.add(url)

        snippet = ""
        date = _extract_date_from_element(container)

        entries.append(SerperResult(
            title=title,
            snippet=snippet,
            url=url,
            rank=len(entries) + 1,
            source_domain=source_domain,
            is_trusted_domain=True,
            date=date,
        ))
        if len(entries) >= max_entries:
            return


# ════════════════════════════════════════════════════════════════════════════
#  HTTP fetching
# ════════════════════════════════════════════════════════════════════════════

async def _fetch_single_source(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    source_domain: str,
    max_entries: int = 5,
) -> tuple[str, list[SerperResult]]:
    """Fetch one feed source and parse its entries."""
    try:
        resp = await client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            },
            timeout=15.0,
            follow_redirects=True,
        )
        if not resp.is_success:
            logger.warning("Direct feed %s returned %s", name, resp.status_code)
            return name, []

        entries = _parse_html_entries(resp.text, source_domain, url, max_entries=max_entries)
        logger.info(
            "Direct feed %s (%s): %d entries",
            name, source_domain, len(entries),
        )
        return name, entries

    except Exception as exc:
        logger.warning("Direct feed fetch failed for %s: %s", name, exc)
        return name, []


# ════════════════════════════════════════════════════════════════════════════
#  Public API
# ════════════════════════════════════════════════════════════════════════════

async def fetch_direct_feeds(
    max_entries_per_source: int = 5,
    concurrency: int = 8,
) -> dict[str, list[SerperResult]]:
    """Fetch all configured direct feed sources in parallel.

    Returns a dict keyed by ``feed:<feed_name>`` (e.g. ``feed:Anthropic``)
    so the researcher node can merge them into the ``by_category`` dict
    alongside vendor and country results.

    Parameters
    ----------
    max_entries_per_source : int
        Max articles to extract per feed source (default 5).
    concurrency : int
        Max parallel HTTP requests (default 8).
    """
    from asyncio import Semaphore, gather

    sem = Semaphore(concurrency)

    async def _bounded(name: str, url: str, domain: str) -> tuple[str, list[SerperResult]]:
        async with sem:
            async with httpx.AsyncClient(timeout=20.0) as client:
                return await _fetch_single_source(client, name, url, domain, max_entries=max_entries_per_source)

    tasks = [_bounded(name, url, domain) for name, url, domain in DIRECT_FEED_SOURCES]
    results: dict[str, list[SerperResult]] = {}

    for name, entries in await gather(*tasks):
        if entries:
            results[f"feed:{name}"] = entries

    total = sum(len(v) for v in results.values())
    logger.info("Direct feeds: %d sources returned %d total entries", len(results), total)
    return results
