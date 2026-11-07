from pathlib import Path

b=Path(__file__).parent;source=(b/'audit-f01-calendar-evidence-r2.py').read_text('utf-8')
for old,new in [
    ('f01-calendar-r1/observations','f01-support-week-r1/observations'),
    ('f01-calendar-r1\\control.private.json','f01-support-week-r1\\control.private.json'),
    ('f01-calendar-evidence-audit-r2.derived.json','f01-support-week-evidence-audit-r1.derived.json'),
    ("spec['initial_plan']['source']","spec['support_week_plan']['source']"),
    ("'f01-calendar-current17'","'f01-support-current17'"),
    ('== 252','== 42'),('==252','==42'),("'actual_main_starts':252","'actual_support_week_starts':42"),
    ("'post_match_gold_fragment_closures':252","'post_match_gold_fragment_closures':42"),
    ("[1,7,14]","[1,7]"),('==27','==6'),('==28','==14'),("'attempts':28","'attempts':14"),
    ("'right_censored_after_attempt':28","'right_censored_after_attempt':14"),
    ("'cohort':actor.split('-')[1]","'cohort':'novice-owned-support'"),
    ('==255','==297'),('==45','==3'),("'total_F01_used':255","'total_F01_used':297"),("'remaining':45","'remaining':3"),
    ("'whole_progress_before_review':'32/35'","'whole_progress_before_review':'33/35'"),
    ("'actual_diagnostic_starts':3","'prior_main_and_diagnostic_starts_preserved':255"),
    ('main_execution_complete','support_week_execution_complete'),
]:
    assert old in source,old;source=source.replace(old,new)
old="""financial=json.loads((b/'f01-calendar-independent-db-audit-r1/result.final.derived.json').read_bytes())
assert financial['completed_matches']==financial['human_settlements']==42
assert financial['season_wallet_and_permanent_soul_ledger_mismatches']==0
assert financial['pending_holds']==financial['active_preparations']==0 and financial['shared_tokens_closed']"""
new="""financial=None  # This audit closes raw per-match gold/fragments; separate DB audit must establish all ledger claims.
prior_journal=(b/'f01-support-week-batch1-r1/prior-journal.original.jsonl').read_bytes()
assert journal.read_bytes().startswith(prior_journal)
original_members=json.loads(Path('docs/season-balance-20261102/evidence/F01-calendar-final-r1/original-archive-members.json').read_bytes())
assert all(hashlib.sha256((b/m['path']).read_bytes()).hexdigest()==m['sha256'] for m in original_members)
initials=[]
for path in root.glob('initial-*.original.json'):
    initial=json.loads(path.read_bytes());assert not initial['actor']['HistoricalOwnershipAssumed']
    owned={c['CardId']:c for c in initial['owned_before'] if c['Unlocked'] and c['CopyCount']>=1};assert len(owned)==51
    ids=initial['actor']['Cards'];assert len(ids)==len(set(ids))==20
    assert all(cid in owned and owned[cid]['Level']==0 for cid in ids)
    initials.append(dict(actor=initial['actor']['Id'],actual_owned_initial_copies=51,selected_deck=ids,source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(initials)==3"""
assert old in source;source=source.replace(old,new)
old="'product_files_changed':False,'production_changed':False,"
new=old+"'fresh_account_inputs_verified':initials,'original1771files_SHA_unchanged':True,'old255journal_prefix_byte_unchanged':True,'D03_budget_not_reset':True,'D03_new':0,'B05_new':0,"
assert old in source;source=source.replace(old,new)
target=b/'audit-f01-support-week-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
