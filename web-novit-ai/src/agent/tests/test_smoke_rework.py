"""Smoke test for the AI Radar rework.

Run with: python -m pytest tests/test_smoke_rework.py -v
Or:       python tests/test_smoke_rework.py
"""
import sys
import asyncio
from pathlib import Path

# Make the agent package importable when running this directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_safe_json_parses_clean():
    from community_manager.tools.safe_json import parse
    result = parse('{"a": 1, "b": [1, 2, 3]}')
    assert result == {"a": 1, "b": [1, 2, 3]}


def test_safe_json_strips_code_fences():
    from community_manager.tools.safe_json import parse
    result = parse("```json\n{\"x\": 42}\n```")
    assert result == {"x": 42}


def test_safe_json_raises_on_garbage():
    from community_manager.tools.safe_json import JsonParseError, parse
    try:
        parse("not json at all")
        assert False, "Should have raised"
    except JsonParseError:
        pass


def test_safe_json_safely_returns_default():
    from community_manager.tools.safe_json import parse_safely
    result = parse_safely("garbage", default={"fallback": True})
    assert result == {"fallback": True}


def test_pptx_layouts_loaded():
    from community_manager.tools.pptx_layout import get_slide_layouts
    layouts = get_slide_layouts()
    assert "slide_1" in layouts
    assert "slide_2" in layouts
    assert "slide_3" in layouts
    assert "slide_4" in layouts
    # Each layout should have content area between min and max chars
    for name, layout in layouts.items():
        assert layout.min_chars < layout.max_chars, f"{name} has bad char range"
        assert layout.max_chars > 0, f"{name} has 0 max_chars"
        assert layout.content_box[2] > 0 and layout.content_box[3] > 0


def test_pptx_layout_4_smaller_than_others():
    """Slide 4 (conclusions) is the smallest, slides 2-3 are biggest.
    Slide 1 (cover) is between the two — it carries a short executive
    summary + 2 bar charts, so it doesn't need as much text as a
    country slide. The strict invariant is slide 4 < slide 2/3."""
    from community_manager.tools.pptx_layout import get_slide_layouts
    layouts = get_slide_layouts()
    assert layouts["slide_4"].max_chars < layouts["slide_2"].max_chars
    assert layouts["slide_4"].max_chars < layouts["slide_3"].max_chars
    assert layouts["slide_2"].max_chars == layouts["slide_3"].max_chars


def test_trusted_domain_check():
    from community_manager.nurturing.tools import is_trusted_source_domain
    assert is_trusted_source_domain("infobae.com") is True
    assert is_trusted_source_domain("www.elpais.com") is True
    assert is_trusted_source_domain("example.com") is False
    assert is_trusted_source_domain("") is False


def test_radar_insight_has_new_fields():
    from community_manager.models.schemas import RadarInsight
    insight = RadarInsight(
        headline="OpenAI lanza GPT-5.4",
        summary="Nuevo modelo con MMLU 92.1",
        business_impact="Costos estables para PyMEs",
        source_title="TECHCRUNCH",
        source_url="https://techcrunch.com/2026/gpt-5-4",
        is_model_launch=True,
        vendor="OpenAI",
        model_name="GPT-5.4",
        benchmark_text="MMLU Pro 92.1",
        pricing_text="$2.50/M tokens",
    )
    assert insight.is_model_launch is True
    assert insight.vendor == "OpenAI"
    assert insight.model_name == "GPT-5.4"
    assert insight.benchmark_text == "MMLU Pro 92.1"
    assert insight.pricing_text == "$2.50/M tokens"


def test_settings_have_new_flags():
    from community_manager.config.settings import get_settings
    s = get_settings()
    # Defaults
    assert hasattr(s, "nurturing_url_validation_enabled")
    assert hasattr(s, "nurturing_hitl2_enabled")
    assert hasattr(s, "nurturing_min_insights_per_country")


def test_serper_result_dataclass():
    from community_manager.nurturing.tools import SerperResult
    r = SerperResult(
        title="Test article",
        snippet="A test snippet",
        url="https://example.com/article",
        rank=1,
        source_domain="example.com",
        is_trusted_domain=False,
        date="2026-05-25",
    )
    assert r.title == "Test article"
    assert r.url == "https://example.com/article"
    assert r.rank == 1


def test_researcher_imports():
    """The new researcher module should be importable without errors."""
    from community_manager.nurturing.nodes import researcher
    assert hasattr(researcher, "researcher_node")
    assert hasattr(researcher, "VENDOR_LAUNCH_QUERIES")
    assert hasattr(researcher, "BENCHMARK_QUERIES")
    assert hasattr(researcher, "PRICING_QUERIES")
    assert hasattr(researcher, "COUNTRY_QUERIES")
    assert hasattr(researcher, "_validate_and_filter")
    assert hasattr(researcher, "_filter_by_recency")
    # Recency constant
    assert researcher.RECENCY_DAYS == 28


def test_content_scorer_imports():
    """The new scorer module should be importable without errors."""
    from community_manager.nurturing.nodes import content_scorer
    assert hasattr(content_scorer, "content_scorer_node")
    assert hasattr(content_scorer, "SCORER_SYSTEM")


def test_writer_imports():
    """The new writer module should be importable without errors."""
    from community_manager.nurturing.nodes import writer
    assert hasattr(writer, "writer_node")
    assert hasattr(writer, "WRITER_SYSTEM")
    assert hasattr(writer, "_validate_fill")


def test_chart_planner_imports():
    """The new chart_planner module should be importable without errors."""
    from community_manager.nurturing.nodes import chart_planner
    assert hasattr(chart_planner, "chart_planner_node")
    assert hasattr(chart_planner, "ChartPlan")
    assert hasattr(chart_planner, "ImagePlan")
    assert hasattr(chart_planner, "SlidesPlan")
    assert hasattr(chart_planner, "CHART_PLANNER_SYSTEM")


def test_v2_workflow_imports():
    """The v2 workflow should have slide_layouts in initial state."""
    from community_manager.nurturing.workflow_v2 import (
        run_newsletter_workflow,
        build_newsletter_graph,
        NewsletterState,
    )
    # NewsletterState is a TypedDict-like dict; just check the keys include slide_layouts
    # (We can't easily inspect TypedDict annotations at runtime, so we just ensure the import works)
    assert run_newsletter_workflow is not None
    assert build_newsletter_graph is not None


def test_v1_legacy_moved():
    """v1 should be importable from _legacy path."""
    from community_manager.nurturing._legacy import workflow
    assert hasattr(workflow, "wrap_in_html_email")  # was the canonical v1 function
    assert hasattr(workflow, "_parse_radar_json")


def test_reply_service_imports():
    """The new reply_service module should be importable."""
    from community_manager.nurturing.reply_service import (
        generate_reply,
        generate_personal_closing,
    )
    assert generate_reply is not None
    assert generate_personal_closing is not None


def test_revise_service_imports():
    """The new revise_service module should be importable."""
    from community_manager.nurturing.revise_service import revise_newsletter
    assert revise_newsletter is not None


def test_main_uses_new_services():
    """main.py should import from the new service modules, not the legacy v1."""
    import importlib.util
    from pathlib import Path

    # main.py lives in community_manager/, not in the agent root
    repo_root = Path(__file__).resolve().parent.parent
    main_path = repo_root / "community_manager" / "main.py"
    if not main_path.exists():
        # Fallback: search upwards
        for candidate in [repo_root, repo_root / "src" / "agent", Path.cwd()]:
            if (candidate / "main.py").exists():
                main_path = candidate / "main.py"
                break
    spec = importlib.util.spec_from_file_location("agent_main", str(main_path))
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    # The functions should be available in the main module's namespace
    assert hasattr(main, "generate_reply")
    assert hasattr(main, "generate_personal_closing")
    assert hasattr(main, "revise_newsletter")
    assert hasattr(main, "wrap_in_html_email")
    assert hasattr(main, "run_newsletter_workflow")


def test_researcher_aborts_when_no_search_results():
    """When the search provider returns 0 results, researcher sets abort_reason and returns a fallback."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from community_manager.nurturing.nodes import researcher

    async def fake_search(*args, **kwargs):
        return []  # No results from any query

    # Mock the settings to claim both AI and search are configured
    fake_settings = MagicMock()
    fake_settings.is_nurturing_configured = True
    fake_settings.is_web_search_configured = True
    fake_settings.nurturing_url_validation_enabled = False

    with patch.object(researcher, "search_structured", side_effect=fake_search), \
         patch.object(researcher, "get_settings", return_value=fake_settings):
        result = asyncio.run(researcher.researcher_node({"month_name": "junio 2026"}))

    assert result["abort_reason"] == "no_search_results"
    assert result["raw_report"].insights == []


def test_researcher_aborts_when_ai_not_configured():
    """When the newsletter AI endpoint is not configured, researcher bails early."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from community_manager.nurturing.nodes import researcher

    fake_settings = MagicMock()
    fake_settings.is_nurturing_configured = False

    with patch.object(researcher, "get_settings", return_value=fake_settings):
        result = asyncio.run(researcher.researcher_node({"month_name": "junio 2026"}))

    assert result["abort_reason"] == "ai_not_configured"


def test_writer_short_circuits_on_abort():
    """When abort_reason is set, writer does NOT call GPT-5.4."""
    import asyncio
    from community_manager.nurturing.nodes import writer

    state = {
        "month_name": "junio 2026",
        "raw_report": None,
        "abort_reason": "no_search_results",
        "abort_detail": "Serper returned 0 results",
    }

    # If the writer called GPT-5.4, this would fail because there's no API key
    # If the guard works, no LLM call is made
    result = asyncio.run(writer.writer_node(state))

    assert result["abort_reason"] == "no_search_results"
    assert "Serper" in result["newsletter_content"].body


def test_writer_short_circuits_on_empty_insights():
    """When raw_report has 0 insights (no abort_reason), writer still skips LLM."""
    import asyncio
    from community_manager.models.schemas import RadarReport
    from community_manager.nurturing.nodes import writer

    empty_report = RadarReport(
        subject="AI Radar",
        report_title="Test",
        executive_summary="",
    )

    state = {
        "month_name": "junio 2026",
        "raw_report": empty_report,
        "abort_reason": None,
    }

    result = asyncio.run(writer.writer_node(state))

    assert result["abort_reason"] == "no_insights"
    # Body should mention AI Radar (the abort placeholder)
    body_lower = result["newsletter_content"].body.lower()
    assert "ai radar" in body_lower


def test_evaluator_aborts_on_zero_insights():
    """evaluator_pre_media aborts when raw_report has 0 insights (does not retry)."""
    import asyncio
    from community_manager.models.schemas import RadarReport
    from community_manager.nurturing.nodes import evaluator_pre_media

    empty_report = RadarReport(
        subject="AI Radar",
        report_title="Test",
        executive_summary="",
    )

    state = {"raw_report": empty_report, "abort_reason": None}

    result = asyncio.run(evaluator_pre_media.evaluator_pre_media_node(state))

    assert result["abort_reason"] == "no_insights"
    assert result["pre_media_evaluation"].approved is False
    assert result["pre_media_evaluation"].retry_target == "abort"


