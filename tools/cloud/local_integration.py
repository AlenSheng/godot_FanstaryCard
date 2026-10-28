"""Real Docker + private PostgreSQL transaction drill; no registry or server access.

Compile a tiny static HTTP fixture into scratch images. This exercises the actual
compose/image/backup controller, not the game's final protected runtime validator.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import types
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
import deployment as d
import remote_deploy as r

C_SOURCE = r'''
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <string.h>
int main(int argc,char**argv){int s=socket(AF_INET,SOCK_STREAM,0),yes=1;
setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons(8080),.sin_addr.s_addr=0};
if(bind(s,(void*)&a,sizeof(a))||listen(s,16))return 1;
char b[4096];const char*ok="HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nHealthy";
const char*bad="HTTP/1.1 503 Unavailable\r\nContent-Length: 9\r\nConnection: close\r\n\r\nUnhealthy";
for(;;){int c=accept(s,0,0);if(c<0)continue;read(c,b,sizeof(b));const char*v=argc>1?bad:ok;write(c,v,strlen(v));close(c);}}
'''


def main(output):
    tools=Path(os.environ['FANTASYCARD_CLOUD_TOOLS'])
    pg=tools/'postgres/bin';socket=tools/'postgres-test/socket'
    token='pr14-local-'+uuid.uuid4().hex[:10]
    database=token.replace('-','_')
    images=[]
    report={'ok':False,'uses_registry':False,'uses_online_server':False,'cases':[]}
    with tempfile.TemporaryDirectory(prefix=token,dir='/tmp') as folder:
        root=Path(folder);repo=root/'repo';repo.mkdir();app=root/'app';app.mkdir()
        project=token
        def command(*args,**kwargs):
            kwargs.setdefault('stdout',subprocess.DEVNULL);kwargs.setdefault('stderr',subprocess.PIPE)
            return subprocess.run(list(map(str,args)),check=True,timeout=kwargs.pop('timeout',120),**kwargs)
        def capture(*args):return command(*args,stdout=subprocess.PIPE,text=True).stdout.strip()
        def docker(*args,**kwargs):return command('docker','--config',root/'docker',*args,**kwargs)
        def db(*args,**kwargs):return command(pg/args[0],'-h',socket,'-p','55432','-U','postgres',*args[1:],**kwargs)
        def sql(statement):return db('psql','-d',database,'-v','ON_ERROR_STOP=1','-Atc',statement,stdout=subprocess.PIPE,text=True).stdout.strip()
        baseline=source=broken=None
        try:
            command('git','init','-q',repo)
            command('git','-C',repo,'config','user.name','Local fixture');command('git','-C',repo,'config','user.email','fixture@example.invalid')
            (repo/'server').mkdir();compose=repo/'server/compose.cloud.yaml'
            compose.write_text(f'name: {project}\nservices:\n  server:\n    image: placeholder\n    ports: ["127.0.0.1::8080"]\n')
            (repo/'server/.env').write_text('FIXTURE_ONLY=1\n')
            command('git','-C',repo,'add','.');command('git','-C',repo,'commit','-qm','baseline');baseline=capture('git','-C',repo,'rev-parse','HEAD')
            (repo/'app.txt').write_text('candidate');command('git','-C',repo,'add','.');command('git','-C',repo,'commit','-qm','candidate');source=capture('git','-C',repo,'rev-parse','HEAD')
            (repo/'app.txt').write_text('broken');command('git','-C',repo,'add','.');command('git','-C',repo,'commit','-qm','broken');broken=capture('git','-C',repo,'rev-parse','HEAD')
            mirror=root/'mirror.git';command('git','clone','-q','--bare',repo,mirror)
            command('git','-C',repo,'checkout','-q',baseline);command('git','-C',repo,'remote','add','origin','https://github.com/'+d.REPOSITORY+'.git')
            (root/'fixture.c').write_text(C_SOURCE);command('cc','-static','-O2',root/'fixture.c','-o',root/'fixture')
            for revision,fail in ((baseline,False),(source,False),(broken,True)):
                context=root/revision;context.mkdir();shutil.copyfile(root/'fixture',context/'fixture')
                (context/'Dockerfile').write_text('FROM scratch\nCOPY --chmod=0555 fixture /fixture\nUSER 1000\nENTRYPOINT ["/fixture"]\n'+('CMD ["broken"]\n' if fail else ''))
                tag=f'{token}:{revision}';docker('build','--network','none','--label','org.opencontainers.image.revision='+revision,'-t',tag,context,timeout=180)
                images.append(tag)
            state=app/'test-deploy';state.mkdir();override=state/'active-image.yaml'
            old_id=capture('docker','--config',root/'docker','image','inspect','--format','{{.Id}}',images[0])
            override.write_text(f'services:\n  server:\n    image: {old_id}\n')
            base=['docker','--config',str(root/'docker'),'compose','-f',str(compose),'--env-file',str(repo/'server/.env'),'-f',str(override)]
            command(*base,'up','-d','--no-build','--pull','never')
            (app/'deployed-runtime-commit').write_text(baseline+'\n');(app/'deployed-git-commit').write_text(baseline+'\n')
            db('createdb',database);sql('CREATE TABLE assets(id integer PRIMARY KEY,gold integer NOT NULL); INSERT INTO assets VALUES(1,12345)')
            controller=d.file_hash(Path(__file__))[:40]
            for run_id,target,expected,decision in ((1001,source,'accepted',True),(1002,baseline,'rolled_back',False),(1003,broken,'rolled_back',True)):
                current_revision=(app/'deployed-runtime-commit').read_text().strip()
                bundle=state/f'incoming/{run_id}-1';bundle.mkdir(parents=True)
                for name in ('remote_deploy.py','deployment.py'):shutil.copyfile(Path(__file__).with_name(name),bundle/name)
                (bundle/'health.sh').write_text('#!/usr/bin/env bash\ntrue\n')
                (bundle/'image-validation.json').write_text('{"fixture_only":true}\n')
                tag=images[(baseline,source,broken).index(target)]
                image_id=capture('docker','--config',root/'docker','image','inspect','--format','{{.Id}}',tag)
                docker('save','-o',bundle/'image.tar.gz',image_id) # docker load detects uncompressed tar; suffix is transport convention.
                row=dict(format=2,repository=d.REPOSITORY,environment=d.ENVIRONMENT,source_sha=target,
                    controller_sha=controller,pr_number=14,run_id=run_id,run_attempt=1,image_id=image_id,
                    approval_mode=d.APPROVAL_MODE,approved_actor_id=d.OWNER_ID,confirmed_source_sha=target,
                    restart_confirmed=True,rollback_baseline_sha=current_revision,rollback_compatibility_confirmed=True)
                for name,field in [('image.tar.gz','archive_sha256'),('health.sh','health_sha256'),('remote_deploy.py','remote_sha256'),('deployment.py','deployment_sha256'),('image-validation.json','image_validation_sha256')]:row[field]=d.file_hash(bundle/name)
                (bundle/'manifest.json').write_text(json.dumps(row))
                real_subprocess=subprocess.run
                def translate(*args,**kwargs):
                    args=list(map(str,args))
                    if args[0]=='git' and 'fetch' in args:args[args.index('origin')]=str(mirror)
                    if args[:3]==['sudo','-n','docker']:
                        args=['docker','--config',str(root/'docker'),*args[3:]]
                        if 'exec' in args and 'postgres' in args:
                            index=args.index('postgres');pg_args=args[index+1:]
                            pg_args=[database if value=='fantasycard' and pg_args[i-1]=='-d' else 'postgres' if value=='fantasycard' else value for i,value in enumerate(pg_args)]
                            args=[str(pg/pg_args[0]),'-h',str(socket),'-p','55432',*pg_args[1:]]
                    return command(*args,**kwargs)
                def health_child(args,**kwargs):
                    if args[0]=='bash' and str(args[1]).endswith('health.sh'):
                        try:
                            port=capture(*base,'port','server','8080').rsplit(':',1)[1]
                            with urllib.request.urlopen('http://127.0.0.1:'+port+'/health/ready',timeout=2) as response:
                                ok=response.status==200 and response.read(32)==b'Healthy'
                        except (urllib.error.URLError,TimeoutError,subprocess.CalledProcessError):ok=False
                        return subprocess.CompletedProcess(args,0 if ok else 1)
                    return real_subprocess(args,**kwargs)
                original_monotonic=time.monotonic
                # Speed only the health retry budget; all Docker/PG operations are real.
                health_tick=iter(range(0,10000,200))
                with contextlib.ExitStack() as stack:
                    for name,value in [('APP',app),('REPO',repo),('COMPOSE',compose),('ENV_FILE',repo/'server/.env'),('LOCK',root/'shared.lock')]:stack.enter_context(patch.object(r,name,value))
                    stack.enter_context(patch('pwd.getpwuid',return_value=types.SimpleNamespace(pw_name='ubuntu')))
                    stack.enter_context(patch.object(r,'run',side_effect=translate))
                    stack.enter_context(patch.object(r,'external_decision',return_value=decision))
                    # Patching subprocess.run also affects command; use the captured implementation.
                    def command_unpatched(*args,**kwargs):
                        kwargs.setdefault('stdout',subprocess.DEVNULL);kwargs.setdefault('stderr',subprocess.PIPE)
                        return real_subprocess(list(map(str,args)),check=True,timeout=kwargs.pop('timeout',120),**kwargs)
                    command=command_unpatched
                    stack.enter_context(patch.object(r.subprocess,'run',side_effect=health_child))
                    stack.enter_context(patch.object(r,'HEALTH_TIMEOUT',0))
                    stack.enter_context(patch('sys.stdout',new=io.StringIO()))
                    if expected=='accepted':
                        with r.deployment_lock():r.deploy(bundle,target,run_id,1,controller)
                    else:
                        try:
                            with r.deployment_lock():r.deploy(bundle,target,run_id,1,controller)
                        except RuntimeError:pass
                        else:raise AssertionError('Failed rollout returned success')
                result=json.loads((bundle/'result.json').read_text())
                assert result['status']==expected,result['status']
                assert not (state/'pending.json').exists()
                assert sql('SELECT gold FROM assets WHERE id=1')=='12345'
                backup=app/'backups'/result['backup']['name'];assert backup.stat().st_mode & 0o777 == 0o600
                db('pg_restore','--list',stdin=backup.open('rb'))
                report['cases'].append({'case':run_id,'status':expected,'assets_preserved':True,'backup_mode':'0600','backup_list_valid':True})
            report['ok']=True
        finally:
            if (repo/'server/compose.cloud.yaml').exists():
                command('docker','--config',root/'docker','compose','-f',repo/'server/compose.cloud.yaml','down','--volumes')
            db('dropdb','--if-exists',database)
            for tag in images:docker('image','rm',tag)
            report['cleanup']='fixture containers, images and private test database removed'
            output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['ok']:raise RuntimeError('Local integration incomplete')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    try:
        main(parser.parse_args().output)
    except subprocess.CalledProcessError as error:
        print((error.stderr or b'').decode(errors='replace'), file=__import__('sys').stderr)
        raise
