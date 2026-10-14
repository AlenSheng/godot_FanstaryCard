    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_coordinator_verdict_faults_preserve_complete_postgres_room_and_exit_contracts()
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
        var cases = new[] {
            ("LOAD-02.1-T01", new[] { ("duration-short", 1) }),
            ("LOAD-02.1-T03", new[] { ("redline-and-invalid", 3) }),
            ("LOAD-02.3-T02", new[] { ("hang", 3) }),
            ("LOAD-02.3-T03", new[] { ("write-failure", 3) }),
            ("LOAD-02.4-T01", new[] { ("prepare-only", 0) }),
            ("LOAD-02.4-T02", new[] { ("redline", 2) }),
            ("LOAD-02.4-T03", new[] { ("invalid", 3), ("operator", 130) })
        };
        foreach (var (caseId, modes) in cases)
        {
            var observations = new List<object>();
            foreach (var (mode, expectedExit) in modes)
            {
                using var process = new Process();
                process.StartInfo = new ProcessStartInfo("python3")
                {
                    RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
                };
                process.StartInfo.ArgumentList.Add("/control/coordinator-fault-guard.original.py");
                process.StartInfo.ArgumentList.Add(mode);
                Assert.True(process.Start());
                var stdout = process.StandardOutput.ReadToEndAsync(Ct);
                var stderr = process.StandardError.ReadToEndAsync(Ct);
                await process.WaitForExitAsync(Ct);
                Assert.Equal(expectedExit, process.ExitCode);
                Assert.Equal(string.Empty, await stderr);
                using var actual = JsonDocument.Parse(await stdout);
                Assert.Equal(mode, actual.RootElement.GetProperty("mode").GetString());
                Assert.Equal(expectedExit, actual.RootElement.GetProperty("actual_child_exit_code").GetInt32());
                var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
                Assert.Equivalent(before, restored.Capture(), strict: true);
                Assert.Equal(durableBefore, await Raw(db, room.RoomId));
                observations.Add(new { mode, actualExitCode = process.ExitCode, actualObservation = actual.RootElement.Clone(),
                    snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(restored.Capture()),
                    databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)) });
            }
            Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
            Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
            Record(caseId, new { roomId = room.RoomId, actualConfigVersion = game.Version, cards,
                actualGuardObservations = observations, actualMatches = 1, actualSnapshots = 1,
                productionSourceModified = false, actualLoadOrCapacitySamples = 0 });
        }
    }
