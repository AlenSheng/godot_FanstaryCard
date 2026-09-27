#!/usr/bin/env bash
set -euo pipefail

app=/opt/fantasycard-github/server
game_base=https://relicbound.cn
admin_base=https://www.relicbound.cn:20000
name="adm_$(date -u +%s)"
player_id=''
key=$(sed -n 's/^FANTASYCARD_ADMIN_KEY=//p' "$app/.env" | tail -n 1)
test ${#key} -ge 32

cleanup() {
    if [[ -n "$player_id" && "$player_id" =~ ^[0-9a-f-]{36}$ ]]; then
        sudo docker compose -f "$app/compose.cloud.yaml" --env-file "$app/.env" exec -T postgres \
            psql -U fantasycard -d fantasycard -v ON_ERROR_STOP=1 -Atc \
            "DELETE FROM players WHERE user_id='$player_id'::uuid AND display_name='$name'" >/dev/null
    fi
}
trap cleanup EXIT
printf 'stage=login\n'

get_admin() {
    curl -sS --fail-with-body --max-time 10 --resolve www.relicbound.cn:20000:127.0.0.1 \
        -H "X-Admin-Key: $key" "$admin_base$1"
}
post_admin() {
    curl -sS --fail-with-body --max-time 10 --resolve www.relicbound.cn:20000:127.0.0.1 -X POST \
        -H "X-Admin-Key: $key" -H 'Content-Type: application/json' \
        -H "Idempotency-Key: $(cat /proc/sys/kernel/random/uuid)" \
        -d "$2" "$admin_base/api/admin/$1"
}
post_player() {
    curl -ksS --fail-with-body --max-time 10 -X POST \
        -H "Authorization: Bearer $token" -H "Idempotency-Key: $(cat /proc/sys/kernel/random/uuid)" \
        "$game_base$1"
}
assert_eq() {
    if [[ "$1" != "$2" ]]; then
        printf 'expected %s, got %s\n' "$2" "$1" >&2
        exit 1
    fi
}

login=$(curl -ksS --fail-with-body --max-time 10 -H 'Content-Type: application/json' \
    -d "{\"deviceId\":\"admin-smoke-device\",\"displayName\":\"$name\"}" \
    "$game_base/api/v1/auth/local")
player_id=$(jq -r '.player.userId' <<< "$login")
token=$(jq -r '.accessToken' <<< "$login")
test "$player_id" != null && test -n "$token"

before=$(get_admin "/api/admin/players?q=$player_id" | jq -r '.[0].gold')
printf 'stage=gold-grant\n'
grant=$(post_admin mail "{\"playerId\":\"$player_id\",\"title\":\"后台测试金币\",\"body\":\"test\",\"attachments\":[{\"kind\":\"Gold\",\"amount\":7}]}")
mail_id=$(jq -r '.mailId' <<< "$grant")
printf 'stage=gold-claim\n'
post_player "/api/v1/mail/$mail_id/claim" >/dev/null
after_grant=$(get_admin "/api/admin/players?q=$player_id" | jq -r '.[0].gold')
assert_eq "$after_grant" "$((before + 7))"

printf 'stage=gold-revoke\n'
post_admin revoke "{\"playerId\":\"$player_id\",\"kind\":\"Gold\",\"amount\":3,\"reason\":\"smoke test\"}" >/dev/null
after_revoke=$(get_admin "/api/admin/players?q=$player_id" | jq -r '.[0].gold')
assert_eq "$after_revoke" "$((before + 4))"

equipment_before=$(get_admin "/api/admin/players/$player_id/equipment" | jq 'length')
printf 'stage=equipment-grant\n'
grant=$(post_admin mail "{\"playerId\":\"$player_id\",\"title\":\"后台测试装备\",\"body\":\"test\",\"attachments\":[{\"kind\":\"Equipment\",\"amount\":1,\"itemId\":\"White|Fire|Head\"}]}")
mail_id=$(jq -r '.mailId' <<< "$grant")
printf 'stage=equipment-claim\n'
post_player "/api/v1/mail/$mail_id/claim" >/dev/null
equipment=$(get_admin "/api/admin/players/$player_id/equipment")
assert_eq "$(jq 'length' <<< "$equipment")" "$((equipment_before + 1))"
equipment_id=$(jq -r '.[0].instanceId' <<< "$equipment")
printf 'stage=equipment-revoke\n'
post_admin revoke "{\"playerId\":\"$player_id\",\"kind\":\"Equipment\",\"amount\":1,\"itemId\":\"$equipment_id\",\"reason\":\"smoke test\"}" >/dev/null
equipment_after=$(get_admin "/api/admin/players/$player_id/equipment")
assert_eq "$(jq 'length' <<< "$equipment_after")" "$equipment_before"

printf 'stage=message\n'
post_admin message "{\"playerId\":\"$player_id\",\"title\":\"后台测试留言\",\"body\":\"hello\"}" >/dev/null
mailbox=$(curl -ksS --fail-with-body --max-time 10 -H "Authorization: Bearer $token" "$game_base/api/v1/mail/")
jq -e '.items[] | select(.title == "后台测试留言")' <<< "$mailbox" >/dev/null
jq -e '.items[] | select(.title == "道具收回通知")' <<< "$mailbox" >/dev/null

printf 'stage=ban\n'
post_admin ban "{\"playerId\":\"$player_id\",\"reason\":\"smoke test\"}" >/dev/null
blocked=$(curl -ksS --max-time 10 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" "$game_base/api/v1/mail/")
assert_eq "$blocked" 401
printf 'stage=unban\n'
post_admin unban "{\"playerId\":\"$player_id\",\"reason\":\"\"}" >/dev/null
restored=$(curl -ksS --max-time 10 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    -d "{\"deviceId\":\"admin-smoke-device\",\"displayName\":\"$name\"}" \
    "$game_base/api/v1/auth/local")
assert_eq "$restored" 200

printf 'admin smoke passed; temporary UID %s will be removed\n' "$player_id"
