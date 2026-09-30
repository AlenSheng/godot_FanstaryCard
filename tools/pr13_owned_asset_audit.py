"""Read-only cloud postconditions, limited to accounts proven by owned run reports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--key',type=Path,default=Path(r'C:\Users\79498\.ssh\relicbound-gpt.pem'))
    args=parser.parse_args();users=set();reports=[];missing=[]
    for run in args.runs:
        for file in sorted(run.glob('g*.json')):
            if file.name.endswith('.status.json'):continue
            report=json.loads(file.read_text(encoding='utf8'))
            if not all(isinstance(report.get(k),str) and report[k] for k in ('run_id','process_epoch','client_id')):
                raise ValueError('Unowned report context: '+str(file))
            value=report.get('user_id')
            if not value:missing.append(file.name);continue
            user=str(uuid.UUID(value));users.add(user);reports.append(dict(path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    if not users:raise ValueError('No owned accounts to audit')
    array=','.join("'"+user+"'::uuid" for user in sorted(users))
    sql="""
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5s';
WITH owned(player_id) AS (SELECT unnest(ARRAY[OWNED_IDS])),
chain AS (
 SELECT player_id,currency,delta,balance_after,created_at,
 lag(balance_after) OVER(PARTITION BY player_id,currency ORDER BY created_at,ledger_id) AS previous
 FROM economy_ledger WHERE currency <> 'ClassSoul'
), rows AS (
 SELECT o.player_id,
 (SELECT count(*) FROM preparations p WHERE p.player_id=o.player_id AND p.status IN ('Active','Queued','Matched')) AS active_preparations,
 (SELECT count(*) FROM match_tickets t WHERE t.player_id=o.player_id AND t.status='Queued') AS queued_tickets,
 (SELECT count(*) FROM match_players p JOIN matches m USING(match_id) WHERE p.player_id=o.player_id AND m.status IN ('Starting','Running') AND p.settled_at IS NULL) AS unfinished_matches,
 (SELECT count(*) FROM match_settlements s WHERE s.player_id=o.player_id AND s.acknowledged_at IS NULL) AS unacknowledged_settlements,
 (SELECT count(*) FROM settlement_asset_holds h WHERE h.player_id=o.player_id AND h.state IN ('Held','Pending')) AS unresolved_holds,
 (SELECT count(*) FROM equipments e WHERE e.owner_id=o.player_id AND e.location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack')) AS locked_equipment,
 (SELECT count(*) FROM match_settlements s WHERE s.player_id=o.player_id) AS settlements,
 (SELECT count(*) FROM chain c WHERE c.player_id=o.player_id AND c.previous IS NOT NULL AND c.previous+c.delta<>c.balance_after) AS ledger_chain_mismatches
 FROM owned o
)
SELECT json_build_object('accounts',(SELECT json_agg(rows) FROM rows),
 'global_ledger_chain_mismatches',(SELECT count(*) FROM chain WHERE previous IS NOT NULL AND previous+delta<>balance_after),
 'checked_at',CURRENT_TIMESTAMP);
ROLLBACK;
""".replace('OWNED_IDS',array)
    script="cd /opt/fantasycard-github\nsudo -n docker compose --env-file server/.env -f server/compose.cloud.yaml exec -T postgres psql -X -qAt -v ON_ERROR_STOP=1 -U fantasycard -d fantasycard <<'PR13_OWNED_SQL'\n"+sql+"\nPR13_OWNED_SQL\n"
    start=time.time();result=subprocess.run(['ssh','-i',str(args.key),'-o','BatchMode=yes','-o','ConnectTimeout=10','ubuntu@43.172.70.182','bash','-s'],
        input=script.encode('utf8'),capture_output=True,timeout=30)
    if result.returncode:raise RuntimeError('Read-only audit failed: '+result.stderr.decode('utf8','replace')[:1000])
    data=json.loads(result.stdout.decode('utf8').strip());accounts=data['accounts']
    if len(accounts)!=len(users):raise RuntimeError('Incomplete owned-account audit')
    for row in accounts:
        row['account_hash']=hashlib.sha256(row.pop('player_id').encode('ascii')).hexdigest()
    postcondition_keys=('active_preparations','queued_tickets','unfinished_matches','unacknowledged_settlements','unresolved_holds','locked_equipment','ledger_chain_mismatches')
    output=dict(schema_version=1,started_at=start,elapsed_seconds=time.time()-start,
        scope='Read-only postconditions for accounts identified by this run; global ledger count gives context, not historical attribution.',
        query_sha256=hashlib.sha256(sql.encode('utf8')).hexdigest(),source_reports=reports,missing_owned_account_identity=missing,
        **data,owned_postconditions_clear=not missing and all(all(row[key]==0 for key in postcondition_keys) for row in accounts),
        historical_attribution='Unknown: requires before-run raw ledger/log evidence; no balance or ledger mutation performed.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(dict(accounts=len(accounts),missing_identities=len(missing),owned_postconditions_clear=output['owned_postconditions_clear'],
        global_ledger_chain_mismatches=data['global_ledger_chain_mismatches'],totals={key:sum(row[key] for row in accounts) for key in postcondition_keys})))
    return 0 if output['owned_postconditions_clear'] else 1


if __name__=='__main__':raise SystemExit(main())
