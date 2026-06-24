"""LangChain tools for nurturing: web_search and fetch_url.

These replicate the C# tool-calling behaviour from NurturingAIService.cs,
but as proper LangChain @tool functions so they integrate natively with
LangGraph's tool-calling agent pattern.

Also exposes ``serper_search_structured`` which returns a list of
``SerperResult`` objects (with URL as a separate field) for use by the
researcher node — this prevents the LLM from confabulating URLs that
were originally embedded in formatted text strings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

from community_manager.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SerperResult:
    """A single organic result from Serper.dev with structured fields.

    The URL is kept as a separate field (not embedded in text) so that
    the downstream LLM cannot accidentally invent or modify it.
    """

    title: str
    snippet: str
    url: str
    rank: int
    source_domain: str
    is_trusted_domain: bool
    date: str = ""  # ISO date if Serper provides one, else ""

PREFERRED_SOURCE_DOMAINS = (
    # Global premium
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "economist.com",
    "washingtonpost.com",
    "bbc.com",
    "theguardian.com",
    # Consulting & research
    "mckinsey.com",
    "gartner.com",
    "idc.com",
    "forrester.com",
    "pwc.com",
    "deloitte.com",
    "accenture.com",
    "bain.com",
    "bcg.com",
    # Tech vendors
    "microsoft.com",
    "openai.com",
    "anthropic.com",
    "google.com",
    "googleblog.com",
    "cloud.google.com",
    "aws.amazon.com",
    "ibm.com",
    "oracle.com",
    "sap.com",
    "nvidia.com",
    # Scientific
    "nature.com",
    "science.org",
    "arxiv.org",
    # International orgs
    "oecd.org",
    "worldbank.org",
    "imf.org",
    "weforum.org",
    "europa.eu",
    "ec.europa.eu",
    "nist.gov",
    # Argentina
    "lanacion.com.ar",
    "ambito.com",
    "clarin.com",
    "infobae.com",
    "perfil.com",
    "forbes.com.ar",
    "boletinoficial.gob.ar",
    "argentina.gob.ar",
    # Spain & Europe
    "elmundo.es",
    "abc.es",
    "elpais.com",
    "expansion.com",
    "eleconomista.es",
    "aepd.es",
    "lemonde.fr",
    "faz.net",
    "corriere.it",
)

BLOCKED_SOURCE_DOMAINS = (
    "itsitio.com",
    "abogacia.es",
    "codespaceacademy.com",
    "puromarketing.com",
    "rootstack.com",
    "medium.com",
    "linkedin.com",
    "reddit.com",
    "youtube.com",
    "tiktok.com",
    "facebook.com",
    "instagram.com",
)


def _normalize_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _matches_domain(host: str, patterns: tuple[str, ...]) -> bool:
    return any(host == pattern or host.endswith(f".{pattern}") for pattern in patterns)


def _source_score(url: str, title: str, snippet: str) -> int:
    host = _normalize_host(url)
    title_text = (title or "").lower()
    snippet_text = (snippet or "").lower()

    if _matches_domain(host, BLOCKED_SOURCE_DOMAINS):
        return -100

    score = 0
    if _matches_domain(host, PREFERRED_SOURCE_DOMAINS):
        score += 100

    if host.endswith(".gov") or host.endswith(".edu"):
        score += 40
    elif host.endswith(".org"):
        score += 15

    if "research" in title_text or "report" in title_text or "survey" in title_text:
        score += 10
    if "sponsored" in snippet_text or "partner content" in snippet_text:
        score -= 25

    return score


async def serper_search(query: str, num: int = 10, max_days_old: int = 0) -> str:
    """Low-level Serper.dev search with optional date filter.

    Parameters
    ----------
    query : str
        Search query string.
    num : int
        Number of results to return (1-100).
    max_days_old : int
        If > 0, filter results to the last N days (Google tbs parameter).
    """
    settings = get_settings()
    api_key = settings.nurturing_serper_api_key
    if not api_key:
        return "Error: Serper API key not configured."

    payload: dict = {"q": query, "num": min(num, 100)}
    if max_days_old > 0:
        # tbs=qdr:d (last day), qdr:w (last week), qdr:m (last month ~30 days)
        if max_days_old <= 1:
            payload["tbs"] = "qdr:d"
        elif max_days_old <= 7:
            payload["tbs"] = "qdr:w"
        else:
            payload["tbs"] = "qdr:m"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key},
                json=payload,
            )

            if not resp.is_success:
                logger.warning("Serper search failed with %s", resp.status_code)
                return f"Error: search request failed ({resp.status_code})."

            data = resp.json()
            organic = data.get("organic", [])
            if not organic:
                return "No results found."

            ranked = sorted(
                organic[:10],
                key=lambda item: _source_score(
                    item.get("link", ""), item.get("title", ""), item.get("snippet", ""),
                ),
                reverse=True,
            )

            filtered = [item for item in ranked if _source_score(item.get("link", ""), item.get("title", ""), item.get("snippet", "")) >= 0]
            candidates = filtered or ranked[:5]

            lines: list[str] = []
            for idx, item in enumerate(candidates[:5], 1):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")
                lines.append(f"{idx}. {title} - {snippet} ({link})")

            logger.info("Web search for '%s' returned %d ranked results (%d filtered)", query, len(ranked), len(lines))
            return "\n".join(lines)

    except Exception as exc:
        logger.error("Web search failed for query '%s': %s", query, exc)
        return f"Error: {exc}"


@tool
async def web_search(query: Annotated[str, "Short search query (1-6 words)"]) -> str:
    """Search the web for current information using Serper.dev.

    Use this when you need recent data, news, prices, events
    or any information that may have changed.
    """
    settings = get_settings()
    api_key = settings.nurturing_serper_api_key
    if not api_key:
        return "Error: Serper API key not configured."

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key},
                json={"q": query, "num": 10},
            )

            if not resp.is_success:
                logger.warning("Serper search failed with %s", resp.status_code)
                return f"Error: search request failed ({resp.status_code})."

            data = resp.json()
            organic = data.get("organic", [])
            if not organic:
                return "No results found."

            ranked = sorted(
                organic[:10],
                key=lambda item: _source_score(
                    item.get("link", ""),
                    item.get("title", ""),
                    item.get("snippet", ""),
                ),
                reverse=True,
            )

            filtered = [item for item in ranked if _source_score(item.get("link", ""), item.get("title", ""), item.get("snippet", "")) >= 0]
            candidates = filtered or ranked[:5]

            lines: list[str] = []
            for idx, item in enumerate(candidates[:5], 1):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")
                lines.append(f"{idx}. {title} - {snippet} ({link})")

            logger.info("Web search for '%s' returned %d ranked results (%d filtered)", query, len(ranked), len(lines))
            return "\n".join(lines)

    except Exception as exc:
        logger.error("Web search failed for query '%s': %s", query, exc)
        return f"Error: {exc}"


@tool
async def fetch_url(url: Annotated[str, "Full URL of the page to read"]) -> str:
    """Fetch and extract readable content from a web page.

    Use after web_search when you need to read a full article.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NovitBot/1.0)"},
            )
            resp.raise_for_status()

            # Simple text extraction: strip HTML tags
            html = resp.text
            # Remove script and style blocks
            import re
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r"<[^>]+>", " ", html)
            # Collapse whitespace
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) > 4000:
                text = text[:4000] + "\n[contenido truncado]"

            logger.info("Fetched content from %s (%d chars)", url, len(text))
            return text

    except Exception as exc:
        logger.error("Failed to fetch URL %s: %s", url, exc)
        return f"Error al leer la página: {exc}"


