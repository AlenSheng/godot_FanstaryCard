    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_dirty_compiled_test_source_has_separate_hash_while_persisted_room_is_unchanged()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var game = GameConfigCatalog.Current;
        var catalog = new CombatCardCatalog(game.Cards.Select(card => new CombatCardDefinition(card.CardId, card.Effect)));
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
            .Concat(Enumerable.Range(1, 7).Select(i => $"GUA-{i:D2}")).ToArray();
        var room = Room(HeroClass.Guardian, game.Numerics, weaponLevel: 0,
            catalog: catalog, cards: cards, configVersion: game.Version);
        await Persist(db, repository, room);
        var before = room.Capture();
        var durableBefore = await Raw(db, room.RoomId);
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo("python3")
        {
            RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
        };
        process.StartInfo.ArgumentList.Add("/control/dirty-source-guard.original.py");
        Assert.True(process.Start());
        var stdout = process.StandardOutput.ReadToEndAsync(Ct);
        var stderr = process.StandardError.ReadToEndAsync(Ct);
        await process.WaitForExitAsync(Ct);
        Assert.Equal(0, process.ExitCode);
        Assert.Equal(string.Empty, await stderr);
        using var actual = JsonDocument.Parse(await stdout);
        var clean = actual.RootElement.GetProperty("clean");
        var dirty = actual.RootElement.GetProperty("dirty");
        const string source = "server/tests/FantasyCard.Server.Tests/Persistence/PostgresNumericalContractTests.cs";
        Assert.False(clean.GetProperty("git_dirty").GetBoolean());
        Assert.True(dirty.GetProperty("git_dirty").GetBoolean());
        Assert.Equal(clean.GetProperty("git_commit").GetString(), dirty.GetProperty("git_commit").GetString());
        Assert.NotEqual(clean.GetProperty("sha256").GetProperty(source).GetString(),
            dirty.GetProperty("sha256").GetProperty(source).GetString());
        Assert.True(actual.RootElement.GetProperty("compiled_dirty_source_matches_frozen_insertion").GetBoolean());
        Assert.False(actual.RootElement.GetProperty("owned_snapshot_commit_is_release_commit").GetBoolean());
        var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
        Assert.Equivalent(before, restored.Capture(), strict: true);
        Assert.Equal(durableBefore, await Raw(db, room.RoomId));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
        var assembly = typeof(PostgresNumericalContractTests).Assembly.Location;
        Record("PR13-A08.1-T02", new { roomId = room.RoomId, actualConfigVersion = game.Version, cards,
            actualProvenance = actual.RootElement.Clone(),
            actualDirtyTestAssemblySha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assembly))).ToLowerInvariant(),
            snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(restored.Capture()),
            databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)),
            actualMatches = 1, actualSnapshots = 1, productionSourceModified = false });
    }