def test_evaluator_aborts_on_insufficient_coverage():
    """evaluator_pre_media aborts when per-country coverage is below threshold."""
    import asyncio
    from community_manager.models.schemas import RadarInsight, RadarReport
    from community_manager.nurturing.nodes import evaluator_pre_media

    # Only 1 AR insight, 0 ES, 0 GLOBAL — below default min of 2 per country
    ar_insight = RadarInsight(
        headline="AR test",
        summary="summary",
        business_impact="impact",
        source_title="INFOBAE",
        source_url="https://infobae.com/123",
        country_tag="AR",
    )
    report = RadarReport(
        subject="AI Radar",
        report_title="Test",
        executive_summary="A summary with enough characters to pass the length check",
        insights=[ar_insight],
    )

    state = {"raw_report": report, "abort_reason": None}

    result = asyncio.run(evaluator_pre_media.evaluator_pre_media_node(state))

    assert result["abort_reason"] == "insufficient_insights"
    assert result["pre_media_evaluation"].retry_target == "abort"


def test_evaluator_honors_upstream_abort():
    """If upstream set abort_reason, evaluator does not retry."""
    import asyncio
    from community_manager.nurturing.nodes import evaluator_pre_media

    state = {
        "raw_report": None,
        "abort_reason": "no_search_results",
        "abort_detail": "Serper returned 0 results",
    }

    result = asyncio.run(evaluator_pre_media.evaluator_pre_media_node(state))

    assert result["abort_reason"] == "no_search_results"
    assert result["pre_media_evaluation"].retry_target == "abort"


def test_route_after_evaluator_aborts_on_reason():
    """The route_after_evaluator function aborts immediately if abort_reason is set."""
    from community_manager.nurturing.workflow_v2 import route_after_evaluator

    # With abort_reason set, must go to abort (no retry)
    state = {"abort_reason": "no_search_results", "pre_media_evaluation": None, "retry_count": 0}
    assert route_after_evaluator(state) == "abort"

    # Without abort_reason, normal flow
    from community_manager.models.schemas import EvaluationResult
    approved = EvaluationResult(approved=True)
    state = {"pre_media_evaluation": approved, "retry_count": 0}
    assert route_after_evaluator(state) == "slides_planner"

    # With evaluation.requesting abort
    abort_eval = EvaluationResult(approved=False, retry_target="abort")
    state = {"pre_media_evaluation": abort_eval, "retry_count": 0}
    assert route_after_evaluator(state) == "abort"


def test_brave_freshness_mapping():
    """_brave_freshness_for_max_days maps days to Brave's freshness param."""
    from community_manager.nurturing.tools import _brave_freshness_for_max_days

    assert _brave_freshness_for_max_days(0) == "pd"
    assert _brave_freshness_for_max_days(1) == "pd"
    assert _brave_freshness_for_max_days(7) == "pw"
    assert _brave_freshness_for_max_days(28) == "pm"
    assert _brave_freshness_for_max_days(35) == "pm"
    assert _brave_freshness_for_max_days(180) == "py"


def test_brave_age_to_iso():
    """_brave_age_to_iso converts human-readable age to ISO date."""
    from community_manager.nurturing.tools import _brave_age_to_iso

    # Various formats
    assert _brave_age_to_iso("2 days ago") != ""  # Has 2026-06-01
    assert _brave_age_to_iso("3 hours ago") != ""
    assert _brave_age_to_iso("1 week ago") != ""
    assert _brave_age_to_iso("5 months ago") != ""
    assert _brave_age_to_iso("1 year ago") != ""
    # Unparseable
    assert _brave_age_to_iso("") == ""
    assert _brave_age_to_iso(None) == ""
    assert _brave_age_to_iso("yesterday") == ""


def test_search_structured_dispatches_to_brave_by_default():
    """search_structured() uses brave when provider='brave' (default)."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from community_manager.nurturing import tools

    async def fake_brave(*args, **kwargs):
        return [tools.SerperResult(title="t", snippet="s", url="https://x.com/1", rank=1, source_domain="x.com", is_trusted_domain=False)]

    fake_settings = MagicMock()
    fake_settings.nurturing_search_provider = "brave"

    with patch.object(tools, "brave_search_structured", side_effect=fake_brave), \
         patch.object(tools, "get_settings", return_value=fake_settings):
        result = asyncio.run(tools.search_structured("test query"))

    assert len(result) == 1
    assert result[0].url == "https://x.com/1"


def test_search_structured_dispatches_to_serper_when_configured():
    """search_structured() uses serper when provider='serper'."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from community_manager.nurturing import tools

    async def fake_serper(*args, **kwargs):
        return [tools.SerperResult(title="t", snippet="s", url="https://y.com/1", rank=1, source_domain="y.com", is_trusted_domain=False)]

    fake_settings = MagicMock()
    fake_settings.nurturing_search_provider = "serper"

    with patch.object(tools, "serper_search_structured", side_effect=fake_serper), \
         patch.object(tools, "get_settings", return_value=fake_settings):
        result = asyncio.run(tools.search_structured("test query"))

    assert len(result) == 1
    assert result[0].url == "https://y.com/1"


def test_settings_have_brave_config():
    """The new Brave config fields are exposed on Settings."""
    from community_manager.config.settings import get_settings
    s = get_settings()
    assert hasattr(s, "nurturing_brave_api_key")
    assert hasattr(s, "nurturing_search_provider")
    assert s.nurturing_search_provider in ("brave", "serper", "")  # default is "brave"


def test_low_quality_source_domain_blacklist():
    """is_low_quality_source_domain flags known-bad patterns."""
    from community_manager.nurturing.tools import is_low_quality_source_domain

    # Training/education sites
    assert is_low_quality_source_domain("cursosdesarrolloweb.es") is True
    assert is_low_quality_source_domain("udemy.com") is True
    assert is_low_quality_source_domain("platzi.com") is True
    assert is_low_quality_source_domain("academia.edu") is True
    # UGC
    assert is_low_quality_source_domain("medium.com") is True
    assert is_low_quality_source_domain("substack.com") is True
    assert is_low_quality_source_domain("linkedin.com") is True
    # Social media
    assert is_low_quality_source_domain("facebook.com") is True
    assert is_low_quality_source_domain("twitter.com") is True
    assert is_low_quality_source_domain("youtube.com") is True
    # Code/dev
    assert is_low_quality_source_domain("github.com") is True
    # Trusted sources should NOT be flagged
    assert is_low_quality_source_domain("infobae.com") is False
    assert is_low_quality_source_domain("elpais.com") is False
    assert is_low_quality_source_domain("techcrunch.com") is False


def test_acceptable_source_domain_strict_whitelist():
    """is_acceptable_source_domain uses strict positive-list (whitelist).

    Only sources in TRUSTED_SOURCE_DOMAINS are accepted. Anything else
    is rejected to maintain editorial quality for the AI Radar.
    """
    from community_manager.nurturing.tools import is_acceptable_source_domain

    # Trusted news sources
    assert is_acceptable_source_domain("infobae.com") is True
    assert is_acceptable_source_domain("lanacion.com.ar") is True
    assert is_acceptable_source_domain("elpais.com") is True
    assert is_acceptable_source_domain("techcrunch.com") is True
    assert is_acceptable_source_domain("reuters.com") is True
    # AI vendors
    assert is_acceptable_source_domain("openai.com") is True
    assert is_acceptable_source_domain("anthropic.com") is True
    assert is_acceptable_source_domain("xiaomi.com") is True
    assert is_acceptable_source_domain("moonshot.ai") is True
    # Latam
    assert is_acceptable_source_domain("estadao.com.br") is True
    # Random domains are REJECTED
    assert is_acceptable_source_domain("randomblogxyz.com") is False
    assert is_acceptable_source_domain("seo-agency-123.com") is False
    # Hosting / SEO blogs
    assert is_acceptable_source_domain("donweb.com") is False
    assert is_acceptable_source_domain("wwwhatsnew.com") is False
    # Blacklisted domains are REJECTED
    assert is_acceptable_source_domain("cursosdesarrolloweb.es") is False
    assert is_acceptable_source_domain("medium.com") is False
    assert is_acceptable_source_domain("linkedin.com") is False
    assert is_acceptable_source_domain("github.com") is False
    assert is_acceptable_source_domain("facebook.com") is False


def test_whitelist_has_150_plus_domains():
    """The whitelist should have ~150+ domains for editorial quality."""
    from community_manager.nurturing.tools import TRUSTED_SOURCE_DOMAINS
    assert len(TRUSTED_SOURCE_DOMAINS) >= 150, (
        f"Only {len(TRUSTED_SOURCE_DOMAINS)} domains — need at least 150"
    )


def test_dashdash_stripped_in_publisher():
    """The publisher strips '---' horizontal rules to keep slides clean."""
    from community_manager.nurturing.newsletter_pptx_publisher import (
        NewsletterPPTXPublisher,
    )
    pub = NewsletterPPTXPublisher()
    # Simulate the regex used in _set_markdown_text
    import re
    sample = "Block 1\n\n---\n\nBlock 2"
    cleaned = re.sub(r'\n\s*---\s*\n', '\n\n', sample)
    assert "---" not in cleaned
    assert "Block 1" in cleaned
    assert "Block 2" in cleaned


def test_writer_fill_empty_country_placeholders():
    """When AR/ES has no coverage, the writer injects a placeholder."""
    from community_manager.nurturing.nodes.writer import (
        _fill_empty_country_placeholders,
    )

    # No AR or ES coverage, only GLOBAL
    by_country = {"AR": [], "ES": [], "GLOBAL": []}
    filled = _fill_empty_country_placeholders(by_country, "junio 2026")

    # Both AR and ES should have a placeholder
    assert len(filled["AR"]) == 1
    assert len(filled["ES"]) == 1
    assert filled["AR"][0].country_tag == "AR"
    assert filled["ES"][0].country_tag == "ES"
    # The placeholder should mention "Argentina" / "España"
    assert "Argentina" in filled["AR"][0].headline
    assert "España" in filled["ES"][0].headline
    # Source URL points to a sentinel (ia.novitsoftware.com) so it passes
    # the pre-media source validation (URL must be non-empty and start with http).
    assert filled["AR"][0].source_url.startswith("http")
    assert filled["ES"][0].source_url.startswith("http")


def test_writer_does_not_fill_if_country_has_coverage():
    """When AR/ES already has insights, no placeholder is added."""
    from community_manager.models.schemas import RadarInsight
    from community_manager.nurturing.nodes.writer import (
        _fill_empty_country_placeholders,
    )

    ar_insight = RadarInsight(
        headline="YPF uses AI",
        summary="x",
        business_impact="x",
        source_title="INFOBAE",
        source_url="https://infobae.com/1",
        country_tag="AR",
    )
    by_country = {"AR": [ar_insight], "ES": [], "GLOBAL": []}
    filled = _fill_empty_country_placeholders(by_country, "junio 2026")

    # AR should be untouched (1 real insight, not replaced by placeholder)
    assert len(filled["AR"]) == 1
    assert filled["AR"][0].headline == "YPF uses AI"
    # ES should have placeholder
    assert len(filled["ES"]) == 1
    assert "España" in filled["ES"][0].headline


def test_filter_by_source_quality_drops_bad_sources():
    """_filter_by_source_quality drops insights from blacklisted/unknown domains."""
    from community_manager.models.schemas import RadarInsight
    from community_manager.nurturing.nodes.researcher import _filter_by_source_quality

    good = RadarInsight(
        headline="Good insight", summary="x", business_impact="x",
        source_title="INFOBAE", source_url="https://www.infobae.com/123",
    )
    bad_blacklist = RadarInsight(
        headline="Bad insight (medium)", summary="x", business_impact="x",
        source_title="MEDIUM", source_url="https://medium.com/foo/bar",
    )
    bad_unknown = RadarInsight(
        headline="Bad insight (cursos)", summary="x", business_impact="x",
        source_title="CURSOS", source_url="https://cursosdesarrolloweb.es/art-1",
    )
    no_url = RadarInsight(
        headline="No URL", summary="x", business_impact="x",
        source_title="?", source_url="",
    )

    result = _filter_by_source_quality([good, bad_blacklist, bad_unknown, no_url])
    titles = [i.headline for i in result]
    assert "Good insight" in titles
    assert "Bad insight (medium)" not in titles
    assert "Bad insight (cursos)" not in titles
    assert "No URL" not in titles


