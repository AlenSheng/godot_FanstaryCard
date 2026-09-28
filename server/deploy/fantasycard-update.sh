#!/usr/bin/env bash
set -euo pipefail

# Run as the ubuntu user; only Docker commands use sudo.
repo=/opt/fantasycard-github
branch=release
app_dir="$repo/server"
compose="$app_dir/compose.cloud.yaml"
env_file="$app_dir/.env"
backup_dir=/opt/fantasycard-app/backups
deployed_marker=/opt/fantasycard-app/deployed-git-commit
manifest_dir=/opt/fantasycard-app/version-manifests
manifest="$manifest_dir/release.md5"
manifest_version="$manifest_dir/release.version"
self_source="$app_dir/deploy/fantasycard-update.sh"

write_manifest() {
  local output="$1"
  mkdir -p "$(dirname "$output")"
  (
    cd "$repo"
    git ls-files -z -- \
      server/src server/config server/protection server/deploy server/monitoring \
      protocol/http protocol/realtime .dockerignore \
      server/Directory.Build.props server/Directory.Packages.props \
      server/global.json server/NuGet.Config server/.dockerignore \
      server/compose.cloud.yaml server/Caddyfile server/site \
      ':(exclude)server/**/bin/**' ':(exclude)server/**/obj/**' |
      xargs -0 -r md5sum -- |
      awk '{ print substr($0, 35) "\t" substr($0, 1, 32) }' | LC_ALL=C sort
  ) > "$output"
}

diff_manifests() {
  local old="$1" new="$2"
  awk -F '\t' '
    NR == FNR { previous[$1] = $2; next }
    !($1 in previous) { print "A\t" $1; next }
    previous[$1] != $2 { print "M\t" $1 }
    { delete previous[$1] }
    END { for (path in previous) print "D\t" path }
  ' "$old" "$new" | LC_ALL=C sort
}

domain_certificate_ok() {
  # Godot verifies TLS against public CAs and the requested hostname. A
  # catch-all :443 site with the IP self-signed cert makes this check fail.
  local cert
  cert=$(echo | openssl s_client -connect 127.0.0.1:443 -servername www.relicbound.cn 2>/dev/null |
    openssl x509 -noout -subject -ext subjectAltName 2>/dev/null || true)
  printf '%s\n' "$cert" | grep -Eq 'DNS:www\.relicbound\.cn|DNS:relicbound\.cn|CN *= *www\.relicbound\.cn|CN *= *relicbound\.cn' &&
    ! printf '%s\n' "$cert" | grep -Eq 'CN *= *43\.172\.70\.182'
}

health_check() {
  [[ "$(curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8080/health/ready)" == Healthy ]] &&
    [[ "$(curl --fail --silent --show-error --max-time 5 \
      --resolve www.relicbound.cn:443:127.0.0.1 \
      https://www.relicbound.cn/health/ready)" == Healthy ]] &&
    domain_certificate_ok &&
    [[ "$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' \
      --resolve www.relicbound.cn:443:127.0.0.1 \
      https://www.relicbound.cn/admin)" == 404 ]] &&
    [[ "$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' \
      --resolve www.relicbound.cn:443:127.0.0.1 \
      https://www.relicbound.cn/api/admin/client-settings)" == 404 ]] &&
    curl --fail --silent --show-error --max-time 5 --output /dev/null \
      --resolve www.relicbound.cn:20000:127.0.0.1 \
      https://www.relicbound.cn:20000/admin
}

normalize_monitoring_permissions() {
  # The deployment uses a restrictive umask. Compose services run as
  # unprivileged users, so bind-mounted monitoring configuration must remain
  # readable without making the repository or secrets world-readable.
  if [[ -d "$app_dir/monitoring" ]]; then
    find "$app_dir/monitoring" -type d -exec chmod 755 {} +
    find "$app_dir/monitoring" -type f -exec chmod 644 {} +
  fi
}

if [[ "$(id -un)" != ubuntu ]]; then
  echo '请以 ubuntu 用户运行此命令（不要在整个命令前加 sudo）。' >&2
  exit 1
fi

exec 9>/tmp/fantasycard-update.lock
if ! flock -n 9; then
  echo '已有一次服务器更新正在运行。' >&2
  exit 1
fi

if [[ ! -f "$compose" || ! -f "$env_file" ]]; then
  echo '缺少云端 Compose 配置或 .env，已停止更新。' >&2
  exit 1
fi

if ! git -C "$repo" diff --quiet || ! git -C "$repo" diff --cached --quiet; then
  echo 'GitHub 工作副本有未提交的代码改动，已停止更新。' >&2
  exit 1
fi

git -C "$repo" fetch --filter=blob:none origin "$branch"
if git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" switch "$branch"
else
  # The original cloud checkout was cloned with --single-branch, so the
  # remote-tracking ref origin/release may not exist yet. FETCH_HEAD was
  # obtained directly from the configured GitHub remote above.
  git -C "$repo" switch -c "$branch" FETCH_HEAD
