using System.Net;
using System.Net.Http.Json;
using System.Reflection;
using Microsoft.AspNetCore.Mvc.Testing;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class AzureSpeechServiceSsmlTests
{
    private static string BuildSsmlBody(string text, bool isEnglish)
    {
        var method = typeof(AzureSpeechService).GetMethod(
            "BuildSsmlBody",
            BindingFlags.NonPublic | BindingFlags.Static)!;
        return (string)method.Invoke(null, [text, isEnglish])!;
    }

    [Fact]
    public void BuildSsmlBody_SpanishGreetingWithNovitAiAndSoftware_DoesNotDoubleWrapLangTag()
    {
        // Regression test: "Novit Software" was causing double <lang xml:lang='en-US'> wrapping
        // because EnglishTechTermsRegex ran AFTER BrandNovitRegex had already emitted a <lang> tag.
        var text = "¡Hola! ¿Cómo estás? Soy Novit AI, la representante comercial de Novit Software. Contame, ¿en qué te puedo ayudar?";

        var result = BuildSsmlBody(text, isEnglish: false);

        Assert.DoesNotContain("<lang xml:lang='en-US'><lang xml:lang='en-US'>", result);
    }

    [Fact]
    public void BuildSsmlBody_SpanishNovitSoftware_ProducesSingleLangTagForSoftware()
    {
        var text = "Somos Novit Software y te ayudamos.";

        var result = BuildSsmlBody(text, isEnglish: false);

        // "Software" must appear exactly once wrapped in <lang xml:lang='en-US'>
        Assert.Contains("<lang xml:lang='en-US'>Software</lang>", result);
        // Must NOT be double-wrapped
        Assert.DoesNotContain("<lang xml:lang='en-US'><lang xml:lang='en-US'>Software</lang></lang>", result);
    }

    [Fact]
    public void BuildSsmlBody_SpanishNovitAI_ContainsPhonemeForNovit()
    {
        var text = "Soy Novit AI, tu asistente.";

        var result = BuildSsmlBody(text, isEnglish: false);

        Assert.Contains("ph='ˈno.βit'", result);
    }

    [Fact]
    public void BuildSsmlBody_SpanishGreetingWithNovitAiAndSoftware_DoesNotNestPhoneme()
    {
        // Regression test: "Novit" inside <phoneme> tags (from BrandNovitAIRegex) was being
        // re-matched by BrandNovitRegex, producing nested <phoneme> elements that Azure TTS rejects.
        var text = "¡Hola! ¿Cómo estás? Soy Novit AI, la representante comercial de Novit Software. Contame, ¿en qué te puedo ayudar?";

        var result = BuildSsmlBody(text, isEnglish: false);

        // Must NOT contain nested phoneme tags
        Assert.DoesNotContain("<phoneme alphabet='ipa' ph='ˈno.βit'><phoneme", result);
    }

    [Fact]
    public void BuildSsmlBody_SpanishNovitAI_DoesNotNestPhoneme()
    {
        var text = "Soy Novit AI, tu asistente.";

        var result = BuildSsmlBody(text, isEnglish: false);

        Assert.DoesNotContain("<phoneme alphabet='ipa' ph='ˈno.βit'><phoneme", result);
    }

    [Fact]
    public void BuildSsmlBody_SimpleSpanishGreeting_ReturnsPlainText()
    {
        // Regression: simple Spanish greetings without brand names should produce
        // clean SSML body with no XML tags (after emoji stripping upstream).
        var text = "¡Hola! ¿En qué te puedo ayudar hoy?";

        var result = BuildSsmlBody(text, isEnglish: false);

        Assert.Equal(text, result);
    }
}

public class ApiIntegrationTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public ApiIntegrationTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task Health_Endpoint_Returns_Ok()
    {
        var response = await _client.GetAsync("/api/health");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Conversation_Create_Get_Delete_Works()
    {
        var createResponse = await _client.PostAsJsonAsync("/api/chat/conversations", new ConversationCreateRequest("es-AR"));
        createResponse.EnsureSuccessStatusCode();
        var created = await createResponse.Content.ReadFromJsonAsync<ConversationCreateResponse>();

        Assert.NotNull(created);

        var getResponse = await _client.GetAsync($"/api/chat/conversations/{created!.ConversationId}");
        Assert.Equal(HttpStatusCode.OK, getResponse.StatusCode);

        var deleteResponse = await _client.DeleteAsync($"/api/chat/conversations/{created.ConversationId}");
        Assert.Equal(HttpStatusCode.NoContent, deleteResponse.StatusCode);
    }

    [Fact]
    public async Task Send_Message_Returns_Bot_Reply()
    {
        var createResponse = await _client.PostAsJsonAsync("/api/chat/conversations", new ConversationCreateRequest("es-AR"));
        var created = await createResponse.Content.ReadFromJsonAsync<ConversationCreateResponse>();

        var sendResponse = await _client.PostAsJsonAsync(
            $"/api/chat/conversations/{created!.ConversationId}/messages",
            new UserMessageRequest("Necesito ayuda con un proyecto", "es-AR"));

        sendResponse.EnsureSuccessStatusCode();
        var payload = await sendResponse.Content.ReadFromJsonAsync<UserMessageResponse>();
        Assert.NotNull(payload);
        Assert.Equal("user", payload!.UserMessage.Role);
        Assert.Equal("bot", payload.BotMessage.Role);
    }

    [Fact]
    public async Task Contact_Form_Invalid_Email_Returns_BadRequest()
    {
        var response = await _client.PostAsJsonAsync(
            "/api/contact/form",
            new ContactFormRequest("Test", "invalid-email", "Hola", "es-AR"));

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }
}

