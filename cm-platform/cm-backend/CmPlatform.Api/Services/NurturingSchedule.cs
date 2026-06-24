namespace CmPlatform.Api.Services;

public static class NurturingSchedule
{
    public static DateTime GetNextRollingIntervalUtc(int intervalMinutes)
    {
        var now = DateTime.UtcNow;
        var minutesSinceMidnight = now.TimeOfDay.TotalMinutes;
        var intervalsSinceMidnight = (int)(minutesSinceMidnight / intervalMinutes);
        return now.Date.AddMinutes((intervalsSinceMidnight + 1) * intervalMinutes);
    }
}
