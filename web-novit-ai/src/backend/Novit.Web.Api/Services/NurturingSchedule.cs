namespace Novit.Web.Api.Services;

public readonly record struct NurturingCycleSlot(
    int Year,
    int Month,
    int CycleNumber,
    DateOnly GenerationDate,
    DateOnly SendDate)
{
    public string CycleKey => $"{Year}-{Month:D2}-c{CycleNumber}";
}

/// <summary>
/// Pure helper methods for nurturing schedule calculations.
/// All methods are static and deterministic for easy unit testing.
/// </summary>
public static class NurturingSchedule
{
    private static readonly TimeZoneInfo BuenosAires = TimeZoneInfo.FindSystemTimeZoneById("America/Buenos_Aires");

    /// <summary>Returns the nth Wednesday of the given month.</summary>
    public static DateOnly GetNthWednesday(int year, int month, int occurrence)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(occurrence, 1);

        var firstDay = new DateOnly(year, month, 1);
        var offset = ((int)DayOfWeek.Wednesday - (int)firstDay.DayOfWeek + 7) % 7;
        var result = firstDay.AddDays(offset + ((occurrence - 1) * 7));

        if (result.Month != month)
            throw new ArgumentOutOfRangeException(nameof(occurrence), $"Month {month}/{year} does not have a {occurrence}th Wednesday.");

