using System.Reflection;
using FantasyCard.Server.Admin;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace FantasyCard.Server.Tests.Deploy;

public sealed class ProtobufPerimeterTests
{
    [Theory]
    [InlineData("http", null, 403)]
    [InlineData("https", null, 503)]
    [InlineData("https", "abcdefghijklmnopqrstuvwxyz0123456789", 200)]
    public void Admin_page_retains_security_headers_on_success_and_rejection(string scheme, string? key, int expected)
    {
        var context = new DefaultHttpContext();
        context.Request.Scheme = scheme;
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(
            new Dictionary<string, string?> { ["Admin:ApiKey"] = key }).Build();
        var method = typeof(AdminEndpoints).GetMethod("PageAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        var result = (IResult)method.Invoke(null, [context, configuration])!;
        Assert.Equal(expected, ((IStatusCodeHttpResult)result).StatusCode ?? 200);
        Assert.Equal("private, no-store", context.Response.Headers.CacheControl.ToString());
        Assert.Equal("nosniff", context.Response.Headers["X-Content-Type-Options"].ToString());
        if (expected == 200)
            Assert.StartsWith("text/html", ((IContentTypeHttpResult)result).ContentType);
    }
    [Theory]
    [InlineData("http", "", 403)]
    [InlineData("https", "wrong-key", 401)]
    [InlineData("https", "abcdefghijklmnopqrstuvwxyz0123456789", 200)]
    public async Task Admin_api_keeps_authentication_and_private_headers(string scheme, string supplied, int expected)
    {
        var context = new DefaultHttpContext();
        context.Request.Scheme = scheme;
        context.Request.Headers["X-Admin-Key"] = supplied;
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            { ["Admin:ApiKey"] = "abcdefghijklmnopqrstuvwxyz0123456789" }).Build();
        using var services = new ServiceCollection().AddSingleton<IConfiguration>(configuration).BuildServiceProvider();
        context.RequestServices = services;
        var invocation = new DefaultEndpointFilterInvocationContext(context);
        EndpointFilterDelegate next = _ => ValueTask.FromResult<object?>(Results.Ok());
        var method = typeof(AdminEndpoints).GetMethod("AuthorizeAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
        var result = await (ValueTask<object?>)method.Invoke(null, [invocation, next])!;
        Assert.Equal(expected, ((IStatusCodeHttpResult)result!).StatusCode);
        Assert.Equal("private, no-store", context.Response.Headers.CacheControl.ToString());
        Assert.Equal("nosniff", context.Response.Headers["X-Content-Type-Options"].ToString());
    }}
