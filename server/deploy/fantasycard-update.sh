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
self_source="$app_dir/deploy/fantasycard-update.sh"

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
  git -C "$repo" switch --track -c "$branch" "origin/$branch"
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

if [[ "$deployed" == "$target" ]]; then
  echo "服务器已是最新版本：$target"
  curl --fail --silent --show-error --max-time 5 http://127.0.0.1/health/ready >/dev/null
  echo '健康检查通过。'
  exit 0
fi

umask 077
mkdir -p "$backup_dir"
backup="$backup_dir/fantasycard-$(date -u +%Y%m%dT%H%M%SZ)-before-$target.dump"
echo "正在备份数据库：$backup"
sudo docker compose -f "$compose" --env-file "$env_file" exec -T postgres \
  pg_dump -U fantasycard -d fantasycard --format=custom --no-owner --no-privileges > "$backup"
test -s "$backup"
sudo docker compose -f "$compose" --env-file "$env_file" exec -T postgres \
  pg_restore --list < "$backup" >/dev/null

if [[ "$current" != "$target" ]]; then
  git -C "$repo" merge --ff-only "$target"
fi

echo "正在构建 GitHub 版本：$target"
sudo docker compose -f "$compose" --env-file "$env_file" build server
sudo docker compose -f "$compose" --env-file "$env_file" up -d --no-deps server

for attempt in {1..24}; do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1/health/ready >/dev/null 2>&1; then
    printf '%s\n' "$target" > "$deployed_marker"
    if [[ -f "$self_source" ]]; then
      install -m 700 "$self_source" "$0"
    fi
    echo "更新成功：$target"
    echo "数据库备份：$backup"
    exit 0
  fi
  sleep 5
done

echo '新版本未通过健康检查；数据库备份与原部署目录均已保留，请先排查，勿清库。' >&2
exit 1
