using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Tests.Identity;

public sealed class LocalAuthPolicyTests
{
    [Theory]
    [InlineData("Development", true, true)]
    [InlineData("development", true, true)]
    [InlineData("Development", false, false)]
    [InlineData("Staging", true, false)]
    [InlineData("Production", true, false)]
    public void Local_auth_requires_development_and_explicit_configuration(
        string environment,
        bool configured,
        bool expected)
    {
        Assert.Equal(expected, LocalAuthPolicy.IsEnabled(environment, configured));
    }

    [Theory]
    [InlineData("Production", false, true, true)]
    [InlineData("Production", false, false, false)]
    [InlineData("Development", true, false, true)]
    public void Managed_test_server_switch_is_separate_from_development_configuration(
        string environment, bool configured, bool managed, bool expected)
    {
        Assert.Equal(expected, LocalAuthPolicy.IsEnabled(environment, configured, managed));
    }
}
