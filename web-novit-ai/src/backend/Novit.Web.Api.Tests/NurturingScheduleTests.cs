using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class NurturingScheduleTests
{
    [Theory]
    [InlineData(2026, 4, 1, 8)]
    [InlineData(2026, 4, 2, 22)]
    [InlineData(2026, 5, 1, 13)]
    [InlineData(2026, 5, 2, 27)]
    public void GetCycleSlot_ReturnsExpectedWednesday(int year, int month, int cycle, int expectedDay)
    {
        var slot = NurturingSchedule.GetCycleSlot(year, month, cycle);

        Assert.Equal(new DateOnly(year, month, expectedDay), slot.SendDate);
        Assert.Equal(DayOfWeek.Wednesday, slot.SendDate.DayOfWeek);
        Assert.Equal($"{year}-{month:D2}-c{cycle}", slot.CycleKey);
    }

    [Theory]
    [InlineData(2026, 4, 1, 3)]
    [InlineData(2026, 4, 2, 17)]
    [InlineData(2026, 5, 1, 8)]
    [InlineData(2026, 5, 2, 22)]
    public void GetCycleSlot_ReturnsExpectedPreviousFriday(int year, int month, int cycle, int expectedDay)
    {
        var slot = NurturingSchedule.GetCycleSlot(year, month, cycle);

        Assert.Equal(new DateOnly(year, month, expectedDay), slot.GenerationDate);
        Assert.Equal(DayOfWeek.Friday, slot.GenerationDate.DayOfWeek);
    }

    [Theory]
    [InlineData(2026, 4, 3, true, 1)]
    [InlineData(2026, 4, 17, true, 2)]
    [InlineData(2026, 4, 8, false, 0)]
    [InlineData(2026, 4, 10, false, 0)]
    public void TryGetGenerationCycle_ReturnsExpected(int year, int month, int day, bool expected, int cycleNumber)
    {
        var today = new DateOnly(year, month, day);
        var result = NurturingSchedule.TryGetGenerationCycle(today, out var slot);

        Assert.Equal(expected, result);
        if (expected)
            Assert.Equal(cycleNumber, slot.CycleNumber);
    }

    [Theory]
    [InlineData(2026, 4, 8, true, 1)]
    [InlineData(2026, 4, 22, true, 2)]
    [InlineData(2026, 4, 17, false, 0)]
    [InlineData(2026, 4, 29, false, 0)]
    public void TryGetSendCycle_ReturnsExpected(int year, int month, int day, bool expected, int cycleNumber)
    {
        var today = new DateOnly(year, month, day);
        var result = NurturingSchedule.TryGetSendCycle(today, out var slot);

        Assert.Equal(expected, result);
        if (expected)
            Assert.Equal(cycleNumber, slot.CycleNumber);
    }

    [Theory]
    [InlineData(2026, 4, 3, true, 1)]
    [InlineData(2026, 4, 6, true, 1)]
    [InlineData(2026, 4, 7, true, 1)]
    [InlineData(2026, 4, 8, true, 1)]
    [InlineData(2026, 4, 11, false, 0)]
    [InlineData(2026, 4, 17, true, 2)]
    [InlineData(2026, 4, 20, true, 2)]
    [InlineData(2026, 4, 21, true, 2)]
    [InlineData(2026, 4, 22, true, 2)]
    [InlineData(2026, 4, 25, false, 0)]
    public void TryGetValidationCycle_ReturnsExpected(int year, int month, int day, bool expected, int cycleNumber)
    {
        var today = new DateOnly(year, month, day);
        var result = NurturingSchedule.TryGetValidationCycle(today, out var slot);

        Assert.Equal(expected, result);
        if (expected)
            Assert.Equal(cycleNumber, slot.CycleNumber);
    }

    [Fact]
    public void GetUpcomingCycles_ReturnsCyclesInChronologicalOrder()
    {
        var cycles = NurturingSchedule.GetUpcomingCycles(new DateOnly(2026, 4, 9), 4);

        Assert.Equal(4, cycles.Count);
        Assert.Equal("2026-04-c2", cycles[0].CycleKey);
        Assert.Equal("2026-05-c1", cycles[1].CycleKey);
        Assert.Equal("2026-05-c2", cycles[2].CycleKey);
        Assert.Equal("2026-06-c1", cycles[3].CycleKey);
    }

    [Theory]
    [InlineData(2026, 4, 3, true)]
    [InlineData(2026, 4, 4, false)]
    [InlineData(2026, 4, 5, false)]
    [InlineData(2026, 4, 6, true)]
    public void IsBusinessDay_ReturnsExpected(int year, int month, int day, bool expected)
    {
        var today = new DateOnly(year, month, day);
        Assert.Equal(expected, NurturingSchedule.IsBusinessDay(today));
    }

    [Theory]
    [InlineData(2026, 4, 22, 11, 0, true)]
    [InlineData(2026, 4, 22, 11, 14, true)]
    [InlineData(2026, 4, 22, 10, 59, false)]
    [InlineData(2026, 4, 22, 11, 15, false)]
    [InlineData(2026, 4, 22, 17, 0, false)]
    public void IsAutomaticDispatchTime_ReturnsExpected(int year, int month, int day, int hour, int minute, bool expected)
    {
        var localTime = new DateTime(year, month, day, hour, minute, 0, DateTimeKind.Unspecified);

        Assert.Equal(expected, NurturingSchedule.IsAutomaticDispatchTime(localTime));
    }

    [Theory]
    [InlineData("2026-04-27T21:03:10Z", 5, "2026-04-27T21:05:00Z")]
    [InlineData("2026-04-27T21:05:00Z", 5, "2026-04-27T21:10:00Z")]
    [InlineData("2026-04-27T21:14:59Z", 5, "2026-04-27T21:15:00Z")]
    public void GetNextRollingIntervalUtc_ReturnsExpected(string utcNow, int intervalMinutes, string expectedUtc)
    {
        var nextRun = NurturingSchedule.GetNextRollingIntervalUtc(DateTime.Parse(utcNow), intervalMinutes);

        Assert.Equal(DateTime.Parse(expectedUtc).ToUniversalTime(), nextRun);
    }
}
