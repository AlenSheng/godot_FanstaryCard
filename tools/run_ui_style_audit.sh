#!/usr/bin/env bash
# Render production UI fixtures at fixed repository commits. No server actions.
set -euo pipefail
task_repo=$(git rev-parse --show-toplevel)
cd "$task_repo"
task_base=${1:-b7099ef716235be68395255360cbd5cf6c67baff}
task_out=${2:-/tmp/relicbound-ui-evidence}
task_sha=$(git rev-parse HEAD)
task_before=$(mktemp -d /tmp/relicbound-ui-before.XXXXXX)
mkdir -p "$task_out/logs" "$task_out/core/before" "$task_out/core/after" "$task_out/extended/before" "$task_out/extended/after" "$task_out/art"
git diff --quiet -- client || { echo 'Tracked client files must be committed before fixed-SHA capture.' >&2; exit 2; }
git archive "$task_base" client | tar -x -C "$task_before"
cp client/tests/ui_style_audit.gd client/tests/ui_style_extended.gd client/tests/ui_style_audit.tscn client/tests/ui_style_extended.tscn "$task_before/client/tests/"
timeout 120s godot --headless --editor --path client --import > "$task_out/logs/import.log" 2>&1
timeout 120s godot --headless --editor --path "$task_before/client" --import > "$task_out/logs/before-import.log" 2>&1
FANTASYCARD_UI_CHECKS="$task_out/native.json" timeout 120s godot --headless --path client --script res://tests/run_ui_style_checks.gd > "$task_out/logs/native.log" 2>&1
for task_phase in before after; do
  task_project="$task_before/client"
  task_capture_sha="$task_base"
  task_assert=0
  if [[ "$task_phase" == after ]]; then
    task_project=client
    task_capture_sha="$task_sha"
    task_assert=1
  fi
  for task_kind in core extended; do
    task_scene=ui_style_audit
    if [[ "$task_kind" == extended ]]; then task_scene=ui_style_extended; fi
    # Baseline failure is expected and retained; after failure stops acceptance.
    task_status=0
    DISPLAY=${DISPLAY:-:93} FANTASYCARD_SERVER_URL=http://127.0.0.1:38971 \
      FANTASYCARD_SOURCE_SHA="$task_capture_sha" FANTASYCARD_UI_ASSERT_FIXES="$task_assert" \
      FANTASYCARD_UI_EVIDENCE="$task_out/$task_kind/$task_phase" \
      timeout 360s godot --path "$task_project" --audio-driver Dummy --windowed --resolution 1920x1080 "res://tests/$task_scene.tscn" > "$task_out/logs/$task_kind-$task_phase.log" 2>&1 || task_status=$?
    if [[ "$task_phase" == after && "$task_status" != 0 ]]; then exit "$task_status"; fi
    test -f "$task_out/$task_kind/$task_phase/report.json"
  done
done
DISPLAY=${DISPLAY:-:93} FANTASYCARD_SERVER_URL=http://127.0.0.1:38971 \
  FANTASYCARD_SOURCE_SHA="$task_sha" FANTASYCARD_ART_LANGUAGE=en FANTASYCARD_ART_EVIDENCE="$task_out/art" timeout 180s godot --path client --audio-driver Dummy --windowed --resolution 1920x1080 res://tests/art_preview.tscn > "$task_out/logs/art.log" 2>&1
python -c 'import json,sys; assert json.load(open(sys.argv[1]))["ok"]' "$task_out/art/report.json"
mkdir -p "$task_out/codex"
DISPLAY=${DISPLAY:-:93} FANTASYCARD_SERVER_URL=http://127.0.0.1:38971 FANTASYCARD_SOURCE_SHA="$task_sha" FANTASYCARD_UI_ASSERT_FIXES=1 FANTASYCARD_UI_EVIDENCE="$task_out/codex" timeout 180s godot --path client --audio-driver Dummy --windowed --resolution 1920x1080 res://tests/ui_style_codex_review.tscn > "$task_out/logs/codex.log" 2>&1
python tools/audit_ui_style_evidence.py --evidence-root "$task_out/core" --out "$task_out/review-core"
python tools/audit_ui_style_evidence.py --evidence-root "$task_out/extended" --out "$task_out/review-extended"
printf 'Evidence: %s\nUI source: %s\nBaseline: %s\n' "$task_out" "$task_sha" "$task_base"