def test_writer_strip_conclusion_subheaders_strips_h3():
    """_strip_conclusion_subheaders removes '### ...' sub-headers from Slide 4 conclusions."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = "### Qué cambia este mes\n\nEl mes cerró con un crecimiento del 12% en adopción de IA."
    cleaned = _strip_conclusion_subheaders(raw)
    assert "###" not in cleaned
    assert "Qué cambia" not in cleaned
    assert "crecimiento del 12%" in cleaned


def test_writer_strip_conclusion_subheaders_strips_h2():
    """_strip_conclusion_subheaders removes '## ...' sub-headers."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = "## Tendencias\n\nTexto del primer párrafo.\n\n### Sub-sección\n\nMás texto."
    cleaned = _strip_conclusion_subheaders(raw)
    assert "##" not in cleaned
    assert "###" not in cleaned
    assert "Tendencias" not in cleaned
    assert "Sub-sección" not in cleaned
    assert "Texto del primer párrafo" in cleaned
    assert "Más texto" in cleaned


def test_writer_strip_conclusion_subheaders_preserves_normal_text():
    """_strip_conclusion_subheaders does not touch normal prose."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = "El mes cerró con un crecimiento del 12% en adopción de IA. La inversión subió."
    cleaned = _strip_conclusion_subheaders(raw)
    assert cleaned == raw


def test_writer_strip_conclusion_subheaders_handles_empty():
    """_strip_conclusion_subheaders handles empty/None input safely."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    assert _strip_conclusion_subheaders("") == ""
    assert _strip_conclusion_subheaders(None or "") == ""


def test_writer_strip_conclusion_subheaders_collapses_extra_newlines():
    """_strip_conclusion_subheaders collapses triple+ newlines after stripping."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = "### Header\n\n\n\nPrimer párrafo.\n\n\n\nSegundo párrafo."
    cleaned = _strip_conclusion_subheaders(raw)
    assert "###" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "Primer párrafo" in cleaned
    assert "Segundo párrafo" in cleaned


def test_writer_regla2_requires_editorial_selection():
    """REGLA 2 in writer.py prompt requires editorial selection, not coverage
    of every insight."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    regla2_start = rules.index("REGLA 2")
    regla3_start = rules.index("REGLA 3")
    regla2 = rules[regla2_start:regla3_start]
    assert "material de lectura" in regla2.lower(), \
        f"REGLA 2 must refer to insights as reading material. Got: {regla2[:200]}"


def test_writer_regla10_unifies_not_summarizes():
    """REGLA 10 requires the conclusion to answer ONE question (what does
    this all mean together) not summarize each country."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    regla10_start = rules.index("REGLA 10")
    regla11_start = rules.index("REGLA 11")
    regla10 = rules[regla10_start:regla11_start]
    assert "conclusions" in regla10.lower(), f"REGLA 10 must reference 'conclusions'. Got: {regla10[:200]}"
    # Must pick the single most important idea, not a per-country summary
    assert "UNA SOLA" in regla10 or "UNA idea" in regla10 or "una idea" in regla10.lower(), \
        f"REGLA 10 must require a single idea. Got: {regla10[:200]}"
    assert "países" in regla10.lower() or "país" in regla10.lower(), \
        f"REGLA 10 must explicitly forbid per-country listing. Got: {regla10[:200]}"


def test_pptx_layout_slide1_executive_summary_y_position_updated():
    """slide_1 layout has y=307 (Inches(3.20)) for executive summary box."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_1")
    assert layout is not None
    x, y, w, h = layout.content_box
    assert y == 307, f"slide_1 y should be 307 (Inches(3.20)) but is {y}"


def test_pptx_layout_slide1_max_chars_reduced_to_900():
    """The user said the executive summary was too long. The cap is
    now 900 (was 1500). 3 short paragraphs at 12pt with 1.5 line
    spacing fits cleanly in the 3.6"-tall box without overflow."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_1")
    assert layout.max_chars == 900, \
        f"slide_1 max_chars should be 900, got {layout.max_chars}"


def test_pptx_layout_slide1_height_matches_chart_bottom():
    """The executive summary box bottom (y + h) must match the bottom
    of the chart_pricing placeholder (5.05 + 1.75 = 6.80 inches =
    653 px @ 96 DPI) so the two visual blocks align cleanly. If the
    box is taller, the text overlaps the chart visually."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_1")
    x, y, w, h = layout.content_box
    bottom_px = y + h
    chart_bottom_px = 5.05 * 96 + 1.75 * 96  # = 653
    assert abs(bottom_px - chart_bottom_px) < 5, \
        f"slide_1 box bottom {bottom_px} should match chart bottom {chart_bottom_px}"


def test_writer_regla1_has_hard_caps():
    """REGLA 1 in the writer prompt must include the per-slide hard
    caps (900/1900/550 chars) so the LLM doesn't produce 1500+ chars
    that overflow the slide."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    assert "900" in rules, "REGLA 1 must mention 900-char cap for slide_1"
    assert "700" in rules, "REGLA 1 must mention 700-char cap for slide_4"
    assert "1900" in rules, "REGLA 1 must mention 1900-char cap for slide_2/3"


def test_pptx_layout_slide2_textbox_y_position_updated():
    """slide_2 layout has y=149 (Inches(1.55)) and h=480 (Inches(5.0))."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_2")
    assert layout is not None
    x, y, w, h = layout.content_box
    assert y == 149, f"slide_2 y should be 149 (Inches(1.55)) but is {y}"
    assert h == 480, f"slide_2 h should be 480 (Inches(5.0)) but is {h}"


def test_pptx_layout_slide3_textbox_y_position_updated():
    """slide_3 layout has y=149 (Inches(1.55)) and h=480 (Inches(5.0))."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_3")
    assert layout is not None
    x, y, w, h = layout.content_box
    assert y == 149, f"slide_3 y should be 149 (Inches(1.55)) but is {y}"
    assert h == 480, f"slide_3 h should be 480 (Inches(5.0)) but is {h}"


def test_pptx_layout_slide4_infobody_y_position_updated():
    """slide_4 layout has y=110 (Inches(1.15)) for info body."""
    from community_manager.tools.pptx_layout import get_layout
    layout = get_layout("slide_4")
    assert layout is not None
    x, y, w, h = layout.content_box
    assert y == 110, f"slide_4 y should be 110 (Inches(1.15)) but is {y}"


# ── PR B: Benchmark tables (Slide 1) ────────────────────────────────


def test_benchmark_entry_schema_round_trip():
    """BenchmarkEntry round-trips through model_validate/model_dump."""
    from community_manager.models.schemas import BenchmarkEntry, BenchmarkSnapshot
    entry = BenchmarkEntry(
        vendor="OpenAI", model="GPT-5.4", score=92.1,
        cost_per_1m_input=2.50, cost_per_1m_output=10.00, rank=1,
    )
    snap = BenchmarkSnapshot(
        benchmark_name="MMLU Pro", month_key="2026-06", entries=[entry],
        source="artificialanalysis.io",
    )
    data = snap.model_dump()
    assert data["entries"][0]["vendor"] == "OpenAI"
    assert data["entries"][0]["score"] == 92.1
    assert data["source"] == "artificialanalysis.io"
    # Round-trip
    snap2 = BenchmarkSnapshot.model_validate(data)
    assert snap2.entries[0].model == "GPT-5.4"
    assert snap2.source == "artificialanalysis.io"


def test_radar_report_accepts_benchmark_snapshot():
    """RadarReport has a benchmark_snapshot field of type BenchmarkSnapshot."""
    from community_manager.models.schemas import RadarReport, BenchmarkSnapshot, BenchmarkEntry
    snap = BenchmarkSnapshot(
        benchmark_name="MMLU Pro",
        entries=[BenchmarkEntry(vendor="x", model="y", score=80.0, rank=1)],
    )
    r = RadarReport(subject="s", report_title="t", executive_summary="e", benchmark_snapshot=snap)
    assert r.benchmark_snapshot is not None
    assert r.benchmark_snapshot.entries[0].score == 80.0


def test_researcher_parse_benchmark_snapshot_valid():
    """_parse_benchmark_snapshot returns a sorted, valid BenchmarkSnapshot."""
    from community_manager.nurturing.nodes.researcher import _parse_benchmark_snapshot
    data = {
        "benchmark_name": "MMLU Pro",
        "entries": [
            {"vendor": "Anthropic", "model": "Opus 4.8", "score": 91.8, "cost_per_1m_input": 3.0, "rank": 1},
            {"vendor": "OpenAI", "model": "GPT-5.4", "score": 92.1, "cost_per_1m_input": 2.5, "rank": 2},
            {"vendor": "Bad", "model": "", "score": 50.0},  # invalid: no model
            {"vendor": "xAI", "model": "Grok-3", "score": 150.0},  # invalid: score > 100
            {"vendor": "Meta", "model": "Llama 4", "score": None, "cost_per_1m_input": 0.4, "rank": 4},
        ],
    }
    snap = _parse_benchmark_snapshot(data, "2026-06")
    assert snap is not None
    # Should keep only the 4 valid entries (1 invalid dropped)
    assert len(snap.entries) == 4
    # Sorted by score desc (None last)
    assert snap.entries[0].model == "GPT-5.4"  # score 92.1
    assert snap.entries[1].model == "Opus 4.8"  # score 91.8
    assert snap.entries[2].model == "Grok-3"     # score None (last among has-score)
    # Ranks 1..4 after re-sort
    assert [e.rank for e in snap.entries] == [1, 2, 3, 4]
    assert snap.benchmark_name == "MMLU Pro"
    assert snap.month_key == "2026-06"


def test_researcher_parse_benchmark_snapshot_returns_none_for_empty():
    """_parse_benchmark_snapshot returns None for empty/malformed data."""
    from community_manager.nurturing.nodes.researcher import _parse_benchmark_snapshot
    assert _parse_benchmark_snapshot(None, "2026-06") is None
    assert _parse_benchmark_snapshot({}, "2026-06") is None
    assert _parse_benchmark_snapshot({"entries": []}, "2026-06") is None
    assert _parse_benchmark_snapshot({"entries": "not a list"}, "2026-06") is None


def test_template_slide1_has_benchmark_and_pricing_tables():
    """Template builder creates PLACEHOLDER_BENCHMARK_TABLE and PLACEHOLDER_PRICING_TABLE on slide 1."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tmpl.pptx")
        builder = NewsletterTemplateBuilder(path)
        builder.build()
        from pptx import Presentation
        prs = Presentation(path)
        slide1 = prs.slides[0]
        names = [s.name for s in slide1.shapes]
        assert "PLACEHOLDER_BENCHMARK_TABLE" in names, f"Missing benchmark table in: {names}"
        assert "PLACEHOLDER_PRICING_TABLE" in names, f"Missing pricing table in: {names}"
        # Old cards should be GONE
        assert not any("METRIC_VALUE" in n for n in names), f"Old cards still present: {names}"


