using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class NurturingHoldResumeTests
{
    [Theory]
    [InlineData("no enviar", true)]
    [InlineData("NO ENVIAR", true)]
    [InlineData("No quiero que se envíe, dejalo en standby", true)]
    [InlineData("Ponelo en espera por favor", true)]
    [InlineData("Hay que pausar este newsletter", true)]
    [InlineData("Suspender el envío", true)]
    [InlineData("Detener el envío hasta nuevo aviso", true)]
    [InlineData("No se envie este mes", true)]
    [InlineData("Me parece bien, solo cambiar el título", false)]
    [InlineData("Ok, se ve bien", false)]
    [InlineData("Corregir el segundo párrafo", false)]
    public void IsHoldRequest_ReturnsExpected(string body, bool expected)
    {
        Assert.Equal(expected, NurturingWorkflowSupport.IsHoldRequest(body));
    }

    [Theory]
    [InlineData("reanudar", true)]
    [InlineData("REANUDAR", true)]
    [InlineData("ok, dale, enviar", true)]
    [InlineData("aprobar", true)]
    [InlineData("Aprobado, se puede enviar", true)]
    [InlineData("Retomar el envío", true)]
    [InlineData("Activar el newsletter", true)]
    [InlineData("no enviar", false)]       // hold takes priority
    [InlineData("No se envie", false)]     // hold takes priority
    [InlineData("Corregir el título", false)] // not a resume keyword
    public void IsResumeRequest_ReturnsExpected(string body, bool expected)
    {
        Assert.Equal(expected, NurturingWorkflowSupport.IsResumeRequest(body));
    }

    [Fact]
    public void HoldKeywords_TakePriority_OverResumeKeywords()
    {
        // "no enviar" contains "enviar" but hold should take priority
        var body = "no enviar este mes";
        Assert.True(NurturingWorkflowSupport.IsHoldRequest(body));
        Assert.False(NurturingWorkflowSupport.IsResumeRequest(body));
    }
}
