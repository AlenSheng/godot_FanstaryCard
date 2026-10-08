"""Run exact reviewed accounting assertions for remaining control contracts."""
import argparse
import contextlib
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
MAPPING={
 'LOAD-07.2-T02':['gameplay_load_validation.test_real_child_exit_is_not_counted_online','gameplay_load_validation.test_exited_failure_is_workload_failure'],
 'LOAD-10.1-T02':['gameplay_load_validation.test_owned_json_file_schema_failure_reaches_explicit_invalid_decision','gameplay_load_validation.test_event_sequence_handles_same_millisecond_and_detects_loss'],
 'LOAD-10.1-T03':['pr13_postgres_cases.test_skipped_database_case_cannot_be_exported_as_passed'],
 'LOAD-10.2-T03':['pr13_runtime_evidence.test_fallback_is_not_normal_completion'],
 'LOAD-10.4-T01':['pr13_runtime_evidence.test_peak_or_group_size_cannot_prove_100_active'],
 'LOAD-11.3-T02':['pr13_postgres_cases.test_skipped_database_case_cannot_be_exported_as_passed'],
 'LOAD-11.4-T01':['pr13_runtime_evidence.test_unknown_dimension_prevents_acceptance','pr13_public_evidence.test_offline_pass_cannot_discharge_mandatory_live_or_database'],
 'PR13-A07.2-T02':['pr13_postgres_cases.test_skipped_database_case_cannot_be_exported_as_passed'],
 'PR13-A07.2-T03':['pr13_owned_postgres.test_unowned_database_is_rejected_before_query'],
 'PR13-A07.4-T03':['pr13_public_evidence.test_old_ci_success_cannot_satisfy_current_source'],
 'PR13-A08.1-T03':['pr13_stages.test_equal_declared_hashes_do_not_hide_wrong_content','pr13_simulation_contracts.test_mixed_frozen_inputs_are_rejected'],
 'PR13-A09.2-T03':['pr13_runtime_evidence.test_fallback_is_not_normal_completion'],
 'PR13-A09.3-T03':['gameplay_load_finalization.test_final_status_bad_json_is_invalid_evidence_exit_three','gameplay_load_finalization.test_final_status_missing_cannot_use_cached_cleanup_as_final_evidence'],
 'PR13-A09.4-T02':['pr13_postgres_cases.test_skipped_database_case_cannot_be_exported_as_passed'],
 'PR13-A10.2-T03':['pr13_runtime_evidence.test_peak_or_group_size_cannot_prove_100_active','gameplay_load_sampling_contract.test_online_and_active_in_separate_windows_do_not_meet_joint_target'],
 'PR13-A10.3-T02':['gameplay_load_finalization.test_explicit_business_cleanup_failure_stays_failed'],
 'PR13-A10.3-T03':['gameplay_load_sampling_contract.test_monitoring_unknown_is_not_capacity_success_even_with_full_load','pr13_runtime_evidence.test_sampling_blackout_in_stop_tail_is_invalid'],
 'PR13-B01.4-T01':['pr13_simulation_contracts.test_observed_p95_and_completed_p95_cannot_claim_all_started_ttk','pr13_simulation_contracts.test_error_and_death_remain_in_denominator'],
 'PR13-B01.4-T02':['pr13_runtime_evidence.test_fallback_is_not_normal_completion'],
 'PR13-B03.3-T02':['pr13_simulation_contracts.test_removed_or_out_of_block_samples_are_rejected','pr13_simulation_contracts.test_missing_whole_seed_pair_and_wrong_seed_are_rejected'],
 'PR13-B03.3-T03':['pr13_simulation_contracts.test_small_single_run_has_no_three_block_claim','pr13_simulation_contracts.test_observed_p95_and_completed_p95_cannot_claim_all_started_ttk'],
 'PR13-B03.4-T03':['pr13_simulation_contracts.test_mixed_frozen_inputs_are_rejected','pr13_simulation_contracts.test_frozen_assembly_or_wrong_factor_manifest_is_rejected'],
 'PR13-B05.2-T01':['pr13_simulation_contracts.test_non_o6_changed_and_hp_factor_windup_are_rejected'],
 'PR13-B05.2-T02':['pr13_simulation_contracts.test_non_o6_changed_and_hp_factor_windup_are_rejected'],
 'PR13-B12.1-T02':['pr13_stages.test_equal_declared_hashes_do_not_hide_wrong_content','pr13_simulation_contracts.test_mixed_frozen_inputs_are_rejected'],
 'PR13-B12.4-T01':['pr13_runtime_evidence.test_preregistered_smoke_scope_does_not_claim_performance','pr13_runtime_evidence.test_peak_or_group_size_cannot_prove_100_active'],
 'PR13-B12.4-T02':['pr13_stages.test_full_coverage_no_runtime_acceptance_and_integrity','pr13_public_evidence.test_offline_pass_cannot_discharge_mandatory_live_or_database'],
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
    needed=sorted({name for names in MAPPING.values() for name in names});results={};source_paths={'tools/pr13_control_cases.py'}
    with (out/'assertions.private.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        for name in needed:
            module_name,method=name.split('.',1);module=importlib.import_module('tools.tests.test_'+module_name)
            owners=[c for _,c in inspect.getmembers(module,inspect.isclass) if issubclass(c,unittest.TestCase) and hasattr(c,method)]
            if len(owners)!=1:raise ValueError('Exact assertion must have one test owner: '+name)
            test=owners[0](method);start=time.monotonic();result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite([test]))
            results[name]={'assertion_id':test.id(),'status':'Passed' if result.wasSuccessful() and not result.skipped and result.testsRun==1 else 'Failed','executed':result.testsRun,'skip_count':len(result.skipped),'elapsed_seconds':time.monotonic()-start}
            source_paths.add(Path(module.__file__).relative_to(ROOT).as_posix())
    # Include executed implementation imports, without local environments or binaries.
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            path=Path(file).resolve()
            if path.is_relative_to(ROOT/'tools') and path.suffix=='.py':source_paths.add(path.relative_to(ROOT).as_posix())
    records=[]
    for case_id,names in MAPPING.items():
        actual=[results[name] for name in names]
        records.append({'case_id':case_id,'executed':True,'status':'Passed' if all(r['status']=='Passed' for r in actual) else 'Failed','setup':contracts[case_id]['setup_and_injection'],'expected':contracts[case_id]['expected'],'actual':{'exact_assertions':actual,'raw_assertion_log_sha256':sha(out/'assertions.private.log')},'profiles_executed':['OFFLINE'],
            'scope':'Actual Python accounting/guard assertions, controlled input faults and owned child process tests. Native PG/EXPERIMENT/LIVE/CAPACITY/AUDIT layers remain separate.'})
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'explicit exact controlled accounting assertions','input_hashes':{p:sha(ROOT/p) for p in sorted(source_paths)}},'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'native_assertions':len(results),'skipped':sum(r['skip_count'] for r in results.values()),'accepted':False})
    write(out/'manifest.json',{'files':[{'path':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(out.glob('*')) if f.is_file()]})
    print(json.dumps({'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'assertions':len(results)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
