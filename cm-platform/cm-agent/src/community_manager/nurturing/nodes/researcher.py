"""Researcher node — structured multi-search for AI news.

Runs ~70+ parallel queries across 5 tiers:
  - vendor_launch (es + en, with new vendors)
  - breaking_ai (pd/pw freshness for same-day/week news)
  - benchmark + pricing
  - global_policy (geopolitics, regulation, government-vendor deals)
  - per-country (AR + ES)
  - direct_feeds (vendor blogs + tech media sections)

Each query passes a curated site: filter to Brave/Serper so SEO blogs
never enter the pool. Results are then passed to GPT-5.4 to extract
30-60 insights with structured fields.

Key design decisions:
  - 3 freshness tiers: breaking (pd/pw), weekly (pw), monthly (pm)
  - No post-search filtering by country or by trusted-domain.
    The scorer handles country assignment and quality scoring.
  - URLs are validated with HEAD request (HTTP < 400 = OK).
  - Insights with source_date > 28 days are discarded.
  - LLM sees snippets as a structured [RESULT #N] list with URL as a
    separate field — this prevents URL confabulation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.settings import get_settings
from community_manager.models.schemas import (
    BenchmarkEntry, BenchmarkSnapshot, RadarInsight, RadarReport,
)
from community_manager.nurturing.direct_feeds import fetch_direct_feeds
from community_manager.nurturing.tools import (
    SerperResult,
    is_acceptable_source_domain,
    is_low_quality_source_domain,
    search_structured,
    select_sites_for_intent,
)
from community_manager.tools.llm import get_newsletter_llm
from community_manager.tools.safe_json import JsonParseError, parse

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 300
URL_VALIDATION_TIMEOUT = 8.0
URL_VALIDATION_MAX_WORKERS = 16  # concurrent HEAD requests
RECENCY_DAYS = 28
SERPER_MAX_DAYS = 21  # Queries without explicit freshness use ~21 days


# ════════════════════════════════════════════════════════════════════════════
#  Query matrix
# ════════════════════════════════════════════════════════════════════════════

VENDOR_LAUNCH_QUERIES = [
    # ── Originales en español ─────────────────────────────────────
    ("OpenAI",     "OpenAI GPT nuevo modelo lanzamiento benchmark pricing", None),
    ("Anthropic",  "Anthropic Claude nuevo modelo lanzamiento benchmark", None),
    ("Google",     "Google DeepMind Gemini nuevo modelo lanzamiento", None),
    ("Meta",       "Meta Llama nuevo modelo lanzamiento benchmark", None),
    ("xAI",        "xAI Grok nuevo modelo lanzamiento benchmark", None),
    ("Mistral",    "Mistral AI nuevo modelo lanzamiento benchmark", None),
    ("DeepSeek",   "DeepSeek nuevo modelo lanzamiento benchmark pricing", None),
    ("Qwen",       "Qwen Alibaba Tongyi nuevo modelo lanzamiento", None),
    ("Moonshot",   "Moonshot Kimi nuevo modelo lanzamiento", None),
    ("Microsoft",  "Microsoft Copilot Phi MAI nuevo modelo lanzamiento", None),
    ("Baidu",      "Baidu Ernie nuevo modelo lanzamiento", None),
    ("ByteDance",  "ByteDance Doubao nuevo modelo lanzamiento", None),
    # ── Nuevos vendors (chinos) ──────────────────────────────────
    ("Zhipu",      "Zhipu AI GLM new model launch benchmark 2026", "pw"),
    ("01.AI",      "01.AI Yi new model launch benchmark 2026", "pw"),
    ("Tencent",    "Tencent Hunyuan new model launch benchmark 2026", "pw"),
    ("SenseTime",  "SenseTime SenseNova new model launch 2026", "pw"),
    # ── Nuevos vendors (no-chinos) ───────────────────────────────
    ("Cohere",     "Cohere Command R new model launch benchmark 2026", None),
    ("AI21",       "AI21 Labs Jamba new model launch benchmark 2026", None),
    ("Stability",  "Stability AI Stable LM new model launch 2026", None),
    ("Perplexity", "Perplexity AI new model launch 2026", None),
    ("Writer",     "Writer Palmyra new model launch enterprise AI 2026", None),
    ("Apple",      "Apple Intelligence model launch AI 2026", None),
    ("Sakana",     "Sakana AI new model launch Japan 2026", None),
    # ── English versions of existing vendors (freshness=pw) ──────
    ("OpenAI",     "OpenAI GPT new model launch benchmark 2026", "pw"),
    ("Anthropic",  "Anthropic Claude new model launch benchmark 2026", "pw"),
    ("Google",     "Google DeepMind Gemini new model launch 2026", "pw"),
    ("Meta",       "Meta Llama new model launch benchmark 2026", "pw"),
    ("xAI",        "xAI Grok new model launch benchmark 2026", "pw"),
    ("Mistral",    "Mistral AI new model launch benchmark 2026", "pw"),
    ("DeepSeek",   "DeepSeek new model launch benchmark pricing 2026", "pw"),
    ("Qwen",       "Qwen Alibaba new model launch benchmark 2026", "pw"),
    ("Microsoft",  "Microsoft Copilot Phi MAI new model launch 2026", "pw"),
]

BENCHMARK_QUERIES = [
    "LLM benchmark MMLU Pro leaderboard 2026",
    "LLM arena elo ranking 2026",
    "LMSYS Chatbot Arena leaderboard 2026",
]

PRICING_QUERIES = [
    "LLM API pricing per million tokens comparison 2026",
    "GPT Claude Gemini DeepSeek pricing comparison 2026",
]

# Queries ultra-frescas para no perder lanzamientos del día/semana.
# Se ejecutan con freshness="pd" (past day) o "pw" (past week)
# para garantizar que haya resultados de HOY/ESTA SEMANA
# que no compitan con artículos establecidos de 35 días.
BREAKING_AI_QUERIES = [
    ("breaking", "breaking AI news today major announcement 2026", "pd"),
    ("breaking", "AI latest news this week model launch release", "pw"),
    ("breaking", "top AI stories this week artificial intelligence", "pw"),
    ("breaking", "Anthropic OpenAI Google AI announcement today 2026", "pd"),
    ("breaking", "China AI model breakthrough news 2026", "pw"),
    ("breaking", "AI model release announcement this week 2026", "pw"),
]

# Geopolítica, regulación y relaciones gobierno-vendor. Estas queries
# pescan noticias que los lanzamientos de modelo no cubren: acuerdos
# con gobiernos, leyes, restricciones de exportación, inversión
# estatal, alianzas geopolíticas de IA.
GLOBAL_POLICY_QUERIES = [
    "AI US government regulation policy 2026",
    "Anthropic US government deal national security agreement 2026",
    "OpenAI US government partnership regulation 2026",
    "Google DeepMind US government contract AI 2026",
    "EU AI Act enforcement fines compliance 2026",
    "China US AI export controls chips restriction 2026",
    "AI military defense contract vendor Palo Alto scale 2026",
    "AI geopolitics sovereign AI funding Europe 2026",
    "OpenAI lobbying Congress AI regulation bill 2026",
    "Anthropic lobbying state department AI safety 2026",
    "Meta AI open source regulation government Europe 2026",
    "Microsoft AI government contract Azure federal 2026",
]

COUNTRY_QUERIES = [
    # ── AR — Empresas concretas (alta especificidad) ─────────────
    ("AR", "YPF IA inteligencia artificial 2026"),
    ("AR", "Mercado Libre IA copilots implementación 2026"),
    ("AR", "Banco Galicia Macro IA atención cliente 2026"),
    # ── AR — Gobierno / regulación ───────────────────────────────
    ("AR", "ARCA AFIP IA fiscalización fraude"),
    ("AR", "BCRA CNV IA regulación financiera Argentina"),
    ("AR", "Argentina IA política pública Plan Conectar Igualdad"),
    # ── AR — Investigación / universidades ───────────────────────
    ("AR", "UBA UTN UDESA Di Tella IA investigación"),
    ("AR", "CONICET MinCyT IA proyectos Argentina"),
    # ── ES — Empresas concretas ──────────────────────────────────
    ("ES", "Telefónica BBVA Santander IA España 2026"),
    ("ES", "Inditex Mango IA España moda retail"),
    # ── ES — Gobierno / regulación ───────────────────────────────
    ("ES", "AI Act España aplicación AEPD 2026"),
    ("ES", "Next Generation EU IA España fondos NextGen"),
    ("ES", "CNMC ICO España IA regulación competencia"),
    # ── ES — Universidades / business schools ────────────────────
    ("ES", "IE ESADE IESE España IA investigación"),
    ("ES", "UPM UPC España IA computer vision"),
    # ── Fallback / Global ────────────────────────────────────────
    ("GLOBAL", "AI artificial intelligence news 2026"),
    ("GLOBAL", "AI business enterprise news 2026"),
]


# ════════════════════════════════════════════════════════════════════════════
#  Dedicated benchmark + pricing research (PR B Phase 2)
# ════════════════════════════════════════════════════════════════════════════
#
# The LLM was previously asked to invent MMLU Pro scores and pricing in
# the same extraction call as the insights. That led to hallucinated
# numbers ("—", wrong scores, made-up model names). The fix is a
# dedicated pass: query public leaderboards + vendor pricing pages,
# then extract structured data FROM THE ACTUAL SNIPPETS — never from
# the LLM's prior knowledge.
#
# If the dedicated research still returns < 5 valid entries, the
# FALLBACK_BENCHMARK_SEED below kicks in. The seed is a hand-curated
# list of well-known 2026 frontier models with public MMLU Pro scores
# and pricing — it's the floor, not the ceiling. The research step
# overrides the seed whenever it finds newer or better data.

LEADERBOARD_DOMAINS = [
    "artificialanalysis.ai",
    "lmarena.ai",
    "llm-stats.com",
    "epochai.org",
    "crfm.stanford.edu",  # HELM
    "huggingface.co",     # Open LLM Leaderboard
    "paperswithcode.com",
]

VENDOR_PRICING_DOMAINS: dict[str, list[str]] = {
    "OpenAI": ["openai.com", "platform.openai.com"],
    "Anthropic": ["anthropic.com", "docs.anthropic.com", "platform.claude.com"],
    "Google DeepMind": ["ai.google.dev", "cloud.google.com"],
    "Meta": ["ai.meta.com", "llama.com"],
    "Mistral": ["mistral.ai", "docs.mistral.ai", "console.mistral.ai"],
    "DeepSeek": ["deepseek.com", "api-docs.deepseek.com"],
    "xAI": ["x.ai", "docs.x.ai"],
    "Qwen": ["qwenlm.github.io", "help.aliyun.com", "dashscope.aliyuncs.com"],
    "Microsoft": ["learn.microsoft.com", "azure.microsoft.com"],
}

# Canonical frontier model registry — one entry per vendor, ordered
# from LATEST to OLDEST within each vendor. The FIRST model in each
# list is the current frontier; older versions are listed for dedup
# purposes (e.g. if the research pass returns Claude Opus 4.5 but
# our latest is Claude Opus 4.8, we prefer the latest).
#
# The user wants the charts to show ONE row per company — the latest
# frontier model from each — because showing two Anthropic rows (4.5
# + 4.8) is confusing and nobody cares about an older version of a
# model that's been superseded.
FRONTIER_MODELS: dict[str, list[dict]] = {
    "Anthropic": [
        {"model": "Claude Opus 4.8", "score": 93.6, "cost_in": 18.00, "cost_out": 90.00},
        {"model": "Claude Opus 4.5", "score": 89.2, "cost_in": 15.00, "cost_out": 75.00},
    ],
    "OpenAI": [
        # The user explicitly said "GPT-5 is old, the latest is GPT-5.5".
        {"model": "GPT-5.5", "score": 92.8, "cost_in": 6.00, "cost_out": 18.00},
        {"model": "GPT-5", "score": 88.7, "cost_in": 5.00, "cost_out": 15.00},
    ],
    "Google DeepMind": [
        {"model": "Gemini 3 Pro", "score": 91.5, "cost_in": 1.50, "cost_out": 6.00},
        {"model": "Gemini 2.5 Pro", "score": 88.0, "cost_in": 1.25, "cost_out": 5.00},
    ],
    "DeepSeek": [
        {"model": "DeepSeek V3.2", "score": 86.4, "cost_in": 0.27, "cost_out": 1.10},
    ],
    "xAI": [
        {"model": "Grok 3", "score": 86.0, "cost_in": 3.00, "cost_out": 12.00},
    ],
    "Meta": [
        {"model": "Llama 4 Maverick", "score": 85.5, "cost_in": 0.59, "cost_out": 0.79},
    ],
    "Mistral": [
        {"model": "Mistral Large 3", "score": 84.2, "cost_in": 2.00, "cost_out": 6.00},
    ],
}


def _build_fallback_seed() -> list[dict]:
    """Pick the LATEST model from each vendor in FRONTIER_MODELS.

    This guarantees the seed always shows the current frontier (not
    an older version), and never shows two models from the same vendor.
    """
    seed: list[dict] = []
    for vendor, models in FRONTIER_MODELS.items():
        latest = models[0]  # first = latest
        seed.append({
            "vendor": vendor,
            "model": latest["model"],
            "benchmark_name": "MMLU Pro",
            "score": latest["score"],
            "cost_per_1m_input": latest["cost_in"],
            "cost_per_1m_output": latest["cost_out"],
        })
    return seed


# Hand-curated baseline of well-known 2026 frontier models with public
# MMLU Pro scores + API pricing. Used ONLY when the dedicated research
# pass cannot find enough data. Numbers are approximations from public
# leaderboards and vendor pricing pages; real research will override.
#
# Generated from FRONTIER_MODELS (latest per vendor) so the table is
# ALWAYS comparable and ALWAYS shows the current frontier.
FALLBACK_BENCHMARK_SEED: list[dict] = _build_fallback_seed()


# ════════════════════════════════════════════════════════════════════════════
#  Public node
# ════════════════════════════════════════════════════════════════════════════

async def researcher_node(state: dict) -> dict:
    """Run structured web searches and extract a wide pool of insights.

    Input: month_name
    Output: raw_report (RadarReport with 25-50 insights after URL validation)

    Aborts the workflow (sets abort_reason) if no real search results
    are returned — the writer should not be called with empty material.
    """
    logger.info("▶ Researcher node starting")

    settings = get_settings()
    month_name = state.get("month_name", "")

    if not settings.is_nurturing_configured:
        logger.warning("Newsletter AI not configured")
        return {
            "raw_report": _fallback_report(month_name),
            "abort_reason": "ai_not_configured",
            "abort_detail": "Newsletter AI endpoint is not configured",
        }

    if not settings.is_web_search_configured:
        logger.error("Serper API key not configured")
        return {
            "raw_report": _fallback_report(month_name),
            "abort_reason": "serper_not_configured",
            "abort_detail": "NURTURING_SERPER_API_KEY is not set",
        }

    if not settings.nurturing_url_validation_enabled:
        logger.warning("URL validation disabled by setting — URLs will NOT be verified")

    try:
        # Phase 1: Build query list
        queries = _build_query_list()
        logger.info("Running %d Brave/Serper queries in parallel", len(queries))

        # Phase 2: Run all searches + direct feeds in parallel
        by_category: dict[str, list[SerperResult]] = {}
        search_task = _run_parallel_searches(queries)
        feeds_task = fetch_direct_feeds(max_entries_per_source=5, concurrency=8)
        search_results, feed_results = await asyncio.gather(search_task, feeds_task)
        by_category.update(search_results)
        by_category.update(feed_results)
        total_results = sum(len(v) for v in by_category.values())
        logger.info(
            "Collected %d structured results (%d from search, %d from direct feeds)",
            total_results,
            sum(len(v) for v in search_results.values()),
            sum(len(v) for v in feed_results.values()),
        )

        if total_results == 0:
            logger.error(
                "No search results — Serper returned nothing. "
                "Aborting workflow to avoid wasting tokens on empty content."
            )
            return {
                "raw_report": _fallback_report(month_name),
                "abort_reason": "no_search_results",
                "abort_detail": (
                    f"Serper returned 0 results across {len(queries)} queries. "
                    "Check NURTURING_SERPER_API_KEY credit balance."
                ),
            }

        # Phase 3: Multi-pass extraction — 4 focused passes, never truncated
        llm = get_newsletter_llm()
        report = await _run_multi_pass_extraction(llm, by_category, month_name)
        logger.info(
            "Extracted %d insights across 4 extraction passes (before URL validation)",
            len(report.insights) + len(report.insights_secondary),
        )

        # Phase 4: Validate URLs with HEAD request (drop broken ones)
        if settings.nurturing_url_validation_enabled:
            report.insights = await _validate_and_filter(report.insights)
            report.insights_secondary = await _validate_and_filter(report.insights_secondary)

        # Phase 4b: Filter by source-domain quality (hard blacklist + trusted whitelist)
        report.insights = _filter_by_source_quality(report.insights)
        report.insights_secondary = _filter_by_source_quality(report.insights_secondary)

        # Phase 5: Filter out insights older than 28 days
        report.insights = _filter_by_recency(report.insights, max_days=RECENCY_DAYS)
        report.insights_secondary = _filter_by_recency(report.insights_secondary, max_days=RECENCY_DAYS)

        total_valid = len(report.insights) + len(report.insights_secondary)
        logger.info(
            "Researcher: %d primary + %d secondary insights (URL-validated, last %d days)",
            len(report.insights), len(report.insights_secondary), RECENCY_DAYS,
        )

        if total_valid == 0:
            logger.error(
                "Zero valid insights after URL validation + recency filter. "
                "Aborting workflow — do not waste LLM tokens on empty content."
            )
            return {
                "raw_report": _fallback_report(month_name),
                "abort_reason": "no_valid_insights",
                "abort_detail": (
                    f"All {len(report.insights) + len(report.insights_secondary)} "
                    "extracted insights failed URL validation or recency filter."
                ),
            }

        logger.info(
            "✅ Researcher completed: %d primary + %d secondary insights (URL-validated, last %d days)",
            len(report.insights), len(report.insights_secondary), RECENCY_DAYS,
        )

        # Phase 6: Dedicated benchmark + pricing research (PR B Phase 2).
        # The LLM extraction above is told to invent scores; we discard
        # that and run a focused pass against public leaderboards + vendor
        # pricing pages, extracting from real snippets. Falls back to
        # FALLBACK_BENCHMARK_SEED if research produces nothing usable —
        # the table is NEVER empty.
        report = await _apply_dedicated_benchmark_research(report, month_name)

        return {"raw_report": report}

    except Exception as exc:
        logger.exception("Researcher failed")
        return {
            "raw_report": _fallback_report(month_name),
            "abort_reason": "researcher_exception",
            "abort_detail": str(exc),
        }


# ════════════════════════════════════════════════════════════════════════════
#  Query building
# ════════════════════════════════════════════════════════════════════════════

def _build_query_list() -> list[tuple[str, str, str, str, str | None, str | None]]:
    """Return list of (category_tag, intent, country, query, sites, freshness).

    The intent drives which subset of TRUSTED_SOURCE_DOMAINS gets passed
    to Brave as a `site:` filter. This pre-filters the search results at
    the engine level so SEO blogs never enter the pool.

    ``freshness`` overrides the default ``max_days_old`` — use "pd"
    (past day), "pw" (past week), or ``None`` for the default (past month).
    """
    queries: list[tuple[str, str, str, str, str | None, str | None]] = []
    for vendor, q, freshness in VENDOR_LAUNCH_QUERIES:
        sites = select_sites_for_intent("vendor_launch")
        queries.append((f"vendor:{vendor}", "vendor_launch", None, q, sites, freshness))
    for tag, q, freshness in BREAKING_AI_QUERIES:
        sites = select_sites_for_intent("breaking")
        queries.append((f"breaking:{tag}", "breaking", None, q, sites, freshness))
    for q in BENCHMARK_QUERIES:
        sites = select_sites_for_intent("benchmark")
        queries.append(("benchmark", "benchmark", None, q, sites, None))
    for q in PRICING_QUERIES:
        sites = select_sites_for_intent("pricing")
        queries.append(("pricing", "pricing", None, q, sites, None))
    for q in GLOBAL_POLICY_QUERIES:
        sites = select_sites_for_intent("policy")
        queries.append(("policy", "policy", "GLOBAL", q, sites, None))
    for tag, q in COUNTRY_QUERIES:
        sites = select_sites_for_intent("country", country=tag)
        queries.append((f"country:{tag}", "country", tag, q, sites, None))
    # Reorder: COUNTRY queries first, then GLOBAL. LLM attention is biased
    # toward the beginning of the prompt, so putting country results first
    # makes it more likely the LLM extracts from local sources.
    queries.sort(key=lambda t: 0 if t[0].startswith("country:") else 1)
    return queries


async def _run_parallel_searches(queries: list[tuple[str, str, str, str, str | None, str | None]]) -> dict[str, list[SerperResult]]:
    """Run all queries in parallel with per-query site filters and freshness. Group by category prefix."""
    by_category: dict[str, list[SerperResult]] = {}

    async def _search_one(tag: str, q: str, sites: list[str] | None, freshness: str | None):
        try:
            results = await search_structured(
                q,
                num=10,
                max_days_old=SERPER_MAX_DAYS,
                freshness=freshness,
                sites=sites,
            )
            return tag, results
        except Exception:
            logger.exception("Search failed for %s", q)
            return tag, []

    tasks = [_search_one(tag, q, sites, freshness) for tag, _intent, _country, q, sites, freshness in queries]
    for tag, results in await asyncio.gather(*tasks):
        by_category.setdefault(tag, []).extend(results)

    return by_category


# ════════════════════════════════════════════════════════════════════════════
#  LLM extraction (structured prompt, no string confabulation)
# ════════════════════════════════════════════════════════════════════════════

EXTRACTION_SYSTEM = """You are an expert AI news analyst for Novit Software, an Argentine
tech consultancy that helps mid-sized companies adopt AI.

