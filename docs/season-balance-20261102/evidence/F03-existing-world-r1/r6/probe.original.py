from pathlib import Path
import subprocess,json,shutil,datetime
pg='e140d6f8ab9f';app='60bab052fd10'
def run(args):return subprocess.check_output(args,text=True,timeout=20).strip()
def sql(s):return run(['docker','exec',pg,'psql','-U','fantasycard','-d','fantasycard','-X','-qAt','-c',s])
def value(s):return json.loads(sql(s))
m=dict(s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu');assert int(m['MemAvailable'].split()[0])*1024>=500*1024**2 and d.free>=3*1024**3 and d.free/d.total>=.05
queries={
 'migrations':"SELECT json_build_object('count',count(*),'maximum',max(version)) FROM schema_migrations",
 'matches':"SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT config_version,status,count(*) AS rows FROM matches GROUP BY config_version,status ORDER BY config_version,status)x",
 'snapshots':"SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT snapshot_json->>'configVersion' AS config_version,count(*) AS rows FROM room_snapshots GROUP BY 1 ORDER BY 1)x",
 'season_definitions_exist':"SELECT json_build_object('exists',to_regclass('public.season_definitions') IS NOT NULL)"
}
result={k:value(s) for k,s in queries.items()}
result['server_identity']=run(['docker','inspect','--format','{{.Id}}|{{.Image}}|{{.State.StartedAt}}',app])
result['resource_guard']=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total)
result['at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();result['readonly']=True;print(json.dumps(result))