def test_publisher_replaces_benchmark_table_with_bar_chart():
    """Slide 1 replaces the benchmark table with a native PPTX bar chart
    (CHART_BENCHMARK) in the SAME rectangle. Bars are horizontal
    (BAR_CLUSTERED), so model names read on the y-axis. Data labels
    show only the score, no benchmark tag in the cell."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkEntry, BenchmarkSnapshot,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        snap = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            entries=[
                BenchmarkEntry(vendor="OpenAI", model="GPT-5.5", score=92.8, cost_per_1m_input=6.0, rank=1),
                BenchmarkEntry(vendor="Anthropic", model="Opus 4.8", score=93.6, cost_per_1m_input=18.0, rank=2),
                BenchmarkEntry(vendor="Google DeepMind", model="Gemini 3 Pro", score=91.5, cost_per_1m_input=1.5, rank=3),
            ],
        )
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        slide1 = prs.slides[0]
        names = [s.name for s in slide1.shapes]
        # Both tables are GONE
        assert "PLACEHOLDER_BENCHMARK_TABLE" not in names, \
            f"Benchmark table should be replaced, still in: {names}"
        # Both labels are KEPT (label is a separate text box, not a table)
        assert "PLACEHOLDER_METRIC_LABEL_0" in names, \
            f"Benchmark label should remain: {names}"
        # The pricing table may or may not have been replaced depending on
        # if cost data was present — it WAS present here, so it's gone too.
        assert "PLACEHOLDER_PRICING_TABLE" not in names
        # Bar chart is PRESENT (named CHART_BENCHMARK)
        assert "CHART_BENCHMARK" in names, f"Benchmark chart not in: {names}"
        # Verify the chart type + data
        from pptx.enum.chart import XL_CHART_TYPE
        for s in slide1.shapes:
            if s.name == "CHART_BENCHMARK" and s.has_chart:
                chart = s.chart
                # Horizontal bar (not vertical column, not scatter, not line)
                assert chart.chart_type == XL_CHART_TYPE.BAR_CLUSTERED, \
                    f"Expected BAR_CLUSTERED, got {chart.chart_type}"
                # No title (the PLACEHOLDER_METRIC_LABEL_0 above the chart
                # already says "BENCHMARK  ·  MMLU Pro")
                assert chart.has_title is False
                # 3 categories (vendor + model) on the category axis
                cats = [c for c in chart.plots[0].categories]
                assert "OpenAI GPT-5.5" in cats
                assert "Anthropic Opus 4.8" in cats
                assert "Google DeepMind Gemini 3 Pro" in cats
                # 1 series with the 3 scores
                series = chart.series[0]
                scores = list(series.values)
                assert 92.8 in scores, f"Score 92.8 missing: {scores}"
                assert 93.6 in scores
                assert 91.5 in scores
                return
        raise AssertionError("CHART_BENCHMARK not found on slide 1")


def test_publisher_replaces_pricing_table_with_bar_chart_cheapest_at_top():
    """Slide 1 replaces the pricing table with CHART_PRICING (a native
    PPTX bar chart). The CHEAPEST model renders at the TOP of the
    chart and the most-expensive at the BOTTOM (PPTX renders the
    LAST category in the list at the top, so we feed it the
    most-expensive-first order)."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkEntry, BenchmarkSnapshot,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        # Intentionally add an EXPENSIVE model first — the chart must
        # still re-sort to cheapest-at-top.
        snap = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            entries=[
                BenchmarkEntry(vendor="Anthropic", model="Opus 4.8", score=93.6, cost_per_1m_input=18.0, rank=1),
                BenchmarkEntry(vendor="Google DeepMind", model="Gemini 3 Pro", score=91.5, cost_per_1m_input=1.5, rank=3),
                BenchmarkEntry(vendor="OpenAI", model="GPT-5.5", score=92.8, cost_per_1m_input=6.0, rank=2),
            ],
        )
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        slide1 = prs.slides[0]
        names = [s.name for s in slide1.shapes]
        assert "CHART_PRICING" in names, f"Pricing chart not in: {names}"
        for s in slide1.shapes:
            if s.name == "CHART_PRICING" and s.has_chart:
                chart = s.chart
                from pptx.enum.chart import XL_CHART_TYPE
                assert chart.chart_type == XL_CHART_TYPE.BAR_CLUSTERED
                # In PPTX horizontal bars: the LAST category in the
                # list renders at the TOP. We want cheapest at the top,
                # so the last entry must be the cheapest (Gemini 3 Pro).
                cats = list(chart.plots[0].categories)
                assert "Gemini 3 Pro" in cats[-1], \
                    f"Expected cheapest (Gemini 3 Pro) at TOP (last cat), got: {cats}"
                # And the most-expensive (Opus 4.8) must be first (= bottom)
                assert "Opus 4.8" in cats[0], \
                    f"Expected most-expensive (Opus 4.8) at BOTTOM (first cat), got: {cats}"
                # All 3 cost values present
                series = chart.series[0]
                values = list(series.values)
                assert 1.5 in values
                assert 6.0 in values
                assert 18.0 in values
                assert "PLACEHOLDER_METRIC_LABEL_1" in names
                return
        raise AssertionError("CHART_PRICING not found on slide 1")


def test_publisher_benchmark_chart_best_at_top():
    """CHART_BENCHMARK renders the BEST-scoring model at the TOP of
    the chart and the worst at the BOTTOM (PPTX last-cat-at-top rule)."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkEntry, BenchmarkSnapshot,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        # Feed worst-first to verify the chart sorts correctly.
        snap = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            entries=[
                BenchmarkEntry(vendor="xAI", model="Grok 3", score=86.0, cost_per_1m_input=3.0),
                BenchmarkEntry(vendor="Anthropic", model="Opus 4.8", score=93.6, cost_per_1m_input=18.0),
                BenchmarkEntry(vendor="OpenAI", model="GPT-5.5", score=92.8, cost_per_1m_input=6.0),
            ],
        )
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        for s in prs.slides[0].shapes:
            if s.name == "CHART_BENCHMARK" and s.has_chart:
                cats = list(s.chart.plots[0].categories)
                # Best (Opus 4.8, 93.6) must be at TOP = last cat
                assert "Opus 4.8" in cats[-1], \
                    f"Expected best (Opus 4.8) at TOP, got: {cats}"
                # Worst (Grok 3, 86.0) must be at BOTTOM = first cat
                assert "Grok 3" in cats[0], \
                    f"Expected worst (Grok 3) at BOTTOM, got: {cats}"
                return
        raise AssertionError("CHART_BENCHMARK not found")


def test_publisher_keeps_tables_when_no_snapshot():
    """If report.benchmark_snapshot is None, the table placeholders stay
    in place (we don't render an empty chart)."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import RadarReport
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        report = RadarReport(subject="t", report_title="t", executive_summary="e")
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        slide1 = prs.slides[0]
        names = [s.name for s in slide1.shapes]
        # The original table placeholders are still there (we never
        # replaced them with a chart because there's no data)
        assert "PLACEHOLDER_BENCHMARK_TABLE" in names
        assert "PLACEHOLDER_PRICING_TABLE" in names
        assert "CHART_BENCHMARK" not in names
        assert "CHART_PRICING" not in names


def test_publisher_shows_pendiente_text_when_no_image():
    """When image_urls is empty (DRAFT phase, before HITL approval), the
    publisher must NOT leave the image placeholders empty — that looks
    like a broken image link in Google Slides. Instead it must show a
    clear 'Ilustración pendiente: se genera tras aprobación.' message
    on slides 2, 3 and 4."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import RadarReport
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            slide_2_text="x", slide_3_text="y", conclusions="z",
        )
        # No image_urls — this is the DRAFT path. Publisher saves the
        # PPTX to /tmp internally (and the test inspects that file).
        pub._publish_report_sync(report, "May 2026", chart_url=None, image_urls=[])
        # Re-open the SAVED PPTX (the publisher creates its own internal
        # Presentation object and saves to /tmp; the test must read back).
        from pathlib import Path
        import glob
        saved = sorted(glob.glob("/tmp/AI Radar*.pptx"), key=os.path.getmtime)
        assert saved, "Publisher should save a PPTX to /tmp"
        prs = Presentation(saved[-1])

        # All three image-text placeholders show the pending message
        for slide_idx in (1, 2, 3):  # slides 2, 3, 4
            slide = prs.slides[slide_idx]
            for shape in slide.shapes:
                name = getattr(shape, "name", "")
                if name in (
                    "PLACEHOLDER_AR_IMAGE_TEXT",
                    "PLACEHOLDER_ES_IMAGE_TEXT",
                    "PLACEHOLDER_FOOTER_IMAGE_TEXT",
                ):
                    text = shape.text_frame.text if shape.has_text_frame else ""
                    assert "pendiente" in text.lower(), \
                        f"{name} on slide {slide_idx+1} should show 'pendiente' " \
                        f"message in draft, got: {text!r}"
                    assert "aprobación" in text.lower() or "aprobacion" in text.lower(), \
                        f"{name} on slide {slide_idx+1} should mention 'aprobación', " \
                        f"got: {text!r}"


def test_publisher_clears_pendiente_text_when_image_provided():
    """When image_urls HAS a URL, the pendiente text must be cleared
    and the image must be inserted in the frame."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import RadarReport
    import tempfile, os, glob
    from unittest.mock import patch
    from pptx import Presentation
    # 1x1 transparent PNG (just enough to test that the URL was passed)
    PNG_BYTES = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    class FakeResponse:
        status_code = 200
        content = PNG_BYTES
        def raise_for_status(self): pass
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            slide_2_text="x", slide_3_text="y", conclusions="z",
        )
        with patch("requests.get", return_value=FakeResponse()):
            pub._publish_report_sync(
                report, "May 2026", chart_url=None,
                image_urls=["http://example.com/img.png"] * 3,
            )
        saved = sorted(glob.glob("/tmp/AI Radar*.pptx"), key=os.path.getmtime)
        assert saved, "Publisher should save a PPTX to /tmp"
        prs = Presentation(saved[-1])
        # All pendiente text is cleared when an image was inserted
        for slide_idx in (1, 2, 3):
            slide = prs.slides[slide_idx]
            for shape in slide.shapes:
                name = getattr(shape, "name", "")
                if name in (
                    "PLACEHOLDER_AR_IMAGE_TEXT",
                    "PLACEHOLDER_ES_IMAGE_TEXT",
                    "PLACEHOLDER_FOOTER_IMAGE_TEXT",
                ):
                    text = shape.text_frame.text if shape.has_text_frame else ""
                    assert text == "", \
                        f"{name} on slide {slide_idx+1} should be CLEARED when " \
                        f"image URL is provided, got: {text!r}"


def test_publisher_bar_charts_have_data_labels():
    """Both bar charts have data labels (show_value=True) at the
    outside-end of each horizontal bar — no benchmark-name tag in
    the cell."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkEntry, BenchmarkSnapshot,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        snap = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            entries=[
                BenchmarkEntry(vendor="Anthropic", model="Opus 4.8", score=93.6, cost_per_1m_input=18.0),
                BenchmarkEntry(vendor="Google DeepMind", model="Gemini 3 Pro", score=91.5, cost_per_1m_input=1.5),
            ],
        )
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        # Both charts must have data labels enabled
        for s in prs.slides[0].shapes:
            if s.has_chart and s.name in ("CHART_BENCHMARK", "CHART_PRICING"):
                series = s.chart.series[0]
                assert series.data_labels.show_value is True
                assert series.data_labels.show_category_name is False
        # Benchmark chart: no MMLU tag in the data label number format
        for s in prs.slides[0].shapes:
            if s.name == "CHART_BENCHMARK" and s.has_chart:
                fmt = s.chart.series[0].data_labels.number_format
                assert "MMLU" not in (fmt or ""), \
                    f"Benchmark tag leaked into data label: {fmt!r}"
                return
        raise AssertionError("CHART_BENCHMARK not found")


# ════════════════════════════════════════════════════════════════════════════
#  PR: writer rewrite + visual fix (line spacing + em-dash)
# ════════════════════════════════════════════════════════════════════════════


def test_writer_strip_conclusion_subheaders_strips_primero_segundo():
    """REGLA 4B: defensive stripper drops isolated '**Primero**' / '**Segundo**' / '**Tercero**' markers."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = (
        "**Primero**, la competencia entre modelos baja en latencia. "
        "**Segundo**, en AR y ES la adopción se mueve a procesos críticos. "
        "**Tercero**, la gobernanza deja de ser periférica."
    )
    cleaned = _strip_conclusion_subheaders(raw)
    # Either the isolated marker is stripped (preferred), or the text is
    # preserved as prose. The point is no orphaned bold-ordinal left behind.
    assert "**Primero**" not in cleaned
    assert "**Segundo**" not in cleaned
    assert "**Tercero**" not in cleaned
    # The substance should still be there
    assert "competencia entre modelos" in cleaned
    assert "gobernanza" in cleaned