# All tools for the nurturing agent
NURTURING_TOOLS = [web_search, fetch_url]


# ════════════════════════════════════════════════════════════════════════════
#  Structured Serper search (used by researcher node, not by the ReAct agent)
# ════════════════════════════════════════════════════════════════════════════

# Trusted-domain whitelist. Only these ~150 domains are accepted as
# sources in the AI Radar. Any source URL whose domain is not in this
# list will be REJECTED at the researcher (Phase 4b source-quality filter).
#
# Organized by category for maintainability. Each domain was selected for
# editorial credibility, technical depth, or regional relevance.
TRUSTED_SOURCE_DOMAINS = frozenset(
    [
        # ── Argentina (23) ─────────────────────────────────────────
        "lanacion.com.ar", "clarin.com", "ambito.com", "infobae.com", "perfil.com",
        "iprofesional.com", "batimes.com.ar", "forbesargentina.com", "cronista.com",
        "tn.com.ar", "pagina12.com.ar", "telam.com.ar", "forbes.com.ar",
        "boletinoficial.gob.ar", "argentina.gob.ar",
        "elesquiu.com", "lagaceta.com.ar", "lavoz.com.ar",
        "unlp.edu.ar", "uba.ar", "itba.edu.ar", "unsam.edu.ar",
        "redusers.com",
        # ── España (24) ────────────────────────────────────────────
        "elpais.com", "elmundo.es", "abc.es", "expansion.com", "eleconomista.es",
        "cincodias.com", "xataka.com", "computerhoy.com", "elconfidencial.com",
        "lavanguardia.com", "elperiodico.com", "publico.es", "20minutos.es",
        "okdiario.com", "lainformacion.com", "rtve.es", "digital.gob.es",
        "genbeta.com", "hipertextual.com", "microsiervos.com", "valenciaplaza.com",
        "diariodesevilla.es", "deia.eus", "lavozdegalicia.es", "murciaeconomia.com",
        # ── Global news (23) ───────────────────────────────────────
        "reuters.com", "bloomberg.com", "ft.com", "economist.com", "bbc.com",
        "bbc.co.uk", "washingtonpost.com", "theguardian.com", "cnn.com",
        "nytimes.com", "wsj.com", "latimes.com", "apnews.com", "usatoday.com",
        "politico.com", "axios.com", "forbes.com", "businessinsider.com",
        "newsweek.com", "time.com", "npr.org", "pbs.org", "theatlantic.com",
        # ── Global tech (26) ────────────────────────────────────────
        "techcrunch.com", "wired.com", "theverge.com", "engadget.com", "zdnet.com",
        "cnet.com", "thenextweb.com", "digitaltrends.com", "tomshardware.com",
        "venturebeat.com", "protocol.com", "theinformation.com", "semianalysis.com",
        "arstechnica.com", "gizmodo.com", "mashable.com",
        "androidauthority.com", "9to5mac.com", "9to5google.com",
        "fastcompany.com", "inc.com", "huffpost.com",
        "theregister.com", "ieee.org", "interestingengineering.com", "newatlas.com",
        "the-decoder.com", "aibusiness.com",
        # ── LatAm (6) ──────────────────────────────────────────────
        "brasil247.com", "estadao.com.br", "folha.uol.com.br",
        "eluniverso.com", "gestion.pe", "latercera.com",
        # ── Asian tech / business media (English) (8) ──────────────
        "scmp.com", "nikkei.com", "technode.com", "pandaily.com",
        "channelnewsasia.com", "japantimes.co.jp", "koreatimes.co.kr", "straitstimes.com",
        # ── AI / Science + Vendors (42) ───────────────────────────
        "nature.com", "science.org", "arxiv.org", "mit.edu", "harvard.edu",
        "stanford.edu", "technologyreview.com", "newscientist.com",
        "openai.com", "anthropic.com", "blog.google", "ai.google",
        "microsoft.com", "meta.com", "nvidia.com", "deepmind.com",
        "huggingface.co", "deepseek.com", "qwen.ai",
        "xiaomi.com", "minimax.com", "moonshot.ai",
        "distill.pub", "paperswithcode.com", "openreview.net",
        "neurips.cc", "acm.org", "oreilly.com",
        # ── Chinese AI vendors missing ────────────────────────────
        "zhipuai.cn", "01.ai", "tencent.com", "sensetime.com", "baichuan-ai.com",
        # ── Other AI vendors missing ──────────────────────────────
        "cohere.com", "ai21.com", "stability.ai", "perplexity.ai",
        "writer.com", "sakana.ai", "databricks.com", "together.ai",
        # ── Consultoras (10) ───────────────────────────────────────
        "mckinsey.com", "gartner.com", "deloitte.com", "pwc.com", "accenture.com",
        "bcg.com", "ey.com", "kpmg.com", "bain.com", "hbr.org",
        # ── Regulación / Gob (7) ───────────────────────────────────
        "europa.eu", "edpb.europa.eu", "aepd.es",
        "congreso.es", "boe.es", "bcra.gob.ar", "enacom.gob.ar",
        # ── Cybersecurity vendors (4) ─────────────────────────────
        "crowdstrike.com", "cloud.google", "aws.amazon.com", "microsoft.com",
        # ── Benchmarks (3) ─────────────────────────────────────────
        "lmarena.ai", "artificialanalysis.ai", "lmsys.org",
        # ── Financial / Markets (4) ────────────────────────────────
        "marketwatch.com", "seekingalpha.com", "coindesk.com", "ibtimes.com",
        # ── Universities Argentina (+6) ────────────────────────────
        "utn.edu.ar", "udesa.edu.ar", "uca.edu.ar", "utdt.edu.ar",
        "uade.edu.ar", "conicet.gov.ar", "mincyt.gob.ar",
        # ── Universities España (+5) ───────────────────────────────
        "ie.edu", "esade.edu", "iese.edu", "upm.es", "upc.edu",
        # ── Universities Europa (+6) ───────────────────────────────
        "imperial.ac.uk", "cam.ac.uk", "ethz.ch", "tum.de",
        "insead.edu", "hec.edu",
        # ── Gobierno Argentina (+7) ────────────────────────────────
        "arca.gob.ar", "cnv.gob.ar", "anses.gob.ar", "indec.gob.ar",
        "gcba.gob.ar", "buenosaires.gob.ar",
        "senado.gob.ar", "diputados.gob.ar",
        # ── Gobierno España/UE (+6) ────────────────────────────────
        "cnmc.es", "ico.es", "enisa.es", "incibe.es",
        "ec.europa.eu", "europarl.europa.eu",
        # ── Think tanks / Business schools AR/ES (+4) ──────────────
        "iae.edu.ar", "cotec.es",
        # ── Think tanks / Policy (global) (+8) ─────────────────────
        "carnegieendowment.org", "csis.org", "brookings.edu",
        "rand.org", "foreignaffairs.com", "foreignpolicy.com",
        "chathamhouse.org", "atlanticcouncil.org",
    ]
)


