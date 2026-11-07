import subprocess,json,datetime
names=['ASPNETCORE_ENVIRONMENT','DOTNET_ENVIRONMENT','Identity__EnableLocalAuth','Identity__AllowManagedLocalAuthInProduction','ProtobufHttp__AllowLegacyJson','Realtime__AllowLegacyAccessTokenQuery'];rows={}
for name in names:
 r=subprocess.run(['sudo','-n','docker','exec','60bab052fd10','printenv',name],capture_output=True,text=True,timeout=10)
 value=r.stdout.strip() if r.returncode==0 else None
 rows[name]=value if value is None or value.lower() in ['true','false','1','0','production','development','staging'] else '[UNEXPECTED VALUE REDACTED]'
print(json.dumps(dict(readonly=True,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),container='60bab052fd10',selected_nonsecret_flags=rows,no_secret_names_requested=True,production_modified=False)))
