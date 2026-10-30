"""Build complete, linkable static translations of the existing official site."""
import argparse
import html as entities
import json
from pathlib import Path
import re
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "server/site"
COPY_ATTRIBUTES = {"data-alt-en": "alt", "data-aria-en": "aria-label"}
PAGES = [SITE / name for name in ("index.html", "classes.html", "seasons.html")]


def update_base_documents(available):
    """Keep the accessible native selector usable before the script loads."""
    selector = '<select class="language-toggle" id="language-toggle" aria-label="语言" disabled aria-busy="true">'
    for entry in available:
        code = entities.escape(entry["code"], quote=True)
        name = entities.escape(entry["name"])
        selected = ' selected' if entry["code"] == "zh" else ''
        selector += f'<option value="{code}" lang="{code}"{selected}>{name}</option>'
    selector += '</select>'
    pattern = re.compile(r'<(button|select)\b(?=[^>]*\bid="language-toggle")[^>]*>.*?</\1>', re.S)
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        text, count = pattern.subn(lambda _: selector, text)
        if count != 1:
            raise ValueError(f"Expected one language selector: {page.name}")
        text = re.sub(r'/assets/site\.(css|js)\?v=[^"\s]+', r'/assets/site.\1?v=20261030-6', text)
        if '/assets/fonts/relicbound-sans.woff2' not in text:
            preloads = ''.join(f'<link rel="preload" href="/assets/fonts/relicbound-{role}.woff2" as="font" type="font/woff2" crossorigin>\n  ' for role in ["sans", "serif"])
            text = text.replace('<link rel="stylesheet"', preloads + '<link rel="stylesheet"', 1)
        fonts = load(SITE / "assets/fonts/manifest.json")
        for role in ("sans", "serif"):
            url = "/assets/fonts/" + fonts[role]["file"]
            text = re.sub(re.escape(url) + r'(?:\?v=[a-f0-9]+)?', url + "?v=" + fonts[role]["sha256"][:12], text)
        page.write_text(text, encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(code):
    if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", code):
        raise ValueError("Invalid language code")
    source = load(ROOT / "config/site_locale_source.json")
    pack = load(ROOT / "config/site_locales" / (code + ".json"))
    values = pack["translations"]
    if len(source) != len(values) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("Every website source string requires a nonempty translation")
    messages = dict(zip(source, values))
    messages.update(pack.get("extra", {}))
    referenced = set()
    for page in PAGES:
        tree = html.document_fromstring(page.read_text(encoding="utf-8"))
        tree.set("lang", code)
        tree.set("dir", pack.get("direction", "ltr"))
        tree.find("body").set("data-lang", code)
        selector = tree.get_element_by_id("language-toggle")
        selector.set("aria-label", messages.get("Language", "Language"))
        for option in selector:
            option.attrib.pop("selected", None)
            if option.get("value") == code:
                option.set("selected", "selected")
        for element in tree.iter():
            if any(node.get("data-site-extension") is not None for node in [element, *element.iterancestors()]):
                continue
            for key, text in list(element.attrib.items()):
                if key in ["data-en", "data-alt-en", "data-aria-en", "data-art-title-en"]:
                    referenced.add(text)
                    if text not in messages:
                        raise ValueError(f"Missing {code} website translation: {text}")
                    translated = messages[text]
                    if key == "data-en":
                        if element.tag == "meta":
                            element.set("content", translated)
                        elif element.tag == "title" or "data-i18n" in element.attrib:
                            if len(element):
                                raise ValueError("Translate nested markup explicitly")
                            element.text = translated
                    elif key in COPY_ATTRIBUTES:
                        element.set(COPY_ATTRIBUTES[key], translated)
            if element.tag == "a":
                href = element.get("href", "")
                if href.startswith("/") and not href.startswith("//") and not href.startswith("/assets/"):
                    if href == "/" or href.startswith("/#") or href.startswith("/?"):
                        href = "/index.html" + href[1:]
                    element.set("href", "/" + code + href)
            if element.text and element.text.strip() in pack.get("extra", {}):
                element.set("data-l10n-extra", element.text.strip())
                element.text = messages[element.text.strip()]
        target = SITE / code / page.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<!doctype html>\n" + html.tostring(tree, encoding="unicode", method="html") + "\n", encoding="utf-8")
    if referenced != set(source):
        raise ValueError("Website source catalog changed; update and review translations")
    destination = SITE / "assets/locales"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / (code + ".json")).write_text(json.dumps({"name": pack["name"], "direction": pack.get("direction", "ltr"), "messages": messages}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"code": code, "name": pack["name"], "direction": pack.get("direction", "ltr"), "source_strings": len(source)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", action="append")
    parser.add_argument("--mark-static-source", action="store_true", help="One-time, idempotent marking of existing English static captions")
    args = parser.parse_args()
    codes = args.locale or [p.stem for p in sorted((ROOT / "config/site_locales").glob("*.json"))]
    if args.mark_static_source:
        extra = load(ROOT / "config/site_locales" / (codes[0] + ".json")).get("extra", {})
        for page in PAGES:
            text = page.read_text(encoding="utf-8")
            for key in extra:
                pattern = r"<([a-z][a-z0-9]*)([^<>]*)>" + re.escape(key) + r"</\1>"
                def mark(match):
                    tag, attrs = match.group(1, 2)
                    if "data-i18n" in attrs or "data-l10n-extra" in attrs:
                        return match.group(0)
                    return f'<{tag}{attrs} data-l10n-extra="{entities.escape(key, quote=True)}">{key}</{tag}>'
                text = re.sub(pattern, mark, text)
            text = text.replace("/assets/site.js?v=5", "/assets/site.js?v=6").replace("/assets/site.css?v=7", "/assets/site.css?v=8")
            page.write_text(text, encoding="utf-8")
    # One registry drives static HTML, dynamic switching, and future locale packs.
    registry = load(ROOT / "client/data/localization_registry.json")["languages"]
    available = [{"code": "zh" if code == "zh-CN" else code, "name": item["name"], "direction": item["direction"]}
                 for code, item in registry.items() if item["status"] in ("baseline", "released")]
    expected = {item["code"] for item in available} - {"zh", "en"}
    if expected != {p.stem for p in (ROOT / "config/site_locales").glob("*.json")}:
        raise ValueError("Website packs must match the game's released languages")
    if len({entry["code"] for entry in available}) != len(available):
        raise ValueError("Duplicate registered website language")
    update_base_documents(available)
    results = [build(code) for code in codes]
    (SITE / "assets/locales/manifest.json").write_text(json.dumps({"languages": available}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "locales": results}, ensure_ascii=True))


if __name__ == "__main__":
    main()
