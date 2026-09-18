namespace FantasyCard.Server.Tests.Deploy;

public sealed class CaddyfileTests
{
    [Fact]
    public void Domain_sites_must_not_share_the_ip_self_signed_certificate()
    {
        var caddyfile = File.ReadAllText(FindServerFile("Caddyfile"));
        var sites = ParseSites(caddyfile);

        Assert.DoesNotContain(sites, site => SiteMatches(site.Address, ":443"));
        var domain = Assert.Single(sites, site =>
            SiteMatches(site.Address, "www.relicbound.cn") || SiteMatches(site.Address, "relicbound.cn"));
        Assert.DoesNotContain("tls /etc/caddy/certs/", domain.Body, StringComparison.Ordinal);
        Assert.Contains("reverse_proxy server:8080", domain.Body, StringComparison.Ordinal);
        Assert.Contains("Strict-Transport-Security", domain.Body, StringComparison.Ordinal);

        var ip = Assert.Single(sites, site => SiteMatches(site.Address, "43.172.70.182"));
        Assert.Contains("tls /etc/caddy/certs/ip2.crt", ip.Body, StringComparison.Ordinal);
        Assert.Contains("respond 404", ip.Body, StringComparison.Ordinal);
        Assert.DoesNotContain("reverse_proxy", ip.Body, StringComparison.Ordinal);

        var admin = Assert.Single(sites, site => SiteMatches(site.Address, ":20000"));
        Assert.Contains("tls /etc/caddy/certs/ip2.crt", admin.Body, StringComparison.Ordinal);
        Assert.Contains("reverse_proxy server:8080", admin.Body, StringComparison.Ordinal);
    }

    [Fact]
    public void Cloud_compose_must_fail_closed_in_production()
    {
        var compose = File.ReadAllText(FindServerFile("compose.cloud.yaml"));

        Assert.Contains("ASPNETCORE_ENVIRONMENT: Production", compose, StringComparison.Ordinal);
        Assert.Contains("Identity__EnableLocalAuth: \"false\"", compose, StringComparison.Ordinal);
        Assert.Contains("FANTASYCARD_ADMIN_KEY:?", compose, StringComparison.Ordinal);
        Assert.Contains("\"127.0.0.1:20000:20000\"", compose, StringComparison.Ordinal);
        Assert.Contains("read_only: true", compose, StringComparison.Ordinal);
        Assert.Contains("no-new-privileges:true", compose, StringComparison.Ordinal);
        Assert.DoesNotContain("ASPNETCORE_ENVIRONMENT: Development", compose, StringComparison.Ordinal);
        Assert.DoesNotContain("\"20000:20000\"", compose.Replace(
            "\"127.0.0.1:20000:20000\"", "", StringComparison.Ordinal), StringComparison.Ordinal);
    }

    [Fact]
    public void Cloud_health_check_must_verify_the_public_domain_certificate()
    {
        var script = File.ReadAllText(FindServerFile(Path.Combine("deploy", "fantasycard-update.sh")));
        Assert.Contains("https://www.relicbound.cn/health/ready", script, StringComparison.Ordinal);
        Assert.Contains("domain_certificate_ok", script, StringComparison.Ordinal);
        Assert.Contains("-servername www.relicbound.cn", script, StringComparison.Ordinal);
        Assert.DoesNotContain("curl -k", script, StringComparison.Ordinal);
        Assert.DoesNotContain("curl --insecure", script, StringComparison.Ordinal);
    }

    private static bool SiteMatches(string address, string host) =>
        address.Split(',').Select(part => part.Trim()).Contains(host, StringComparer.Ordinal);

    private static string FindServerFile(string relativePath)
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var nested = Path.Combine(directory.FullName, "server", relativePath);
            if (File.Exists(nested)) return nested;
            var local = Path.Combine(directory.FullName, relativePath);
            if (File.Exists(local) && File.Exists(Path.Combine(directory.FullName, "compose.cloud.yaml")))
                return local;
            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException($"Could not locate server/{relativePath}.");
    }

    private static List<(string Address, string Body)> ParseSites(string caddyfile)
    {
        var sites = new List<(string Address, string Body)>();
        var lines = caddyfile.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n');
        string? address = null;
        var body = new List<string>();
        var depth = 0;
        foreach (var raw in lines)
        {
            var line = raw.Trim();
            if (line.StartsWith('#') && depth == 0) continue;
            if (depth == 0 && line.EndsWith('{'))
            {
                address = line[..^1].Trim();
                body.Clear();
                depth = 1;
                continue;
            }

            if (address is null) continue;
            depth += line.Count(character => character == '{');
            depth -= line.Count(character => character == '}');
            if (depth > 0) body.Add(line);
            if (depth == 0)
            {
                sites.Add((address, string.Join('\n', body)));
                address = null;
            }
        }

        return sites;
    }
}
