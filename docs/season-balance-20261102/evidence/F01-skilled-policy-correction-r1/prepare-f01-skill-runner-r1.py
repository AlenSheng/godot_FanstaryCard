from pathlib import Path

b=Path(__file__).parent;source=(b/'run-f01-support-week-batch1-r1.py').read_text('utf-8')
changes=[('f01-support-week-batch1-r1','f01-skill-correction-r1'),('f01-support-week-preflight-r2','f01-skill-preflight-r1'),
    ("case_id = 'support-week-first42'","case_id = 'original-skills-day15-three'"),('maximum_new = 42','maximum_new = 3'),
    ("calendar_output = b / 'f01-support-week-r1/observations'","calendar_output = b / 'f01-skill-correction/observations'"),
    ("calendar_control = private / 'f01-support-week-r1/control.private.json'","calendar_control = private / 'f01-skill-correction/control.private.json'"),
    ("budget['used'] == 255","budget['used'] == 297"),('and not calendar_control.exists()','and calendar_control.exists()'),
    ("('D03',299)","('D03',308)"),
    ("['support_week_plan','support_week_policy']","['skill_correction_plan','skill_correction_policy']"),
    ("FANTASYCARD_RUN_F01_SUPPORT_WEEK='1'","FANTASYCARD_RUN_F01_SKILL_CORRECTION='1'"),
    ('ThreeFreshNovicesReorganizeOwnedCardsDuringFirstWeek','OriginalSkilledAccountsContinueWithUsefulStarterEquipmentPolicy'),
    ('original_main_accounts_and_incomes_not_imported=True','original_accounts_continued_without_reset=True'),('support_week_only=True','skill_correction_only=True')]
for old,new in changes:
    assert old in source,old;source=source.replace(old,new)
old="{row['id'] for row in json.loads(Path(budget['support_week_plan']['source']).read_bytes())['attempts']}"
new=old+" | {row['id'] for row in json.loads(Path(budget['skill_correction_plan']['source']).read_bytes())['attempts']}"
assert old in source;source=source.replace(old,new)
target=b/'run-f01-skill-correction-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8');print(str(target))