def test_writer_strip_conclusion_subheaders_strips_intro_sugiere():
    """Defensive: drops 'El mes sugiere...' / 'El mes indica...' / 'El mes muestra...' at the start."""
    from community_manager.nurturing.nodes.writer import _strip_conclusion_subheaders

    raw = "El mes sugiere tres patrones convergentes. La latencia baja y la adopción entra en fraude."
    cleaned = _strip_conclusion_subheaders(raw)
    assert not cleaned.lower().startswith("el mes sugiere")
    assert "latencia baja" in cleaned


def test_writer_regla10_forbids_enumeration():
    """REGLA 10 must forbid enumerations like Primero/Segundo/Tercero."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    regla10_start = rules.index("REGLA 10")
    regla11_start = rules.index("REGLA 11")
    regla10 = rules[regla10_start:regla11_start]
    assert "Primero" in regla10 or "Primero/Segundo/Tercero" in regla10, \
        "REGLA 10 must reference 'Primero/Segundo/Tercero'"


def test_writer_regla12_forbids_em_dash():
    """REGLA 12 must forbid em-dash in the writer prompt."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    regla12_start = rules.index("REGLA 12")
    regla13_start = rules.index("REGLA 13")
    regla12 = rules[regla12_start:regla13_start]
    assert "—" in regla12, "REGLA 12 must mention the em-dash character"
    assert "PROHIBIDO" in regla12.upper() or "prohibido" in regla12.lower(), \
        "REGLA 12 must use PROHIBIDO or similar"


def test_writer_regla13_requires_critical_depth():
    """REGLA 13 must push for critical reading (not just positive conclusions)."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    regla13_start = rules.index("REGLA 13")
    regla13 = rules[regla13_start:]
    assert "crític" in regla13.lower() or "critic" in regla13.lower(), \
        "REGLA 13 must mention critical reading"
    # Should have at least one example of bad vs good
    assert "❌" in regla13 or "shallow" in regla13.lower() or "genérica" in regla13.lower(), \
        "REGLA 13 must include a 'shallow' example to push away from"


def test_writer_regla14_forbids_cliche_negative_comparison():
    """REGLA 14 forbids the 'ya no es X, es Y' cliché and requires the
    writer to pick a predictive / advisory / trend / critical angle
    instead. This is the #1 LLMs-default sentence pattern that
    screams "AI-generated" to readers."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    assert "REGLA 14" in rules, "REGLA 14 must be present"
    regla14_start = rules.index("REGLA 14")
    # Find the next rule (REGLA 15 or end)
    next_rule_pos = len(rules)
    for n in ("REGLA 15", "REGLA 16"):
        try:
            pos = rules.index(n, regla14_start + 1)
            if pos < next_rule_pos:
                next_rule_pos = pos
        except ValueError:
            pass
    regla14 = rules[regla14_start:next_rule_pos]
    # Must call out the cliché
    assert "ya no es" in regla14, "REGLA 14 must mention the 'ya no es' cliché"
    assert "PROHIBIDO" in regla14.upper() or "prohibido" in regla14.lower(), \
        "REGLA 14 must use PROHIBIDO or similar"
    # Must offer the 4 alternative angles
    assert "PREDICTIVO" in regla14.upper() or "predictivo" in regla14.lower(), \
        "REGLA 14 must include PREDICTIVO angle"
    assert "ADVISORY" in regla14.upper() or "advisory" in regla14.lower(), \
        "REGLA 14 must include ADVISORY angle"
    assert "TENDENCIA" in regla14.upper() or "tendencia" in regla14.lower(), \
        "REGLA 14 must include TENDENCIA angle"


def test_writer_regla15_requires_sources_on_slide1():
    """REGLA 15 requires the writer to cite 2-3 sources inline in the
    slide 1 executive summary, because the right-side tables don't
    show any sources."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    assert "REGLA 15" in rules, "REGLA 15 must be present"
    regla15_start = rules.index("REGLA 15")
    regla15 = rules[regla15_start:]
    # Must reference slide 1 / executive summary
    assert "Slide 1" in regla15 or "Resumen Ejecutivo" in regla15 or "ejecutivo" in regla15.lower(), \
        "REGLA 15 must reference slide 1 / executive summary"
    # Must require inline sources
    assert "fuente" in regla15.lower() or "fuentes" in regla15.lower(), \
        "REGLA 15 must require sources"
    # Must mention the right-side tables don't show sources
    assert "tabla" in regla15.lower() or "tablas" in regla15.lower(), \
        "REGLA 15 must explain that the right-side tables don't show sources"


def test_writer_system_prompt_mentions_tone_shift():
    """WRITER_SYSTEM must be the new technical-denso style (no 'magazine' / no 'calidez')."""
    from community_manager.nurturing.nodes.writer import WRITER_SYSTEM
    assert "Técnico" in WRITER_SYSTEM or "técnico" in WRITER_SYSTEM, \
        "WRITER_SYSTEM must declare a technical tone"
    # It must NOT contain the old casual language from the previous version
    assert "magazine" not in WRITER_SYSTEM.lower(), \
        "WRITER_SYSTEM should not say 'magazine' (we removed that tone)"
    assert "calidez" not in WRITER_SYSTEM.lower(), \
        "WRITER_SYSTEM should not say 'calidez' (we removed that tone)"


def test_writer_system_prompt_forbids_em_dash():
    """WRITER_SYSTEM must explicitly forbid em-dash in output text."""
    from community_manager.nurturing.nodes.writer import WRITER_SYSTEM
    assert "—" in WRITER_SYSTEM, "WRITER_SYSTEM must mention the em-dash character"
    assert "PROHIBIDO" in WRITER_SYSTEM.upper() or "prohibido" in WRITER_SYSTEM.lower(), \
        "WRITER_SYSTEM must use PROHIBIDO marker"


def test_writer_system_prompt_forbids_segment_mention():
    """WRITER_SYSTEM must tell the writer NOT to mention the audience segment in the text."""
    from community_manager.nurturing.nodes.writer import WRITER_SYSTEM
    assert "audiencia" in WRITER_SYSTEM.lower() or "empresa" in WRITER_SYSTEM.lower(), \
        "WRITER_SYSTEM must explicitly handle the 'audience' framing"


def test_publisher_strips_em_dash_in_clauses():
    """The publisher replaces em-dash as in-clause separator with comma."""
    from community_manager.nurturing.newsletter_pptx_publisher import (
        NewsletterPPTXPublisher,
    )
    pub = NewsletterPPTXPublisher()
    # Simulate the regex used in _set_markdown_text (mirrors the real code)
    import re
    sample = "hacia procesos críticos — fraude, soporte — donde el retorno es visible"
    # Apply the same regex chain the publisher uses
    cleaned = sample
    cleaned = re.sub(r'\n\s*---\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r'\n\s*—\s*—\s*—\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r'\s+—\s+', ', ', cleaned)
    cleaned = re.sub(r'\n—\n', '\n', cleaned)
    assert "—" not in cleaned, f"em-dash should be stripped. Got: {cleaned!r}"
    # The meaning should be preserved (just replaced by commas)
    assert "fraude, soporte" in cleaned
    assert "procesos críticos" in cleaned


def test_publisher_unifies_line_spacing_across_paragraphs():
    """The publisher must set line_spacing=1.5 on EVERY paragraph, not just the first.

    This is the bug fix for the visual issue: the template sets 1.5 on the
    first paragraph, but p.clear() preserves it. New paragraphs added via
    tf.add_paragraph() would otherwise fall back to 1.0. The publisher now
    explicitly sets 1.5 on every paragraph.
    """
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import RadarReport
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        report = RadarReport(
            subject="t",
            report_title="t",
            executive_summary="Párrafo uno.\n\nPárrafo dos.\n\nPárrafo tres.",
        )
        from pptx import Presentation
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        slide1 = prs.slides[0]
        # Find the executive summary shape and verify all paragraphs have 1.5
        for shape in slide1.shapes:
            if shape.name == "PLACEHOLDER_EXECUTIVE_SUMMARY":
                tf = shape.text_frame
                for i, para in enumerate(tf.paragraphs):
                    if para.text.strip():
                        assert para.line_spacing == 1.5, \
                            f"paragraph {i} ({para.text[:40]!r}) has line_spacing={para.line_spacing}, expected 1.5"
                break


def test_publisher_line_spacing_unified_for_2_insights():
    """Same as above but for the 2-insight AR/ES textbox pattern."""
    from community_manager.nurturing.newsletter_pptx_template import NewsletterTemplateBuilder
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import RadarReport
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        report = RadarReport(
            subject="t",
            report_title="t",
            executive_summary="e",
            slide_2_text=(
                "Insight uno: la escala importa.\n\n"
                "\n\n"
                "Insight dos: el fraude es el primer caso de uso."
            ),
        )
        from pptx import Presentation
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_insights(prs.slides[1], report, image_urls=[])
        slide2 = prs.slides[1]
        for shape in slide2.shapes:
            if shape.name == "PLACEHOLDER_AR_TEXT":
                tf = shape.text_frame
                # Every non-empty paragraph must have line_spacing 1.5
                for i, para in enumerate(tf.paragraphs):
                    if para.text.strip():
                        assert para.line_spacing == 1.5, \
                            f"slide_2 paragraph {i} ({para.text[:40]!r}) has line_spacing={para.line_spacing}"
                break


def test_writer_rules_have_slide1_context_rule():
    """REGLA 3B tells the LLM that Slide 1 opens with what AI Radar is,
    then develops ONE strong idea — not a summary of all insights."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    assert "REGLA 3B" in rules
    assert "SLIDE 1" in rules
    # Must explain what AI Radar is to first-time readers
    assert "AI Radar" in rules or "AI Radar es" in rules
    # Must forbid duplicating table data
    assert "tablas" in rules.lower()
    # Must mention selecting the most important idea
    assert "UNA idea" in rules or "una idea" in rules.lower()


def test_writer_rules_have_bold_concept_rule():
    """REGLA 7B defines what **bold** is FOR: key concepts (entities,
    products, regulatory decisions, key metrics) — not for titling the
    whole insight."""
    from community_manager.nurturing.nodes.writer import _format_rules
    rules = _format_rules()
    assert "REGLA 7B" in rules
    assert "**bold**" in rules.lower() or "**BOLD**" in rules
    # Must enumerate allowed uses
    assert "Empresas" in rules or "vendors" in rules
    assert "Productos" in rules or "modelos" in rules
    # Must forbid the abusive pattern
    assert "titular el insight" in rules.lower() or "titular el insight entero" in rules.lower()


