namespace Novit.Web.Api.Services;

/// <summary>
/// Defines the function-calling tools that are sent to Azure AI Foundry
/// so the model can request Cal.com scheduling operations.
/// </summary>
public static class ChatToolDefinitions
{
    public static List<object> GetAll() =>
    [
        new
        {
            type = "function",
            function = new
            {
                name = "get_available_slots",
                description = "Get available meeting time slots from the calendar for a date range. " +
                              "Use this when the lead wants to schedule a meeting and you need to show them available times. " +
                              "Always ask for or infer the lead's timezone before calling this.",
                parameters = new
                {
                    type = "object",
                    properties = new Dictionary<string, object>
                    {
                        ["date_from"] = new
                        {
                            type = "string",
                            description = "Start date in YYYY-MM-DD format (e.g. 2025-03-15). Should be today or a future date."
                        },
                        ["date_to"] = new
                        {
                            type = "string",
                            description = "End date in YYYY-MM-DD format (e.g. 2025-03-17). Range should typically be 1-5 business days."
                        },
                        ["meeting_type"] = new
                        {
                            type = "string",
                            description = "Type of meeting to schedule.",
                            @enum = new[] { "demo", "discovery" }
                        },
                        ["timezone"] = new
                        {
                            type = "string",
                            description = "IANA timezone of the lead (e.g. America/Argentina/Buenos_Aires, America/New_York, Europe/Madrid)."
                        }
                    },
                    required = new[] { "date_from", "date_to", "meeting_type", "timezone" }
                }
            }
        },
        new
        {
            type = "function",
            function = new
            {
                name = "create_booking",
                description = "Book a meeting slot with a member of Novit's sales team. " +
                              "Only call this after confirming the slot, the lead's name, email, and timezone. " +
                              "The start_time must be one of the slots returned by get_available_slots.",
                parameters = new
                {
                    type = "object",
                    properties = new Dictionary<string, object>
                    {
                        ["start_time"] = new
                        {
                            type = "string",
                            description = "Exact slot start time in ISO 8601 UTC format as returned by get_available_slots (e.g. 2025-03-15T14:00:00Z)."
                        },
                        ["meeting_type"] = new
                        {
                            type = "string",
                            description = "Type of meeting.",
                            @enum = new[] { "demo", "discovery" }
                        },
                        ["attendee_name"] = new
                        {
                            type = "string",
                            description = "Full name of the lead / attendee."
                        },
                        ["attendee_email"] = new
                        {
                            type = "string",
                            description = "Email address of the lead."
                        },
                        ["attendee_timezone"] = new
                        {
                            type = "string",
                            description = "IANA timezone of the lead."
                        },
                        ["company"] = new
                        {
                            type = "string",
                            description = "Company or organization name of the lead, if known."
                        },
                        ["notes"] = new
                        {
                            type = "string",
                            description = "REQUIRED. A concise summary of the conversation with the lead so far. " +
                                          "Include: lead's name, company, role, what they need, key pain points discussed, " +
                                          "and any relevant context that would help the sales team prepare for the meeting. " +
                                          "Write it as a brief professional recap in the same language as the conversation."
                        }
                    },
                    required = new[] { "start_time", "meeting_type", "attendee_name", "attendee_email", "attendee_timezone", "notes" }
                }
            }
        },
        new
        {
            type = "function",
            function = new
            {
                name = "cancel_booking",
                description = "Cancel an existing meeting booking. Use this when the lead asks to cancel a previously booked meeting.",
                parameters = new
                {
                    type = "object",
                    properties = new Dictionary<string, object>
                    {
                        ["booking_uid"] = new
                        {
                            type = "string",
                            description = "The unique identifier (UID) of the booking to cancel."
                        },
                        ["reason"] = new
                        {
                            type = "string",
                            description = "Optional reason for cancellation."
                        }
                    },
                    required = new[] { "booking_uid" }
                }
            }
        },
        new
        {
            type = "function",
            function = new
            {
                name = "reschedule_booking",
                description = "Reschedule an existing meeting to a different time. Use get_available_slots first to find the new slot.",
                parameters = new
                {
                    type = "object",
                    properties = new Dictionary<string, object>
                    {
                        ["booking_uid"] = new
                        {
                            type = "string",
                            description = "The unique identifier (UID) of the booking to reschedule."
                        },
                        ["new_start_time"] = new
                        {
                            type = "string",
                            description = "New slot start time in ISO 8601 UTC format."
                        },
                        ["reason"] = new
                        {
                            type = "string",
                            description = "Optional reason for rescheduling."
                        }
                    },
                    required = new[] { "booking_uid", "new_start_time" }
                }
            }
        },
        new
        {
            type = "function",
            function = new
            {
                name = "update_booking_notes",
                description = "Update the notes/description of an existing booking with new information gathered after scheduling. " +
                              "Use this when the lead provides additional context about their project after the meeting was already booked. " +
                              "The notes should be a complete updated summary (cumulative), not just the new info.",
                parameters = new
                {
                    type = "object",
                    properties = new Dictionary<string, object>
                    {
                        ["booking_uid"] = new
                        {
                            type = "string",
                            description = "The unique identifier (UID) of the booking to update."
                        },
                        ["notes"] = new
                        {
                            type = "string",
                            description = "The full updated summary of the conversation. Should include all previously known info " +
                                          "plus the new details. Write it as a professional brief for the sales team."
                        }
                    },
                    required = new[] { "booking_uid", "notes" }
                }
            }
        }
    ];
}
