
    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Source_workbook_reexport_mismatch_cannot_replace_a_persisted_room()
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
        var durableBefore = await Raw(db, room.RoomId);
        var before = room.Capture();
        var matchesBefore = await db.ScalarAsync<long>("SELECT count(*) FROM matches");
        var snapshotsBefore = await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots");
        using var resource = typeof(GameConfigCatalog).Assembly.GetManifestResourceStream(
            "FantasyCard.Config.fantasycard.config.bytes")!;
        using var resourceBytes = new MemoryStream();
        resource.CopyTo(resourceBytes);
        var published = File.ReadAllBytes("/control/base-root/server/config/generated/fantasycard.config.bytes");
        Assert.Equal(HashBytes(published), HashBytes(resourceBytes.ToArray()));

        async Task<(int Exit, JsonDocument Report)> Check(string root)
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo("python3")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
            };
            process.StartInfo.ArgumentList.Add("/control/base-root/tools/source-export-guard.original.py");
            process.StartInfo.ArgumentList.Add(root);
            Assert.True(process.Start());
            var stdout = process.StandardOutput.ReadToEndAsync(Ct);
            var stderr = process.StandardError.ReadToEndAsync(Ct);
            await process.WaitForExitAsync(Ct);
            Assert.Equal(string.Empty, await stderr);
            return (process.ExitCode, JsonDocument.Parse(await stdout));
        }
        var positive = await Check("positive");
        using var positiveReport = positive.Report;
        Assert.Equal(0, positive.Exit);
        Assert.Equal("ValidExport", positiveReport.RootElement.GetProperty("state").GetString());
        Assert.Equal(game.Version, positiveReport.RootElement.GetProperty("version").GetString());
        var negative = await Check("negative");
        using var negativeReport = negative.Report;
        Assert.Equal(3, negative.Exit);
        Assert.Equal("Blocked", negativeReport.RootElement.GetProperty("state").GetString());
        Assert.False(negativeReport.RootElement.GetProperty("runtime_stage_created").GetBoolean());
        Assert.Equal("Source re-export differs from frozen published config",
            negativeReport.RootElement.GetProperty("reason").GetString());
        var witness = JsonDocument.Parse(File.ReadAllText("/control/source-export-witness.original.json"));
        using (witness)
        {
            Assert.True(witness.RootElement.GetProperty("same_export_version").GetBoolean());
            Assert.True(witness.RootElement.GetProperty("original_export_matches_published").GetBoolean());
            Assert.True(witness.RootElement.GetProperty("changed_reexport_embedded_hash_valid").GetBoolean());
            Assert.Equal(1, witness.RootElement.GetProperty("changed_semantic_cells").GetInt32());
            var after = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
            Assert.Equivalent(before, after.Capture(), strict: true);
            Assert.Equal(durableBefore, await Raw(db, room.RoomId));
            Assert.Equal(matchesBefore, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
            Assert.Equal(snapshotsBefore, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
            Record("PR13-B12.1-T01", new
            {
                roomId = room.RoomId, actualConfigVersion = game.Version, cards,
                embeddedPublishedBytesSha256 = HashBytes(resourceBytes.ToArray()),
                originalPublishedBytesSha256 = HashBytes(published),
                actualPositiveExitCode = positive.Exit, actualInvalidExitCode = negative.Exit,
                actualPositive = positiveReport.RootElement.Clone(),
                actualRejection = negativeReport.RootElement.Clone(),
                actualSourceExportWitness = witness.RootElement.Clone(),
                snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(after.Capture()),
                databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)),
                matchesBefore, matchesAfter = await db.ScalarAsync<long>("SELECT count(*) FROM matches"),
                snapshotsBefore, snapshotsAfter = await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"),
                candidateAdmitted = false, productionSourceModified = false
            });
        }
    }