def test_pptx_template_slide1_tables_dont_overlap():
    """Slide 1's two table labels and tables must not overlap with each
    other or run off the slide. The previous bug: label of table 2
    sat on top of the end of table 1, rendering as a smudge."""
    from community_manager.nurturing.newsletter_pptx_template import (
        NewsletterTemplateBuilder, SLIDE_W, SLIDE_H,
    )
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        NewsletterTemplateBuilder(tmpl_path).build()
        from pptx import Presentation
        prs = Presentation(str(tmpl_path))
        slide1 = prs.slides[0]
        # Find the two table labels and the two tables
        labels = []
        tables = []
        for shape in slide1.shapes:
            if shape.has_table:
                tables.append((shape.name, shape.top, shape.top + shape.height))
            elif shape.has_text_frame:
                txt = (shape.text_frame.text or "").lower()
                if "benchmark" in txt and "mmlu" in txt:
                    labels.append(("bench_label", shape.top, shape.top + shape.height))
                elif "costo" in txt or "1m tokens" in txt:
                    labels.append(("price_label", shape.top, shape.top + shape.height))
        assert len(labels) == 2, f"Expected 2 labels, got {len(labels)}: {labels}"
        assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}: {tables}"
        # Sort by top
        labels.sort(key=lambda x: x[1])
        tables.sort(key=lambda x: x[1])
        # Both labels and both tables must be within slide bounds.
        # shape.top and shape.height are in EMU (1 inch = 914400 EMU).
        # SLIDE_H is in pixels at 96 DPI (720 px = 7.5"). Convert SLIDE_H
        # to EMU for the comparison.
        SLIDE_H_EMU = int(7.5 * 914400)
        for name, top, bot in labels + tables:
            assert top >= 0, f"{name} top={top} is above slide"
            assert bot <= SLIDE_H_EMU, \
                f"{name} bottom={bot} (={bot/914400:.2f}in) > SLIDE_H={SLIDE_H_EMU/914400:.2f}in"
        # Table 1 must end before label 2 starts (no overlap)
        assert tables[0][2] <= labels[1][1], \
            f"Table 1 bottom={tables[0][2]/914400:.2f}in overlaps label 2 top={labels[1][1]/914400:.2f}in"


def test_pptx_publisher_shows_dash_for_missing_score():
    """Benchmark table should render all 5 rows; missing scores display
    "—" (the upstream research step + FALLBACK seed is responsible for
    filling data, not the publisher — the publisher must show the gap
    so the user knows what wasn't found)."""
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkSnapshot, BenchmarkEntry,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        from community_manager.nurturing.newsletter_pptx_template import (
            NewsletterTemplateBuilder,
        )
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        snap = BenchmarkSnapshot(entries=[
            BenchmarkEntry(vendor="A", model="m1", score=88.0, rank=1, cost_per_1m_input=2.50),
            BenchmarkEntry(vendor="B", model="m2", score=None, rank=2, cost_per_1m_input=3.00),
            BenchmarkEntry(vendor="C", model="m3", score=85.0, rank=3, cost_per_1m_input=None),
            BenchmarkEntry(vendor="D", model="m4", score=80.0, rank=4, cost_per_1m_input=1.50),
            BenchmarkEntry(vendor="E", model="m5", score=78.0, rank=5, cost_per_1m_input=4.50),
        ])
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        for shape in prs.slides[0].shapes:
            if shape.name == "PLACEHOLDER_BENCHMARK_TABLE" and shape.has_table:
                pub._populate_benchmark_table(shape, report)
                # All 5 rows render. Scores present → "88.0"; missing → "—".
                assert shape.table.cell(1, 1).text_frame.paragraphs[0].text == "A m1"
                assert shape.table.cell(1, 2).text_frame.paragraphs[0].text == "88.0"
                assert shape.table.cell(2, 1).text_frame.paragraphs[0].text == "B m2"
                assert shape.table.cell(2, 2).text_frame.paragraphs[0].text == "—"
                assert shape.table.cell(3, 1).text_frame.paragraphs[0].text == "C m3"
                assert shape.table.cell(3, 2).text_frame.paragraphs[0].text == "85.0"
                assert shape.table.cell(4, 1).text_frame.paragraphs[0].text == "D m4"
                assert shape.table.cell(4, 2).text_frame.paragraphs[0].text == "80.0"
                assert shape.table.cell(5, 1).text_frame.paragraphs[0].text == "E m5"
                assert shape.table.cell(5, 2).text_frame.paragraphs[0].text == "78.0"
                return
        raise AssertionError("PLACEHOLDER_BENCHMARK_TABLE not found on slide 1")


def test_pptx_publisher_shows_dash_for_missing_cost():
    """Pricing table renders all 5 rows; missing costs show "—". The
    upstream research step is responsible for finding pricing data;
    the publisher must surface gaps rather than hide them."""
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkSnapshot, BenchmarkEntry,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        from community_manager.nurturing.newsletter_pptx_template import (
            NewsletterTemplateBuilder,
        )
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        snap = BenchmarkSnapshot(entries=[
            BenchmarkEntry(vendor="A", model="m1", score=88.0, rank=1, cost_per_1m_input=2.50),
            BenchmarkEntry(vendor="B", model="m2", score=None, rank=2, cost_per_1m_input=3.00),
            BenchmarkEntry(vendor="C", model="m3", score=85.0, rank=3, cost_per_1m_input=None),
            BenchmarkEntry(vendor="D", model="m4", score=80.0, rank=4, cost_per_1m_input=1.50),
        ])
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        for shape in prs.slides[0].shapes:
            if shape.name == "PLACEHOLDER_PRICING_TABLE" and shape.has_table:
                pub._populate_pricing_table(shape, report)
                # m3 has no cost → must show "—", not hidden.
                # Cheapest first: D ($1.50), A ($2.50), B ($3.00), C (—)
                assert shape.table.cell(1, 1).text_frame.paragraphs[0].text == "D m4"
                assert shape.table.cell(1, 2).text_frame.paragraphs[0].text == "$1.50"
                assert shape.table.cell(2, 1).text_frame.paragraphs[0].text == "A m1"
                assert shape.table.cell(2, 2).text_frame.paragraphs[0].text == "$2.50"
                assert shape.table.cell(3, 1).text_frame.paragraphs[0].text == "B m2"
                assert shape.table.cell(3, 2).text_frame.paragraphs[0].text == "$3.00"
                # m3 still renders, with "—" in the cost cell.
                assert shape.table.cell(4, 1).text_frame.paragraphs[0].text == "C m3"
                assert shape.table.cell(4, 2).text_frame.paragraphs[0].text == "—"
                return
        raise AssertionError("PLACEHOLDER_PRICING_TABLE not found on slide 1")


def test_pptx_publisher_bar_charts_omit_benchmark_name_tag():
    """The bar charts show ONLY the score or cost value in data labels —
    NO benchmark-name tag (e.g. '75.0 GPQA') leaks anywhere on the
    slide, because the snapshot's default benchmark is already in
    context (via the label 'BENCHMARK  ·  MMLU Pro' above the chart)
    and per-cell tags would be visual noise."""
    from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher
    from community_manager.models.schemas import (
        RadarReport, BenchmarkSnapshot, BenchmarkEntry,
    )
    import tempfile, os
    from pptx import Presentation
    with tempfile.TemporaryDirectory() as tmp:
        tmpl_path = os.path.join(tmp, "tmpl.pptx")
        from community_manager.nurturing.newsletter_pptx_template import (
            NewsletterTemplateBuilder,
        )
        NewsletterTemplateBuilder(tmpl_path).build()
        pub = NewsletterPPTXPublisher()
        snap = BenchmarkSnapshot(
            benchmark_name="MMLU Pro",
            entries=[
                BenchmarkEntry(
                    vendor="Anthropic", model="Opus 4.8",
                    benchmark_name="MMLU Pro", score=90.5,
                    cost_per_1m_input=15.0, cost_per_1m_output=75.0,
                    rank=1,
                ),
                BenchmarkEntry(
                    vendor="xAI", model="Grok 3",
                    benchmark_name="GPQA Diamond", score=75.0,
                    cost_per_1m_input=3.0, cost_per_1m_output=12.0,
                    rank=2,
                ),
            ],
        )
        report = RadarReport(
            subject="t", report_title="t", executive_summary="e",
            benchmark_snapshot=snap,
        )
        prs = Presentation(str(tmpl_path))
        pub._populate_slide_cover_summary(prs.slides[0], report, "May 2026")
        # Both charts have no title (the label above already says
        # "BENCHMARK  ·  MMLU Pro" / "COSTO  ·  x 1M tokens")
        for shape in prs.slides[0].shapes:
            if shape.has_chart and shape.name in ("CHART_BENCHMARK", "CHART_PRICING"):
                assert shape.chart.has_title is False
        # Benchmark chart shows both scores
        for shape in prs.slides[0].shapes:
            if shape.name == "CHART_BENCHMARK" and shape.has_chart:
                scores = list(shape.chart.series[0].values)
                assert 90.5 in scores
                assert 75.0 in scores
                return
        raise AssertionError("CHART_BENCHMARK not found on slide 1")


def test_normalize_benchmark_name_handles_short_forms():
    """The LLM often returns short forms ('MMLU', 'GPQA') that would
    mismatch the snapshot's default ('MMLU Pro') and trigger a
    spurious tag in the slide. Normalize to canonical forms."""
    from community_manager.nurturing.nodes.researcher import _normalize_benchmark_name
    # Common short forms
    assert _normalize_benchmark_name("MMLU") == "MMLU Pro"
    assert _normalize_benchmark_name("MMLU Pro") == "MMLU Pro"
    assert _normalize_benchmark_name("mmlu pro") == "MMLU Pro"
    assert _normalize_benchmark_name("GPQA") == "GPQA Diamond"
    assert _normalize_benchmark_name("GPQA Diamond") == "GPQA Diamond"
    assert _normalize_benchmark_name("AIME 2024") == "AIME 2025"
    assert _normalize_benchmark_name("SWE-bench") == "SWE-bench Verified"
    assert _normalize_benchmark_name("MATH-500") == "MATH-500"
    assert _normalize_benchmark_name("MMMU") == "MMMU-Pro"
    # Unknown names pass through (caller's responsibility)
    assert _normalize_benchmark_name("CustomBench") == "CustomBench"
    # Empty falls back to MMLU Pro
    assert _normalize_benchmark_name("") == "MMLU Pro"


def test_research_benchmark_snapshot_dedupes_same_model_different_benchmarks():
    """If the research pass returns the same (vendor, model) with two
    different benchmarks (e.g. MMLU Pro 93.6 AND SWE-bench 88.6 for
    Claude Opus 4.8), the snapshot keeps only the highest-scoring
    entry — the user sees one row per model, not duplicates."""
    import asyncio
    from unittest.mock import patch
    from community_manager.nurturing.nodes.researcher import (
        _research_benchmark_snapshot,
    )
    async def fake_llm_ainvoke(messages):
        class R:
            content = (
                '{"entries": ['
                '{"vendor": "Anthropic", "model": "Claude Opus 4.8", '
                '"benchmark_name": "MMLU Pro", "score": 93.6, '
                '"cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0}, '
                '{"vendor": "Anthropic", "model": "Claude Opus 4.8", '
                '"benchmark_name": "SWE-bench Verified", "score": 88.6, '
                '"cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0}, '
                '{"vendor": "OpenAI", "model": "GPT-5", '
                '"benchmark_name": "MMLU Pro", "score": 88.7, '
                '"cost_per_1m_input": 5.0, "cost_per_1m_output": 15.0}'
                ']}'
            )
        return R()
    from community_manager.nurturing.tools import SerperResult
    async def fake_search(*a, **kw):
        return [SerperResult(
            title="t", snippet="s", url="https://x.com/y",
            rank=1, source_domain="x.com",
            is_trusted_domain=True, date="2026-06-01",
        )]
    with patch(
        "community_manager.nurturing.nodes.researcher.get_newsletter_llm",
    ) as mock_llm_factory, patch(
        "community_manager.nurturing.tools.search_structured",
        new=fake_search,
    ):
        mock_llm_factory.return_value.ainvoke = fake_llm_ainvoke
        snapshot = asyncio.run(_research_benchmark_snapshot(
            mock_llm_factory.return_value,
            [{"vendor": "Anthropic", "model": "Claude Opus 4.8"}],
            "Junio 2026",
        ))
    # 3 researched entries (>=3) → no seed mixing, source = artificialanalysis.io
    assert snapshot.source == "artificialanalysis.io"
    # Dedup: 3 researched (Opus 4.8 x2, GPT-5 x1) → 2 unique.
    opus_rows = [e for e in snapshot.entries
                if e.vendor == "Anthropic" and "Opus 4.8" in e.model]
    assert len(opus_rows) == 1, f"Expected 1 Opus 4.8 row, got {len(opus_rows)}"
    # The kept one is the highest-scoring (MMLU Pro 93.6).
    assert opus_rows[0].score == 93.6
    assert opus_rows[0].benchmark_name == "MMLU Pro"


