import json
import sys
from pr13_review_policy import asset_gate

observed=json.loads(sys.argv[1])
assert observed['ledger_chain_mismatch_count']==1 and observed['total_violation_count']==1
assert observed['healthy'] is False and observed['observed_delta']==5 and observed['unexplained_balance_gap']==7
alerts=[{'id':observed['alert_id'],'explained':False,'actual_database_observation':observed}]
blocked=asset_gate(alerts)
assert blocked['state']=='Blocked' and blocked['unexplained_alerts']==[observed['alert_id']]
assert blocked['asset_acceptance'] is False
positive=asset_gate([])
assert positive['state']=='ReadyForMainReview' and positive['asset_acceptance'] is False
print(json.dumps({'ok':True,'actual_alerts':alerts,'actual_asset_gate':blocked,
    'healthy_no_alert_positive_gate':positive,'faulted_ledger_was_not_repaired_or_deleted_to_pass':True}))