# ════════════════════════════════════════════════════════════════════════════
#  Per-intent domain subsets for Brave site: filter
# ════════════════════════════════════════════════════════════════════════════
# Brave Search supports the `site:domain.com` operator in the q parameter.
# By pre-filtering at the search engine level we avoid the noise from SEO
# blogs and only get results from sources we have vetted.
#
# Each subset is a curated slice of TRUSTED_SOURCE_DOMAINS. The researcher
# picks the relevant slice per query so we never send a query to Brave
# without an editorial boundary.

SITES_GLOBAL_TECH = [
    # Global news
    "reuters.com", "bloomberg.com", "ft.com", "bbc.com",
    "theguardian.com", "wsj.com", "axios.com",
    # Global tech press
    "techcrunch.com", "theverge.com", "arstechnica.com",
    "wired.com", "theinformation.com", "technologyreview.com",
    # Asian tech / business
    "scmp.com", "nikkei.com",
    # Global tech (more)
    "theregister.com", "ieee.org",
    # Science / research
    "nature.com", "arxiv.org", "mit.edu",
    # Benchmarks
    "lmarena.ai", "artificialanalysis.ai",
]

SITES_TECH_VENDORS = [
    "openai.com", "anthropic.com", "blog.google",
    "deepmind.com", "meta.com", "huggingface.co",
    "deepseek.com", "qwen.ai", "minimax.com",
    "zhipuai.cn", "01.ai", "tencent.com",
    "cohere.com", "ai21.com", "stability.ai",
    "writer.com", "sakana.ai", "perplexity.ai",
]