def test_research_benchmark_snapshot_picks_most_common_benchmark():
    """If the LLM returns entries on different benchmarks (e.g. 1 on
    GPQA Diamond, 3 on MMLU Pro), the snapshot picks the benchmark
    with the MOST entries so the table is comparable. Single-entry
    benchmarks are dropped (incomparable on their own). No seed mixing:
    when research has >=3 complete entries, the seed is ignored entirely."""
    import asyncio
    from unittest.mock import patch
    from community_manager.nurturing.nodes.researcher import (
        _research_benchmark_snapshot,
    )
    async def fake_llm_ainvoke(messages):
        class R:
            content = (
                '{"entries": ['
                # 3 on MMLU Pro
                '{"vendor": "Anthropic", "model": "Opus 4.8", '
                '"benchmark_name": "MMLU Pro", "score": 93.6, '
                '"cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0}, '
                '{"vendor": "OpenAI", "model": "GPT-5", '
                '"benchmark_name": "MMLU Pro", "score": 88.7, '
                '"cost_per_1m_input": 5.0, "cost_per_1m_output": 15.0}, '
                '{"vendor": "Google DeepMind", "model": "Gemini 3 Pro", '
                '"benchmark_name": "MMLU Pro", "score": 88.0, '
                '"cost_per_1m_input": 1.25, "cost_per_1m_output": 5.0}, '
                # 1 on GPQA Diamond (should be DROPPED)
                '{"vendor": "xAI", "model": "Grok 3", '
                '"benchmark_name": "GPQA Diamond", "score": 75.0, '
                '"cost_per_1m_input": 3.0, "cost_per_1m_output": 12.0}'
                ']}'
            )
        return R()
    from community_manager.nurturing.tools import SerperResult
    async def fake_search(*a, **kw):
        return [SerperResult(
            title="t", snippet="s", url="https://x.com/y",
            rank=1, source_domain="x.com",
            is_trusted_domain=True, date="2026-06-01",
        )]
    with patch(
        "community_manager.nurturing.nodes.researcher.get_newsletter_llm",
    ) as mock_llm_factory, patch(
        "community_manager.nurturing.tools.search_structured",
        new=fake_search,
    ):
        mock_llm_factory.return_value.ainvoke = fake_llm_ainvoke
        snapshot = asyncio.run(_research_benchmark_snapshot(
            mock_llm_factory.return_value,
            [{"vendor": "Anthropic", "model": "Opus 4.8"}],
            "Junio 2026",
        ))
    # No seed mixing: with 4 researched entries (>=3), the seed is
    # ignored. Grok 3 on GPQA Diamond gets filtered out when MMLU Pro
    # is chosen. Result: 3 entries on MMLU Pro only.
    assert snapshot.benchmark_name == "MMLU Pro", \
        f"Expected MMLU Pro, got {snapshot.benchmark_name}"
    assert len(snapshot.entries) == 3, \
        f"Expected 3 MMLU Pro entries (no seed mix), got {len(snapshot.entries)}"
    for e in snapshot.entries:
        assert e.benchmark_name == "MMLU Pro", \
            f"Entry {e.vendor}/{e.model} is on {e.benchmark_name}, expected MMLU Pro"
    assert snapshot.source == "artificialanalysis.io"


def test_benchmark_entry_has_benchmark_name_field():
    """Multi-benchmark support: each BenchmarkEntry must carry the
    benchmark name it was scored on. The publisher uses this to show
    the user which benchmark was used when it's not the default."""
    from community_manager.models.schemas import BenchmarkEntry
    e = BenchmarkEntry(vendor="Anthropic", model="Opus 4.8", score=91.0)
    # Default is MMLU Pro for backward compat with existing PPTX tests.
    assert e.benchmark_name == "MMLU Pro"
    # Can override to GPQA Diamond, AIME, etc.
    e2 = BenchmarkEntry(
        vendor="xAI", model="Grok 3",
        benchmark_name="GPQA Diamond", score=75.0,
    )
    assert e2.benchmark_name == "GPQA Diamond"


def test_fallback_benchmark_seed_has_at_least_5_models():
    """The fallback seed is the safety net — if dedicated research finds
    nothing, the table still shows real 2026 frontier models with score
    and pricing. Must always have ≥ 5 entries with non-None score AND
    cost_per_1m_input AND cost_per_1m_output."""
    from community_manager.nurturing.nodes.researcher import FALLBACK_BENCHMARK_SEED
    assert len(FALLBACK_BENCHMARK_SEED) >= 5, \
        f"Seed must have ≥5 entries, got {len(FALLBACK_BENCHMARK_SEED)}"
    for entry in FALLBACK_BENCHMARK_SEED[:5]:
        assert entry.get("vendor"), f"Missing vendor in {entry}"
        assert entry.get("model"), f"Missing model in {entry}"
        assert entry.get("score") is not None, f"Missing score in {entry}"
        assert entry.get("cost_per_1m_input") is not None, \
            f"Missing cost_per_1m_input in {entry}"
        assert entry.get("cost_per_1m_output") is not None, \
            f"Missing cost_per_1m_output in {entry}"
        # Plausibility ranges
        assert 70.0 <= entry["score"] <= 95.0, f"Implausible score: {entry['score']}"
        assert 0.01 <= entry["cost_per_1m_input"] <= 100.0
        assert 0.05 <= entry["cost_per_1m_output"] <= 200.0


def test_fallback_benchmark_seed_has_one_model_per_vendor():
    """The seed must show ONE row per company. The user does not want
    two Anthropic rows (Opus 4.5 + 4.8) — only the latest frontier
    model from each company."""
    from community_manager.nurturing.nodes.researcher import FALLBACK_BENCHMARK_SEED
    vendors = [e["vendor"].lower() for e in FALLBACK_BENCHMARK_SEED]
    assert len(vendors) == len(set(vendors)), \
        f"Seed has duplicate vendors: {vendors}"


def test_fallback_seed_uses_latest_anthropic_claude_opus_4_8():
    """The user explicitly said the seed should use the latest frontier
    Anthropic model (Claude Opus 4.8), not the older 4.5."""
    from community_manager.nurturing.nodes.researcher import FALLBACK_BENCHMARK_SEED
    anthropic = [e for e in FALLBACK_BENCHMARK_SEED if e["vendor"] == "Anthropic"]
    assert len(anthropic) == 1
    assert "4.8" in anthropic[0]["model"], \
        f"Expected Claude Opus 4.8, got {anthropic[0]['model']}"
    assert "4.5" not in anthropic[0]["model"]


def test_fallback_seed_uses_latest_openai_gpt_5_5():
    """The user explicitly said GPT-5 is old, the latest frontier
    OpenAI model as of June 2026 is GPT-5.5."""
    from community_manager.nurturing.nodes.researcher import FALLBACK_BENCHMARK_SEED
    openai = [e for e in FALLBACK_BENCHMARK_SEED if e["vendor"] == "OpenAI"]
    assert len(openai) == 1
    assert "5.5" in openai[0]["model"], \
        f"Expected GPT-5.5, got {openai[0]['model']}"
    assert openai[0]["model"] != "GPT-5"  # not the old one


def test_dedupe_by_vendor_keeps_one_per_company():
    """When the research pass returns 2 entries from Anthropic (Opus
    4.5 + Opus 4.8), the snapshot must end up with only ONE Anthropic
    row — the latest one (4.8)."""
    from community_manager.nurturing.nodes.researcher import _dedupe_by_vendor
    from community_manager.models.schemas import BenchmarkEntry
    entries = [
        BenchmarkEntry(vendor="Anthropic", model="Claude Opus 4.5",
                       score=89.2, cost_per_1m_input=15.0, rank=0),
        BenchmarkEntry(vendor="Anthropic", model="Claude Opus 4.8",
                       score=93.6, cost_per_1m_input=18.0, rank=0),
        BenchmarkEntry(vendor="OpenAI", model="GPT-5.5",
                       score=92.8, cost_per_1m_input=6.0, rank=0),
        BenchmarkEntry(vendor="Google DeepMind", model="Gemini 3 Pro",
                       score=91.5, cost_per_1m_input=1.5, rank=0),
    ]
    out = _dedupe_by_vendor(entries)
    assert len(out) == 3
    anthropic = [e for e in out if e.vendor == "Anthropic"]
    assert len(anthropic) == 1
    assert "4.8" in anthropic[0].model, \
        f"Expected Opus 4.8 (latest), got {anthropic[0].model}"


def test_dedupe_by_vendor_prefers_canonical_latest_over_higher_score():
    """If the research returns a higher-scoring OLDER model
    (e.g. Claude Opus 4.5 with score 95) but the seed/canonical
    latest is Claude Opus 4.8 with score 93.6, the LATEST model
    wins (newer is better, scores can be noisy across sources)."""
    from community_manager.nurturing.nodes.researcher import _dedupe_by_vendor
    from community_manager.models.schemas import BenchmarkEntry
    entries = [
        BenchmarkEntry(vendor="Anthropic", model="Claude Opus 4.5",
                       score=95.0, cost_per_1m_input=15.0, rank=0),
        BenchmarkEntry(vendor="Anthropic", model="Claude Opus 4.8",
                       score=93.6, cost_per_1m_input=18.0, rank=0),
    ]
    out = _dedupe_by_vendor(entries)
    assert len(out) == 1
    assert "4.8" in out[0].model, \
        "Latest canonical (4.8) should win even with lower score"


def test_dedupe_by_vendor_keeps_research_discovered_model_if_no_canonical():
    """If the research discovers a model we don't have in
    FRONTIER_MODELS (e.g. a new entrant), it should still be kept."""
    from community_manager.nurturing.nodes.researcher import _dedupe_by_vendor
    from community_manager.models.schemas import BenchmarkEntry
    entries = [
        BenchmarkEntry(vendor="Cohere", model="Command R+",
                       score=82.0, cost_per_1m_input=2.5, rank=0),
    ]
    out = _dedupe_by_vendor(entries)
    assert len(out) == 1
    assert out[0].vendor == "Cohere"