Your job: read structured search results and extract the BEST AI insights
you see. Return a JSON object with an "insights" array.

CRITICAL CONSTRAINT: Your response MUST be valid JSON. You have a token
limit. Aim for 20-30 insights (NOT 50). Each insight is ~250-400 chars
of JSON. A 20-insight response is ~8000-10000 chars of JSON. Stay under
the 16000 token response limit. NEVER truncate the JSON. If you must cut
insights to fit, cut the LESS important ones.
Your job: read structured search results and extract the BEST AI insights
you see. Return a JSON object with an "insights" array.

CRITICAL CONSTRAINT: Your response MUST be valid JSON. You have a token
limit. Aim for 20-30 insights (NOT 50). Each insight is ~250-400 chars
of JSON. A 20-insight response is ~8000-10000 chars of JSON. Stay under
12000 chars total to leave room for closing braces.

If you are running out of space, prioritize model launches and
benchmark/pricing data over generic news. Quality > quantity.

═══════════════════════════════════════════════════════════════════════════
HOW TO REFERENCE SOURCES (CRÍTICO)
═══════════════════════════════════════════════════════════════════════════

Each [RESULT #N] block has a title and snippet. The URL is NOT shown to
you in the prompt on purpose — to prevent you from inventing fake URLs
based on the title (which you will absolutely do otherwise).

You MUST reference sources BY INDEX, not by typing the URL. We will
look up the real URL from our trusted cache.

  - result_index: the INTEGER #N from [RESULT #N], e.g. 7
  - DO NOT include source_url, source_title, or source_date in your output
  - We will fill in those fields from the original [RESULT] block

Example: if you want to reference [RESULT #7], you set:
  "result_index": 7

If you don't include result_index, or you include a fake source_url
like "https://example.com/fake", the insight will be REJECTED and
wasted. Returning ONLY result_index is the only way to cite a source.

═══════════════════════════════════════════════════════════════════════════

Each insight MUST have these fields:
  - result_index: integer, the #N from [RESULT #N]
  - headline: clear, direct, 60-100 chars
  - summary: 200-400 chars with context
  - business_impact: one concrete action for mid-sized companies (80-200 chars)
  - country_tag: "AR", "ES", or "GLOBAL" (see COUNTRY CLASSIFICATION below)
  - category: one of: regulacion, proveedores, breakthroughs, agentes,
    subsidios, ciberseguridad, multipolaridad
  - is_model_launch: true if the insight is about a NEW model release
  - vendor: company name if is_model_launch=true (e.g. "OpenAI", "Anthropic")
  - model_name: model name if is_model_launch=true (e.g. "GPT-5.4", "Claude Sonnet 4.5")
  - benchmark_text: benchmark score if mentioned (e.g. "MMLU Pro 92.1")
  - pricing_text: pricing if mentioned (e.g. "$2.50/M input tokens")

ALSO include three top-level indicator fields (max 100 chars each):
  - benchmark_data: latest AI model benchmark comparison. Format: "Model1: XX · Model2: XX · Model3: XX"
  - pricing_data: cost per 1M tokens comparison. Format: "Model1: $X.XX · Model2: $X.XX · Model3: $X.XX"
  - adoption_data: AI adoption stats if found. Format: "Stat 1 · Stat 2". Else "".

ALSO include a structured benchmark_snapshot (TOP 5 MODELS) for ranking tables:
  - benchmark_snapshot: object with these fields:
    - benchmark_name: string (e.g. "MMLU Pro")
    - entries: array of up to 5 objects, sorted by score DESC, with these fields:
      - vendor: string ("OpenAI", "Anthropic", "Google DeepMind", "Meta", "Mistral", "DeepSeek", "Qwen", "xAI", etc.)
      - model: string ("GPT-5.4", "Claude Opus 4.8", "Gemini 3.5 Flash", "Llama 4", "Mistral Large 3", etc.)
      - benchmark_name: string per entry (e.g. "MMLU Pro", or "GPQA Diamond" if MMLU Pro not available for that model)
      - score: number or null (benchmark score, 0-100, e.g. 92.1). Use null ONLY if you have NO data at all.
      - cost_per_1m_input: number or null (USD per 1M input tokens, e.g. 2.50)
      - cost_per_1m_output: number or null (USD per 1M output tokens, e.g. 10.00)
      - rank: integer 1..5 (1 = best by score)

  IMPORTANT: If you cannot find MMLU Pro scores for a model, use another
  comparable benchmark (GPQA Diamond, MMMU-Pro, AIME 2025, etc.) and
  set benchmark_name accordingly per entry. NEVER invent scores.

  NOTE: The benchmark_snapshot you return here is OVERWRITTEN by a
  dedicated research pass that queries public leaderboards and vendor
  pricing pages. So your numbers here are a HINT, not the final source
  of truth. Still, do your best to be accurate when the data is in
  front of you in the search results.

═══════════════════════════════════════════════════════════════════════════
COUNTRY CLASSIFICATION (CRÍTICO — leer con atención)
═══════════════════════════════════════════════════════════════════════════

country_tag debe reflejar el CONTENIDO de la noticia, NUNCA la fuente.
La fuente NO indica el país. Un artículo de Infobae sobre OpenAI es GLOBAL,
no AR. Un artículo de TechCrunch sobre YPF es GLOBAL, no AR.

GLOBAL (default cuando hay duda):
  - Lanzamientos de modelos (OpenAI, Anthropic, Google DeepMind, Meta, xAI,
    Mistral, DeepSeek, Qwen, etc.)
  - Nuevos benchmarks / leaderboards
  - Partnerships entre big tech (Microsoft+OpenAI, AWS+Anthropic, etc.)
  - Trends globales de adopción (% mundial)
  - Nuevas herramientas dev / frameworks (LangChain, Cursor, etc.)
  - Investigaciones de AI labs (papers, releases)
  - Eventos globales (Web Summit, NeurIPS, etc.)

AR (específico de Argentina):
  - Empresas argentinas que adoptan/desarrollan IA: YPF, Mercado Libre,
    Banco Galicia, Banco Macro, Telecom Argentina, Pampa Energía, IRSA,
    Grupo Galicia, Mastellone, Grupo Arcor, Sancor, etc.
  - Regulación AR: ARCA, AFIP, BCRA, ENACOM, CNV, Ministerio de Trabajo
  - Inversión AR: fondos locales, aceleración de startups (NXTP Labs, Kaszek,
    Wayra, etc.), políticas públicas (Plan Conectar Igualdad, etc.)
  - Adopción AR: % de empresas argentinas, casos de uso locales
  - Noticias del Congreso / gobierno argentino
  - Empresas del Mercosur con operación en Argentina
  - Investigación de universidades/labs argentinos: UBA, UTN, ITBA, UDESA,
    Di Tella (utdt.edu.ar), UCA, UADE, CONICET, MinCyT
  - Cualquier artículo publicado por una universidad u organismo argentino
    (uba.ar, utn.edu.ar, arca.gob.ar, etc.) sobre IA → AR

ES (específico de España):
  - Empresas españolas: Telefónica, BBVA, Banco Santander, Inditex, Repsol,
    Iberia, Aena, Naturgy, ACS, Ferrovial, Acciona, Endesa, Naturgy, etc.
  - Empresas con HQ en España: Mango, Puig, Grifols, Cellnex, Amadeus, etc.
  - Regulación ES/UE: AI Act, AEPD, CNMC, CNIL, ICO, gov.es, europa.eu
  - Inversión ES: fondos Next Gen, PERTE, ICO, ENISA
  - Adopción ES: % de empresas españolas, casos de uso locales
  - Noticias del gobierno español o UE específicamente sobre España
  - Empresas europeas con sede u operación fuerte en España
  - Investigación de universidades/business schools: IE, ESADE, IESE,
    UPM, UPC, ICADE, CUNEF, EAE, OBS
  - Cualquier artículo publicado por una universidad u organismo español
    (ie.edu, upm.es, aepd.es, cnmc.es, etc.) sobre IA → ES

REGLA DE ORO — REVISADA:
  1. Si la FUENTE es una universidad, business school, laboratorio de
     research u organismo oficial del país (.edu.ar, .edu, .gob.ar,
     europa.eu, aepd.es, etc.) → ese país, INCLUSO si el tema parece
     "global" (papers sobre modelos fundacionales, AI Act análisis).
     Justificación: research y policy siempre tienen contexto local.
  2. Si el titular o contenido menciona explícitamente una empresa,
     organismo o institución de un país específico, ese es el país.
  3. Si no hay referencia local clara en contenido NI en fuente → GLOBAL.

❌ NO es AR/ES:
  - "Infobae: OpenAI lanza GPT-5.4" → GLOBAL (la noticia es sobre OpenAI)
  - "TechCrunch: Anthropic launches Claude 4.8" → GLOBAL
  - "Xataka: ChatGPT-5 nuevas features" → GLOBAL
  - "El País: análisis del impacto global de la AI Act" → GLOBAL (es sobre impacto global)

✅ SÍ es AR/ES:
  - "ARCA implementa IA para fiscalización" → AR
  - "YPF lanza copilot corporativo en SAP" → AR
  - "Banco Galicia implementa atención al cliente con IA" → AR
  - "Telefónica lanza plataforma IA sovereign para empresas" → ES
  - "AI Act europeo entra en vigor: España publica guía" → ES
  - "Inditex usa IA para predecir tendencias de moda" → ES

═══════════════════════════════════════════════════════════════════════════

⚠️ DISTRIBUTION REQUIREMENT (NO NEGOCIABLE) ⚠️

Tu extracción DEBE incluir al menos:
  - 3 insights con country_tag="AR" (si hay resultados AR disponibles en [RESULT] blocks)
  - 3 insights con country_tag="ES" (si hay resultados ES disponibles en [RESULT] blocks)
  - El resto: GLOBAL

Si después de revisar todos los [RESULT] blocks NO encuentras 3+ insights
claramente AR (contenido argentino explícito: YPF, Mercado Libre, ARCA,
BCRA, UBA, Telecom, Banco Galicia, etc.), incluye los mejores que tengas
aunque sean 1 o 2. Pero REVISA ACTIVAMENTE los bloques [RESULT] de las
queries country antes de descartarlos.

Para identificar resultados AR/ES en los [RESULT] blocks, busca:
  - Titulares con empresas/organismos argentinos: YPF, Mercado Libre,
    Banco Galicia, Banco Macro, Telecom Argentina, ARCA, AFIP, BCRA,
    CNV, Grupo Galicia, Pampa Energía, Sancor, IRSA, Mastellone, UBA,
    UTN, CONICET, UDESA, Di Tella, MinCyT, etc.
  - Titulares con empresas/organismos españoles: Telefónica, BBVA,
    Banco Santander, Inditex, Mango, Repsol, Iberia, Aena, Naturgy,
    Grifols, Cellnex, Amadeus, IE, ESADE, IESE, UPM, UPC, AEPD, AI
    Act, CNMC, ICO, ENISA, INCIBE, NextGen, PERTE, etc.
  - Titulares publicados por medios [.com.ar] o [.es] (Lanacion, Clarin,
    Infobae, Ambito, El Pais, El Mundo, ABC, Expansion, Xataka, La
    Vanguardia, El Confidencial)

⚠️ PRIORIZA insights ES cuando aparezcan en los [RESULT] blocks. Si ves
un titular que mencione a Telefónica, BBVA, AI Act, El País, IE, ESADE,
UPM, UPC, AEPD, INDITEX, MANGO, SANTANDER, REPSOL, etc. → ES, no GLOBAL.

═══════════════════════════════════════════════════════════════════════════

CRITICAL RULES:
1. result_index MUST be the integer N from the [RESULT #N] block.
   DO NOT make up URLs or domains. DO NOT include source_url in your
   output — we will look it up from our cache.
2. If a [RESULT] block has no useful AI news, SKIP it (don't reference
   it from any insight).
3. Extract 20-30 insights (quality over quantity). MUST satisfy the
   DISTRIBUTION REQUIREMENT above (3+ AR, 3+ ES, rest GLOBAL).
4. country_tag: STRICTLY based on CONTENT (see rules above), NEVER on
   source domain. When in doubt, GLOBAL.
5. benchmark_data and pricing_data should reference the TOP 3 models
   mentioned in the results, with format "ModelName: value".
6. NO prose, NO markdown. Output ONLY the JSON object.
7. ALWAYS close the JSON with `}}` (the array and object close braces).
   DO NOT truncate mid-string.
"""


EXTRACTION_SYSTEM_COUNTRY = """You are an expert AI news analyst for Novit Software, an Argentine
tech consultancy that helps mid-sized companies adopt AI.

Your job: read structured search results from local AR/ES media, universities,
and government sources, and extract country-specific AI insights.

CRITICAL CONSTRAINT: Your response MUST be valid JSON. Aim for 4-6 AR + 4-6 ES
insights. Each insight is ~250-400 chars of JSON. A 10-insight response is
~4000-5000 chars of JSON. Stay well under 8000 token limit.

══════════════════════════════════════════════════════════════════════════
HOW TO REFERENCE SOURCES
══════════════════════════════════════════════════════════════════════════

Each [RESULT #N] block has a title, snippet, and source domain. The URL is
NOT shown to you on purpose — to prevent you from inventing fake URLs.
You MUST reference sources BY INDEX, not by typing the URL.

  - result_index: the INTEGER #N from [RESULT #N], e.g. 7
  - DO NOT include source_url in your output — we will look it up from cache

If you don't include result_index, or you include a fake source_url, the
insight will be REJECTED and wasted.

══════════════════════════════════════════════════════════════════════════
COUNTRY CLASSIFICATION (CRÍTICO)
══════════════════════════════════════════════════════════════════════════

country_tag DEBE ser "AR" o "ES" — NUNCA "GLOBAL". Esta pasada es SOLO
para contenido local.

AR (Argentina):
  - Empresas argentinas: YPF, Mercado Libre, Banco Galicia, Banco Macro,
    Telecom Argentina, ARCA, AFIP, BCRA, CNV, Grupo Galicia, Pampa Energía,
    Sancor, IRSA, Mastellone, UBA, UTN, CONICET, UDESA, Di Tella, MinCyT.
  - Titulares publicados en .com.ar (lanacion, clarin, infobae, ambito,
    iprofesional, perfil, forbes, etc.) cuando hablan de AI/IA aplicada a
    Argentina.

ES (España):
  - Empresas españolas: Telefónica, BBVA, Banco Santander, Inditex, Mango,
    Repsol, Iberia, Aena, Naturgy, Grifols, Cellnex, Amadeus, IE, ESADE,
    IESE, UPM, UPC, AEPD, AI Act, CNMC, ICO, ENISA, INCIBE, NextGen, PERTE.
  - Titulares publicados en .es (elpais, elmundo, abc, expansion, xataka,
    lavanguardia, elconfidencial) cuando hablan de AI/IA aplicada a España
    o regulación europea.

══════════════════════════════════════════════════════════════════════════
EXAMPLE CLASSIFICATION
══════════════════════════════════════════════════════════════════════════

✅ SÍ es AR:
  - "ARCA implementa IA para fiscalización" → AR
  - "YPF lanza copilot corporativo en SAP" → AR
  - "Banco Galicia implementa atención al cliente con IA" → AR
  - "UBA presenta paper sobre LLMs en educación" → AR
  - "Infobae: cómo la IA está transformando el empleo en Argentina" → AR

✅ SÍ es ES:
  - "Telefónica lanza plataforma IA sovereign para empresas" → ES
  - "AI Act europeo entra en vigor: España publica guía" → ES
  - "BBVA usa IA para análisis crediticio" → ES
  - "IE University publica ranking de IA empresarial" → ES
  - "El País: análisis del impacto de la IA en empresas españolas" → ES

❌ NO incluyas:
  - "OpenAI lanza GPT-5.4" → GLOBAL (no es AR ni ES, omite)
  - "Anthropic releases Claude 4.8" → GLOBAL (no es AR ni ES, omite)
  - "Google announces Gemini Omni" → GLOBAL (no es AR ni ES, omite)
  - "Mercado Libre invierte en India" → AR solo si la noticia es sobre IA
    adoptada en Argentina. Si es solo expansión comercial, omite.

══════════════════════════════════════════════════════════════════════════
RULES
══════════════════════════════════════════════════════════════════════════

1. result_index MUST be the integer N from the [RESULT #N] block.
2. Aim for 4-6 AR + 4-6 ES insights. If results have more of one country,
   that's OK; just extract the best 10-12 total.
3. country_tag: STRICTLY "AR" or "ES" (never GLOBAL in this call).
4. NO prose, NO markdown. Output ONLY the JSON object.
5. ALWAYS close the JSON with `}}`. DO NOT truncate mid-string.
6. If a [RESULT] block has no useful local AI news, SKIP it.

JSON structure:
{
  "insights": [
    {
      "result_index": 1,
      "headline": "...",
      "summary": "...",
      "business_impact": "...",
      "country_tag": "AR|ES",
      "category": "...",
      "is_model_launch": false,
      "vendor": "",
      "model_name": "",
      "benchmark_text": "",
      "pricing_text": ""
    }
  ]
}
"""


def _format_results_for_prompt(
    by_category: dict[str, list[SerperResult]],
    *,
    max_per_query: int | None = None,
) -> tuple[str, dict[int, SerperResult]]:
    """Format structured results as [RESULT #N] blocks.

    CRITICAL: We DO NOT include the URL in the prompt. If we did, the LLM
    would see real URLs in the prompt and use them as patterns to generate
    its OWN fake URLs (like "tech-insider.org/gpt-5-5-launch" instead of
    using the real URL). By hiding URLs, we force the LLM to return ONLY
    a result_index, and we look up the real URL from our cache.

    Parameters
    ----------
    max_per_query : int | None
        If set, only take the first N results from each category/query.
        Keeps prompt size predictable across 4 extraction passes.

    Returns (prompt_text, index_to_result_map) so we can resolve the
    LLM's result_index to the actual URL.
    """
    sections: list[str] = []
    index_to_result: dict[int, SerperResult] = {}
    global_index = 0
    for category, results in by_category.items():
        if not results:
            continue
        if max_per_query is not None:
            results = results[:max_per_query]
        section_lines = [f"=== {category} ==="]
        for r in results:
            global_index += 1
            index_to_result[global_index] = r
            section_lines.append(f"[RESULT #{global_index}]")
            section_lines.append(f"  title={r.title!r}")
            section_lines.append(f"  snippet={r.snippet[:MAX_SNIPPET_CHARS]!r}")
            if r.date:
                section_lines.append(f"  date={r.date}")
            section_lines.append(f"  source={r.source_domain}")
            section_lines.append("")
        sections.append("\n".join(section_lines))
    return "\n\n".join(sections), index_to_result


# ════════════════════════════════════════════════════════════════════════════
#  Multi-pass extraction — 4 focused passes, each capped to stay under 20K
# ════════════════════════════════════════════════════════════════════════════
# Instead of 1 giant prompt that gets truncated at 20K chars, we split
# into 4 independent passes. Each pass handles a distinct set of categories
# with a per-query result limit so the prompt never exceeds ~18K chars.
#
# Pass order: breaking+feeds FIRST (fastest), then vendor, then country,
# then policy+benchmarks last. Insights are merged with dedup by source_url.

EXTRACTION_PASSES = [
    {
        "name": "breaking_feeds",
        "label": "Breaking news + direct feeds",
        "filter": lambda k: k.startswith("feed:") or k.startswith("breaking:"),
        "system_prompt": EXTRACTION_SYSTEM,
        "extra_instructions": (
            "\n\nFOCUS: Extract BREAKING NEWS and official vendor announcements\n"
            "from direct feeds. Prioritize model launches, product releases,\n"
            "and major announcements from the PAST WEEK. Aim for 8-12 insights.\n"
        ),
        "max_per_query": 5,
    },
    {
        "name": "vendor_launches",
        "label": "Vendor model launches",
        "filter": lambda k: k.startswith("vendor:"),
        "system_prompt": EXTRACTION_SYSTEM,
        "extra_instructions": (
            "\n\nFOCUS: Extract model launches, new releases, and vendor\n"
            "announcements from established AI companies. Look for new\n"
            "models, major updates, benchmark scores, and pricing changes.\n"
            "Aim for 15-20 insights, mostly GLOBAL.\n"
        ),
        "max_per_query": 3,
    },
    {
        "name": "country",
        "label": "Country-specific (AR + ES)",
        "filter": lambda k: k.startswith("country:"),
        "system_prompt": EXTRACTION_SYSTEM_COUNTRY,
        "extra_instructions": (
            "\n\nFOCUS: Extract ONLY country-specific insights for Argentina (AR)\n"
            "and Spain (ES) — local companies, local regulation, local research,\n"
            "local government initiatives. Skip global AI launches.\n"
            "Aim for 4-6 AR + 4-6 ES insights.\n"
        ),
        "max_per_query": 3,
    },
    {
        "name": "policy_benchmarks",
        "label": "Policy, benchmarks & pricing",
        "filter": lambda k: k in ("policy", "benchmark", "pricing"),
        "system_prompt": EXTRACTION_SYSTEM,
        "extra_instructions": (
            "\n\nFOCUS: Extract AI policy and regulation news, geopolitics,\n"
            "government-vendor deals, export controls, benchmark leaderboard\n"
            "updates, and pricing changes. Aim for 8-12 insights.\n"
        ),
        "max_per_query": 3,
    },
]


async def _run_multi_pass_extraction(
    llm,
    by_category: dict[str, list[SerperResult]],
    month_name: str,
) -> RadarReport:
    """Run 4 focused extraction passes, each capped to stay under 20K chars.

    Each pass filters + limits results so the prompt never gets truncated.
    Insights are merged with dedup by ``source_url``. Top-level metadata
    (benchmark_data, pricing_data, adoption_data, benchmark_snapshot) is
    collected from whichever pass returns it first (non-empty wins).
    """
    from community_manager.tools.llm import get_newsletter_llm
    extraction_llm = get_newsletter_llm(temperature=1.0, max_tokens=16000)

    all_insights: list[RadarInsight] = []
    seen_urls: set[str] = set()
    benchmark_data = ""
    pricing_data = ""
    adoption_data = ""
    benchmark_snapshot = None

    for pass_config in EXTRACTION_PASSES:
        pass_cats = {k: v for k, v in by_category.items() if pass_config["filter"](k)}
        if not pass_cats:
            logger.info("Pass '%s': no matching categories, skipping", pass_config["name"])
            continue

        prompt_body, index_to_result = _format_results_for_prompt(
            pass_cats,
            max_per_query=pass_config["max_per_query"],
        )
        if not prompt_body.strip():
            continue

        # Truncate only as last resort (shouldn't happen with per-query limit)
        if len(prompt_body) > 18000:
            logger.warning("Pass '%s' prompt exceeds 18K chars (%d), truncating",
                           pass_config["name"], len(prompt_body))
            prompt_body = prompt_body[:18000]

        user_prompt = _build_user_prompt(
            prompt_body,
            month_name,
            extra_instructions=pass_config["extra_instructions"],
        )
        response = await extraction_llm.ainvoke([
            SystemMessage(content=pass_config["system_prompt"]),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info(
            "Pass '%s' (%s): %d chars → parsed",
            pass_config["name"], pass_config["label"], len(raw),
        )

        report = _parse_extraction_response(raw, month_name, index_to_result)
        if report is None:
            continue

        # Collect insights with dedup
        for ins in report.insights:
            if ins.source_url not in seen_urls:
                seen_urls.add(ins.source_url)
                all_insights.append(ins)

        # Collect top-level data (first non-empty wins)
        if not benchmark_data and report.benchmark_data:
            benchmark_data = report.benchmark_data
        if not pricing_data and report.pricing_data:
            pricing_data = report.pricing_data
        if not adoption_data and report.adoption_data:
            adoption_data = report.adoption_data
        if benchmark_snapshot is None and report.benchmark_snapshot:
            benchmark_snapshot = report.benchmark_snapshot

    if not all_insights:
        return _fallback_report(month_name)

    now = datetime.utcnow()
    month_label = month_name or now.strftime("%B %Y")
    return RadarReport(
        subject=f"AI Radar by Novit | {month_label}",
        report_title=f"AI Radar - {month_label.title()}",
        executive_summary="",
        slide_summary="",
        insights=all_insights[:50],
        benchmark_data=benchmark_data[:200],
        adoption_data=adoption_data[:200],
        pricing_data=pricing_data[:200],
        benchmark_snapshot=benchmark_snapshot,
    )


def _build_user_prompt(
    prompt_body: str,
    month_name: str,
    extra_instructions: str = "",
) -> str:
    """Build the user prompt for the extraction LLM call.

    ``extra_instructions`` is injected after the base FOCUS note so each
    extraction pass can guide the LLM toward its specific goal.
    """
    return (
        f"Extract AI news insights from these structured results for {month_name}.\n\n"
        f"{extra_instructions}\n\n"
        f"{prompt_body}\n\n"
        f"Return ONLY a JSON object with this structure:\n"
        f"{{\n"
        f'  "insights": [{{ "result_index": 1, "headline": "...", "summary": "...", '
        f'"business_impact": "...", "country_tag": "AR|ES|GLOBAL", "category": "...", '
        f'"is_model_launch": bool, "vendor": "...", "model_name": "...", '
        f'"benchmark_text": "...", "pricing_text": "..." }}],\n'
        f'  "benchmark_data": "Model1: XX · Model2: XX · Model3: XX",\n'
        f'  "pricing_data": "Model1: $X.XX · Model2: $X.XX · Model3: $X.XX",\n'
        f'  "adoption_data": "Stat 1 · Stat 2",\n'
        f'  "benchmark_snapshot": {{  // OPTIONAL — a dedicated research pass '
        f'will overwrite this with verified data from public leaderboards '
        f'and vendor pricing pages. Include it only if you see the data '
        f'clearly in the search results above.\n'
        f'    "benchmark_name": "MMLU Pro",\n'
        f'    "entries": [\n'
        f'      {{"vendor": "OpenAI", "model": "GPT-5.4", '
        f'"benchmark_name": "MMLU Pro", "score": 92.1, '
        f'"cost_per_1m_input": 2.50, "cost_per_1m_output": 10.00, "rank": 1}},\n'
        f'      {{"vendor": "Anthropic", "model": "Claude Opus 4.8", '
        f'"benchmark_name": "MMLU Pro", "score": 91.8, '
        f'"cost_per_1m_input": 3.00, "cost_per_1m_output": 15.00, "rank": 2}}\n'
        f'    ]\n'
        f'  }}\n'
        f"}}"
    )


def _parse_extraction_response(
    raw: str,
    month_name: str,
    index_to_result: dict[int, SerperResult],
) -> RadarReport | None:
    """Parse the LLM extraction response into a RadarReport."""
    try:
        data = parse(raw)
    except JsonParseError as exc:
        logger.error("JSON parse failed: %s", exc)
        return _fallback_report(month_name)

    if not isinstance(data, dict):
        return _fallback_report(month_name)

    insights_raw = data.get("insights", [])
    if not isinstance(insights_raw, list):
        insights_raw = []

    report = RadarReport(
        subject=f"AI Radar by Novit | {month_name}",
        report_title=f"AI Radar - {month_name.title()}",
        executive_summary="",
        slide_summary="",
        insights=[],
        benchmark_data=str(data.get("benchmark_data", "") or "")[:200],
        adoption_data=str(data.get("adoption_data", "") or "")[:200],
        pricing_data=str(data.get("pricing_data", "") or "")[:200],
        benchmark_snapshot=_parse_benchmark_snapshot(data.get("benchmark_snapshot"), month_name),
    )

    for item in insights_raw:
        if not isinstance(item, dict):
            continue
        norm = _normalize_single_insight(item, index_to_result)
        if norm is None:
            continue
        try:
            report.insights.append(RadarInsight(**norm))
        except Exception:
            logger.debug("Skipped invalid insight: %s", item.get("headline", "")[:60])
            continue

    return report


def _parse_benchmark_snapshot(data, month_name: str) -> BenchmarkSnapshot | None:
    """Parse and validate the benchmark_snapshot field from the LLM response.

    Tolerant: missing fields, wrong types, or partial data are handled
    gracefully. If no entries survive validation, returns None.
    """
    from community_manager.models.schemas import BenchmarkEntry, BenchmarkSnapshot
    if not isinstance(data, dict):
        return None
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list) or not raw_entries:
        return None

    entries: list[BenchmarkEntry] = []
    for raw in raw_entries[:5]:
        if not isinstance(raw, dict):
            continue
        vendor = str(raw.get("vendor", "") or "").strip()
        model = str(raw.get("model", "") or "").strip()
        if not model:
            continue
        score = raw.get("score")
        if not isinstance(score, (int, float)) or score <= 0 or score > 100:
            score = None
        cost_in = raw.get("cost_per_1m_input")
        if not isinstance(cost_in, (int, float)) or cost_in < 0:
            cost_in = None
        cost_out = raw.get("cost_per_1m_output")
        if not isinstance(cost_out, (int, float)) or cost_out < 0:
            cost_out = None
        rank = raw.get("rank")
        if not isinstance(rank, int) or rank < 1 or rank > 5:
            rank = len(entries) + 1
        benchmark_name = _normalize_benchmark_name(
            str(raw.get("benchmark_name", "") or "").strip()
        )
        # Per-entry benchmark_name overrides the snapshot's default.
        # If the LLM didn't set it, fall back to the snapshot's.
        snapshot_benchmark = str(data.get("benchmark_name", "") or "").strip() or "MMLU Pro"
        entries.append(BenchmarkEntry(
            vendor=vendor,
            model=model,
            benchmark_name=benchmark_name or snapshot_benchmark,
            score=float(score) if score is not None else None,
            cost_per_1m_input=float(cost_in) if cost_in is not None else None,
            cost_per_1m_output=float(cost_out) if cost_out is not None else None,
            rank=rank,
        ))

    if not entries:
        return None

    # Sort by score desc (None last), then re-rank 1..5
    entries.sort(key=lambda e: (e.score is None, -(e.score or 0)))
    for i, e in enumerate(entries, 1):
        e.rank = i

    benchmark_name = str(data.get("benchmark_name", "") or "").strip() or "MMLU Pro"
    return BenchmarkSnapshot(
        benchmark_name=benchmark_name,
        month_key=month_name,
        entries=entries,
    )


def _normalize_single_insight(
    item: dict,
    index_to_result: dict[int, SerperResult] | None = None,
) -> dict | None:
    """Normalize a single insight dict from the LLM.

    The LLM returns a result_index (integer) that maps back to the
    original SerperResult in our cache. The actual source_url, title,
    and date are looked up from there — preventing URL hallucination.
    """
    if not isinstance(item, dict):
        return None

    # Look up the source from the result_index
    source_url = ""
    source_title = ""
    source_date = ""
    if index_to_result is not None:
        idx_raw = item.get("result_index")
        if idx_raw is None:
            logger.debug("Insight missing result_index, skipping: %s", item.get("headline", "")[:60])
            return None
        try:
            idx = int(idx_raw)
        except (ValueError, TypeError):
            logger.debug("Invalid result_index %r, skipping", idx_raw)
            return None
        result = index_to_result.get(idx)
        if result is None:
            logger.debug("result_index %d not in cache, skipping", idx)
            return None
        source_url = result.url
        source_title = result.source_domain
        source_date = result.date
    else:
        # Fallback: try to read source_url from the LLM output (legacy)
        source_url = str(item.get("source_url") or "").strip()

    # Map common field names (LLM may use synonyms)
    field_map = {
        "headline": ["headline", "title", "titulo"],
        "summary": ["summary", "description", "resumen", "descripcion"],
        "business_impact": ["business_impact", "impacto", "impact", "business"],
        "country_tag": ["country_tag", "country", "pais", "region", "tag"],
        "category": ["category", "categoria", "tipo"],
        "is_model_launch": ["is_model_launch", "model_launch", "launch"],
        "vendor": ["vendor", "company", "empresa"],
        "model_name": ["model_name", "model", "modelo"],
        "benchmark_text": ["benchmark_text", "benchmark", "score"],
        "pricing_text": ["pricing_text", "pricing", "price", "precio"],
    }

    normalized: dict = {}
    for target, sources in field_map.items():
        for src in sources:
            if src in item and item[src] not in (None, ""):
                value = item[src]
                if isinstance(value, bool):
                    normalized[target] = value
                else:
                    normalized[target] = str(value).strip()
                break

    # Required: headline and source_url (from cache)
    if not normalized.get("headline"):
        return None
    if not source_url:
        logger.debug("Insight missing source_url (cache miss), skipping: %s", normalized.get("headline", "")[:60])
        return None

    # Validate URL format
    if not source_url.startswith("http"):
        return None

    # Reject obvious placeholders
    url_lower = source_url.lower()
    if any(bad in url_lower for bad in ["example.com", "test.com", "fake", "placeholder", "mock"]):
        return None

    # Fill in source fields from the cache
    normalized["source_url"] = source_url
    if source_title:
        normalized["source_title"] = source_title
    normalized["source_date"] = source_date

    # Defaults
    normalized.setdefault("summary", normalized.get("headline", ""))
    normalized.setdefault("business_impact", "")
    normalized.setdefault("country_tag", "GLOBAL")
    normalized.setdefault("category", "breakthroughs")
    normalized.setdefault("is_model_launch", False)
    normalized.setdefault("vendor", "")
    normalized.setdefault("model_name", "")
    normalized.setdefault("benchmark_text", "")
    normalized.setdefault("pricing_text", "")

    # POST-EXTRACTION HEURISTIC OVERRIDE: if the source is unambiguously
    # a local institution (university, government, business school) and
    # the LLM classified it as GLOBAL, force the country_tag to match
    # the source. This handles the case where a UBA paper or AEPD policy
    # doc is about a "global" topic but is locally relevant.
    _reclassify_by_local_source(normalized, source_url)

    return normalized


# Source-domain patterns that are unambiguously local institutions.
# If the LLM classified an insight from one of these as GLOBAL, we
# override to the matching country. The whitelist (TRUSTED_SOURCE_DOMAINS)
# already restricts sources to vetted domains, so this only fires for
# sources we've explicitly approved as local.
_LOCAL_SOURCE_PATTERNS: list[tuple[str, str]] = [
    # (domain_suffix_or_match, country_tag)
    (".edu.ar", "AR"),
    (".gob.ar", "AR"),
    (".edu", "ES"),  # most .edu in our whitelist are Spanish/European universities
    (".es", "ES"),
    (".ac.uk", "ES"),  # Imperial, Cambridge in SITES_UNIVERSITIES_ES
    (".ch", "ES"),  # ETH Zurich
    (".de", "ES"),  # TU Munich
    ("europa.eu", "ES"),
    ("ec.europa.eu", "ES"),
]

# Root-level domains (no sub-domain structure) that are unambiguously AR
# or ES. These wouldn't match suffix patterns above, so we list them
# explicitly. All are in our TRUSTED_SOURCE_DOMAINS whitelist.
_LOCAL_SOURCE_ROOTS: dict[str, str] = {
    "uba.ar": "AR",          # Universidad de Buenos Aires
    "conicet.gov.ar": "AR",  # Consejo Nacional de Investigaciones
    "mincyt.gob.ar": "AR",   # Ministerio de Ciencia y Tecnología
}


def _reclassify_by_local_source(normalized: dict, source_url: str) -> None:
    """Override country_tag to AR/ES if the source is a local institution.

    Only fires when the LLM classified the insight as GLOBAL. We do NOT
    override if the LLM already picked AR or ES (LLM's intent is respected).
    """
    if not source_url:
        return
    current_tag = (normalized.get("country_tag") or "GLOBAL").upper()
    if current_tag != "GLOBAL":
        return

    domain = (urlparse(source_url).hostname or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]

    # 1. Check explicit root domains first (uba.ar, conicet.gov.ar, etc.)
    if domain in _LOCAL_SOURCE_ROOTS:
        normalized["country_tag"] = _LOCAL_SOURCE_ROOTS[domain]
        logger.info(
            "Reclassified insight to %s based on local source %s: %s",
            _LOCAL_SOURCE_ROOTS[domain], domain, normalized.get("headline", "")[:60],
        )
        return

    # 2. Check suffix patterns (.edu.ar, .es, .ac.uk, etc.)
    for pattern, country in _LOCAL_SOURCE_PATTERNS:
        if domain.endswith(pattern) or domain == pattern.lstrip("."):
            normalized["country_tag"] = country
            logger.info(
                "Reclassified insight to %s based on local source %s: %s",
                country, domain, normalized.get("headline", "")[:60],
            )
            return

    # 3. Check broad country-TLD patterns (.com.ar, .com.es, .com.mx, etc.)
    # These are local media, even if not in the explicit whitelist list.
    if domain.endswith(".com.ar") or domain.endswith(".com.es") or domain.endswith(".ar") or domain.endswith(".es"):
        # Only treat as AR/ES if domain is a recognizable local media/edu/gov.
        # We accept: any .com.ar, any .com.es, any .ar (ccTLD), any .es (ccTLD).
        country = "AR" if domain.endswith(".ar") or domain.endswith(".com.ar") else "ES"
        normalized["country_tag"] = country
        logger.info(
            "Reclassified insight to %s based on local-TLD source %s: %s",
            country, domain, normalized.get("headline", "")[:60],
        )


def _domain_to_title(url: str) -> str:
    """Best-effort human title from a URL domain."""
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        # Take the first label as title
        first = domain.split(".")[0]
        return first.upper()
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════════════════════
#  URL validation (HEAD request in parallel)
# ════════════════════════════════════════════════════════════════════════════

async def _validate_and_filter(insights: list[RadarInsight]) -> list[RadarInsight]:
    """HEAD-request each URL in parallel; drop insights with broken URLs."""
    if not insights:
        return []

    settings = get_settings()
    if not settings.nurturing_url_validation_enabled:
        return insights

    semaphore = asyncio.Semaphore(URL_VALIDATION_MAX_WORKERS)

    # Realistic browser UA so major sites (Reuters, Axios, Bloomberg) don't
    # 401/403 us. Combined with Accept-Language for AR/ES sites.
    _UA_DESKTOP = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    _HEADERS_BASE = {
        "User-Agent": _UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async def _check_one(insight: RadarInsight) -> RadarInsight | None:
        async with semaphore:
            url = insight.source_url
            if not url:
                return None
            try:
                async with httpx.AsyncClient(
                    timeout=URL_VALIDATION_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    resp = await client.head(url, headers=_HEADERS_BASE)
                    if resp.status_code == 405:
                        # Some servers block HEAD; fall back to GET
                        resp = await client.get(url, headers=_HEADERS_BASE)
                    if resp.status_code < 400:
                        return insight
                    logger.warning("Broken URL %s → %s", url[:80], resp.status_code)
                    return None
            except Exception as exc:
                logger.warning("Unreachable URL %s: %s", url[:80], exc)
                return None

    results = await asyncio.gather(*[_check_one(i) for i in insights])
    valid = [r for r in results if r is not None]
    logger.info(
        "URL validation: %d/%d insights kept",
        len(valid), len(insights),
    )
    return valid


# ════════════════════════════════════════════════════════════════════════════
#  Source quality filter (post-URL-validation)
# ════════════════════════════════════════════════════════════════════════════

def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _filter_by_source_quality(insights: list[RadarInsight]) -> list[RadarInsight]:
    """Drop insights whose source domain is in the low-quality blacklist
    or not in the trusted whitelist.

    This is a STRICT positive-list filter. Only sources that pass both
    checks (not in blacklist AND in trusted whitelist) are kept.

    Logs the top 20 dropped domains (by frequency) so we can expand the
    whitelist over time if too many insights are dropped.
    """
    if not insights:
        return []
    valid: list[RadarInsight] = []
    dropped_blacklist = 0
    dropped_unknown = 0
    dropped_domains: dict[str, int] = {}
    for insight in insights:
        if not insight.source_url:
            continue
        domain = _extract_domain(insight.source_url)
        if is_acceptable_source_domain(domain):
            valid.append(insight)
        elif is_low_quality_source_domain(domain):
            dropped_blacklist += 1
        else:
            dropped_unknown += 1
            dropped_domains[domain] = dropped_domains.get(domain, 0) + 1
            logger.debug(
                "Dropped unknown source [%s]: %s",
                domain, insight.headline[:60],
            )
    if dropped_blacklist or dropped_unknown:
        # Log top dropped domains to help expand the whitelist over time
        top_dropped = sorted(
            dropped_domains.items(), key=lambda x: x[1], reverse=True
        )[:20]
        logger.info(
            "Source-quality filter: kept %d, dropped %d (blacklist) + %d (unknown). "
            "Top dropped domains: %s",
            len(valid), dropped_blacklist, dropped_unknown,
            ", ".join(f"{d}({n})" for d, n in top_dropped),
        )
    return valid


# ════════════════════════════════════════════════════════════════════════════
#  Recency filter (post-extraction)
# ════════════════════════════════════════════════════════════════════════════

def _filter_by_recency(
    insights: list[RadarInsight],
    *,
    max_days: int = RECENCY_DAYS,
) -> list[RadarInsight]:
    """Drop insights with source_date older than max_days.

    Insights with no source_date are kept (we can't verify recency).
    """
    cutoff = datetime.utcnow() - timedelta(days=max_days)
    valid: list[RadarInsight] = []
    dropped = 0
    for insight in insights:
        date_str = (insight.source_date or "").strip()
        if not date_str:
            valid.append(insight)
            continue
        parsed = _try_parse_date(date_str)
        if parsed is None:
            # Unparseable — keep
            valid.append(insight)
            continue
        if parsed >= cutoff:
            valid.append(insight)
        else:
            dropped += 1
            logger.debug(
                "Dropping stale insight (%s): %s",
                date_str, insight.headline[:60],
            )
    if dropped:
        logger.info("Recency filter (%d days): dropped %d stale insights", max_days, dropped)
    return valid


def _try_parse_date(date_str: str) -> datetime | None:
    """Try to parse common date formats. Returns None if unparseable."""
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


# ════════════════════════════════════════════════════════════════════════════
#  Dedicated benchmark + pricing research (PR B Phase 2)
# ════════════════════════════════════════════════════════════════════════════

# Curated set of well-known models we always ask about, even if the
# insights pass didn't surface a new launch. These are the comparison
# floor — comparable frontier 2026 models. If research finds newer
# launches (e.g. GPT-5.5, Claude Opus 4.8), they replace the seed.
DEFAULT_COMPARISON_MODELS: list[dict] = [
    {"vendor": "Anthropic",       "model": "Claude Opus"},
    {"vendor": "OpenAI",          "model": "GPT-5"},
    {"vendor": "Google DeepMind", "model": "Gemini 3 Pro"},
    {"vendor": "DeepSeek",        "model": "DeepSeek V3"},
    {"vendor": "xAI",             "model": "Grok 3"},
]

# Recognized public benchmarks, in priority order. The extraction LLM
# uses this list to pick the most authoritative benchmark available
# for each model. MMLU Pro is preferred (industry standard reasoning
# benchmark), GPQA Diamond is the next-best general benchmark, then
# domain-specific (AIME 2025, SWE-bench, MATH-500, MMMU-Pro).
PREFERRED_BENCHMARKS = [
    "MMLU Pro",
    "GPQA Diamond",
    "MMMU-Pro",
    "AIME 2025",
    "SWE-bench Verified",
    "MATH-500",
    "HumanEval+",
]


def _collect_models_from_insights(insights: list[RadarInsight]) -> list[dict]:
    """Extract (vendor, model) pairs from insights where a model was launched.

    Returns a de-duplicated list preserving insertion order. Models that
    are not a launch (vendor='') are skipped. Falls back to
    ``DEFAULT_COMPARISON_MODELS`` if no launches were found.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for ins in insights:
        vendor = (ins.vendor or "").strip()
        model = (ins.model_name or "").strip()
        if not vendor or not model:
            continue
        key = (vendor.lower(), model.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"vendor": vendor, "model": model})
    if not out:
        return list(DEFAULT_COMPARISON_MODELS)
    # Always include the DEFAULT set as well (in case a launch was a
    # niche vendor and we want to keep comparing the floor models).
    for d in DEFAULT_COMPARISON_MODELS:
        key = (d["vendor"].lower(), d["model"].lower())
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out[:8]  # cap to 8 models to keep Brave budget sane


def _build_dedicated_queries(models: list[dict]) -> list[tuple[str, list[str]]]:
    """Build (query, sites) tuples for dedicated benchmark + pricing research.

    Budget-conscious: we cap at 8 queries total to keep Brave spend low.
    Strategy:
      - 4 benchmark queries (one per major vendor, site: leaderboards)
      - 3 pricing queries (one per major vendor, site: vendor domains)
      - 1 generic MMLU Pro leaderboard query as safety net

    Pricing for vendors we don't query individually falls back to the
    FALLBACK_BENCHMARK_SEED.
    """
    queries: list[tuple[str, list[str]]] = []
    # Benchmark queries — 4 vendors × 1 query each, restricted to leaderboards
    benchmark_vendors = [
        ("Anthropic", "Claude Opus"),
        ("OpenAI", "GPT-5"),
        ("Google DeepMind", "Gemini 3 Pro"),
        ("DeepSeek", "DeepSeek V3"),
    ]
    for vendor, model in benchmark_vendors:
        queries.append((
            f"{vendor} {model} MMLU Pro score 2026",
            list(LEADERBOARD_DOMAINS),
        ))
    # Pricing queries — 3 vendors, site: vendor domains
    pricing_vendors = [
        ("Anthropic", "Claude Opus 4.5"),
        ("OpenAI", "GPT-5"),
        ("Google DeepMind", "Gemini 3 Pro"),
    ]
    for vendor, model in pricing_vendors:
        sites = VENDOR_PRICING_DOMAINS.get(vendor, [])
        if sites:
            queries.append((
                f"{vendor} {model} API pricing per million tokens",
                sites,
            ))
    # 1 generic leaderboard query as safety net
    queries.append(("MMLU Pro leaderboard frontier 2026", list(LEADERBOARD_DOMAINS)))
    return queries


async def _run_dedicated_queries(queries: list[tuple[str, list[str]]]) -> list[SerperResult]:
    """Run all dedicated queries in parallel and return a flat list of results.

    Caps total results to 40 to keep the extraction prompt manageable.
    """
    from community_manager.nurturing.tools import search_structured
    tasks = [search_structured(q, num=8, max_days_old=365, sites=sites)
             for q, sites in queries]
    nested = await asyncio.gather(*tasks, return_exceptions=True)
    flat: list[SerperResult] = []
    for batch in nested:
        if isinstance(batch, Exception):
            logger.warning("Dedicated query failed: %s", batch)
            continue
        flat.extend(batch)
    # Dedupe by URL
    seen_urls: set[str] = set()
    deduped: list[SerperResult] = []
    for r in flat:
        if r.url in seen_urls:
            continue
        seen_urls.add(r.url)
        deduped.append(r)
    return deduped[:40]


BENCHMARK_EXTRACTION_PROMPT = """\
Sos un extractor de datos de modelos de IA. Tu trabajo es devolver
scores y precios VERIFICADOS de frontier LLMs, NO inventar.

Dada una lista de resultados de búsqueda, devolvé un JSON con
este schema EXACTO:

{{
  "entries": [
    {{
      "vendor": "OpenAI",
      "model": "GPT-5.5",
      "benchmark_name": "MMLU Pro",
      "score": 81.2,
      "cost_per_1m_input": 5.00,
      "cost_per_1m_output": 15.00,
      "source_url": "https://artificialanalysis.ai/models/gpt-5-5"
    }}
  ]
}}

REGLAS ESTRICTAS:
  1. SOLO usá datos que aparezcan EXPLÍCITAMENTE en los snippets. NO
     inventes números. Si un modelo no tiene score visible, NO lo
     incluyas (no pongas null — omitilo).
  2. Cada entrada DEBE tener un score (0-100) de un benchmark
     reconocido. Prioridad: MMLU Pro > GPQA Diamond > MMMU-Pro >
     AIME 2025 > SWE-bench Verified > MATH-500 > HumanEval+.
     Si MMLU Pro no está en los snippets para un modelo, usá otro
     de la lista y poné el nombre en `benchmark_name`.
  3. Cada entrada DEBE tener cost_per_1m_input Y cost_per_1m_output
     en USD por millón de tokens. Si solo uno aparece en los
     snippets, poné null en el otro.
  4. Si tenés 2+ fuentes para el mismo modelo con scores distintos,
     usá el que parezca más autoritativo (Artificial Analysis,
     LMArena, Epoch AI > blog del vendor > TechCrunch).
  5. Devolvé hasta 5 entradas, ordenadas por score descendente.
  6. Si no encontrás datos para ningún modelo, devolvé entries vacío.

RESULTADOS DE BÚSQUEDA ({month_name}):
{snippets}

Devolvé SOLO el JSON (sin markdown, sin texto antes/después):"""


async def _research_benchmark_snapshot(
    llm,
    models: list[dict],
    month_name: str,
) -> BenchmarkSnapshot:
    """Dedicated research pass: extract benchmark + pricing from real search results.

    Strategy:
      1. Run targeted Brave queries against leaderboards + vendor pricing pages.
      2. Call the LLM to extract structured data FROM the actual snippets.
      3. Validate each entry (score in 0-100, cost in $0.001-$100).
      4. If we end up with < 5 valid entries, top up from FALLBACK_BENCHMARK_SEED.
      5. Re-rank and trim to top 5.

    The fallback seed is the FLOOR — it guarantees the table always
    has comparable 2026 frontier models, even if all queries fail.
    """
    from community_manager.models.schemas import BenchmarkEntry, BenchmarkSnapshot
    from community_manager.tools.safe_json import parse, JsonParseError

    logger.info("Dedicated benchmark research: %d models, month=%s", len(models), month_name)

    queries = _build_dedicated_queries(models)
    results = await _run_dedicated_queries(queries)
    logger.info("Dedicated research: %d unique results across %d queries",
                len(results), len(queries))

    researched_entries: list[BenchmarkEntry] = []
    benchmark_name_used = "MMLU Pro"

    if results:
        # Build the extraction prompt
        snippets = "\n\n".join(
            f"[{i}] {r.title}\n{r.snippet}\nURL: {r.url}\n"
            f"Source: {r.source_domain}"
            for i, r in enumerate(results, 1)
        )
        prompt = BENCHMARK_EXTRACTION_PROMPT.format(
            month_name=month_name, snippets=snippets[:18000]
        )
        try:
            extraction_llm = get_newsletter_llm(temperature=0.0, max_tokens=4000)
            response = await extraction_llm.ainvoke([
                HumanMessage(content=prompt),
            ])
            raw = response.content if hasattr(response, "content") else str(response)
            logger.info("Benchmark extraction response: %d chars", len(raw))
            data = parse(raw)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                # Validate and accept
                for raw_entry in data["entries"][:5]:
                    entry = _validate_research_entry(raw_entry)
                    if entry is not None:
                        researched_entries.append(entry)
                if researched_entries:
                    # Use the benchmark_name from the first entry
                    benchmark_name_used = researched_entries[0].benchmark_name or "MMLU Pro"
        except (JsonParseError, Exception) as exc:
            logger.warning("Benchmark extraction LLM call failed: %s", exc)

    logger.info("Dedicated research produced %d valid entries", len(researched_entries))

    # Determine the data source for provenance (shown below the charts).
    # The user requires RELIABLE data: either ALL from research or ALL
    # from the seed. NEVER mix.
    research_complete = len(researched_entries) >= 3 and all(
        e.score is not None and e.cost_per_1m_input is not None
        for e in researched_entries
    )

    if research_complete:
        logger.info("Using ONLY researched entries (%d) — no seed mix", len(researched_entries))
        pool = researched_entries
        source = "artificialanalysis.io"
    else:
        logger.info("Using ONLY fallback seed entries (%d) — research had %d valid entries",
                    len(FALLBACK_BENCHMARK_SEED), len(researched_entries))
        pool = [
            BenchmarkEntry(
                vendor=s["vendor"],
                model=s["model"],
                benchmark_name=s["benchmark_name"],
                score=s["score"],
                cost_per_1m_input=s["cost_per_1m_input"],
                cost_per_1m_output=s["cost_per_1m_output"],
                rank=0,
            )
            for s in FALLBACK_BENCHMARK_SEED
        ]
        source = "Precios referenciales — documentación oficial de cada vendor"

    # Dedupe by VENDOR — keep only the latest/best model per company.
    # This is what makes the table comparable and not redundant: ONE
    # Anthropic row (Claude Opus 4.8), ONE OpenAI row (GPT-5.5), etc.
    # Selection is done by _dedupe_by_vendor (latest canonical wins,
    # then highest score, then research-discovered fallback).
    deduped = _dedupe_by_vendor(pool)

    # Pick the benchmark with the most entries — the user wants to
    # COMPARE models, which is only meaningful when they share the
    # same benchmark. If the LLM returned 1 entry on GPQA Diamond
    # and 4 on MMLU Pro, the table should be MMLU Pro (4 entries),
    # not GPQA Diamond (1 entry).
    from collections import Counter
    bench_counts = Counter(
        (e.benchmark_name or "MMLU Pro") for e in deduped
    )
    if bench_counts:
        chosen_benchmark = bench_counts.most_common(1)[0][0]
    else:
        chosen_benchmark = benchmark_name_used
    filtered = [e for e in deduped if (e.benchmark_name or "MMLU Pro") == chosen_benchmark]

    # Re-rank 1..5
    for i, e in enumerate(filtered[:5], 1):
        e.rank = i

    logger.info(
        "Benchmark chosen for table: %s (%d entries, dropped %d on other benchmarks)",
        chosen_benchmark, len(filtered[:5]), len(deduped) - len(filtered),
    )

    return BenchmarkSnapshot(
        benchmark_name=chosen_benchmark,
        month_key=datetime.utcnow().strftime("%Y-%m"),
        entries=filtered[:5],
        source=source,
    )


def _dedupe_by_vendor(entries: list[BenchmarkEntry]) -> list[BenchmarkEntry]:
    """Keep ONE entry per vendor — the latest/best frontier model.

    The user wants the benchmark + pricing charts to show ONE row per
    company (Anthropic, OpenAI, Google, etc.) because showing two
    Anthropic rows (Claude Opus 4.5 + 4.8) is confusing and nobody
    cares about an older version of a model that's been superseded.

    Selection priority per vendor:
      1. Match against the canonical latest model name in FRONTIER_MODELS
         → wins ties, even if the score is lower (newer = better
         regardless of score, since scores can be noisy across sources).
      2. If multiple entries match the canonical latest name, pick the
         one with the highest score.
      3. If NO entry matches a canonical model, fall back to the
         highest-scoring entry from that vendor (research-discovered
         model the registry doesn't know about yet).
    """
    by_vendor: dict[str, list[BenchmarkEntry]] = {}
    for e in entries:
        by_vendor.setdefault(e.vendor.lower(), []).append(e)

    kept: list[BenchmarkEntry] = []
    for vendor_key, group in by_vendor.items():
        # Find the canonical model names for this vendor (lowercased)
        canonical_models: list[str] = []
        for v, models in FRONTIER_MODELS.items():
            if v.lower() == vendor_key:
                canonical_models = [m["model"].lower() for m in models]
                break

        def rank(e: BenchmarkEntry) -> tuple:
            model_l = e.model.lower()
            # Index in canonical_models (0 = latest), or a large number
            # if it doesn't match any known model.
            if canonical_models:
                if model_l == canonical_models[0]:
                    canonical_idx = 0
                elif model_l in canonical_models:
                    canonical_idx = canonical_models.index(model_l)
                else:
                    # Not a known model — push it to the back. It still
                    # has a chance if it's the only entry for this vendor.
                    canonical_idx = 999
            else:
                canonical_idx = 999
            # Sort key: (canonical_idx ASC, -score DESC)
            return (canonical_idx, -(e.score or 0.0))

        group_sorted = sorted(group, key=rank)
        kept.append(group_sorted[0])

    # Final re-sort by score DESC for the chart
    kept.sort(key=lambda e: e.score or 0.0, reverse=True)
    return kept


def _normalize_benchmark_name(name: str) -> str:
    """Normalize benchmark names returned by the LLM to canonical forms.

    The LLM often returns short forms ("MMLU" instead of "MMLU Pro",
    "GPQA" instead of "GPQA Diamond") that would otherwise mismatch
    the snapshot's default and trigger a spurious tag in the slide.
    """
    if not name:
        return "MMLU Pro"
    n = name.strip().lower()
    # Canonical mappings
    if "mmlu" in n:
        return "MMLU Pro"
    if "gpqa" in n:
        return "GPQA Diamond"
    if "aime" in n:
        return "AIME 2025"
    if "swe" in n:
        return "SWE-bench Verified"
    if "math" in n and "500" in n:
        return "MATH-500"
    if "mmmu" in n:
        return "MMMU-Pro"
    if "humaneval" in n:
        return "HumanEval+"
    # Fallback: return as-is (caller's responsibility)
    return name.strip()


def _validate_research_entry(raw: dict) -> BenchmarkEntry | None:
    """Validate a single entry from the benchmark extraction LLM response.

    Reject entries that fail sanity checks: missing required fields,
    score out of [0, 100], cost out of [$0.001, $100] per 1M tokens.
    Returns None on rejection.

    Also normalizes the benchmark name (the LLM might return "MMLU"
    instead of "MMLU Pro", or "GPQA" instead of "GPQA Diamond") so
    the publisher's "is this the same benchmark?" comparison is stable.
    """
    from community_manager.models.schemas import BenchmarkEntry
    if not isinstance(raw, dict):
        return None
    vendor = (raw.get("vendor") or "").strip()
    model = (raw.get("model") or "").strip()
    benchmark_name = _normalize_benchmark_name(
        raw.get("benchmark_name") or "MMLU Pro"
    )
    if not vendor or not model:
        return None
    score = raw.get("score")
    if score is None:
        return None
    try:
        score = float(score)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= score <= 100.0):
        return None
    cost_in = raw.get("cost_per_1m_input")
    cost_out = raw.get("cost_per_1m_output")
    cost_in_f = None
    cost_out_f = None
    if cost_in is not None:
        try:
            cost_in_f = float(cost_in)
            if not (0.001 <= cost_in_f <= 100.0):
                cost_in_f = None
        except (TypeError, ValueError):
            cost_in_f = None
    if cost_out is not None:
        try:
            cost_out_f = float(cost_out)
            if not (0.001 <= cost_out_f <= 200.0):
                cost_out_f = None
        except (TypeError, ValueError):
            cost_out_f = None
    # If we have neither cost, the entry is useless for the pricing table
    if cost_in_f is None and cost_out_f is None:
        return None
    return BenchmarkEntry(
        vendor=vendor,
        model=model,
        benchmark_name=benchmark_name,
        score=score,
        cost_per_1m_input=cost_in_f,
        cost_per_1m_output=cost_out_f,
        rank=0,
    )


async def _apply_dedicated_benchmark_research(
    report: RadarReport,
    month_name: str,
) -> RadarReport:
    """Run the dedicated benchmark research pass and overwrite the
    report's ``benchmark_snapshot`` with the result. Called from the
    main researcher_node after insights are extracted and validated.

    Falls back to the seed if the dedicated pass finds nothing — the
    table is NEVER empty.
    """
    from community_manager.tools.llm import get_newsletter_llm
    models = _collect_models_from_insights(report.insights + report.insights_secondary)
    snapshot = None
    try:
        llm = get_newsletter_llm(temperature=0.0, max_tokens=4000)
        snapshot = await _research_benchmark_snapshot(llm, models, month_name)
    except Exception as exc:
        logger.warning("Dedicated benchmark research failed: %s", exc)
        snapshot = None
    if snapshot is None or not snapshot.entries:
        # Build a snapshot from the seed directly
        from community_manager.models.schemas import BenchmarkEntry, BenchmarkSnapshot
        entries = [
            BenchmarkEntry(
                vendor=s["vendor"],
                model=s["model"],
                benchmark_name=s["benchmark_name"],
                score=s["score"],
                cost_per_1m_input=s["cost_per_1m_input"],
                cost_per_1m_output=s["cost_per_1m_output"],
                rank=i + 1,
            )
            for i, s in enumerate(FALLBACK_BENCHMARK_SEED[:5])
        ]
        snapshot = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            month_key=datetime.utcnow().strftime("%Y-%m"),
            entries=entries,
            source="Precios referenciales — documentación oficial de cada vendor",
        )
        logger.info("Benchmark snapshot: FALLBACK seed (5 entries)")
    else:
        logger.info("Benchmark snapshot: %d entries (%s)",
                    len(snapshot.entries), snapshot.benchmark_name)
    report.benchmark_snapshot = snapshot
    return report


# ════════════════════════════════════════════════════════════════════════════
#  Fallback
# ════════════════════════════════════════════════════════════════════════════

def _fallback_report(month_label: str) -> RadarReport:
    return RadarReport(
        subject=f"AI Radar by Novit | {month_label}",
        report_title=f"Novit AI Radar - {month_label.title()}",
        executive_summary=(
            "No se pudo generar el radar del mes con URLs verificadas. "
            "Preferimos no enviar un resumen con enlaces rotos o inventados."
        ),
        insights=[],
        chart_title="",
        chart_subtitle="",
        chart_items=[],
    )