SITES_ARGENTINA = [
    "lanacion.com.ar", "clarin.com", "ambito.com", "infobae.com",
    "perfil.com", "iprofesional.com", "forbes.com.ar",
]

SITES_SPAIN = [
    "elpais.com", "elmundo.es", "abc.es", "expansion.com",
    "xataka.com", "lavanguardia.com", "elconfidencial.com",
]

SITES_LATAM = [
    "estadao.com.br", "folha.uol.com.br", "latercera.com",
]

SITES_UNIVERSITIES_AR = [
    "uba.ar", "itba.edu.ar", "unsam.edu.ar", "unlp.edu.ar",
    "utn.edu.ar", "udesa.edu.ar", "utdt.edu.ar", "uade.edu.ar",
    "uca.edu.ar", "conicet.gov.ar", "mincyt.gob.ar", "iae.edu.ar",
]

SITES_UNIVERSITIES_ES = [
    "ie.edu", "esade.edu", "iese.edu", "upm.es", "upc.edu",
    "imperial.ac.uk", "cam.ac.uk", "ethz.ch", "tum.de",
    "insead.edu", "hec.edu",
]

SITES_GOVERNMENT_AR = [
    "argentina.gob.ar", "boletinoficial.gob.ar", "bcra.gob.ar",
    "arca.gob.ar", "cnv.gob.ar", "anses.gob.ar", "gcba.gob.ar",
    "buenosaires.gob.ar", "indec.gob.ar", "enacom.gob.ar",
    "mincyt.gob.ar", "senado.gob.ar", "diputados.gob.ar",
]

