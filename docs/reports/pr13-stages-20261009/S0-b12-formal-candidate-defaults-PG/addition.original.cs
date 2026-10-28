
    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Formal_candidate_default_flags_are_rejected_without_changing_persisted_room()
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
        var cases = new[] { "baseline", "cards_spent_draw", "fractional_guardian",
            "optional_monster_pool", "budgeted_bot_loot", "mortal_bot_pve", "monster_capacity" };
        var observations = new List<object>();
        foreach (var mode in cases)
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo("python3")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false
            };
            process.StartInfo.ArgumentList.Add("/control/default-policy-guard.original.py");
            process.StartInfo.ArgumentList.Add(mode);
            Assert.True(process.Start());
            var stdout = process.StandardOutput.ReadToEndAsync(Ct);
            var stderr = process.StandardError.ReadToEndAsync(Ct);
            await process.WaitForExitAsync(Ct);
            Assert.Equal(string.Empty, await stderr);
            using var actual = JsonDocument.Parse(await stdout);
            Assert.Equal(mode == "baseline" ? 0 : 3, process.ExitCode);
            Assert.Equal(mode == "baseline" ? "ValidDefault" : "Blocked",
                actual.RootElement.GetProperty("state").GetString());
            if (mode != "baseline")
                Assert.Equal("Formal numerical candidate defaults changed; isolate experiments and retain the frozen default policy",
                    actual.RootElement.GetProperty("reason").GetString());
            var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId, Ct))!, catalog, 999);
            Assert.Equivalent(before, restored.Capture(), strict: true);
            Assert.Equal(durableBefore, await Raw(db, room.RoomId));
            Assert.False(restored.Numerics.CardsSpentDraw);
            Assert.False(restored.Numerics.FractionalGuardian);
            Assert.False(restored.Numerics.OptionalMonsterPool);
            var combat = restored.GetPlayer(before.Players[0].PlayerId).Combat;
            Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, combat.FenxianDrawPolicy);
            Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, combat.GuardianShieldPolicy);
            observations.Add(new { mode, actualExitCode = process.ExitCode, actualGuard = actual.RootElement.Clone(),
                snapshotBeforeHash = Hash(before), snapshotAfterHash = Hash(restored.Capture()),
                databaseBeforeHash = Hash(durableBefore), databaseAfterHash = Hash(await Raw(db, room.RoomId)),
                combat.FenxianDrawPolicy, combat.GuardianShieldPolicy });
        }
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM room_snapshots"));
        Record("PR13-B12.3-T03", new { roomId = room.RoomId, actualConfigVersion = game.Version, cards,
            actualGuardObservations = observations, actualDefaultNumerics = game.Numerics,
            candidateAdmitted = false, actualMatches = 1, actualSnapshots = 1, productionSourceModified = false });
    }
