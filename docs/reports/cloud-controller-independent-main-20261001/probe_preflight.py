"""Invoke production preflight with a pinned synthetic context and mocked API only."""
import argparse,os,pathlib,sys
from unittest.mock import patch
B=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(B/'release/tools/cloud'))
import deployment as d
p=argparse.ArgumentParser();p.add_argument('--omit');p.add_argument('--directory',type=pathlib.Path,required=True);a=p.parse_args()
SOURCE='a'*40;CONTROL='65361bcc27c51c28651c86c5dbba4f083a9b39e0';BASELINE='c'*40
context=dict(GITHUB_REPOSITORY=d.REPOSITORY,GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/release',GITHUB_SHA=CONTROL,GITHUB_ACTOR='AlenSheng',GITHUB_TRIGGERING_ACTOR='AlenSheng',GITHUB_ACTOR_ID=str(d.OWNER_ID),GITHUB_RUN_ID='21',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(a.directory/'github-output'),TEST_DEPLOY_ENABLED='true',TEST_DEPLOY_APPROVAL_MODE=d.APPROVAL_MODE,TEST_DEPLOY_APPROVED_WORKFLOW_SHA=CONTROL,PR_NUMBER='13',COMMIT_SHA=SOURCE,CONFIRM_SOURCE_SHA=SOURCE,CONFIRM_RESTART='true',ROLLBACK_BASELINE_SHA=BASELINE,CONFIRM_ROLLBACK_COMPATIBILITY='true')
if a.omit:del context[a.omit]
def fake_api(path):
    if not path:return {'full_name':d.REPOSITORY,'default_branch':'main','owner':{'id':d.OWNER_ID}}
    if path=='/pulls/13':return {'number':13,'state':'open','head':{'repo':{'full_name':d.REPOSITORY},'sha':SOURCE},'base':{'repo':{'full_name':d.REPOSITORY},'ref':'release'}}
    if path.endswith('deployment-branch-policies'):return {'total_count':1,'branch_policies':[{'name':'release','type':'branch'}]}
    return {'name':d.ENVIRONMENT,'protection_rules':[],'deployment_branch_policy':{'custom_branch_policies':True,'protected_branches':False}}
with patch.dict(os.environ,context,clear=True),patch.object(d,'api',side_effect=fake_api):d.preflight(a.directory/'preflight.json')
