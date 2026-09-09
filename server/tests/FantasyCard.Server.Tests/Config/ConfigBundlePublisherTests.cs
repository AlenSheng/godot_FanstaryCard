using FantasyCard.ConfigExporter;

namespace FantasyCard.Server.Tests.Config;

public sealed class ConfigBundlePublisherTests
{
    [Fact]
    public void Publish_writes_identical_bundle_to_server_and_client()
    {
        var root = Path.Combine(Path.GetTempPath(), "fantasycard-config-test-" + Guid.NewGuid().ToString("N"));
        var server = Path.Combine(root, "server");
        var client = Path.Combine(root, "client");
        try
        {
            ConfigBundlePublisher.Publish(server, client, [1, 2, 3], "v-test", "abc123");

            Assert.Equal(File.ReadAllBytes(Path.Combine(server, "fantasycard.config.bytes")), File.ReadAllBytes(Path.Combine(client, "fantasycard.config.bytes")));
            Assert.Equal("v-test", File.ReadAllText(Path.Combine(server, "fantasycard.config.version.txt")).Trim());
            Assert.Equal("abc123", File.ReadAllText(Path.Combine(client, "fantasycard.config.sha256")).Trim());
            Assert.Empty(Directory.GetFiles(root, "*.stage-*", SearchOption.AllDirectories));
            Assert.Empty(Directory.GetFiles(root, "*.backup-*", SearchOption.AllDirectories));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void Publish_replaces_existing_files_on_both_sides()
    {
        var root = Path.Combine(Path.GetTempPath(), "fantasycard-config-test-" + Guid.NewGuid().ToString("N"));
        var server = Path.Combine(root, "server");
        var client = Path.Combine(root, "client");
        try
        {
            ConfigBundlePublisher.Publish(server, client, [1], "v1", "hash1");
            ConfigBundlePublisher.Publish(server, client, [2], "v2", "hash2");

            Assert.Equal([2], File.ReadAllBytes(Path.Combine(server, "fantasycard.config.bytes")));
            Assert.Equal([2], File.ReadAllBytes(Path.Combine(client, "fantasycard.config.bytes")));
            Assert.Equal("v2", File.ReadAllText(Path.Combine(server, "fantasycard.config.version.txt")).Trim());
            Assert.Equal("hash2", File.ReadAllText(Path.Combine(client, "fantasycard.config.sha256")).Trim());
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void Publish_restores_server_bundle_when_client_commit_fails()
    {
        var root = Path.Combine(Path.GetTempPath(), "fantasycard-config-test-" + Guid.NewGuid().ToString("N"));
        var server = Path.Combine(root, "server");
        var client = Path.Combine(root, "client");
        try
        {
            ConfigBundlePublisher.Publish(server, client, [1], "v1", "hash1");
            var blockedClientTarget = Path.Combine(client, "fantasycard.config.bytes");
            File.Delete(blockedClientTarget);
            Directory.CreateDirectory(blockedClientTarget);

            Assert.ThrowsAny<IOException>(() =>
                ConfigBundlePublisher.Publish(server, client, [2], "v2", "hash2"));

            Assert.Equal([1], File.ReadAllBytes(Path.Combine(server, "fantasycard.config.bytes")));
            Assert.Equal("v1", File.ReadAllText(Path.Combine(server, "fantasycard.config.version.txt")).Trim());
            Assert.Equal("hash1", File.ReadAllText(Path.Combine(server, "fantasycard.config.sha256")).Trim());
            Assert.Equal("v1", File.ReadAllText(Path.Combine(client, "fantasycard.config.version.txt")).Trim());
            Assert.Equal("hash1", File.ReadAllText(Path.Combine(client, "fantasycard.config.sha256")).Trim());
            Assert.Empty(Directory.GetFiles(root, "*.stage-*", SearchOption.AllDirectories));
            Assert.Empty(Directory.GetFiles(root, "*.backup-*", SearchOption.AllDirectories));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
