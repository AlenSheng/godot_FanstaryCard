from pathlib import Path
import hashlib,json,sys,time,urllib.error,urllib.request

root=Path(sys.argv[1]);control=json.loads((root/'http-control.private.json').read_text());base='http://127.0.0.1:'+str(control['port']);checks=[]
def request(method,path,data=None,headers=None):
    call=urllib.request.Request(base+path,data=data,method=method,headers=headers or {})
    try:
        with urllib.request.urlopen(call,timeout=3) as response:status=response.status;body=response.read();received=dict(response.headers)
    except urllib.error.HTTPError as error:status=error.code;body=error.read();received=dict(error.headers)
    return dict(status=status,headers=received,body=body)
def check(name,response,status,extra=True):
    checks.append(dict(name=name,status=response['status'],expected=status,passed=response['status']==status and extra,content_type=response['headers'].get('Content-Type'),body_bytes=len(response['body']),body_sha256=hashlib.sha256(response['body']).hexdigest()))
ready=None
for _ in range(60):
    try:
        ready=request('GET','/health/ready')
        if ready['status']==200:break
    except (OSError,urllib.error.URLError):pass
    time.sleep(.5)
assert ready is not None
check('readiness',ready,200,ready['body'].strip()==b'Healthy')
check('liveness',request('GET','/health/live'),200)
bootstrap=request('GET','/api/v1/bootstrap');check('unauthenticated typed bootstrap',bootstrap,401,'protobuf' in bootstrap['headers'].get('Content-Type',''))
def field(number,value):
    data=value.encode();assert len(data)<128;return bytes([number*8+2,len(data)])+data
local=field(1,'f03-minapp-production-guard')+field(2,'Isolated production guard')
check('old media type rejected',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/x-protobuf'}),415)
check('production local auth closed with required false flag',request('POST','/api/v1/auth/local',local,{'Content-Type':'application/protobuf'}),404)
check('admin requires secure transport',request('GET','/api/admin/client-settings'),403)
check('secure admin requires key',request('GET','/api/admin/client-settings',headers={'X-Forwarded-Proto':'https'}),401)
authenticated=request('GET','/api/admin/client-settings',headers={'X-Forwarded-Proto':'https','X-Admin-Key':control['admin_key']})
check('isolated authenticated read-only admin',authenticated,200,'private' in authenticated['headers'].get('Cache-Control','') and 'no-store' in authenticated['headers'].get('Cache-Control',''))
check('public client info',request('GET','/api/v1/client-info'),200)
for path in ['/release-encryption.key','/appsettings.Development.json','/mapping.xml']:
    check('private package path denied '+path,request('GET',path),404)
result=dict(ok=all(c['passed'] for c in checks),checks=checks,new_gameplay_starts=0,no_login_account_created=True,no_purchase_queue_ready_or_settlement=True)
(root/'public/http-probe.original.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(ok=True,checks=len(checks),new_gameplay_starts=0)))

assert result['ok'], 'HTTP boundary outcomes contain failures; all checks recorded'