SITES_GOVERNMENT_ES = [
    "europa.eu", "edpb.europa.eu", "ec.europa.eu", "europarl.europa.eu",
    "aepd.es", "digital.gob.es", "congreso.es", "boe.es",
    "cnmc.es", "ico.es", "enisa.es", "incibe.es",
]

SITES_THINKTANKS_AR = [
    "iae.edu.ar", "cotec.es",
]

# Benchmarks confiables: leaderboards públicos y repositorios académicos.
# Nada de medios generalistas — solo fuentes que publican scores verificables.
SITES_BENCHMARK = [
    "artificialanalysis.ai",   # #1: benchmarks + pricing multi-vendor
    "lmarena.ai",              # LMSYS Chatbot Arena (ELO rankings vivos)
    "lmsys.org",
    "epochai.org",             # Tendencias de capacidad de modelos (Epoch AI)
    "crfm.stanford.edu",       # Stanford CRFM HELM leaderboard
    "paperswithcode.com",      # SOTA leaderboards por tarea
    "huggingface.co",          # Open LLM Leaderboard v2
]

# Pricing oficial por vendor + artificialanalysis como referencia comparativa.
# Solo fuentes primarias — nada de blogs de terceros con precios especulativos.
SITES_PRICING = [
    "openai.com",              # Pricing oficial OpenAI
    "anthropic.com",           # Pricing oficial Anthropic / Claude
    "ai.google.dev",           # Pricing oficial Google AI (Gemini)
    "mistral.ai",              # Pricing oficial Mistral AI
    "deepseek.com",            # Pricing oficial DeepSeek
    "x.ai",                    # Pricing oficial xAI (Grok)
    "artificialanalysis.ai",   # Comparativa multi-vendor con precios verificados
]


def select_sites_for_intent(
    intent: str,
    *,
    country: str | None = None,
    max_sites: int = 12,
) -> list[str] | None:
    """Pick the right site subset for a given search intent.

    Returns a list of trusted domains to pass to Brave as a `site:` filter
    (joined as ORs), or None to skip filtering (broad search).

    The total is capped at ``max_sites`` (default 12) to keep query URLs
    under Brave's max length (~400-500 chars after URL encoding). This
    is the highest-priority subset of trusted domains; the post-search
    whitelist filter still enforces the full TRUSTED_SOURCE_DOMAINS list
    for the rest of the results.
    """
    intent = (intent or "").lower()

    if intent == "vendor_launch":
        sites = SITES_GLOBAL_TECH + SITES_TECH_VENDORS
    elif intent == "benchmark":
        sites = SITES_BENCHMARK
    elif intent == "pricing":
        sites = SITES_PRICING
    elif intent == "policy":
        # Geopolítica y regulación de IA: medios globales + tech press.
        # No filtramos por vendor porque las noticias de política
        # involucran a todos los actores (gobiernos, reguladores, ONGs).
        sites = SITES_GLOBAL_TECH
    elif intent == "breaking":
        # Breaking / ultra-fresh AI news: redirect to global tech press
        # which covers breaking news the fastest (TechCrunch, Reuters,
        # Bloomberg, The Verge, Ars Technica, etc.)
        sites = SITES_GLOBAL_TECH
    elif intent == "country":
        if country == "AR":
            # For AR queries: prioritize local news + universities + government.
            # Skip SITES_GLOBAL_TECH because techcrunch/reuters don't cover
            # YPF, ARCA, etc. — they pollute results with global launches.
            sites = SITES_ARGENTINA + SITES_UNIVERSITIES_AR + SITES_GOVERNMENT_AR + SITES_LATAM
        elif country == "ES":
            # For ES queries: same logic — prioritize local sources.
            sites = SITES_SPAIN + SITES_UNIVERSITIES_ES + SITES_GOVERNMENT_ES + SITES_LATAM
        else:
            sites = SITES_GLOBAL_TECH
    else:
        # Unknown intent — use global tech only
        sites = SITES_GLOBAL_TECH

    # Deduplicate and cap
    seen: set[str] = set()
    out: list[str] = []
    for s in sites:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_sites:
            break
    return out