public class StripTimestampsTests
{
    [Fact]
    public void Strips_leading_timestamp()
    {
        var result = AzureAIChatService.StripTimestamps("[2026-03-19 12:08] Hola, ¿cómo estás?");
        Assert.Equal("Hola, ¿cómo estás?", result);
    }

    [Fact]
    public void Strips_timestamp_with_seconds()
    {
        var result = AzureAIChatService.StripTimestamps("[2026-03-19 12:08:30] Hello!");
        Assert.Equal("Hello!", result);
    }

    [Fact]
    public void Strips_mid_text_timestamp()
    {
        var result = AzureAIChatService.StripTimestamps("Hola [2026-03-19 12:08] ¿cómo estás?");
        Assert.Equal("Hola ¿cómo estás?", result);
    }

    [Fact]
    public void Strips_multiple_timestamps()
    {
        var result = AzureAIChatService.StripTimestamps("[2026-03-19 12:08] Hola [2026-03-20 14:00] mundo");
        Assert.Equal("Hola mundo", result);
    }

    [Fact]
    public void Does_not_modify_clean_text()
    {
        var result = AzureAIChatService.StripTimestamps("Just a normal message");
        Assert.Equal("Just a normal message", result);
    }
}

public class ExpandTimezoneAbbreviationsTests
{
    [Fact]
    public void Spanish_ARG_Expands_To_Horario_Argentina()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("Lunes 30 de marzo, 10:30am ARG", isEnglish: false);
        Assert.Equal("Lunes 30 de marzo, 10:30am horario Argentina", result);
    }

    [Fact]
    public void Spanish_ESP_Expands_To_Horario_España()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("3:30pm ESP", isEnglish: false);
        Assert.Equal("3:30pm horario España", result);
    }

    [Fact]
    public void Spanish_USET_Expands_To_Horario_Estados_Unidos()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("10:30am US-ET", isEnglish: false);
        Assert.Equal("10:30am horario Estados Unidos Eastern", result);
    }

    [Fact]
    public void Spanish_All_Three_Timezones_Expand()
    {
        var input = "Lunes 30 de marzo, 10:30am ARG, 3:30pm ESP, 10:30am US-ET.";
        var result = AzureSpeechService.ExpandTimezoneAbbreviations(input, isEnglish: false);
        Assert.Equal("Lunes 30 de marzo, 10:30am horario Argentina, 3:30pm horario España, 10:30am horario Estados Unidos Eastern.", result);
    }

    [Fact]
    public void English_ARG_Expands_To_Argentina_Time()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("Monday March 30th, 10:30am ARG", isEnglish: true);
        Assert.Equal("Monday March 30th, 10:30am Argentina time", result);
    }

    [Fact]
    public void English_ESP_Expands_To_Spain_Time()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("3:30pm ESP", isEnglish: true);
        Assert.Equal("3:30pm Spain time", result);
    }

    [Fact]
    public void English_USET_Expands_To_US_Eastern_Time()
    {
        var result = AzureSpeechService.ExpandTimezoneAbbreviations("10:30am US-ET", isEnglish: true);
        Assert.Equal("10:30am US Eastern time", result);
    }

    [Fact]
    public void No_Timezone_Returns_Unchanged()
    {
        var input = "Hola, te confirmo la reunión para el lunes.";
        var result = AzureSpeechService.ExpandTimezoneAbbreviations(input, isEnglish: false);
        Assert.Equal(input, result);
    }

    [Fact]
    public void Does_Not_Expand_ARG_Inside_Longer_Word()
    {
        var input = "La ARGENTINA es un país hermoso.";
        var result = AzureSpeechService.ExpandTimezoneAbbreviations(input, isEnglish: false);
        Assert.Equal(input, result);
    }
}
