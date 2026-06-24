using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Options;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public sealed class AzureSpeechService : ISpeechService
{
    private readonly AzureAIOptions _options;
    private readonly HttpClient _http;

    public AzureSpeechService(IOptions<AzureAIOptions> options, HttpClient http)
    {
        _options = options.Value;
        _http = http;
    }

    public bool IsConfigured => _options.IsSpeechConfigured;

    public async Task<(string text, double confidence, int durationMs)> TranscribeAsync(Stream audio, string locale, string contentType = "audio/wav", CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            var fallback = locale.StartsWith("en", StringComparison.OrdinalIgnoreCase)
                ? "Thanks for your voice message."
                : "Gracias por tu mensaje de voz.";
            return (fallback, 0.99, 850);
        }

        var language = locale.StartsWith("en", StringComparison.OrdinalIgnoreCase) ? "en-US" : "es-AR";
        var url = $"{_options.STTUrl}/speech/recognition/dictation/cognitiveservices/v1?language={language}&format=detailed&profanity=raw";

        // Map browser MIME types to Azure STT supported types
        var azureContentType = contentType switch
        {
            var mime when mime.Contains("ogg", StringComparison.OrdinalIgnoreCase) => "audio/ogg; codecs=opus",
            var mime when mime.Contains("webm", StringComparison.OrdinalIgnoreCase) => "audio/webm; codecs=opus",
            var mime when mime.Contains("mp4", StringComparison.OrdinalIgnoreCase) => "audio/mp4",
            _ => "audio/wav"
        };

        using var content = new StreamContent(audio);
        content.Headers.ContentType = MediaTypeHeaderValue.Parse(azureContentType);

        using var request = new HttpRequestMessage(HttpMethod.Post, url);
        request.Headers.Add("Ocp-Apim-Subscription-Key", _options.AzureAISpeechKey);
        request.Content = content;

        var response = await _http.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        var root = doc.RootElement;

        var status = root.TryGetProperty("RecognitionStatus", out var statusProp) ? statusProp.GetString() : null;
        if (status != "Success")
        {
            return ("", 0.0, 0);
        }

        var text = root.TryGetProperty("DisplayText", out var displayText) ? displayText.GetString() ?? "" : "";
        var confidence = root.TryGetProperty("NBest", out var nbest) && nbest.GetArrayLength() > 0
            ? nbest[0].GetProperty("Confidence").GetDouble()
            : 0.0;
        var durationTicks = root.TryGetProperty("Duration", out var dur) ? dur.GetInt64() : 0;
        var durationMs = (int)(durationTicks / 10000);

        return (text, confidence, durationMs);
    }

    public async Task<byte[]> SynthesizeAsync(string text, string locale, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            throw new InvalidOperationException("TTS synthesis is not configured.");
        }

        using var request = BuildTtsRequest(text, locale);
        var response = await _http.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        return await response.Content.ReadAsByteArrayAsync(ct);
    }

    public async Task SynthesizeStreamAsync(string text, string locale, Stream destination, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            throw new InvalidOperationException("TTS synthesis is not configured.");
        }

        using var request = BuildTtsRequest(text, locale);
        // ResponseHeadersRead allows streaming: the call returns as soon as response headers arrive,
        // before the full body is downloaded. This lets us pipe audio to the client progressively.
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();

        await response.Content.CopyToAsync(destination, ct);
    }

    private HttpRequestMessage BuildTtsRequest(string text, string locale)
    {
        // Auto-detect language from content if locale is ambiguous
        var isEnglish = DetectIsEnglish(text, locale);
        var lang = isEnglish ? "en-US" : "es-AR";
        // Use the same multilingual voice for both languages — it natively handles
        // code-switching between Spanish and English via <lang> SSML tags.
        const string voiceName = "en-US-AvaMultilingualNeural";

        var cleanText = CleanInterjections(StripEmojis(StripMarkdown(text)));
        cleanText = ExpandTimezoneAbbreviations(cleanText, isEnglish);
        var ssmlBody = BuildSsmlBody(cleanText, isEnglish);

        // For Spanish, wrap the body in <lang xml:lang='es-AR'> so the multilingual
        // voice speaks with Argentine accent. English words are already wrapped in
        // <lang xml:lang='en-US'> by BuildSsmlBody, so they'll be pronounced in English.
        var prosodyContent = isEnglish
            ? ssmlBody
            : $"<lang xml:lang='es-AR'>{ssmlBody}</lang>";

        var ssml = $"""
            <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{lang}'>
                <voice name='{voiceName}'>
                    <prosody rate='+15%' pitch='+2%'>{prosodyContent}</prosody>
                </voice>
            </speak>
            """;

        var url = $"{_options.TTSUrl}/cognitiveservices/v1";

        var request = new HttpRequestMessage(HttpMethod.Post, url);
        request.Headers.Add("Ocp-Apim-Subscription-Key", _options.AzureAISpeechKey);
        request.Headers.Add("X-Microsoft-OutputFormat", "audio-24khz-48kbitrate-mono-mp3");
        request.Headers.Add("User-Agent", "NovitWebAI/1.0");
        request.Content = new StringContent(ssml, Encoding.UTF8, "application/ssml+xml");

        return request;
    }

    /// <summary>Detect whether text is primarily English based on content analysis.</summary>
    private static bool DetectIsEnglish(string text, string locale)
    {
        // If locale explicitly says en, trust it
        if (locale.StartsWith("en", StringComparison.OrdinalIgnoreCase))
            return true;

        // Content-based detection — check regardless of locale
        var lower = " " + text.ToLowerInvariant() + " ";
        var englishMarkers = new[] { " the ", " we ", " our ", " you ", " your ", " what ", " that ", " this ",
            " is ", " are ", " have ", " has ", " with ", " from ", " about ", " would ", " could ",
            " don't ", " let's ", " here's ", " we've ", " i'm ", " it's ", " can ", " will ",
            " been ", " were ", " they ", " their ", " also ", " just ", " more ", " some " };
        var spanishMarkers = new[] { " que ", " los ", " las ", " una ", " para ", " por ", " con ",
            " del ", " más ", " como ", " pero ", " está ", " tiene ", " puede ", " hay ",
            " todo ", " muy ", " nos ", " vos ", " también ", " sobre ", " desde " };
        int englishCount = 0;
        int spanishCount = 0;
        foreach (var marker in englishMarkers)
            if (lower.Contains(marker)) englishCount++;
        foreach (var marker in spanishMarkers)
            if (lower.Contains(marker)) spanishCount++;

        // English if more English markers than Spanish, with at least 2 English markers
        return englishCount >= 2 && englishCount > spanishCount;
    }

    /// <summary>Build SSML body with proper pronunciation for brand names and mixed-language words.</summary>
    private static string BuildSsmlBody(string text, bool isEnglish)
    {
        var escaped = System.Security.SecurityElement.Escape(text);

        // Replace tech acronyms with phoneme tags BEFORE other passes so they don't get
        // double-wrapped by EnglishTechTermsRegex or misread by the TTS engine.
        escaped = TechAcronymRegex.Replace(escaped, m =>
        {
            var (ph, display) = m.Value.Contains('/') switch
            {
                true => ("juː.ɛks juː.aɪ", m.Value), // UX/UI — keep original display
                _ => m.Value.ToUpperInvariant() switch
                {
                    "IT"  => ("aɪ.tiː", "IT"),
                    "UX"  => ("juː.ɛks", "UX"),
                    "UI"  => ("juː.aɪ", "UI"),
                    "API" => ("eɪ.piː.aɪ", "API"),
                    "QA"  => ("kjuː.eɪ", "QA"),
                    _     => ((string?)null, m.Value)
                }
            };

            if (ph == null) return m.Value;

            return isEnglish
                ? $"<phoneme alphabet='ipa' ph='{ph}'>{display}</phoneme>"
                : $"<lang xml:lang='en-US'><phoneme alphabet='ipa' ph='{ph}'>{display}</phoneme></lang>";
        });

        // In Spanish voice, wrap common English tech terms BEFORE brand-name replacements so
        // that words like "Software" are not double-wrapped when the brand regex also emits
        // a <lang> tag for them (e.g. "Novit Software" → double <lang xml:lang='en-US'>).
        if (!isEnglish)
        {
            escaped = EnglishMultiWordRegex.Replace(escaped, m => $"<lang xml:lang='en-US'>{m.Value}</lang>");
            escaped = EnglishTechTermsRegex.Replace(escaped, m => $"<lang xml:lang='en-US'>{m.Value}</lang>");
        }

        // Replace "Novit AI" with proper pronunciation (Novit with accent on O, AI as English acronym)
        escaped = BrandNovitAIRegex.Replace(escaped, match =>
        {
            return isEnglish
                ? "<phoneme alphabet='ipa' ph='ˈnoʊ.vɪt'>Novit</phoneme> <phoneme alphabet='ipa' ph='eɪ.aɪ'>AI</phoneme>"
                : "<phoneme alphabet='ipa' ph='ˈno.βit'>Novit</phoneme> <lang xml:lang='en-US'><phoneme alphabet='ipa' ph='eɪ.aɪ'>AI</phoneme></lang>";
        });

        // Replace "Novit Software" or "Novit" alone (after Novit AI is already handled).
        // When running in Spanish mode, "Software" may already be wrapped in a <lang> tag by
        // the tech-terms pass above, so the "Novit Software" branch will no longer match and
        // "Novit" will be caught by the standalone branch instead — the net result is the same.
        escaped = BrandNovitRegex.Replace(escaped, match =>
        {
            // "Novit Software" → pronounce Novit with accent on O, Software in English
            if (match.Groups[1].Success)
            {
                return isEnglish
                    ? "<phoneme alphabet='ipa' ph='ˈnoʊ.vɪt'>Novit</phoneme> <lang xml:lang='en-US'>Software</lang>"
                    : "<phoneme alphabet='ipa' ph='ˈno.βit'>Novit</phoneme> <lang xml:lang='en-US'>Software</lang>";
            }
            // Just "Novit" alone
            return isEnglish
                ? "<phoneme alphabet='ipa' ph='ˈnoʊ.vɪt'>Novit</phoneme>"
                : "<phoneme alphabet='ipa' ph='ˈno.βit'>Novit</phoneme>";
        });

        // Standalone "AI" (not already inside a phoneme tag) — pronounce as English acronym
        escaped = StandaloneAIRegex.Replace(escaped, m =>
        {
            return isEnglish
                ? "<phoneme alphabet='ipa' ph='eɪ.aɪ'>AI</phoneme>"
                : "<lang xml:lang='en-US'><phoneme alphabet='ipa' ph='eɪ.aɪ'>AI</phoneme></lang>";
        });

        return escaped;
    }

    // Match "Novit AI" (must come before generic Novit regex)
    private static readonly Regex BrandNovitAIRegex = new(@"\bNovit\s+AI\b", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    // Match "Novit Software" or "Novit" alone — but NOT "Novit AI" (already handled)
    // The (?<!>) lookbehind prevents re-matching "Novit" already inside <phoneme> tags from BrandNovitAIRegex.
    private static readonly Regex BrandNovitRegex = new(@"(?<!>)\bNovit\s+(Software)\b|(?<!>)\bNovit\b(?!\s+AI)", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    // Match standalone "AI" not preceded by "Novit" (already handled) and not inside XML tags
    private static readonly Regex StandaloneAIRegex = new(@"(?<!\bNovit\s)(?<!['>=/])\bAI\b(?![<'])", RegexOptions.Compiled);

    // Match tech acronyms that need phoneme-based pronunciation (case-sensitive: uppercase only)
    // UX/UI must come before individual UX and UI to match the combined form first.
    private static readonly Regex TechAcronymRegex = new(@"\bUX\s*/\s*UI\b|\b(?:IT|UX|UI|API|QA)\b", RegexOptions.Compiled);

    private const string VoiceMessageMarker = "voice";

    // Pre-compiled regex for English tech terms that should be pronounced in English even in Spanish speech.
    // Note: IT, QA, UX, UI, API are handled separately by TechAcronymRegex with phoneme tags.
    private static readonly Regex EnglishTechTermsRegex = new(
        @"\b(software|hardware|cloud|DevOps|backend|frontend|deploy|sprint|scrum|dashboard|startup|feedback|testing|streaming|framework|open source|stack|full stack|workflow|pipeline|monitoring|hosting|e-commerce|ecommerce|academy|online|marketing|digital|consulting|outsourcing|staffing|coaching|mentoring|training|branding|design|product|performance|analytics|insight|agile|roadmap|feature|release|upgrade|support|partner|enterprise|business|intelligence|automation|integration|microservices|serverless|container|cluster|mobile|responsive|chatbot|token|prompt|embedding|fine-tuning|co-pilot|scalable|real-time|end-to-end)\b",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    // Multi-word terms handled separately
    private static readonly Regex EnglishMultiWordRegex = new(
        @"\b(machine learning|data science|deep learning|continuous integration|continuous delivery|artificial intelligence|natural language processing|computer vision|big data|product owner|tech lead|team building|quality assurance|user experience|user interface|digital transformation|code review|pull request|best practices)\b",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static readonly Regex MultiSpaceRegex = new(@"\s{2,}", RegexOptions.Compiled);

    // Interjection patterns: Mmm/Hmm/Shhh/Ahhh/Ohhh and Spanish laughs (Jajaja)
    private static readonly Regex InterjectionRegex = new(
        @"\b(?:m{3,}|h+m{2,}|s+h{2,}|[aou]+h{2,})\b",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex SpanishLaughRegex = new(
        @"\b[jJ]([aeiou])\1*(?:[jJ]\1*)+\b", RegexOptions.Compiled);
    private static readonly Regex EmptyPunctuationRegex = new(@"[¡¿]\s*[!?]", RegexOptions.Compiled);

    // Markdown stripping regexes
    private static readonly Regex MarkdownBoldRegex = new(@"\*\*(.+?)\*\*", RegexOptions.Compiled);
    private static readonly Regex MarkdownItalicRegex = new(@"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", RegexOptions.Compiled);
    private static readonly Regex MarkdownHeadingRegex = new(@"^#{1,6}\s+", RegexOptions.Compiled | RegexOptions.Multiline);
    private static readonly Regex MarkdownLinkRegex = new(@"\[([^\]]+)\]\([^\)]+\)", RegexOptions.Compiled);
    private static readonly Regex MarkdownListRegex = new(@"^[\s]*[-*+]\s+", RegexOptions.Compiled | RegexOptions.Multiline);

    private static string StripMarkdown(string text)
    {
        // Remove bold markers but keep content
        var result = MarkdownBoldRegex.Replace(text, "$1");
        // Remove italic markers but keep content
        result = MarkdownItalicRegex.Replace(result, "$1");
        // Remove heading markers
        result = MarkdownHeadingRegex.Replace(result, "");
        // Replace links with just the label
        result = MarkdownLinkRegex.Replace(result, "$1");
        // Remove list markers
        result = MarkdownListRegex.Replace(result, "");
        return result;
    }

    private static string StripEmojis(string text)
    {
        var sb = new StringBuilder(text.Length);
        var enumerator = System.Globalization.StringInfo.GetTextElementEnumerator(text);
        while (enumerator.MoveNext())
        {
            var element = enumerator.GetTextElement();
            var category = char.GetUnicodeCategory(element, 0);
            // Skip surrogate pairs (emojis are in supplementary planes) and symbol characters
            if (char.IsSurrogatePair(element, 0))
                continue;
            if (category == System.Globalization.UnicodeCategory.OtherSymbol)
                continue;
            // Skip common emoji characters in BMP
            var c = element[0];
            if (c >= '\u2600' && c <= '\u27BF') continue; // Misc symbols, dingbats
            if (c >= '\uFE00' && c <= '\uFE0F') continue; // Variation selectors
            if (c == '\u200D' || c == '\u200B' || c == '\u20E3') continue; // ZWJ, ZWSP, combining enclosing keycap
            sb.Append(element);
        }
        // Collapse multiple spaces left by removed emojis
        return MultiSpaceRegex.Replace(sb.ToString(), " ").Trim();
    }

    private static string CleanInterjections(string text)
    {
        // Remove interjections entirely — TTS spells them out as individual letters
        var result = InterjectionRegex.Replace(text, "");
        // Replace Spanish laughs (Jajaja→ja ja, Jejeje→je je)
        result = SpanishLaughRegex.Replace(result, m =>
        {
            var vowel = m.Groups[1].Value.ToLower();
            return $"j{vowel} j{vowel}";
        });
        // Clean up leftover empty punctuation (e.g. "¡!" from removed interjections)
        result = EmptyPunctuationRegex.Replace(result, "");
        return MultiSpaceRegex.Replace(result, " ").Trim();
    }

    // Timezone abbreviation regex: matches ARG, ESP, US-ET as standalone words
    // (typically used after time like "10:30am ARG" or "2pm ESP")
    private static readonly Regex TimezoneAbbrRegex = new(
        @"\bARG\b|\bESP\b|\bUS-ET\b",
        RegexOptions.Compiled);

    /// <summary>
    /// Expand timezone abbreviations (ARG, ESP, US-ET) into spoken-form labels
    /// so the TTS engine reads them naturally instead of spelling out letters.
    /// </summary>
    internal static string ExpandTimezoneAbbreviations(string text, bool isEnglish)
    {
        return TimezoneAbbrRegex.Replace(text, m => m.Value switch
        {
            "ARG" => isEnglish ? "Argentina time" : "horario Argentina",
            "ESP" => isEnglish ? "Spain time" : "horario España",
            "US-ET" => isEnglish ? "US Eastern time" : "horario Estados Unidos Eastern",
            _ => m.Value
        });
    }
}
