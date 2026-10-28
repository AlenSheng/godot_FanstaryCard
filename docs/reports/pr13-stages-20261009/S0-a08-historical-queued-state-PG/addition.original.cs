    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Historical_and_queued_claims_remain_limited_while_actual_postgres_room_is_preserved()
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
        foreach (var (caseId, mode) in new[] { ("PR13-A08.2-T01", "historical-counts"),
            ("PR13-A08.2-T02", "queued-fortyeight"), ("PR13-A08.2-T03", "unresolved-thirty") })
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo("python3")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
            };
            process.StartInfo.ArgumentList.Add("/control/history-state-guard.original.py");
            process.StartInfo.ArgumentList.Add(mode);
            Assert.True(process.Start());
            var stdout = process.StandardOutput.ReadToEndAsync(Ct);
            var stderr = process.StandardError.ReadToEndAsync(Ct);
            await process.WaitForExitAsync(Ct);
            Assert.Equal(0, process.ExitCode);
            Assert.Equal(string.Empty, await stderr);
            using var actual = JsonDocument.Parse(await stdout);
            Assert.True(actual.RootElement.GetProperty("ok").GetBoolean());
            Assert.Equal(mode, actual.RootElement.GetProperty("mode").GetString());
            var output = actual.RootElement.GetProperty("actual_policy_output");
            if (mode == "queued-fortyeight")
            {
                Assert.Equal(48, output.GetProperty("historical_queue_tasks").GetInt32());
                Assert.Equal(48, output.GetProperty("actual_classifier_observations").GetArrayLength());
                Assert.True(output.GetProperty("current_real_B_register_was_not_reclassified").GetBoolean());
            }
            else
            {
                Assert.Equal(0, output.GetProperty("current_passed").GetInt32());
                Assert.False(output.GetProperty("runtime_revalidated").GetBoolean());
                Assert.Equal("Blocked", output.GetProperty("comparison_state").GetString());
            }
            var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
            Assert.Equivalent(before, restored.Capture(), strict: true);
            Assert.Equal(durableBefore, await Raw(db, room.RoomId));
            Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
            Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
            Record(caseId, new { roomId = room.RoomId, actualConfigVersion = game.Version, cards,
                actualStateGuard = actual.RootElement.Clone(), actualExitCode = process.ExitCode,
                snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(restored.Capture()),
                databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)),
                actualMatches = 1, actualSnapshots = 1, productionSourceModified = false,
                actualHistoricalRawReconciliation = false, actualLoadOrCapacitySamples = 0 });
        }
    }