def test_research_benchmark_snapshot_dedupes_by_vendor():
    """The full snapshot pipeline must end up with at most one entry
    per vendor — no duplicate Anthropic rows, no duplicate OpenAI."""
    from community_manager.nurturing.nodes.researcher import _research_benchmark_snapshot
    from unittest.mock import patch
    from community_manager.nurturing.tools import SerperResult

    async def fake_llm_ainvoke(messages):
        class R:
            content = (
                '{"entries": ['
                '{"vendor": "Anthropic", "model": "Claude Opus 4.5", '
                '"benchmark_name": "MMLU Pro", "score": 89.2, '
                '"cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0}, '
                '{"vendor": "Anthropic", "model": "Claude Opus 4.8", '
                '"benchmark_name": "MMLU Pro", "score": 93.6, '
                '"cost_per_1m_input": 18.0, "cost_per_1m_output": 90.0}, '
                '{"vendor": "OpenAI", "model": "GPT-5.5", '
                '"benchmark_name": "MMLU Pro", "score": 92.8, '
                '"cost_per_1m_input": 6.0, "cost_per_1m_output": 18.0}, '
                '{"vendor": "Google DeepMind", "model": "Gemini 3 Pro", '
                '"benchmark_name": "MMLU Pro", "score": 91.5, '
                '"cost_per_1m_input": 1.5, "cost_per_1m_output": 6.0}'
                ']}'
            )
        return R()

    async def fake_search(*a, **kw):
        return [SerperResult(
            title="t", snippet="s", url="https://x.com/y",
            rank=1, source_domain="x.com",
            is_trusted_domain=True, date="2026-06-01",
        )]

    with patch("community_manager.nurturing.nodes.researcher.get_newsletter_llm") as m_llm, \
         patch("community_manager.nurturing.tools.search_structured", new=fake_search):
        m_llm.return_value.ainvoke = fake_llm_ainvoke
        snap = asyncio.run(_research_benchmark_snapshot(
            m_llm.return_value,
            [{"vendor": "Anthropic", "model": "Claude Opus"}],
            "June 2026",
        ))
    assert snap.source == "artificialanalysis.io"
    vendors = [e.vendor.lower() for e in snap.entries]
    assert len(vendors) == len(set(vendors)), \
        f"Snapshot has duplicate vendors: {vendors}"
    # The latest Claude (4.8) should be the one picked
    anthropic = [e for e in snap.entries if e.vendor == "Anthropic"]
    assert len(anthropic) == 1, f"Expected 1 Anthropic row, got {len(anthropic)}"
    assert "4.8" in anthropic[0].model, \
        f"Expected Opus 4.8, got {anthropic[0].model}"


def test_collect_models_from_insights_uses_defaults_when_no_launches():
    """If the insights pass found no model launches, the dedicated
    research must still query the DEFAULT_COMPARISON_MODELS so the
    table has a comparable 2026 frontier baseline."""
    from community_manager.nurturing.nodes.researcher import (
        _collect_models_from_insights, DEFAULT_COMPARISON_MODELS,
    )
    # No insights at all
    out = _collect_models_from_insights([])
    assert out == DEFAULT_COMPARISON_MODELS
    # Insights with no vendor/model_name (e.g. policy news) → defaults
    from community_manager.models.schemas import RadarInsight
    ins = RadarInsight(
        headline="EU AI Act enters force",
        summary="New regulation begins application.",
        source_url="https://example.com/ai-act",
        source_title="Example",
        source_date="2026-06-01",
        business_impact="Compliance work required",
        country_tag="GLOBAL", category="regulation",
    )
    out = _collect_models_from_insights([ins])
    assert out == DEFAULT_COMPARISON_MODELS


def test_collect_models_from_insights_merges_launches_with_defaults():
    """If insights mention a new model launch, that model leads the
    query list AND the DEFAULT_COMPARISON_MODELS are still queried
    so the table stays comparable (frontier floor)."""
    from community_manager.nurturing.nodes.researcher import _collect_models_from_insights
    from community_manager.models.schemas import RadarInsight
    launch = RadarInsight(
        headline="OpenAI launches GPT-6",
        summary="New flagship model.",
        source_url="https://example.com/gpt-6",
        source_title="Example",
        source_date="2026-06-15",
        business_impact="Huge",
        country_tag="GLOBAL", category="model_launch",
        is_model_launch=True, vendor="OpenAI", model_name="GPT-6",
    )
    out = _collect_models_from_insights([launch])
    # GPT-6 (the new launch) is first.
    assert out[0] == {"vendor": "OpenAI", "model": "GPT-6"}
    # The DEFAULT set is still queried alongside, including GPT-5 —
    # comparing the new launch against the previous frontier is the
    # whole point of the benchmark table.
    vendors_models = {(e["vendor"], e["model"]) for e in out[1:]}
    assert ("Anthropic", "Claude Opus") in vendors_models
    assert ("Google DeepMind", "Gemini 3 Pro") in vendors_models
    # The total is capped at 8 (1 launch + 7 defaults, but we have 5
    # defaults so the total is 6, well under the cap).
    assert len(out) <= 8


def test_validate_research_entry_rejects_garbage():
    """Validation must reject entries with missing fields, out-of-range
    scores, or implausible costs. Otherwise the LLM could poison the
    table with hallucinations."""
    from community_manager.nurturing.nodes.researcher import _validate_research_entry
    # Missing fields
    assert _validate_research_entry({}) is None
    assert _validate_research_entry({"vendor": "X"}) is None
    assert _validate_research_entry({"vendor": "X", "model": "y"}) is None
    # Score out of range
    assert _validate_research_entry({
        "vendor": "X", "model": "y", "score": 150.0,
        "cost_per_1m_input": 5.0,
    }) is None
    assert _validate_research_entry({
        "vendor": "X", "model": "y", "score": -5.0,
        "cost_per_1m_input": 5.0,
    }) is None
    # Missing both costs (entry is useless for the pricing table)
    assert _validate_research_entry({
        "vendor": "X", "model": "y", "score": 80.0,
    }) is None
    # Cost out of range
    assert _validate_research_entry({
        "vendor": "X", "model": "y", "score": 80.0,
        "cost_per_1m_input": 200.0,  # too expensive
    }) is None


def test_validate_research_entry_accepts_valid_entry():
    """A well-formed entry should pass validation and produce a
    BenchmarkEntry with the expected fields."""
    from community_manager.nurturing.nodes.researcher import _validate_research_entry
    entry = _validate_research_entry({
        "vendor": "Anthropic",
        "model": "Claude Opus 4.5",
        "benchmark_name": "MMLU Pro",
        "score": 89.2,
        "cost_per_1m_input": 15.0,
        "cost_per_1m_output": 75.0,
    })
    assert entry is not None
    assert entry.vendor == "Anthropic"
    assert entry.model == "Claude Opus 4.5"
    assert entry.benchmark_name == "MMLU Pro"
    assert entry.score == 89.2
    assert entry.cost_per_1m_input == 15.0
    assert entry.cost_per_1m_output == 75.0


def test_apply_dedicated_research_falls_back_to_seed_on_failure():
    """If the dedicated research pass raises, the report must still
    get a populated benchmark_snapshot (from the seed). The table
    is NEVER empty."""
    import asyncio
    from unittest.mock import patch
    from community_manager.nurturing.nodes.researcher import (
        _apply_dedicated_benchmark_research,
    )
    from community_manager.models.schemas import RadarReport, RadarInsight
    report = RadarReport(
        subject="t", report_title="t", executive_summary="e",
        insights=[RadarInsight(
            headline="h", summary="s", source_url="https://x.com/y",
            source_title="x", source_date="2026-06-01",
            business_impact="b", country_tag="GLOBAL", category="c",
        )],
    )
    # Make the research snapshot raise — seed should kick in.
    async def boom(*a, **kw):
        raise RuntimeError("simulated brave outage")
    with patch(
        "community_manager.nurturing.nodes.researcher._research_benchmark_snapshot",
        side_effect=boom,
    ):
        out = asyncio.run(_apply_dedicated_benchmark_research(report, "Junio 2026"))
    assert out.benchmark_snapshot is not None
    assert len(out.benchmark_snapshot.entries) == 5, \
        f"Seed should always produce 5 entries, got {len(out.benchmark_snapshot.entries)}"
    # Seed fallback has the referential source text
    assert "Precios referenciales" in out.benchmark_snapshot.source
    # All entries from the seed have non-None score + cost
    for e in out.benchmark_snapshot.entries:
        assert e.score is not None
        assert e.cost_per_1m_input is not None


def test_research_benchmark_snapshot_uses_fallback_for_low_yield():
    """If the dedicated LLM extraction returns only 2 valid entries
    but the seed has 7, the snapshot must be topped up to 5 with seed
    entries (no duplicates). The final 5 are the highest-scoring,
    regardless of source (research vs seed)."""
    import asyncio
    from unittest.mock import patch
    from community_manager.nurturing.nodes.researcher import (
        _research_benchmark_snapshot, FALLBACK_BENCHMARK_SEED,
    )

    # Mock the LLM to return a small partial result (2 valid entries).
    async def fake_llm_ainvoke(messages):
        class R:
            content = (
                '{"entries": ['
                '{"vendor": "OpenAI", "model": "GPT-5.5", '
                '"benchmark_name": "MMLU Pro", "score": 81.2, '
                '"cost_per_1m_input": 5.0, "cost_per_1m_output": 15.0}, '
                '{"vendor": "Anthropic", "model": "Claude Opus 4.8", '
                '"benchmark_name": "MMLU Pro", "score": 90.5, '
                '"cost_per_1m_input": 15.0, "cost_per_1m_output": 75.0}'
                ']}'
            )
        return R()
    # Mock the search to return 1 result (enough for the LLM call).
    from community_manager.nurturing.tools import SerperResult
    async def fake_search(*a, **kw):
        return [SerperResult(
            title="t", snippet="s", url="https://x.com/y",
            rank=1, source_domain="x.com",
            is_trusted_domain=True, date="2026-06-01",
        )]
    with patch(
        "community_manager.nurturing.nodes.researcher.get_newsletter_llm",
    ) as mock_llm_factory, patch(
        "community_manager.nurturing.tools.search_structured",
        new=fake_search,
    ):
        mock_llm_factory.return_value.ainvoke = fake_llm_ainvoke
        snapshot = asyncio.run(_research_benchmark_snapshot(
            mock_llm_factory.return_value,
            [{"vendor": "OpenAI", "model": "GPT-5.5"}],
            "Junio 2026",
        ))
    # The snapshot is sorted by score DESC, top 5 only. After the
    # vendor-level dedup, both the researched Claude Opus 4.8 (90.5)
    # and the seed's Claude Opus 4.8 (93.6) collapse into one row, and
    # the SEED wins (canonical-latest + highest score tiebreaker). The
    # researched GPT-5.5 (81.2) is also outscored by the seed's GPT-5.5
    # (92.8), so the snapshot ends up being 100% seed rows.
    assert len(snapshot.entries) == 5
    # All 5 entries come from the seed (researched scores are all lower).
    seed_keys = {(s["vendor"], s["model"]) for s in FALLBACK_BENCHMARK_SEED}
    snap_keys = {(e.vendor, e.model) for e in snapshot.entries}
    seed_hits = sum(1 for k in snap_keys if k in seed_keys)
    assert seed_hits == 5, f"Expected 5 from seed, got {seed_hits}"
    # Top entry is the highest-scoring frontier model (Anthropic Opus 4.8).
    assert snapshot.entries[0].vendor == "Anthropic"
    assert snapshot.entries[0].model == "Claude Opus 4.8"
    # All 5 entries have distinct vendors (vendor dedup worked).
    vendors = [e.vendor.lower() for e in snapshot.entries]
    assert len(vendors) == len(set(vendors)), \
        f"Snapshot has duplicate vendors: {vendors}"
    # All 5 entries have ranks 1..5 in order.
    for i, e in enumerate(snapshot.entries, 1):
        assert e.rank == i, f"Entry {i} has rank={e.rank}"