def build_site_filter_query(base_query: str, sites: list[str] | None) -> str:
    """Append a Brave-compatible site: filter to a base query string.

    Example output:
        OpenAI GPT (site:techcrunch.com OR site:reuters.com OR site:theverge.com)
    """
    if not sites:
        return base_query
    parts = [f"site:{d}" for d in sites]
    if len(parts) == 1:
        return f"{base_query} {parts[0]}"
    return f"{base_query} ({" OR ".join(parts)})"

# Blacklist of low-quality source patterns. These domains PASS a HEAD
# request (200 OK) but are NOT considered editorial/news sources. They
# should NEVER appear in the AI Radar — they're training sites, personal
# blogs, UGC platforms, or generic SEO content.
LOW_QUALITY_DOMAIN_PATTERNS = [
    # Training / education / cursos
    "cursos", "curso", "academy", "academia", "bootcamp", "learn.",
    "tutorial", "udemy", "coursera", "edx.org", "platzi",
    # UGC platforms (not editorial)
    "medium.com", "substack.com", "linkedin.com", "reddit.com",
    "quora.com", "wordpress.com", "blogspot.com", "tumblr.com",
    # Social media
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "tiktok.com", "youtube.com", "pinterest.com", "snapchat.com",
    # Code / dev (not news)
    "github.com", "gitlab.com", "stackoverflow.com", "stackexchange.com",
    "npmjs.com", "pypi.org",
    # Personal/SEO blogs (TBD lists of bad patterns)
    "itsfoss", "maketecheasier", "gadgetsnow", "techpp",
    "hongkiat", "wptavern",
    # Generic free blog hosts
    ".weebly.com", ".wixsite.com", ".wordpress.com",
]


def is_low_quality_source_domain(domain: str) -> bool:
    """Return True if the domain is in the low-quality blacklist."""
    if not domain:
        return False
    d = domain.lower()
    for pattern in LOW_QUALITY_DOMAIN_PATTERNS:
        if pattern.startswith("."):
            # Suffix match
            if d.endswith(pattern):
                return True
        else:
            # Substring match
            if pattern in d:
                return True
    return False


def is_acceptable_source_domain(domain: str) -> bool:
    """Return True if the domain is acceptable for AI Radar.

    Strategy: strict positive-list (whitelist). Only sources in
    TRUSTED_SOURCE_DOMAINS are accepted. Everything else is rejected
    to maintain editorial quality — the AI Radar is for executives
    and business leaders, not for general SEO blogs.
    """
    if not domain:
        return False
    if is_low_quality_source_domain(domain):
        return False
    return is_trusted_source_domain(domain)


def is_trusted_source_domain(domain: str) -> bool:
    """Check if a domain (or any of its parents) is in the trusted whitelist."""
    if not domain:
        return False
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    for trusted in TRUSTED_SOURCE_DOMAINS:
        if d == trusted or d.endswith("." + trusted):
            return True
    return False


def _serper_post(query: str, num: int, max_days_old: int, sites: list[str] | None = None) -> list[dict]:
    """Low-level POST to Serper.dev. Returns the raw organic list.

    If ``sites`` is provided, appends a site: filter to the query so
    Serper only returns results from those trusted domains.
    """
    settings = get_settings()
    api_key = settings.nurturing_serper_api_key
    if not api_key:
        return []

    final_query = build_site_filter_query(query, sites)
    payload: dict = {"q": final_query, "num": min(num, 100)}
    if max_days_old > 0:
        if max_days_old <= 1:
            payload["tbs"] = "qdr:d"
        elif max_days_old <= 7:
            payload["tbs"] = "qdr:w"
        else:
            payload["tbs"] = "qdr:m"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key},
                json=payload,
            )
            if not resp.is_success:
                logger.warning("Serper search failed with %s", resp.status_code)
                return []
            data = resp.json()
            return data.get("organic", [])
    except Exception as exc:
        logger.error("Serper search failed for query '%s': %s", query, exc)
        return []


