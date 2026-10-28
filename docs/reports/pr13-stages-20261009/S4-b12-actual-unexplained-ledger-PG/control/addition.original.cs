    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_unexplained_postgres_ledger_gap_blocks_asset_gate_without_deleting_evidence()
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
        var identity = new FantasyCard.Server.Identity.IdentityRepository(db.DataSource,
            new FantasyCard.Server.Progression.PlayerProvisioningService());
        var now = DateTimeOffset.UtcNow;
        var profile = await identity.SignInLocalAsync("asset-gate-" + Guid.NewGuid().ToString("N"),
            "Isolated ledger gate", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), Ct);
        var player = profile.UserId;
        var initialGold = await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player);
        var ledger1 = Guid.NewGuid(); var ledger2 = Guid.NewGuid();
        var baseTime = DateTimeOffset.UtcNow.AddSeconds(1);
        await using (var command = db.DataSource.CreateCommand(
            "INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at) " +
            "VALUES($1,$3,'declared-ledger-first','Gold',10,$4,'pr13.owned.ledger.fixture',$6)," +
            "($2,$3,'declared-ledger-second','Gold',5,$5,'pr13.owned.ledger.fixture',$7)"))
        {
            command.Parameters.AddWithValue(ledger1);command.Parameters.AddWithValue(ledger2);
            command.Parameters.AddWithValue(player);command.Parameters.AddWithValue(initialGold+10);
            command.Parameters.AddWithValue(initialGold+15);command.Parameters.AddWithValue(baseTime);
            command.Parameters.AddWithValue(baseTime.AddSeconds(1));
            await command.ExecuteNonQueryAsync(Ct);
        }
        await using (var command = db.DataSource.CreateCommand("UPDATE player_wallets SET gold=$1 WHERE player_id=$2"))
        {
            command.Parameters.AddWithValue(initialGold+15);command.Parameters.AddWithValue(player);
            await command.ExecuteNonQueryAsync(Ct);
        }
        var reconciliation = new FantasyCard.Server.Progression.EconomyReconciliationRepository(db.DataSource);
        var healthy = await reconciliation.InspectAsync(Ct);
        Assert.True(healthy.IsHealthy);Assert.Equal(0, healthy.TotalViolationCount);
        var rawHealthy = await db.ScalarAsync<string>(
            "SELECT jsonb_agg(jsonb_build_object('ledger_id',ledger_id,'delta',delta,'balance_after',balance_after) ORDER BY created_at,ledger_id)::text " +
            "FROM economy_ledger WHERE player_id=$1 AND reason='pr13.owned.ledger.fixture'",player);
        await using (var command = db.DataSource.CreateCommand("UPDATE economy_ledger SET balance_after=balance_after+7 WHERE ledger_id=$1"))
        {
            command.Parameters.AddWithValue(ledger2);Assert.Equal(1,await command.ExecuteNonQueryAsync(Ct));
        }
        var broken = await reconciliation.InspectAsync(Ct);
        Assert.False(broken.IsHealthy);Assert.Equal(1,broken.LedgerChainMismatchCount);Assert.Equal(1,broken.TotalViolationCount);
        var rows = await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='pr13.owned.ledger.fixture'",player);
        Assert.Equal(2,rows);
        var firstBalance = await db.ScalarAsync<long>("SELECT balance_after FROM economy_ledger WHERE ledger_id=$1",ledger1);
        var secondBalance = await db.ScalarAsync<long>("SELECT balance_after FROM economy_ledger WHERE ledger_id=$1",ledger2);
        var secondDelta = await db.ScalarAsync<long>("SELECT delta FROM economy_ledger WHERE ledger_id=$1",ledger2);
        Assert.Equal(7,secondBalance-firstBalance-secondDelta);
        var rawBroken = await db.ScalarAsync<string>(
            "SELECT jsonb_agg(jsonb_build_object('ledger_id',ledger_id,'delta',delta,'balance_after',balance_after) ORDER BY created_at,ledger_id)::text " +
            "FROM economy_ledger WHERE player_id=$1 AND reason='pr13.owned.ledger.fixture'",player);
        var observed = new { ledger_chain_mismatch_count = broken.LedgerChainMismatchCount,
            total_violation_count = broken.TotalViolationCount, healthy = broken.IsHealthy,
            observed_delta = secondDelta, unexplained_balance_gap = secondBalance-firstBalance-secondDelta,
            alert_id = "owned-ledger-chain-" + ledger2.ToString("N") };
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo("python3")
        {
            RedirectStandardOutput = true,RedirectStandardError = true,UseShellExecute = false
        };
        process.StartInfo.ArgumentList.Add("/control/asset-alert-guard.original.py");
        process.StartInfo.ArgumentList.Add(JsonSerializer.Serialize(observed));
        Assert.True(process.Start());var stdout = process.StandardOutput.ReadToEndAsync(Ct);var stderr = process.StandardError.ReadToEndAsync(Ct);
        await process.WaitForExitAsync(Ct);Assert.Equal(0,process.ExitCode);Assert.Equal(string.Empty,await stderr);
        using var actual = JsonDocument.Parse(await stdout);
        Assert.Equal("Blocked",actual.RootElement.GetProperty("actual_asset_gate").GetProperty("state").GetString());
        Assert.False(actual.RootElement.GetProperty("actual_asset_gate").GetProperty("asset_acceptance").GetBoolean());
        Assert.Equal(rawBroken,await db.ScalarAsync<string>(
            "SELECT jsonb_agg(jsonb_build_object('ledger_id',ledger_id,'delta',delta,'balance_after',balance_after) ORDER BY created_at,ledger_id)::text " +
            "FROM economy_ledger WHERE player_id=$1 AND reason='pr13.owned.ledger.fixture'",player));
        var stillBroken = await reconciliation.InspectAsync(Ct);Assert.Equal(1,stillBroken.LedgerChainMismatchCount);
        Assert.Equal(initialGold+15,await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",player));
        var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId,Ct))!,catalog,999);
        Assert.Equivalent(before,restored.Capture(),strict:true);Assert.Equal(durableBefore,await Raw(db,room.RoomId));
        Record("PR13-B12.4-T03",new { roomId=room.RoomId,actualConfigVersion=game.Version,cards,
            playerId=player,ledgerFirstId=ledger1,ledgerSecondId=ledger2,initialGold,
            healthyReconciliation=healthy,brokenReconciliation=broken,stillBrokenReconciliation=stillBroken,
            actualLedgerRows=rows,actualFirstBalance=firstBalance,actualSecondBalance=secondBalance,actualSecondDelta=secondDelta,
            healthyLedgerRaw=rawHealthy,brokenLedgerRaw=rawBroken,actualAssetGuard=actual.RootElement.Clone(),
            snapshotBeforeHash=Hash(before),snapshotAfterHash=Hash(restored.Capture()),
            databaseBeforeHash=Hash(durableBefore),databaseAfterHash=Hash(await Raw(db,room.RoomId)),
            corruptEvidenceNotRepairedOrDeleted=true,productionSourceModified=false,liveAssetsTouched=false });
    }
