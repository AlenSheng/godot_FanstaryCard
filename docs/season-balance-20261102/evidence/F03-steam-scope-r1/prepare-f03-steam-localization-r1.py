from pathlib import Path
import json, hashlib

b = Path(__file__).parent
w = b / 'work/f03-steam-integration-r1'
out = b / 'f03-steam-localization-r1'
assert not out.exists()
out.mkdir()
entries = {
    'zh-CN': ['进入', 'Steam 登录暂未就绪，请稍后重试。'],
    'en': ['Enter', 'Steam sign-in is not ready. Please try again later.'],
    'es': ['Entrar', 'El inicio de sesión de Steam aún no está listo. Inténtalo de nuevo más tarde.'],
    'fr': ['Entrer', "La connexion Steam n'est pas encore prête. Réessayez plus tard."],
    'pt': ['Entrar', 'O início de sessão Steam ainda não está pronto. Tente novamente mais tarde.'],
    'id': ['Masuk', 'Login Steam belum siap. Coba lagi nanti.'],
    'hi': ['प्रवेश', 'Steam लॉगिन अभी तैयार नहीं है। कृपया बाद में फिर कोशिश करें।'],
    'ar': ['دخول', 'تسجيل الدخول عبر Steam غير جاهز بعد. يرجى المحاولة لاحقًا.'],
    'ru': ['Войти', 'Вход через Steam пока недоступен. Повторите попытку позже.'],
    'ja': ['入る', 'Steamログインの準備ができていません。しばらくしてから再試行してください。'],
    'ko': ['입장', 'Steam 로그인이 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.'],
}
changes = []
def save(path, content):
    old = path.read_bytes()
    relative = path.relative_to(w)
    archive = out / 'before' / relative
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(old)
    path.write_text(content, encoding='utf-8', newline='\n')
    final = out / 'after' / relative
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(path.read_bytes())
    changes.append({'path': relative.as_posix(), 'before_sha256': hashlib.sha256(old).hexdigest(),
                    'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})

for code, values in entries.items():
    p = w / ('client/data/locales/' + code + '.json')
    pack = json.loads(p.read_bytes())
    original = dict(pack['strings'])
    assert 'steam_enter' not in original and 'steam_entry_unavailable' not in original
    pack['strings']['steam_enter'], pack['strings']['steam_entry_unavailable'] = values
    assert all(pack['strings'][k] == v for k, v in original.items())
    save(p, json.dumps(pack, ensure_ascii=False, indent=2) + '\n')
p = w / 'client/ui/main.gd'
s = p.read_text(encoding='utf-8')
assert s.count('I18n.t("进入")') == 1 and s.count('I18n.t("Steam 登录暂未就绪，请稍后重试。")') == 1
save(p, s.replace('I18n.t("进入")', 'P.localized("steam_enter")').replace('I18n.t("Steam 登录暂未就绪，请稍后重试。")', 'P.localized("steam_entry_unavailable")'))

p = w / 'client/tests/ui_steam_entry_review.gd'
s = p.read_text(encoding='utf-8')
s = s.replace('for locale in ["zh-CN", "en"]:', 'for locale in Palette.languages():')
s = s.replace('("Enter" if locale == "en" else "进入")', 'Palette.localized("steam_enter")')
s = s.replace('screenshot_count == 12', 'screenshot_count == 66')
needle = '\t\t\t\treview_checks[name_tag + ": readiness state"] = buttons[0].disabled == not ready\n'
assert needle in s
s = s.replace(needle, needle + '\t\t\t\tif not ready:\n\t\t\t\t\tvar notices := $UI.content.find_children("*", "Label", true, false)\n\t\t\t\t\treview_checks[name_tag + ": localized unavailability"] = notices.any(func(label): return label.text == Palette.localized("steam_entry_unavailable"))\n')
save(p, s)
(out / 'changes.original.json').write_text(json.dumps({'new_keys': ['steam_enter', 'steam_entry_unavailable'],
    'all_existing_locale_values_preserved': True, 'languages': list(entries), 'changes': changes,
    'scope': 'Steam entry copy and 66-frame fixture only; no authentication or balance rule changes'}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'changed_files': len(changes), 'new_keys': 2, 'languages': len(entries), 'expected_frames': 66}))