fi

current=$(git -C "$repo" rev-parse HEAD)
target=$(git -C "$repo" rev-parse FETCH_HEAD)
deployed=$(cat "$deployed_marker" 2>/dev/null || true)

if [[ "$current" != "$target" ]]; then
  if ! git -C "$repo" merge-base --is-ancestor "$current" "$target"; then
    if [[ -f "$repo/.git/shallow" ]]; then
      git -C "$repo" fetch --filter=blob:none --unshallow origin "$branch"
      target=$(git -C "$repo" rev-parse FETCH_HEAD)
    fi
  fi
  if ! git -C "$repo" merge-base --is-ancestor "$current" "$target"; then
    echo '远端分支不能快进到当前版本，已停止更新（不会强制覆盖）。' >&2
    exit 1
  fi
fi

if [[ "$current" == "$target" && "$deployed" == "$target" ]]; then
  echo "服务器已是最新版本：$target"
  health_check
  if [[ ! -f "$manifest" || ! -f "$manifest_version" || "$(cat "$manifest_version")" != "$target" ]]; then
    umask 077
    write_manifest "$manifest.new"
    mv "$manifest.new" "$manifest"
    printf '%s\n' "$target" > "$manifest_version"
  fi
  echo '健康检查通过。'
  exit 0
fi

umask 077
changes=$(mktemp)
trap 'rm -f "$changes" "$manifest.new"' EXIT
baseline_valid=false
if [[ -f "$manifest" && -f "$manifest_version" && "$(cat "$manifest_version")" == "$deployed" ]]; then
  baseline_valid=true
fi

if [[ "$current" != "$target" ]]; then
  git -C "$repo" merge --ff-only "$target"
fi

normalize_monitoring_permissions

write_manifest "$manifest.new"
runtime_changed=false
proxy_changed=false
if [[ "$baseline_valid" == true ]]; then
  diff_manifests "$manifest" "$manifest.new" > "$changes"
  echo "文件 MD5 差异：$(wc -l < "$changes" | tr -d ' ') 个；A=新增，M=修改，D=删除。"
  if [[ -s "$changes" ]]; then cat "$changes"; fi
  while IFS=$'\t' read -r action file; do
    case "$file" in
      server/Caddyfile|server/site/*) proxy_changed=true ;;
      server/compose.cloud.yaml) runtime_changed=true; proxy_changed=true ;;
      server/deploy/*) ;;
      server/*|protocol/*|.dockerignore) runtime_changed=true ;;
    esac
  done < "$changes"
else
  echo '没有与已部署版本匹配的 MD5 基线，本次完整重建服务。'
  runtime_changed=true
  proxy_changed=true
fi

backup=''
if [[ "$runtime_changed" == true ]]; then
  mkdir -p "$backup_dir"
  backup="$backup_dir/fantasycard-$(date -u +%Y%m%dT%H%M%SZ)-before-$target.dump"
  echo "正在备份数据库：$backup"
  sudo docker compose -f "$compose" --env-file "$env_file" exec -T postgres \
    pg_dump -U fantasycard -d fantasycard --format=custom --no-owner --no-privileges > "$backup"
  test -s "$backup"
  sudo docker compose -f "$compose" --env-file "$env_file" exec -T postgres \
    pg_restore --list < "$backup" >/dev/null
  echo "正在构建服务端版本：$target"
  sudo docker compose -f "$compose" --env-file "$env_file" build server
  sudo docker compose -f "$compose" --env-file "$env_file" up -d --no-deps server
  sudo docker compose -f "$compose" --env-file "$env_file" up -d --no-deps \
    otel-collector node-exporter prometheus grafana
fi
if [[ "$proxy_changed" == true ]]; then
  sudo docker compose -f "$compose" --env-file "$env_file" up -d --no-deps --force-recreate caddy
fi
if [[ "$runtime_changed" == false && "$proxy_changed" == false ]]; then
  echo '服务端运行文件未变化，无需重建容器。Git 已按差异拉取版本。'
fi

for attempt in {1..24}; do
  if health_check >/dev/null 2>&1; then
    mv "$manifest.new" "$manifest"
    printf '%s\n' "$target" > "$manifest_version"
    printf '%s\n' "$target" > "$deployed_marker"
    if [[ -f "$self_source" ]] && ! cmp -s "$self_source" "$0"; then
      install -m 700 "$self_source" "$0"
    fi
    echo "更新成功：$target"
    if [[ -n "$backup" ]]; then echo "数据库备份：$backup"; fi
    exit 0
  fi
  sleep 5
done

echo '新版本未通过健康检查；数据库备份与原部署目录均已保留，请先排查，勿清库。' >&2
echo 'www.relicbound.cn certificate:' >&2
echo | openssl s_client -connect 127.0.0.1:443 -servername www.relicbound.cn 2>/dev/null |
  openssl x509 -noout -subject -issuer -ext subjectAltName >&2 || true
exit 1
