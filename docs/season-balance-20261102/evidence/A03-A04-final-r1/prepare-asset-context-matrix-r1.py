from pathlib import Path
import hashlib, json

repo = Path.cwd()
b = Path(__file__).parent
out = b / 'asset-context-matrix-r1.original.json'
assert not out.exists()
def family(key, requirement, sources, evidence, limits):
    for name in sources + evidence:
        assert (repo / name).is_file(), name
    return dict(id=key, requirement=requirement, source_sha256={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in sources},
                prior_evidence=evidence, evidence_limit=limits)
s = 'server/src/FantasyCard.Server/'
d = 'docs/season-balance-20261102/evidence/'
common = ['server/src/FantasyCard.Domain/Seasons/SeasonAssetDomain.cs', s+'Seasons/SeasonArchiveRepository.cs']
families = [
 family('permanent-cards-decks-cosmetics', 'Unlocks, actual copies/reserves, levels, copy policy, decks, cosmetics and selected slots survive the actual archive.',
        common+[s+'Progression/PlayerProvisioningService.cs',s+'Progression/PermanentCardCopies.cs',s+'Progression/SeasonJourneyRewardAssets.cs'],
        [d+'C13-shop/result.json',d+'C15-final-r1/result.json',d+'A03-mail-resource-ledger-r1/result.json',d+'A03-admin-equipment-r1/result.json'],
        'The two new composite cases use explicitly seeded earned experience followed by 30 actual claims; this is not a combat route.'),
 family('permanent-souls-diamonds-legacy-balances', 'Exact soul currencies and diamonds remain permanent; legacy Gold/fragments never become a current season balance.',
        [s+'Seasons/SeasonRepository.cs',s+'Settlement/SettlementRepository.cs',s+'Mail/MailRepository.cs',s+'Admin/AdminRepository.cs'],
        [d+'A03-storage/result.json',d+'A03-mail-resource-ledger-r1/result.json',d+'A03-admin-revoke-r1/result.json',d+'C12-market/result.json'],
        'Unversioned legacy mail/admin rows retain unknown metadata; no current-season inference or historical rewrite.'),
 family('permanent-weapon-selected-wallet', 'Signature weapon +5 and total 248 fragments remain; selected current/archived wallet debit is atomic and replay-safe.',
        [s+'Progression/ProgressionRepository.cs',s+'Seasons/SeasonRepository.cs'],
        [d+'A03-storage/result.json'],
        'Current composite proves old 80 fragments can pay 8 for a permanent Mage weapon while neither old nor legacy fragments pay new armor.'),
 family('seasonal-wallet-recipe-mark-pity-progress', 'Season currency, recipe, mark, pity, challenge and journey/activity state remain keyed to their original season.',
        [s+'Seasons/SeasonRepository.cs',s+'Progression/SeasonCraftingRepository.cs',s+'Progression/SeasonRecipeRepository.cs',s+'Progression/SeasonJourneyRepository.cs',s+'Progression/SeasonActivityTransactions.cs'],
        [d+'C07-C08-backend/result.json',d+'C07-C08-ui/result.json',d+'C14-activities/result.json',d+'A04-activity-context-r1/result.json'],
        'Existing feature evidence is reused at its recorded configuration; it is not described as a fresh single combined run.'),
 family('equipment-origin-stats-legacy-null', 'Actual armor identity, origin/domain, quality, generated difficulty and stats persist; legal absent historical secondary traits stay absent.',
        [s+'Settlement/SettlementRepository.cs',s+'Matchmaking/PreparationRepository.cs',s+'Matchmaking/RoomReadyCoordinator.cs',s+'Admin/AdminRepository.cs',s+'Mail/MailRepository.cs'],
        [d+'A03-A04-historical-equipment-r1/result.json',d+'A03-admin-revoke-r1/result.json',d+'A03-admin-equipment-r1/result.json'],
        'Account-level movement D0 is not a rewrite of generated difficulty. Card/weapon difficulty caps do not reduce armor +5.'),
 family('market-relic-hold-original-item', 'Listings, transfer, death/extraction, held returns and late settlement move original IDs and original money domains.',
        [s+'Progression/MarketTransactions.cs',s+'Progression/MarketReturns.cs',s+'Settlement/SettlementRepository.cs'],
        [d+'C12-market/result.json',d+'A04-market-movements-r1/result.json',d+'A04-settlement/result.json',d+'C11-red/result.json'],
        'Market transfer is not a new red mint and cannot refund/recreate the weekly quota.'),
 family('consumable-and-paid-backpack', 'Account consumable counts survive archive; original preparations reserve/debit potions and original settlement returns unused potions or spends paid bags once.',
        [s+'Matchmaking/PreparationRepository.cs',s+'Matchmaking/MatchmakingRepository.cs',s+'Settlement/SettlementRepository.cs'],
        [d+'A04-matchmaking/result.json',d+'A04-settlement/result.json',d+'C13-shop/result.json'],
        'Consumable provenance is through unique parent receipts/preparation/match/hold; it does not claim a new per-item GUID scheme.'),
 family('borrowed-and-bot-source', 'Borrowed cards/weapons and bot combat projections do not mint permanent copies, recipes or materials; real bot-held original items keep identity.',
        [s+'Matchmaking/RoomReadyCoordinator.cs',s+'Settlement/SettlementBotRewards.cs',s+'Progression/SeasonRecipeRepository.cs'],
        [d+'C10-bots/result.json',d+'C07-C08-backend/result.json'],
        'Original source restrictions and red mint limits remain; no capacity test is implied.'),
 family('archive-resume-late-original-credit', 'Bounded original-season pages commit item moves and cursor together, preserve permanent accounts, wait for unsafe holds and never credit the next season.',
        [s+'Seasons/SeasonArchiveRepository.cs',s+'Seasons/SeasonArchiveWorker.cs',s+'Settlement/SettlementSeasonContext.cs'],
        [d+'A05-archive/result.json',d+'A03-loadouts/result.json',d+'A03-api-readmodels/result.json'],
        'Repository recreation/page fault and HostedService coverage do not replace the separate whole-process crash matrix F02.'),
]
context_sources = [s+'Matchmaking/PreparationRepository.cs',s+'Matchmaking/MatchmakingRepository.cs',s+'Matchmaking/RoomReadyCoordinator.cs',s+'Rooms/RoomSnapshotRepository.cs',s+'Rooms/RoomRecoveryWorker.cs',s+'Settlement/SettlementSeasonContext.cs',s+'Progression/MarketTransactions.cs']
for n in context_sources: assert (repo/n).is_file(), n
data = dict(kind='static source and existing evidence audit; runtime acceptance requires r115 terminal proof', families=families,
            fixed_context=['season_id','difficulty_id','ruleset_id','config_version','stats_version','original_bundle_content_hash'],
            context_source_sha256={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in context_sources},
            context_prior_evidence=[d+x+'/result.json' for x in ['A04-preparation-config-r1','A04-client-preparation-config-r1','A04-reward-refresh-funding-r1','A04-market-movements-r1','A04-activity-context-r1']],
            local_reserve_GiB=2,startup_budget_GiB=1,cloud_reserve_MiB=500,cloud_disk_floor_GiB=3,cloud_disk_fraction=.05,
            production_deployed=False,capacity100_retest=False,new_full_routes=0,new_encounters=0)
out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'families':len(families),'source_files':len(set(context_sources + [n for x in families for n in x['source_sha256']])),'runtime_acceptance_claimed':False}))
