"""Bounded cloud software rendering with owned resources and retained pixels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import uuid

LABEL = 'pr13-cloud-render-20261010'
FLOOR = 500000000
BASE_IMAGE = 'sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f'


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def docker(*args, check=True):
    return subprocess.run(['sudo', '-n', 'docker', *args], check=check,
                          capture_output=True, text=True, timeout=30)


def guard(output, reserve_memory=0, reserve_disk=0):
    memory = {line.split(':')[0]: int(line.split()[1]) * 1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if line.startswith('MemAvailable:')}
    disk = shutil.disk_usage(output)
    sample = {'at': time.time(), 'memory_available_bytes': memory['MemAvailable'],
              'disk_available_bytes': disk.free, 'disk_total_bytes': disk.total}
    with (output/'resource-samples.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(sample) + '\n')
    if memory['MemAvailable'] < FLOOR + reserve_memory or disk.free < disk.total * .15 + reserve_disk:
        raise RuntimeError('Cloud resource floor would be crossed')
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
        if response.status != 200:
            raise RuntimeError('Production health unavailable during owned rendering')
    return sample


def wait_process(process, output, deadline):
    try:
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned render/build deadline reached')
            guard(output)
            time.sleep(2)
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def inspect_owned(container):
    if not re.fullmatch(r'[0-9a-f]{64}', container):
        raise ValueError('Exact immutable container ID required')
    info = json.loads(docker('inspect', container).stdout)[0]
    labels = info.get('Config', {}).get('Labels') or {}
    if info['Id'] != container or labels.get('codex.task') != LABEL:
        raise ValueError('Exact owned renderer identity differs; teardown refused')
    return info


def build(dockerfile, output):
    dockerfile = dockerfile.resolve(strict=True)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    guard(output, reserve_memory=1024**3, reserve_disk=256*1024**2)
    docker('image', 'inspect', BASE_IMAGE)
    context = output/'context'
    context.mkdir()
    shutil.copyfile(dockerfile, context/'Dockerfile')
    tag = 'fantasycard-pr13-render:' + uuid.uuid4().hex
    command = ['sudo', '-n', 'docker', 'build', '--memory', '1024m', '--cpu-period', '100000',
               '--cpu-quota', '100000', '--label', 'codex.task=' + LABEL,
               '--build-arg', 'BASE_IMAGE=' + BASE_IMAGE, '-t', tag, str(context)]
    write(output/'preregistration.json', {'mode': 'build', 'base_image': BASE_IMAGE,
          'dockerfile_sha256': sha(dockerfile), 'command': command, 'deadline_seconds': 600,
          'memory_floor_bytes': FLOOR, 'disk_floor_percent': 15, 'production_changed': False})
    result = {'ok': False, 'scope': 'Owned software-render test image only'}
    try:
        with (output/'build.log').open('xb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'DOCKER_BUILDKIT': '0'})
            result['exit_code'] = wait_process(process, output, time.monotonic()+600)
        if result['exit_code'] == 0:
            info = json.loads(docker('image', 'inspect', tag).stdout)[0]
            result.update(image_id=info['Id'], tag=tag, dockerfile_sha256=sha(dockerfile), ok=True)
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
    finally:
        write(output/'result.json', result)
    return result


def render(image, source, inputs, output, scene, *, expected_rows=48, expected_screenshots=8):
    if type(expected_rows) is not int or not 1 <= expected_rows <= 5000 or type(expected_screenshots) is not int or not 1 <= expected_screenshots <= 64:
        raise ValueError('Explicit bounded render matrix and screenshot counts required')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('Immutable renderer image ID required')
    if not scene.startswith('res://tests/') or not scene.endswith('.tscn') or '..' in scene:
        raise ValueError('Only an explicit repository fixture scene may run')
    source = source.resolve(strict=True)
    output = output.resolve()
    frozen = json.loads(inputs.read_text('utf-8'))
    if not isinstance(frozen, dict) or not frozen:
        raise ValueError('Exact source input manifest required')
    for name, digest in frozen.items():
        path = (source/name).resolve(strict=True)
        if not path.is_relative_to(source) or sha(path) != digest:
            raise ValueError('Renderer source escaped or changed')
    output.mkdir(parents=True, exist_ok=False)
    launch = guard(output, reserve_memory=1536*1024**2, reserve_disk=64*1024**2)
    container = None
    result = {'ok': False, 'render_image': image, 'production_changed': False,
              'scope': 'Cloud software GPU rendered fixture; no hardware FPS, LIVE, human or capacity claim'}
    write(output/'preregistration.json', {'mode': 'render', 'image': image, 'scene': scene,
          'input_manifest_sha256': sha(inputs), 'expected_matrix_rows': expected_rows, 'expected_screenshots': expected_screenshots,
          'network': 'none', 'memory_limit_bytes': 1536*1024**2, 'cpu_cores': 1,
          'deadline_seconds': 180, 'launch_resources': launch})
    try:
        container = docker('run', '-d', '--name', 'pr13-cloud-render-' + uuid.uuid4().hex,
                           '--label', 'codex.task=' + LABEL, '--network', 'none', '--memory', '1536m',
                           '--cpus', '1', '--shm-size', '128m', '--user', '1000:1000',
                           '-e', 'HOME=/tmp/render-home', '-e', 'XDG_DATA_HOME=/tmp/render-data',
                           '-e', 'XDG_CONFIG_HOME=/tmp/render-config', '-e', 'XDG_CACHE_HOME=/tmp/render-cache',
                           '-e', 'FANTASYCARD_SERVER_URL=http://127.0.0.1:1',
                           '-e', 'FANTASYCARD_ART_EVIDENCE=/evidence',
                           '-v', str(source/'client')+':/work/client:ro', '-v', str(output)+':/evidence',
                           image, 'sleep', '240').stdout.strip()
        inspect_owned(container)
        command = ['sudo', '-n', 'docker', 'exec', container, 'xvfb-run', '-a', '-s',
                   '-screen 0 1920x1080x24 -nolisten tcp', 'godot', '--path', '/work/client',
                   '--display-driver', 'x11', '--rendering-method', 'gl_compatibility',
                   '--audio-driver', 'Dummy', '--max-fps', '30', '--windowed', scene]
        with (output/'engine.log').open('xb') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            code = wait_process(process, output, time.monotonic()+180)
        text = (output/'engine.log').read_text('utf-8', errors='replace')
        native = json.loads((output/'native-result.json').read_text('utf-8')) if (output/'native-result.json').exists() else {}
        pixels = sorted(output.glob('*.png'))
        result.update(exit_code=code, native_ok=native.get('ok') is True,
                      observations=len(native.get('observations', [])), screenshots=len(pixels),
                      display_driver=native.get('display_driver'), adapter=native.get('adapter'))
        result['native_clean'] = not any(marker in text for marker in ['SCRIPT ERROR', 'Parse Error', 'Failed to load script'])
        result['ok'] = code == 0 and result['native_clean'] and result['native_ok'] and result['observations'] == expected_rows and len(pixels) == expected_screenshots and result['display_driver'] != 'headless'
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
    finally:
        if container:
            info = inspect_owned(container)
            result['oom_killed'] = info['State']['OOMKilled']
            docker('rm', '-f', container)
            result['owned_container_removed'] = True
        result['source_inputs_unchanged'] = all(sha(source/name) == digest for name, digest in frozen.items())
        result['ok'] = result['ok'] and result.get('owned_container_removed', False) and not result.get('oom_killed', True) and result['source_inputs_unchanged']
        write(output/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    building = sub.add_parser('build')
    building.add_argument('--dockerfile', type=Path, required=True)
    building.add_argument('--output', type=Path, required=True)
    rendering = sub.add_parser('render')
    rendering.add_argument('--image', required=True)
    rendering.add_argument('--source', type=Path, required=True)
    rendering.add_argument('--inputs', type=Path, required=True)
    rendering.add_argument('--output', type=Path, required=True)
    rendering.add_argument('--scene', default='res://tests/pr13_target_wait_frames.tscn')
    rendering.add_argument('--expected-rows', type=int, default=48)
    rendering.add_argument('--expected-screenshots', type=int, default=8)
    args = parser.parse_args()
    result = build(args.dockerfile, args.output) if args.mode == 'build' else render(args.image, args.source, args.inputs, args.output, args.scene, expected_rows=args.expected_rows, expected_screenshots=args.expected_screenshots)
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