async def serper_search_structured(
    query: str,
    *,
    num: int = 10,
    max_days_old: int = 28,
    freshness: str | None = None,
    sites: list[str] | None = None,
) -> list[SerperResult]:
    """Run a Serper search and return structured results.

    Unlike ``serper_search`` (which returns formatted text), this returns
    a list of ``SerperResult`` objects. The URL is a separate field so
    the downstream LLM cannot accidentally confabulate it.

    Parameters
    ----------
    query : str
        Search query.
    num : int
        Number of results to request from Serper (max 100).
    max_days_old : int
        If > 0, filter results to the last N days. Default 28 (recent AI news).
        Ignored if ``freshness`` is explicitly provided.
    freshness : str | None
        Explicit Serper tbs param: "d" (past day), "w" (past week), "m" (past month).
        If provided, overrides ``max_days_old`` to avoid conflicting filters.
    sites : list[str] | None
        If provided, restrict Serper to only return results from these
        trusted domains (passed as a `site:` filter in the query).
    """
    if freshness is not None:
        max_days_old = 0
    organic = _serper_post(query, num=num, max_days_old=max_days_old, sites=sites)
    results: list[SerperResult] = []
    for idx, item in enumerate(organic[:num], 1):
        url = (item.get("link") or "").strip()
        if not url or not url.startswith("http"):
            continue
        domain = _normalize_host(url)
        results.append(
            SerperResult(
                title=(item.get("title") or "").strip(),
                snippet=(item.get("snippet") or "").strip(),
                url=url,
                rank=idx,
                source_domain=domain,
                is_trusted_domain=is_trusted_source_domain(domain),
                date=(item.get("date") or "").strip(),
            )
        )
    logger.info(
        "Serper search for '%s' returned %d results (max_days_old=%d, freshness=%s)",
        query, len(results), max_days_old, freshness,
    )
    return results


# ════════════════════════════════════════════════════════════════════════════
#  Brave Search API (https://api.search.brave.com/res/v1/web/search)
#  Free tier: 2000 queries/month, 1 query/second rate limit.
# ════════════════════════════════════════════════════════════════════════════

def _brave_post(query: str, count: int, freshness: str, sites: list[str] | None = None) -> list[dict]:
    """Low-level POST to Brave Search API. Returns the raw web results list.

    If ``sites`` is provided, appends a site: filter to the query so
    Brave only returns results from those trusted domains.

    Brave's q parameter is capped at ~400-500 chars URL-encoded. If the
    site-filtered query exceeds that, we fall back to a no-filter query.
    The post-search whitelist in the researcher node still enforces the
    full TRUSTED_SOURCE_DOMAINS list.
    """
    settings = get_settings()
    api_key = settings.nurturing_brave_api_key
    if not api_key:
        return []

    final_query = build_site_filter_query(query, sites)
    params = {
        "q": final_query,
        "count": min(count, 20),  # Brave free tier max is 20 per call
    }
    if freshness:
        params["freshness"] = freshness  # "pd" past day, "pw" past week, "pm" past month, "py" past year

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
                params=params,
            )
            if not resp.is_success:
                # 422 means the q param was too long — retry without site filter
                if resp.status_code == 422 and sites:
                    logger.warning(
                        "Brave site-filtered query too long (%d sites), "
                        "retrying without filter",
                        len(sites),
                    )
                    fallback_params = {
                        "q": query,
                        "count": min(count, 20),
                    }
                    if freshness:
                        fallback_params["freshness"] = freshness
                    resp = client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        headers={
                            "X-Subscription-Token": api_key,
                            "Accept": "application/json",
                        },
                        params=fallback_params,
                    )
                    if not resp.is_success:
                        logger.warning(
                            "Brave fallback search failed with %s: %s",
                            resp.status_code, resp.text[:200],
                        )
                        return []
                else:
                    logger.warning(
                        "Brave search failed with %s: %s",
                        resp.status_code, resp.text[:200],
                    )
                    return []
            data = resp.json()
            return data.get("web", {}).get("results", [])
    except Exception as exc:
        logger.error("Brave search failed for query '%s': %s", query, exc)
        return []


