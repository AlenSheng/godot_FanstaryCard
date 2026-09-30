import pathlib,subprocess,json,hashlib,time
root=pathlib.Path(__file__).resolve().parents[1];h=root/'harness';e=root/'evidence';commands=[];results=[]
old=subprocess.check_output(['git','-C','/workspace/godot_FanstaryCard','show','28c6c7e7:server/tests/FantasyCard.Domain.Tests/Combat/CombatAuthoritativeRulesTests.cs'])
(e/'historical-CombatAuthoritativeRulesTests.cs.txt').write_bytes(old)
for name,body,diagnostic in [
 ('old-fenxian','var state=new PlayerCombatState(HeroClass.Mage,cards,new Random(31),useConsumptionBasedFenxian:true);','CS1739'),
 ('old-guardian','var state=new PlayerCombatState(HeroClass.Guardian,cards,new Random(31),useFractionalGuardianWeapon:true);','CS1739'),
 ('old-remainder','var state=new PlayerCombatState(HeroClass.Guardian,cards,new Random(31)); var x=state.GuardianWeaponRemainderTenths;','CS1061')]:
 p=h/name;p.mkdir(exist_ok=True)
 (p/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup><ItemGroup><ProjectReference Include="../../source/server/src/FantasyCard.Domain/FantasyCard.Domain.csproj" /></ItemGroup></Project>')
 (p/'Program.cs').write_text('using FantasyCard.Domain.Combat; using FantasyCard.Domain.Players; var cards=Enumerable.Repeat("common-01",20).ToArray(); '+body)
 argv=['dotnet','build',str(p/'Probe.csproj'),'-c','Release'];t=time.monotonic();log=e/(name+'.log')
 with log.open('w') as f:r=subprocess.run(argv,cwd=root,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 text=log.read_text();ok=r.returncode!=0 and diagnostic in text
 commands.append({'name':name,'argv':argv,'cwd':str(root),'exit_code':r.returncode,'expected':'nonzero '+diagnostic,'elapsed_seconds':time.monotonic()-t,'raw':str(log.relative_to(root)),'probe_sha256':hashlib.sha256((p/'Program.cs').read_bytes()).hexdigest()})
 results.append({'probe':name,'diagnostic':diagnostic,'exit_code':r.returncode,'matched':ok})
 (e/'commands-negative.json').write_text(json.dumps(commands,indent=2))
 if not ok:raise RuntimeError(name+' did not fail for expected old API diagnostic')
row={'case_id':'PR13-B02.1-T01','status':'Passed','historical_source_sha':'28c6c7e7','historical_test_sha256':hashlib.sha256(old).hexdigest(),'actual':results,'runtime_modified':False}
(e/'negative-case.json').write_text(json.dumps(row,indent=2));print(json.dumps(row))
