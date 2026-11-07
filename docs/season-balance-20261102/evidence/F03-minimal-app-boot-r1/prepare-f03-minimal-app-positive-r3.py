from pathlib import Path
import json

b=Path(__file__).parent;source=(b/'f03-minimal-app-worker-r2.py').read_text('utf-8')
source=source.replace('season-balance-20261107-f03-minimal-app-r2','season-balance-20261107-f03-minimal-app-r3').replace('fc-f03-app2-','fc-f03-app3-').replace('app-candidate-r2','app-candidate-r3')
assert 'Identity__EnableLocalAuth=true' in source;source=source.replace('Identity__EnableLocalAuth=true','Identity__EnableLocalAuth=false')
source=source.replace('production local auth remains closed despite enable flag','production local auth closed with required false flag')
target=b/'f03-minimal-app-worker-r3.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
prepare=(b/'prepare-f03-minimal-app-input-r2.py').read_text('utf-8').replace('f03-minimal-app-input-r2','f03-minimal-app-input-r3').replace('season-balance-20261107-f03-minimal-app-r2','season-balance-20261107-f03-minimal-app-r3')
(b/'prepare-f03-minimal-app-input-r3.py').write_text(prepare,encoding='utf-8')
runner=(b/'run-f03-minimal-app-cloud-r2.py').read_text('utf-8').replace('f03-minimal-app-cloud-r2','f03-minimal-app-cloud-r3').replace('f03-minimal-app-input-r2','f03-minimal-app-input-r3').replace('f03-minimal-app-worker-r2.py','f03-minimal-app-worker-r3.py').replace('season-balance-20261107-f03-minimal-app-r2','season-balance-20261107-f03-minimal-app-r3')
(b/'run-f03-minimal-app-cloud-r3.py').write_text(runner,encoding='utf-8')
(b/'f03-minimal-app-cloud-r2/current-guard-interpretation.derived.json').write_text(json.dumps(dict(original_positive_probe_failed=True,startup_guard_negative_behavior_verified=True,
    explicit_fixture_config='Production + Identity.EnableLocalAuth=true + AllowManagedLocalAuth=false',source='Program.cs Production local authentication startup guard',
    old_doc_endpoint404_expectation_not_applicable_to_this_invalid_config=True,no_product_change=True,original_failure_and_stderr_preserved=True),indent=2)+'\n')
print(str(target))
