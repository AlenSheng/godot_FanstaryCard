from pathlib import Path
import hashlib,json,shutil,subprocess

b=Path(__file__).parent;out=b/'f03-main-integration-r1';work=b/'work/f03-main-integration-r1';name='client/tests/ui_branch_sync_preview.gd'
staged=subprocess.check_output(['git','-C',str(work),'diff','--cached','--name-only','-z']).decode().strip('\0').split('\0');assert staged==[name]
raw=(work/name).read_bytes();cached=subprocess.check_output(['git','-C',str(work),'show',':'+name]);assert raw.replace(b'\r\n',b'\n')==cached.replace(b'\r\n',b'\n')
subprocess.run(['git','-C',str(work),'diff','--cached','--check'],check=True)
shutil.copyfile(out/'source.current.json',out/'source.native112.original.json')
(out/'ui-r1-visual-rejection.original.json').write_text(json.dumps(dict(automated_report_ok=True,visual_accepted=False,reviewed_images=11,
    reason='Preview combined retained standalone settings entry with the existing hall, occluding the hall currency header in several locales; isolate the component preview background.',
    component_popup_copy_glyphs_and_bounds_passed=True,product_hall_not_modified_by_fix=True,original_33_images_retained=True),indent=2)+'\n')
subprocess.run(['git','-C',str(work),'commit','-m','test(ui): isolate retained settings preview from hall chrome'],check=True,stdout=subprocess.DEVNULL)
head=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip();info=json.loads((out/'source.current.json').read_bytes());info.update(head=head,detached_validation_commit=head,preview_only_fix_after_native112=True)
info['modified_source_sha256'][name]=hashlib.sha256(raw).hexdigest();(out/'source.current.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(dict(head=head,only_fixture_changed=True,native112_product_inputs_unchanged=True)))
