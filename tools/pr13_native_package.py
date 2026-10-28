"""Verify a complete private debug package before direct Native launch."""
import hashlib
import json
from pathlib import Path, PurePosixPath

SCHEMA='pr13-native-gameplay-package-v1'
CONTRACT_LIMIT=4*1024*1024

def sha256(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def _hash(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def _relative(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:raise ValueError('Unsafe package input path')
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or path.as_posix()!=value:raise ValueError('Unsafe package input path')
    return path

def _actual_input(project,name,expected):
    relative=_relative(name);path=project/Path(*relative.parts)
    if not _hash(expected) or not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(project):
        raise ValueError('Package input is missing or unsafe: '+name)
    if sha256(path)!=expected:raise ValueError('Package input checksum changed: '+name)

def verify_package(executable,contract_path,project,expected_source_paths):
    executable,contract_path,project=Path(executable),Path(contract_path),Path(project).resolve()
    if executable.is_symlink() or not executable.is_file() or executable.suffix.lower()!='.exe' or executable.name.lower().endswith(('console.exe','_console.exe')):
        raise ValueError('Package must directly execute the verified Windows engine, not a launcher')
    pck=executable.with_suffix('.pck')
    if not pck.is_file() or pck.is_symlink():raise ValueError('Companion PCK is missing or unsafe')
    if not contract_path.is_file() or contract_path.is_symlink() or contract_path.stat().st_size>CONTRACT_LIMIT:raise ValueError('Package contract missing or too large')
    raw=contract_path.read_bytes();contract=json.loads(raw.decode('utf8'))
    if not isinstance(contract,dict) or contract.get('schema')!=SCHEMA:raise ValueError('Unsupported package contract')
    if contract.get('entry_scene')!='res://tests/gameplay_load_client.tscn':raise ValueError('Package does not declare the complete gameplay entry')
    features=contract.get('runtime_features')
    if not isinstance(features,dict) or features.get('debug_features') is not True or type(features.get('max_fps')) is not int or features['max_fps']!=0 or type(features.get('physics_ticks')) is not int or features['physics_ticks']!=60:
        raise ValueError('Package runtime must preserve debug login, uncapped FPS and physics')
    inputs=contract.get('source_inputs');expected=set(expected_source_paths)
    if not expected or not isinstance(inputs,dict) or set(inputs)!=expected:raise ValueError('Complete tracked client input set is required')
    for name,digest in inputs.items():
        relative=_relative(name)
        if not relative.parts or relative.parts[0]!='client':raise ValueError('Package source is outside client')
        _actual_input(project,PurePosixPath(*relative.parts[1:]).as_posix(),digest)
    extras=contract.get('extra_inputs')
    if not isinstance(extras,dict) or not extras:raise ValueError('Private entry inputs must be bound to the package')
    for name,digest in extras.items():_actual_input(project,name,digest)
    for name,path in (('executable_sha256',executable),('pck_sha256',pck)):
        if not _hash(contract.get(name)) or sha256(path)!=contract[name]:raise ValueError('Package checksum changed: '+name)
    return {'schema':SCHEMA,'executable':str(executable.resolve()),'pck':str(pck.resolve()),'contract':str(contract_path.resolve()),
            'executable_sha256':contract['executable_sha256'],'pck_sha256':contract['pck_sha256'],
            'contract_sha256':hashlib.sha256(raw).hexdigest(),'source_input_count':len(inputs),'extra_input_count':len(extras),
            'runtime_features':features,'scope':'Static verified complete debug package; per-process PID/epoch authority remains Native status and final report'}

def launch_command(editor,project,*,package=None,max_fps=None):
    if package is not None:
        if max_fps is not None:raise ValueError('Verified full debug package requires its uncapped FPS profile')
        return [str(package),'--headless','--audio-driver','Dummy']
    result=[str(editor),'--headless','--audio-driver','Dummy','--path',str(project)]
    if max_fps is not None:result+=['--max-fps',str(max_fps)]
    return result+['res://tests/gameplay_load_client.tscn']

def package_environment(feature_report):
    if not str(feature_report):raise ValueError('Unique runtime feature path required')
    return {'FANTASYCARD_PRIVATE_QA_MODE':'gameplay','NATIVE_RUNTIME_FEATURE_REPORT':str(feature_report)}

def package_unchanged(proof):
    return all(sha256(proof[name])==proof[name+'_sha256'] for name in ('executable','pck','contract'))

def runtime_capabilities(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>65536:raise ValueError('Runtime capability report missing or unsafe')
    raw=path.read_bytes();value=json.loads(raw.decode('utf8'))
    if not isinstance(value,dict):raise ValueError('Runtime capability report must be an object')
    required={'debug_features_retained','game_process_not_editor_hint','development_login_unchanged','no_FPS_cap','normal_physics_tick_rate','no_export_key_environment'}
    checks=value.get('checks') if isinstance(value,dict) else None
    if (value.get('mode')!='gameplay' or value.get('debug_features') is not True
            or type(value.get('max_fps')) is not int or value['max_fps']!=0
            or type(value.get('physics_ticks')) is not int or value['physics_ticks']!=60
            or value.get('is_editor_binary') is not False or not isinstance(checks,dict)
            or set(checks)!=required or any(checks[key] is not True for key in required)):
        raise ValueError('Runtime capability contract changed')
    return {'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'features':value,
            'scope':'Runtime capability evidence only; PID/session ownership is validated from Native status and final report'}
