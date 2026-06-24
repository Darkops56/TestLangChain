using System.Net;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Novit.Web.Api.Data;
using Novit.Web.Api.Data.Entities;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

[ApiController]
[Route("api/community/review")]
public sealed class CommunityReviewController(
    NovitDbContext db,
    CommunityPublicationPublisher publisher,
    IAgentClient agentClient,
    CommunityReviewService reviewService,
    ILogger<CommunityReviewController> logger) : ControllerBase
{
    [HttpGet("{reviewToken}/approve")]
    public async Task<IActionResult> Approve(string reviewToken, CancellationToken ct)
    {
        var draft = await db.CommunityPublications.FirstOrDefaultAsync(p => p.ReviewToken == reviewToken, ct);
        if (draft is null)
            return HtmlPage("Link inválido", "No encontramos una publicación asociada a este link de revisión.");

        var reviewStage = CommunityReviewService.NormalizeReviewStage(draft.ReviewStage);

        if (draft.Status == CommunityPublicationStatus.Published)
            return HtmlPage("Publicación ya enviada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya había sido publicada.", success: true);

        if (draft.Status == CommunityPublicationStatus.Denied)
            return HtmlPage("Publicación denegada", $"La propuesta <b>{WebUtility.HtmlEncode(draft.Topic)}</b> fue denegada internamente antes de enviarse a revisión. Revisá el historial en el panel o generá una nueva versión.");

        if (draft.Status == CommunityPublicationStatus.Rejected)
            return HtmlPage("Publicación rechazada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya estaba rechazada y no se publicará.");

        if (draft.Status == CommunityPublicationStatus.RevisionQueued)
            return HtmlPage(
                "Revisión en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya tiene otra revisión en curso. Cuando termine, vas a recibir otro mail para aprobarla o rechazarla.");

        if (draft.Status == CommunityPublicationStatus.MediaGenerationQueued)
            return HtmlPage(
                "Generación multimedia en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya fue aprobada en la etapa previa y la multimedia se está generando. Cuando la versión final esté lista, va a llegar otro mail de revisión.");

        if (draft.Status == CommunityPublicationStatus.PendingReview)
        {
            if (reviewStage == CommunityReviewStage.PreMedia)
            {
                RecordLinkAction(draft, "approved_pre_media", "APROBAR PRE-MULTIMEDIA (via link)");
                draft.Status = CommunityPublicationStatus.MediaGenerationQueued;
                draft.ApprovedAt = null;
                draft.RejectedAt = null;
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                draft.LastError = string.Empty;
                await db.SaveChangesAsync(ct);

                return HtmlPage(
                    "Plan aprobado",
                    $"Aprobaste el plan de la publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b>. Ahora quedó en cola la generación de imágenes o video finales. Cuando esa versión esté lista, vas a recibir otro mail para la aprobación final.",
                    success: true);
            }

            RecordLinkAction(draft, CommunityPublicationStatus.Approved, "APROBAR FINAL (via link)");
            draft.Status = CommunityPublicationStatus.Approved;
            draft.ApprovedAt = DateTimeOffset.UtcNow;
            draft.RejectedAt = null;
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            await db.SaveChangesAsync(ct);
        }

        var publishResult = await publisher.PublishApprovedDraftAsync(draft, ct);
        await db.SaveChangesAsync(ct);

        if (publishResult?.InstagramSuccess == true)
        {
            return HtmlPage(
                "Aprobada y publicada",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> fue aprobada y publicada en Instagram correctamente.",
                success: true);
        }

        logger.LogWarning("Draft {DraftId} was approved via link but automatic publish did not complete", draft.Id);
        return HtmlPage(
            "Aprobada",
            $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> quedó aprobada, pero la publicación automática no terminó correctamente. El equipo puede reintentar sin perder la aprobación.");
    }

    [HttpGet("{reviewToken}/reject")]
    public async Task<IActionResult> RejectForm(string reviewToken, CancellationToken ct)
    {
        var draft = await db.CommunityPublications.FirstOrDefaultAsync(p => p.ReviewToken == reviewToken, ct);
        if (draft is null)
            return HtmlPage("Link inválido", "No encontramos una publicación asociada a este link de revisión.");

        if (draft.Status == CommunityPublicationStatus.Published)
            return HtmlPage("Publicación ya enviada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya fue publicada y no puede rechazarse desde este link.");

        if (draft.Status == CommunityPublicationStatus.Denied)
            return HtmlPage("Publicación denegada", $"La propuesta <b>{WebUtility.HtmlEncode(draft.Topic)}</b> fue denegada internamente antes de enviarse a revisión y no puede rechazarse desde este link.");

        if (draft.Status == CommunityPublicationStatus.Rejected)
            return HtmlPage("Publicación ya rechazada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya estaba rechazada.");

        if (draft.Status == CommunityPublicationStatus.RevisionQueued)
            return HtmlPage(
                "Revisión en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya tiene otra revisión en curso con feedback previo. Cuando la nueva versión esté lista, vas a recibir otro mail.");

        if (draft.Status == CommunityPublicationStatus.MediaGenerationQueued)
            return HtmlPage(
                "Generación multimedia en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya está generando la multimedia final. Cuando termine, vas a recibir otro mail para la aprobación final.");

        return RejectFeedbackForm(draft.Topic);
    }

    [HttpPost("{reviewToken}/reject")]
    public async Task<IActionResult> RejectWithFeedback(
        string reviewToken,
        [FromForm] string? feedback,
        [FromForm] string? intent,
        CancellationToken ct)
    {
        var draft = await db.CommunityPublications.FirstOrDefaultAsync(p => p.ReviewToken == reviewToken, ct);
        if (draft is null)
            return HtmlPage("Link inválido", "No encontramos una publicación asociada a este link de revisión.");

        var reviewStage = CommunityReviewService.NormalizeReviewStage(draft.ReviewStage);

        if (draft.Status == CommunityPublicationStatus.Published)
            return HtmlPage("Publicación ya enviada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya fue publicada y no puede rechazarse desde este link.");

        if (draft.Status == CommunityPublicationStatus.Denied)
            return HtmlPage("Publicación denegada", $"La propuesta <b>{WebUtility.HtmlEncode(draft.Topic)}</b> fue denegada internamente antes de enviarse a revisión y no acepta feedback desde este link.");

        if (draft.Status == CommunityPublicationStatus.Rejected)
            return HtmlPage("Publicación ya rechazada", $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya estaba rechazada.");

        if (draft.Status == CommunityPublicationStatus.RevisionQueued)
            return HtmlPage(
                "Revisión en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya tiene otra revisión en curso con feedback previo. Esperá la próxima versión por mail.");

        if (draft.Status == CommunityPublicationStatus.MediaGenerationQueued)
            return HtmlPage(
                "Generación multimedia en proceso",
                $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya está generando su versión final. Cuando termine, vas a recibir otro mail para la aprobación final.");

        var trimmedFeedback = (feedback ?? "").Trim();
        var hasFeedback = !string.IsNullOrWhiteSpace(trimmedFeedback);
        var wantsRevision = hasFeedback;

        if (wantsRevision)
        {
            var revisionTarget = CommunityReviewService.DetectRevisionTarget(trimmedFeedback);
            logger.LogInformation("Draft {DraftId} link-based revision queued from review form", draft.Id);
            draft.Status = CommunityPublicationStatus.RevisionQueued;
            draft.LastReviewerFeedback = trimmedFeedback;
            draft.LastRevisionTarget = revisionTarget;
            draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                draft.ReviewerFeedbackHistoryJson,
                [new IncomingEmail(
                    MessageId: Guid.NewGuid().ToString("N"),
                    From: "review-link@novit.local",
                    Subject: draft.ReviewSubject,
                    Body: trimmedFeedback,
                    Date: DateTimeOffset.UtcNow,
                    InReplyTo: null)],
                CommunityPublicationStatus.PendingReview,
                revisionTarget);
            draft.ApprovedAt = null;
            draft.RejectedAt = null;
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            draft.LastError = reviewStage == CommunityReviewStage.PreMedia
                ? "Queued for asynchronous pre-media revision from the review link."
                : "Queued for asynchronous final-stage revision from the review link.";
            await db.SaveChangesAsync(ct);

            return HtmlPage(
                "Revisión en cola",
                $"Tu feedback fue guardado. La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> ya tiene una revisión en curso y vas a recibir la próxima versión por mail cuando salga.",
                success: true);
        }

        // Plain reject
        var rejectNote = string.IsNullOrWhiteSpace(trimmedFeedback)
            ? "RECHAZAR (via link)"
            : $"RECHAZAR con feedback: {trimmedFeedback}";
        RecordLinkAction(draft, CommunityPublicationStatus.Rejected, rejectNote);
        draft.Status = CommunityPublicationStatus.Rejected;
        draft.LastRevisionTarget = CommunityRevisionTarget.All;
        draft.LastReviewerFeedback = rejectNote;
        draft.ApprovedAt = null;
        draft.RejectedAt = DateTimeOffset.UtcNow;
        draft.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync(ct);

        return HtmlPage(
            "Publicación rechazada",
            $"La publicación <b>{WebUtility.HtmlEncode(draft.Topic)}</b> quedó rechazada.");
    }

    private static ContentResult RejectFeedbackForm(string topic)
    {
        var encodedTopic = WebUtility.HtmlEncode(topic);
        var html = $$"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rechazar publicación</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f4f7fb; color: #102033; margin: 0; }
    main { max-width: 640px; margin: 48px auto; background: #fff; border-radius: 16px; padding: 32px; box-shadow: 0 12px 30px rgba(16,32,51,.12); }
    h1 { margin: 0 0 12px; color: #8f2d2d; }
    p { line-height: 1.6; margin: 0 0 14px; }
    label { display: block; font-weight: bold; margin-bottom: 6px; }
    textarea { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; resize: vertical; min-height: 100px; font-family: inherit; }
    .hint { font-size: 13px; color: #666; margin-top: 6px; margin-bottom: 0; }
    .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
    .btn { padding: 10px 20px; border-radius: 999px; font-weight: 700; cursor: pointer; border: none; font-size: 14px; }
    .btn-reject { background: #8f2d2d; color: #fff; }
    .btn-revise { background: #1b4f7c; color: #fff; }
    .btn:hover { opacity: .88; }
  </style>
</head>
<body>
  <main>
    <h1>Rechazar publicación</h1>
    <p>Publicación: <b>{{encodedTopic}}</b></p>
    <form method="POST">
      <label for="feedback">Feedback (opcional):</label>
            <textarea id="feedback" name="feedback" placeholder="Escribí los cambios que querés. Si este campo tiene texto, siempre se tomará como pedido de revisión y recibirás una nueva versión por mail..."></textarea>
            <p class="hint">Si escribís feedback, siempre se pedirá revisión y te llegará una nueva propuesta. Para rechazarla definitivamente, dejá este campo vacío.</p>
      <div class="actions">
                <button type="submit" name="intent" value="revise" class="btn btn-revise">Pedir cambios y reenviar por mail</button>
                <button type="submit" name="intent" value="reject" class="btn btn-reject">Rechazar definitivamente</button>
      </div>
    </form>
  </main>
</body>
</html>
""";

        return new ContentResult
        {
            Content = html,
            ContentType = "text/html; charset=utf-8",
            StatusCode = StatusCodes.Status200OK,
        };
    }

    private static void RecordLinkAction(CommunityPublicationEntity draft, string action, string body)
    {
        draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
            draft.ReviewerFeedbackHistoryJson,
            [new IncomingEmail(
                MessageId: Guid.NewGuid().ToString("N"),
                From: "review-link@novit.local",
                Subject: draft.ReviewSubject,
                Body: body,
                Date: DateTimeOffset.UtcNow,
                InReplyTo: null)],
            action,
            draft.LastRevisionTarget);
    }

    private static ContentResult HtmlPage(string title, string message, bool success = false)
    {
        var accent = success ? "#1f7a4d" : "#1b4f7c";
        var html = $$"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{WebUtility.HtmlEncode(title)}}</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f4f7fb; color: #102033; margin: 0; }
    main { max-width: 640px; margin: 48px auto; background: #fff; border-radius: 16px; padding: 32px; box-shadow: 0 12px 30px rgba(16,32,51,.12); }
    h1 { margin: 0 0 16px; color: {{accent}}; }
    p { line-height: 1.6; margin: 0; }
  </style>
</head>
<body>
  <main>
    <h1>{{WebUtility.HtmlEncode(title)}}</h1>
    <p>{{message}}</p>
  </main>
</body>
</html>
""";

        return new ContentResult
        {
            Content = html,
            ContentType = "text/html; charset=utf-8",
            StatusCode = StatusCodes.Status200OK,
        };
    }
}