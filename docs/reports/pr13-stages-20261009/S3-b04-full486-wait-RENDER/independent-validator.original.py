import hashlib,itertools,json,struct,subprocess,zlib
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/B04-wait-boundary-render-r8-20261012';S=B/'work/B04-wait-boundary-render-r8-20261012/client';D=B/'work/cap-RENDER-r7-inputs';OWNER='pr13-pool-segment-b04-wait-boundary-r8-20261012';SOURCE='e745bee30335407c4e8df4ae533641e90c516bde'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def png(p):
 raw=p.read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n';at=8;size=None;ended=False;idat=bytearray()
 while at<len(raw):
  n=struct.unpack('>I',raw[at:at+4])[0];kind=raw[at+4:at+8];body=raw[at+8:at+8+n];crc=struct.unpack('>I',raw[at+8+n:at+12+n])[0];assert zlib.crc32(kind+body)&0xffffffff==crc
  if kind==b'IHDR':size=struct.unpack('>II',body[:8])
  if kind==b'IDAT':idat.extend(body)
  at+=12+n
  if kind==b'IEND':ended=True;break
 assert at==len(raw) and ended and size==(960,540) and len(zlib.decompress(idat))>960*540
 return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'width':960,'height':540,'all_PNG_chunk_CRC_verified':True,'complete_pixel_stream_verified':True}
def main():
 state=dict(l.split('=',1) for l in subprocess.check_output(['systemctl','show',OWNER,'--property=MainPID,ActiveState,ExecMainStatus,LoadState'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0' and state['LoadState']=='loaded';result=json.loads((E/'result.original.json').read_bytes());assert result['ok'] and result['native_clean'] and result['owned_container_removed'] and result['original_outputs_preserved_before_teardown'];native=json.loads((E/'retained-native-outputs/native-result.json').read_bytes());rows=native['observations'];keys=[(r['hero'],r['language'],tuple(r['resolution']),r['fps_cap'],r['controlled_response_delay_ms'],r['case_id']) for r in rows];expected=set(itertools.product(('Mage','Priest','Guardian'),('zh-CN','en'),((1920,1080),(1280,720),(960,540)),(30,60,144),(0,100,300),('PR13-B04.3-T01','PR13-B04.3-T02','PR13-B04.3-T03')));assert len(rows)==len(set(keys))==486 and set(keys)==expected and all(r['passed'] for r in rows) and native['ok'] and not native['failures'] and native['source_sha']==SOURCE and native['display_driver']!='headless'
 R=Path('/opt/fantasycard-github');git=['git','-c','safe.directory='+str(R),'-C',str(R)];verified=0
 for line in subprocess.check_output([*git,'ls-tree','-r',SOURCE,'--','client'],text=True).splitlines():
  header,name=line.split('\t');mode,kind,oid=header.split();assert kind=='blob'
  if name=='client/tests/pr13_cap_effective_render.gd':continue
  p=S/Path(name).relative_to('client');assert p.is_file() and not p.is_symlink();raw=p.read_bytes();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid;verified+=1
 assert verified==2123
 meta=json.loads((D/'manifest.json').read_bytes())
 for r in meta['files']:
  p=D/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
 eligible=[r for r in rows if r['screenshot']];assert len(eligible)==18 and len({r['screenshot'] for r in eligible})==18;images=[]
 for r in eligible:
  p=E/'original-pixels'/r['screenshot'];info=png(p);assert info['sha256']==r['actual']['original_pixel_SHA256'] and info['bytes']==r['actual']['original_pixel_bytes'] and r['actual']['original_pixel_copied_immediately_after_successful_capture'];images.append({'name':p.name,**info})
 assert len(list((E/'original-pixels').glob('*.png')))==18
 logs='\n'.join(p.read_text(errors='replace') for p in (E/'retained-native-outputs').glob('*.original.log'));assert not any(marker.lower() in logs.lower() for marker in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use'))
 v={'ok':True,'implementation_source_sha':SOURCE,'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,'actual_client_Git_objects_verified':verified,'actual_native_frame_rows':486,'original_PNGs':images,'actual_shared_source_members_unchanged':len(meta['files']),'actual_source_still_complete_after_render':True,'normal_shutdown_clean':True,'visual_review_pending':True,'canonical_profiles_closed':0,'MAIN_accepted':False};p=E/'independent-validation.original.json';assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode());print(json.dumps({'ok':True,'actual_rows':486,'original_PNGs':18,'client_Git_objects':verified,'normal_shutdown_clean':True,'visual_review_pending':True}))
if __name__=='__main__':main()
