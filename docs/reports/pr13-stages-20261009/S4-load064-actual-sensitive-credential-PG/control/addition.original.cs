    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_postgres_session_token_and_issued_ticket_are_rejected_from_public_evidence()
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
        await Persist(db, repository, room);var before = room.Capture();var durableBefore = await Raw(db,room.RoomId);
        var token = FantasyCard.Server.Identity.SessionToken.Create();
        var tokenHash = FantasyCard.Server.Identity.SessionToken.Hash(token);
        var now = DateTimeOffset.UtcNow;
        var identity = new FantasyCard.Server.Identity.IdentityRepository(db.DataSource,
            new FantasyCard.Server.Progression.PlayerProvisioningService());
        var profile = await identity.SignInLocalAsync("public-review-"+Guid.NewGuid().ToString("N"),
            "Public review",tokenHash,now,now.AddHours(1),Ct);
        var lookupBefore = await identity.FindByTokenHashAsync(tokenHash,DateTimeOffset.UtcNow,Ct);
        Assert.Equal(profile.UserId,lookupBefore.Player!.UserId);Assert.False(lookupBefore.IsExpired);
        var store = new FantasyCard.Server.Realtime.RealtimeTicketStore(TimeProvider.System);
        var issued = store.Issue(profile.UserId,tokenHash)!;
        var directory = "/control/owned-sensitive-candidates";Directory.CreateDirectory(directory);
        var sessionFile = Path.Combine(directory,"actual-session-token.json");
        var ticketFile = Path.Combine(directory,"actual-realtime-ticket.json");
        File.WriteAllText(sessionFile,JsonSerializer.Serialize(new { token }));
        File.WriteAllText(ticketFile,JsonSerializer.Serialize(new { ticketBody=issued.Ticket }));
        var sessionBytes = File.ReadAllBytes(sessionFile);var ticketBytes = File.ReadAllBytes(ticketFile);
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo("python3")
        {
            RedirectStandardOutput=true,RedirectStandardError=true,UseShellExecute=false
        };
        process.StartInfo.ArgumentList.Add("/control/sensitive-evidence-guard.original.py");
        Assert.True(process.Start());var stdout=process.StandardOutput.ReadToEndAsync(Ct);var stderr=process.StandardError.ReadToEndAsync(Ct);
        await process.WaitForExitAsync(Ct);Assert.Equal(0,process.ExitCode);Assert.Equal(string.Empty,await stderr);
        using var actual=JsonDocument.Parse(await stdout);
        Assert.True(actual.RootElement.GetProperty("ok").GetBoolean());
        Assert.False(actual.RootElement.GetProperty("raw_values_written_to_public_report").GetBoolean());
        Assert.Equal(sessionBytes,File.ReadAllBytes(sessionFile));Assert.Equal(ticketBytes,File.ReadAllBytes(ticketFile));
        var consumed = store.Consume(issued.Ticket);Assert.NotNull(consumed);
        Assert.Equal(profile.UserId,consumed.PlayerId);Assert.Equal(tokenHash,consumed.SessionHash);
        Assert.Null(store.Consume(issued.Ticket));
        var lookupAfter = await identity.FindByTokenHashAsync(tokenHash,DateTimeOffset.UtcNow,Ct);
        Assert.Equal(profile.UserId,lookupAfter.Player!.UserId);Assert.False(lookupAfter.IsExpired);
        var publicBytes=File.ReadAllText("/output/public-review-sanitized.original.json");
        Assert.DoesNotContain(token,publicBytes);Assert.DoesNotContain(issued.Ticket,publicBytes);
        var restored = BattleRoom.Restore((await repository.GetAsync(room.RoomId,Ct))!,catalog,999);
        Assert.Equivalent(before,restored.Capture(),strict:true);Assert.Equal(durableBefore,await Raw(db,room.RoomId));
        Record("LOAD-06.4-T03",new { roomId=room.RoomId,actualConfigVersion=game.Version,cards,
            actualOwnedPlayerId=profile.UserId,actualDatabaseSessionLookupBeforeAndAfter=true,
            actualIssuedTicketConsumedOnce=true,generatedEphemeralTestCredentialsOnly=true,
            tokenSha256=Convert.ToHexString(tokenHash).ToLowerInvariant(),
            ticketSha256=Convert.ToHexString(FantasyCard.Server.Identity.SessionToken.Hash(issued.Ticket)).ToLowerInvariant(),
            privateCandidateSessionFileSha256=Convert.ToHexString(SHA256.HashData(sessionBytes)).ToLowerInvariant(),
            privateCandidateTicketFileSha256=Convert.ToHexString(SHA256.HashData(ticketBytes)).ToLowerInvariant(),
            actualPublicReview=actual.RootElement.Clone(),sensitiveValuesNeverWrittenToPublicReceipt=true,
            snapshotBeforeHash=Hash(before),snapshotAfterHash=Hash(restored.Capture()),
            databaseBeforeHash=Hash(durableBefore),databaseAfterHash=Hash(await Raw(db,room.RoomId)),
            productionSourceModified=false,productionCredentialsUsed=false });
    }