def _brave_freshness_for_max_days(max_days_old: int) -> str:
    """Map a max_days_old value to Brave's freshness param.

    Brave only supports: pd (past day), pw (past week), pm (past month), py (past year).
    We treat anything up to ~45 days as "pm" so a 28-35 day recency window
    (our default) still maps to "past month" rather than "past year".
    """
    if max_days_old <= 1:
        return "pd"
    if max_days_old <= 7:
        return "pw"
    if max_days_old <= 45:
        return "pm"
    return "py"


def _brave_age_to_iso(age_str: str | None) -> str:
    """Best-effort: convert Brave's 'age' field (e.g. '2 days ago') to ISO date.

    Returns '' if not parseable. The downstream recency filter treats empty
    dates as 'keep' so we err on the side of including results.
    """
    if not age_str:
        return ""
    import re
    s = age_str.lower().strip()
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", s)
    if not m:
        return ""
    n = int(m.group(1))
    unit = m.group(2)
    days = n
    if unit == "second" or unit == "minute" or unit == "hour":
        days = 0
    elif unit == "week":
        days = n * 7
    elif unit == "month":
        days = n * 30
    elif unit == "year":
        days = n * 365
    from datetime import datetime, timedelta
    target = datetime.utcnow() - timedelta(days=days)
    return target.strftime("%Y-%m-%d")


async def brave_search_structured(
    query: str,
    *,
    num: int = 10,
    max_days_old: int = 28,
    freshness: str | None = None,
    sites: list[str] | None = None,
) -> list[SerperResult]:
    """Run a Brave search and return structured results.

    Parameters
    ----------
    query : str
        Search query.
    num : int
        Number of results to request from Brave (max 20 on free tier).
    max_days_old : int
        If > 0, map to Brave's freshness param (pd/pw/pm/py). Default 28.
        Ignored if ``freshness`` is explicitly provided.
    freshness : str | None
        Explicit Brave freshness param: "pd" (past day), "pw" (past week),
        "pm" (past month), "py" (past year). Overrides ``max_days_old``.
    sites : list[str] | None
        If provided, restrict Brave to only return results from these
        trusted domains (passed as a `site:` filter in the query).
    """
    if freshness is None:
        freshness = _brave_freshness_for_max_days(max_days_old)
    raw_results = _brave_post(query, count=num, freshness=freshness, sites=sites)

    results: list[SerperResult] = []
    for idx, item in enumerate(raw_results[:num], 1):
        url = (item.get("url") or "").strip()
        if not url or not url.startswith("http"):
            continue
        domain = _normalize_host(url)
        # Brave returns age as a human-readable string like "2 days ago"
        age = item.get("age")
        iso_date = _brave_age_to_iso(age) if age else ""
        results.append(
            SerperResult(
                title=(item.get("title") or "").strip(),
                snippet=(item.get("description") or "").strip(),
                url=url,
                rank=idx,
                source_domain=domain,
                is_trusted_domain=is_trusted_source_domain(domain),
                date=iso_date,
            )
        )
    logger.info(
        "Brave search for '%s' returned %d results (freshness=%s)",
        query, len(results), freshness,
    )
    return results


async def search_structured(
    query: str,
    *,
    num: int = 10,
    max_days_old: int = 28,
    freshness: str | None = None,
    sites: list[str] | None = None,
) -> list[SerperResult]:
    """Search using the configured provider (brave by default, serper fallback).

    This is the function the researcher node should call. The provider is
    selected via the NURTURING_SEARCH_PROVIDER env var (default: "brave").

    Parameters
    ----------
    freshness : str | None
        Explicit freshness param: "pd", "pw", "pm", "py" for Brave;
        or "d", "w", "m" for Serper. Overrides ``max_days_old``.
    sites : list[str] | None
        If provided, restrict the search to these trusted domains via a
        `site:` operator in the query. This is the primary quality gate —
        it avoids SEO blogs and other low-quality sources BEFORE Brave
        even returns them, so we don't waste tokens filtering later.
    """
    settings = get_settings()
    provider = (settings.nurturing_search_provider or "brave").lower()
    if provider == "brave":
        return await brave_search_structured(query, num=num, max_days_old=max_days_old, freshness=freshness, sites=sites)
    if provider == "serper":
        return await serper_search_structured(query, num=num, max_days_old=max_days_old, freshness=freshness, sites=sites)
    logger.warning("Unknown search provider '%s', falling back to brave", provider)
    return await brave_search_structured(query, num=num, max_days_old=max_days_old, freshness=freshness, sites=sites)