        return result;
    }

    /// <summary>Returns the Friday immediately before the given date.</summary>
    public static DateOnly GetPreviousFriday(DateOnly date)
    {
        var offset = ((int)date.DayOfWeek - (int)DayOfWeek.Friday + 7) % 7;
        if (offset == 0)
            offset = 7;

        return date.AddDays(-offset);
    }

    /// <summary>Returns the configured cycle slot for the given month.</summary>
    public static NurturingCycleSlot GetCycleSlot(int year, int month, int cycleNumber)
    {
        var sendDate = cycleNumber switch
        {
            1 => GetNthWednesday(year, month, 2),
            2 => GetNthWednesday(year, month, 4),
            _ => throw new ArgumentOutOfRangeException(nameof(cycleNumber), "Only cycle 1 (2nd Wednesday) and cycle 2 (4th Wednesday) are supported.")
        };

        return new NurturingCycleSlot(year, month, cycleNumber, GetPreviousFriday(sendDate), sendDate);
    }

    /// <summary>True if <paramref name="today"/> is a business day (Mon-Fri).</summary>
    public static bool IsBusinessDay(DateOnly today)
    {
        return today.DayOfWeek is >= DayOfWeek.Monday and <= DayOfWeek.Friday;
    }

    /// <summary>True if <paramref name="today"/> is the automatic review generation day for a cycle.</summary>
    public static bool TryGetGenerationCycle(DateOnly today, out NurturingCycleSlot slot)
    {
        foreach (var candidate in GetMonthCycles(today.Year, today.Month))
        {
            if (candidate.GenerationDate == today)
            {
                slot = candidate;
                return true;
            }
        }

        slot = default;
        return false;
    }

    /// <summary>True if <paramref name="today"/> is the scheduled send day for a cycle.</summary>
    public static bool TryGetSendCycle(DateOnly today, out NurturingCycleSlot slot)
    {
        foreach (var candidate in GetMonthCycles(today.Year, today.Month))
        {
            if (candidate.SendDate == today)
            {
                slot = candidate;
                return true;
            }
        }

        slot = default;
        return false;
    }

    /// <summary>True if <paramref name="today"/> falls within the validation window of a cycle.</summary>
    public static bool TryGetValidationCycle(DateOnly today, out NurturingCycleSlot slot)
    {
        if (!IsBusinessDay(today))
        {
            slot = default;
            return false;
        }

        foreach (var candidate in GetMonthCycles(today.Year, today.Month))
        {
            if (today >= candidate.GenerationDate && today <= candidate.SendDate)
            {
                slot = candidate;
                return true;
            }
        }

        slot = default;
        return false;
    }

    /// <summary>Returns upcoming cycle slots ordered by send date.</summary>
    public static IReadOnlyList<NurturingCycleSlot> GetUpcomingCycles(DateOnly today, int count = 4)
    {
        var results = new List<NurturingCycleSlot>(count);
        var cursor = new DateOnly(today.Year, today.Month, 1);

        while (results.Count < count)
        {
            foreach (var slot in GetMonthCycles(cursor.Year, cursor.Month))
            {
                if (slot.SendDate >= today)
                    results.Add(slot);

                if (results.Count == count)
                    break;
            }

            cursor = cursor.AddMonths(1);
        }

        return results;
    }

    /// <summary>Returns the current date in Buenos Aires timezone.</summary>
    public static DateOnly TodayInBuenosAires()
    {
        var now = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, BuenosAires);
        return DateOnly.FromDateTime(now);
    }

    /// <summary>Returns the current time in Buenos Aires timezone.</summary>
    public static DateTime NowInBuenosAires()
    {
        return TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, BuenosAires);
    }

    /// <summary>
    /// True only during the automatic 11:00 AM Argentina run window.
    /// This gate is used for newsletter generation and final send so those actions
    /// cannot be retriggered by the 15-minute validation/reply polling loop.
    /// </summary>
    public static bool IsAutomaticDispatchTime(DateTime localBuenosAiresTime, int windowMinutes = 15)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(windowMinutes, 1);

        return localBuenosAiresTime.Hour == 11 &&
               localBuenosAiresTime.Minute < windowMinutes;
    }

    /// <summary>
    /// Returns the next occurrence of 11:00 AM Buenos Aires time on a business day.
    /// </summary>
    public static DateTime GetNextRunUtc()
    {
        var now = NowInBuenosAires();
        var targetLocal = now.Date.AddHours(11); // 11:00 AM ARG

        if (now >= targetLocal)
            targetLocal = targetLocal.AddDays(1);

        while (!IsBusinessDay(DateOnly.FromDateTime(targetLocal)))
            targetLocal = targetLocal.Date.AddDays(1).AddHours(11);

        return TimeZoneInfo.ConvertTimeToUtc(targetLocal, BuenosAires);
    }

    /// <summary>
    /// During an active validation window, returns the next 15-minute check during business hours (9–18 ARG).
    /// Outside validation windows, falls back to the standard 11:00 AM business-day run.
    /// </summary>
    public static DateTime GetNextValidationCheckUtc(int intervalMinutes = 15)
    {
        var now = NowInBuenosAires();
        var today = DateOnly.FromDateTime(now);

        if (TryGetValidationCycle(today, out _))
        {
            var businessStart = now.Date.AddHours(9);
            var businessEnd = now.Date.AddHours(18);

            if (now < businessStart)
                return TimeZoneInfo.ConvertTimeToUtc(businessStart, BuenosAires);

            if (now < businessEnd)
            {
                var nextCheck = RoundUpToNextInterval(now, intervalMinutes);
                if (nextCheck < businessEnd)
                    return TimeZoneInfo.ConvertTimeToUtc(nextCheck, BuenosAires);
            }
        }

        for (var cursor = today.AddDays(1); cursor <= today.AddDays(45); cursor = cursor.AddDays(1))
        {
            if (TryGetValidationCycle(cursor, out _))
            {
                var nextBusinessCheck = cursor.ToDateTime(new TimeOnly(9, 0));
                return TimeZoneInfo.ConvertTimeToUtc(nextBusinessCheck, BuenosAires);
            }
        }

        return GetNextRunUtc();
    }

    /// <summary>
    /// Returns the next rolling UTC interval regardless of newsletter windows.
    /// Community review approvals use this path so manual drafts are not blocked
    /// by the nurturing calendar.
    /// </summary>
    public static DateTime GetNextRollingIntervalUtc(int intervalMinutes = 5)
    {
        return GetNextRollingIntervalUtc(DateTime.UtcNow, intervalMinutes);
    }

    internal static DateTime GetNextRollingIntervalUtc(DateTime utcNow, int intervalMinutes)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(intervalMinutes, 1);

        var normalizedUtc = utcNow.Kind == DateTimeKind.Utc
            ? utcNow
            : utcNow.ToUniversalTime();

        return RoundUpToNextInterval(normalizedUtc, intervalMinutes);
    }

    private static IEnumerable<NurturingCycleSlot> GetMonthCycles(int year, int month)
    {
        yield return GetCycleSlot(year, month, 1);
        yield return GetCycleSlot(year, month, 2);
    }

    private static DateTime RoundUpToNextInterval(DateTime dateTime, int intervalMinutes)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(intervalMinutes, 1);

        var truncated = new DateTime(dateTime.Year, dateTime.Month, dateTime.Day, dateTime.Hour, dateTime.Minute, 0, dateTime.Kind);
        var minutesToAdd = intervalMinutes - (truncated.Minute % intervalMinutes);
        if (minutesToAdd == 0)
            minutesToAdd = intervalMinutes;

        return truncated.AddMinutes(minutesToAdd);
    }
}
