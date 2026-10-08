"""Immutable ledger-alert attribution; missing evidence never clears asset risk."""
from datetime import datetime
import hashlib,json,re
from pathlib import Path
try:
 from pr13_audit_replay import check_files
except ModuleNotFoundError:
 from tools.pr13_audit_replay import check_files


def timestamp(value):
 # PostgreSQL JSON trims trailing fractional zeroes; Python 3.10 accepts
 # only certain fractional widths. Pad equivalent microseconds, keep raw intact.
 if not isinstance(value,str):raise ValueError('Timestamp text required')
 value=value.replace('Z','+00:00')
 value=re.sub(r'\.(\d{1,6})(?=[+-]\d{2}:\d{2}$)',lambda m:'.'+m[1].ljust(6,'0'),value)
 return datetime.fromisoformat(value)


def ledger_state(snapshot):
 if not isinstance(snapshot,dict) or not isinstance(snapshot.get('scope'),str) or not snapshot['scope'] or snapshot.get('transaction')!='READ ONLY; rollback; no mutation':raise ValueError('Owned read-only snapshot identity required')
 query=snapshot.get('querySha256')
 if not isinstance(query,str) or not re.fullmatch('[0-9a-f]{64}',query):raise ValueError('Query identity missing')
 result=snapshot['result'];count=result.get('ledger_chain_mismatches');rows=result.get('ledger')
 if type(count)is not int or count<0 or not isinstance(rows,list) or len(rows)>100000:raise ValueError('Complete bounded ledger chain required')
 checked=timestamp(result['checked_at'])
 if checked.tzinfo is None:raise ValueError('Authority timestamp timezone missing')
 groups={};identities={}
 for row in rows:
  if not isinstance(row,dict) or not all(row.get(k) is not None for k in ('ledger_id','player_id','currency','created_at','delta','balance_after')):raise ValueError('Ledger chain fields missing')
  if any(type(row[k])is not int or not -(2**63)<=row[k]<2**63 for k in ('delta','balance_after')):raise ValueError('Native integer ledger balances required')
  if any(not isinstance(row[k],str) or not row[k] for k in ('player_id','currency')):raise ValueError('Ledger context identity missing')
  identity=row['ledger_id']
  if not isinstance(identity,str) or identity in identities:raise ValueError('Unique ledger row identity required')
  created=timestamp(row['created_at'])
  if created.tzinfo is None:raise ValueError('Ledger timestamp timezone missing')
  identities[identity]=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if row['currency']!='ClassSoul':groups.setdefault((row['player_id'],row['currency']),[]).append((created,identity,row))
 calculated=0
 for group in groups.values():
  ordered=sorted(group,key=lambda r:(r[0],r[1]))
  calculated+=sum(previous[2]['balance_after']+current[2]['delta']!=current[2]['balance_after'] for previous,current in zip(ordered,ordered[1:]))
 if calculated!=count:raise ValueError('Reported alert count differs from complete raw chain')
 return {'scope':snapshot['scope'],'query':query,'checked_at':checked,'count':count,'rows':identities}


def attribute(root,manifest):
 validation=check_files(Path(root),manifest)
 blocked=lambda reason: {'classification':'Blocked','reason':reason,'existing_attribution':False,'asset_acceptance':False,'files':validation,'mutation':False}
 if len(validation)!=2 or any(r['state']!='Matching' for r in validation):return blocked('Original before/after source missing or changed')
 try:
  before,after=[ledger_state(json.loads((Path(root)/r['path']).read_text(encoding='utf8'))) for r in validation]
  if before['scope']!=after['scope'] or before['query']!=after['query'] or after['checked_at']<=before['checked_at']:return blocked('Scope/query/authority chronology does not match')
 except (ValueError,KeyError,TypeError):return blocked('Unavailable, denied or incomplete read-only ledger evidence')
 changes=[]
 for identity in sorted(set(before['rows'])|set(after['rows'])):
  if before['rows'].get(identity)!=after['rows'].get(identity):changes.append({'identity_sha256':hashlib.sha256(identity.encode()).hexdigest(),'before_row_sha256':before['rows'].get(identity),'after_row_sha256':after['rows'].get(identity)})
 if after['count']>before['count']:classification='NewDifferenceBlocksAssets'
 elif before['count']>0 and after['count']==before['count'] and not changes:classification='ExistingWithEvidence'
 elif after['count']==before['count']==0:classification='NoAlertInObservedScope'
 else:classification='ChangedChainNeedsReview'
 return {'classification':classification,'existing_attribution':classification=='ExistingWithEvidence','asset_acceptance':False,'before_alerts':before['count'],'after_alerts':after['count'],'changes':changes,'files':validation,'mutation':False,'scope':'Only these complete owned snapshots; no historical/global attribution or asset acceptance inferred'}
