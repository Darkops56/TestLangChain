using System.Collections.Concurrent;
using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public sealed class MockAgentClient : IAgentClient
{
    public bool IsConfigured => true;

    private static readonly Random Rng = new();
    private static readonly ConcurrentDictionary<string, MockJob> Jobs = new();

    private static readonly string[] Platforms = ["instagram", "facebook", "twitter", "linkedin", "tiktok"];
    private static readonly string[] ContentTypes = ["image_post", "carousel", "reel", "story"];
    private static readonly string[] Topics =
        ["Productividad con IA", "Tendencias 2026", "Automatizaci\u00f3n de procesos", "Customer Experience", "Data-Driven Marketing"];
    private static readonly string[] Angles =
        ["Educativo", "Inspiracional", "Promocional", "Entretenimiento", "Caso de \u00e9xito"];
    private static readonly string[] Objectives =
        ["Engagement", "Tr\u00e1fico", "Brand Awareness", "Leads", "Ventas"];
    private static readonly string[] HashtagPool =
        ["#IA", "#Innovacion", "#MarketingDigital", "#Automatizacion", "#CX", "#Data", "#Productividad", "#Futuro"];

    private sealed record MockJob(string Id, string ContentType, string? Topic, string? Angle, string? Objective)
    {
        public string State { get; set; } = "processing";
        public string? Step { get; set; }
        public string? DraftId { get; set; }
        public string? DraftStatus { get; set; }
        public DateTimeOffset StartedAt { get; set; } = DateTimeOffset.UtcNow;
        public DateTimeOffset? UpdatedAt { get; set; }
    }

    public Task<AgentReplyResult?> ForwardWebhookMessageAsync(
        string senderId, string text, string platform, string? messageId,
        CancellationToken ct = default, string? senderName = null,
        string? replyTargetId = null, string? replyTargetType = null,
        string? postContextId = null, string? postContextText = null)
    {
        return Task.FromResult<AgentReplyResult?>(new AgentReplyResult(
            Reply: $"\u00a1Gracias por tu mensaje, {senderName ?? "usuario"}! Soy el asistente CM y estoy procesando tu consulta. Te responderemos a la brevedad."));
    }

    public Task<AgentNewsletterResult?> GenerateNewsletterAsync(CancellationToken ct = default)
    {
        return Task.FromResult<AgentNewsletterResult?>(new AgentNewsletterResult(
            Subject: $"Newsletter CM - {DateTimeOffset.UtcNow:MMMM yyyy}",
            Body: $"<h1>Novidades de CM Platform</h1><p>En esta edici\u00f3n: tendencias de IA aplicadas a Community Management, casos de \u00e9xito y novedades de la plataforma.</p><p>Saludos,<br/>Equipo CM</p>",
            ReportTitle: $"Reporte {DateTimeOffset.UtcNow:MMMM yyyy}",
            ExecutiveSummary: "Resumen ejecutivo generado autom\u00e1ticamente por el asistente CM."
        ));
    }

    public Task<AgentNewsletterResult?> ReviseNewsletterAsync(
        string currentSubject, string currentBody, string reviewerFeedback, CancellationToken ct = default)
    {
        return Task.FromResult<AgentNewsletterResult?>(new AgentNewsletterResult(
            Subject: $"[Revisado] {currentSubject}",
            Body: currentBody.Replace("<p>", "<p>[Ajustado seg\u00fan feedback] "),
            ExecutiveSummary: $"Revisado con base en: {reviewerFeedback}"));
    }

    public Task<string?> GenerateReplyAsync(
        string originalSubject, string originalBody, string senderName, CancellationToken ct = default)
    {
        return Task.FromResult<string?>(
            $"Hola {senderName},\n\nGracias por tu inter\u00e9s en nuestra newsletter. Respondemos a continuaci\u00f3n a tus comentarios:\n\n[Respuesta generada autom\u00e1ticamente]\n\nSaludos,\nEquipo CM");
    }

    public Task<string?> GenerateClosingAsync(
        string newsletterSubject, string? newsletterBody, string? firstName,
        string? orgName, IReadOnlyList<string> dealNotes, CancellationToken ct = default)
    {
        var name = firstName ?? "usuario";
        return Task.FromResult<string?>(
            $"\u00a1{name}, gracias por leer! Si ten\u00e9s preguntas sobre este contenido, no dudes en responder a este correo. Estamos ac\u00e1 para ayudarte.");
    }

    public Task<CommunityDraftPayload?> ReviseCommunityDraftAsync(
        string strategyJson, string copyJson, string designJson,
        string reviewerFeedback, string revisionTarget, string reviewerMemory,
        CancellationToken ct = default)
    {
        var payload = BuildDraftPayload("image_post", revisionTarget: revisionTarget);
        return Task.FromResult<CommunityDraftPayload?>(payload);
    }

    public Task<CommunityDraftPayload?> GenerateCommunityDraftAsync(
        string contentType, string reviewerMemory = "",
        IReadOnlyList<string>? publicationHistory = null,
        string? topic = null, string? angle = null, string? objective = null,
        int? numImages = null, CancellationToken ct = default)
    {
        var payload = BuildDraftPayload(contentType, topic, angle, objective);
        return Task.FromResult<CommunityDraftPayload?>(payload);
    }

    public Task<AgentCommunityDraftKickResult?> KickCommunityDraftAsync(
        string contentType, string? topic = null, string? angle = null,
        string? objective = null, int? numImages = null, CancellationToken ct = default)
    {
        var jobId = Guid.NewGuid().ToString("N")[..12];
        var job = new MockJob(jobId, contentType, topic, angle, objective);
        Jobs[jobId] = job;

        _ = Task.Run(async () =>
        {
            await Task.Delay(3000);
            job.Step = "strategist";
            await Task.Delay(2000);
            job.Step = "copywriter";
            await Task.Delay(2000);
            job.Step = "designer";
            await Task.Delay(2000);
            job.State = "completed";
            job.Step = "evaluator";
            job.DraftId = Guid.NewGuid().ToString();
            job.DraftStatus = CommunityPublicationStatus.PendingReview;
            job.UpdatedAt = DateTimeOffset.UtcNow;
        }, CancellationToken.None);

        return Task.FromResult<AgentCommunityDraftKickResult?>(new AgentCommunityDraftKickResult(
            JobId: jobId,
            Status: "accepted",
            ContentType: contentType,
            Topic: topic ?? PickRandom(Topics),
            Angle: angle ?? PickRandom(Angles),
            Objective: objective ?? PickRandom(Objectives)));
    }

    public Task<AgentCommunityDraftJobStatusResult?> GetCommunityDraftJobStatusAsync(
        string jobId, CancellationToken ct = default)
    {
        if (!Jobs.TryGetValue(jobId, out var job))
        {
            return Task.FromResult<AgentCommunityDraftJobStatusResult?>(new AgentCommunityDraftJobStatusResult(
                Found: false, JobId: jobId, State: "not_found", Step: null,
                ContentType: null, Topic: null, Angle: null, Objective: null, DraftId: null,
                DraftStatus: null, ReviewSubject: null, ReviewToken: null,
                FailureReason: null, Error: $"Job {jobId} not found", StartedAt: null, UpdatedAt: null, CompletedAt: null));
        }

        return Task.FromResult<AgentCommunityDraftJobStatusResult?>(new AgentCommunityDraftJobStatusResult(
            Found: true,
            JobId: jobId,
            State: job.State,
            Step: job.Step,
            ContentType: job.ContentType,
            Topic: job.Topic,
            Angle: job.Angle,
            Objective: job.Objective,
            DraftId: job.DraftId,
            DraftStatus: job.DraftStatus,
            ReviewSubject: job.DraftStatus == CommunityPublicationStatus.PendingReview ? "Mock Draft - Revision Needed" : null,
            ReviewToken: job.DraftId,
            FailureReason: null,
            Error: null,
            StartedAt: job.StartedAt.ToString("O"),
            UpdatedAt: job.UpdatedAt?.ToString("O"),
            CompletedAt: job.State == "completed" ? DateTimeOffset.UtcNow.ToString("O") : null));
    }

    public Task<bool> DeleteCommunityDraftMediaAsync(string designJson, CancellationToken ct = default)
    {
        return Task.FromResult(true);
    }

    public Task<CommunityDraftPayload?> MaterializeCommunityDraftMediaAsync(
        string strategyJson, string copyJson, string designJson, CancellationToken ct = default)
    {
        var payload = BuildDraftPayload("image_post", draftStatus: CommunityPublicationStatus.Approved);
        return Task.FromResult<CommunityDraftPayload?>(payload);
    }

    public Task<AgentCommunityPublishResult?> PublishCommunityDraftAsync(
        string strategyJson, string copyJson, string designJson, CancellationToken ct = default)
    {
        var results = Platforms.Take(Rng.Next(1, 3)).Select(p => new AgentPlatformPublishResult(
            Platform: p,
            Success: true,
            PostId: Guid.NewGuid().ToString("N")[..12],
            Error: null,
            Permalink: $"https://{p}.com/p/{Guid.NewGuid().ToString("N")[..8]}"
        )).ToList();

        return Task.FromResult<AgentCommunityPublishResult?>(new AgentCommunityPublishResult(
            Results: results,
            PublishedAt: DateTimeOffset.UtcNow,
            AllSuccess: true));
    }

    public Task<string?> PublishCommunityNowAsync(
        string contentType, string? topic = null, string? angle = null,
        string? objective = null, CancellationToken ct = default)
    {
        var jobId = Guid.NewGuid().ToString("N")[..12];
        return Task.FromResult<string?>(jobId);
    }

    public Task<string?> WrapEmailAsync(
        string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default)
    {
        var wrapped = $"<div style=\"font-family:Arial;max-width:600px;margin:auto\">" +
                      $"<div style=\"background:#1a73e8;color:white;padding:20px;text-align:center\">" +
                      $"<h1>CM Platform</h1></div>" +
                      $"<div style=\"padding:20px\">{htmlBody}</div>" +
                      $"<div style=\"padding:20px;color:#666;font-size:12px;border-top:1px solid #eee\">" +
                      $"<p>{personalClosing ?? "Saludos,<br/>Equipo CM"}</p></div></div>";
        return Task.FromResult<string?>(wrapped);
    }

    public Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default)
    {
        return Task.FromResult<AgentStatusResult?>(new AgentStatusResult(
            State: "running",
            LastRun: DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O"),
            SchedulerActive: true,
            NurturingV2Enabled: false));
    }

    private static CommunityDraftPayload BuildDraftPayload(
        string contentType,
        string? topic = null,
        string? angle = null,
        string? objective = null,
        string? revisionTarget = null,
        string draftStatus = CommunityPublicationStatus.PendingReview)
    {
        topic ??= PickRandom(Topics);
        angle ??= PickRandom(Angles);
        objective ??= PickRandom(Objectives);

        var caption = $"Descubr\u00ed c\u00f3mo {topic.ToLower()} puede transformar tu estrategia digital. " +
                      $"En este post exploramos un enfoque {angle!.ToLower()} para lograr {objective!.ToLower()}.\n\n" +
                      $"\u00bfQu\u00e9 opinas? Dejanos tu comentario.";

        var hashtags = Enumerable.Range(0, 5).Select(_ => PickRandom(HashtagPool)).Distinct().ToList();

        var mediaUrls = contentType switch
        {
            "carousel" => Enumerable.Range(1, 3).Select(i => $"https://placehold.co/600x600?text=Imagen+{i}").ToList(),
            _ => ["https://placehold.co/600x600?text=CM+Mock"]
        };

        return new CommunityDraftPayload(
            ContentType: contentType,
            Topic: topic,
            Angle: angle,
            Objective: objective,
            Caption: caption,
            Hashtags: hashtags,
            AltText: $"Imagen ilustrativa sobre {topic}",
            StrategyJson: $$"""{"topic":"{{topic}}","angle":"{{angle}}","objective":"{{objective}}","target_audience":"community_managers"}""",
            CopyJson: $$"""{"caption":"{{caption}}","hashtags":["{{string.Join("\",\"", hashtags)}}"],"tone":"profesional"}""",
            DesignJson: $$"""{"media_type":"{{contentType}}","num_images":1,"style":"minimal","colors":["#1a73e8","#ffffff"]}""",
            EvaluationJson: """{"score":8,"feedback":"Cumple con los criterios de calidad","approved":true}""",
            MediaUrls: mediaUrls,
            MediaBlobNames: mediaUrls.Select(u => $"mock-blob-{Guid.NewGuid():N}.jpg").ToList(),
            VideoDurationSeconds: contentType == "reel" ? 30 : 0,
            DraftStatus: draftStatus,
            ReviewStage: revisionTarget is not null ? CommunityReviewStage.PreMedia : CommunityReviewStage.Final,
            FailureReason: null,
            RetryCount: 0);
    }

    private static string PickRandom(string[] items) => items[Rng.Next(items.Length)];
}
