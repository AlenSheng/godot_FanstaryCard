"""Verify generated website copies. This does not replace browser layout QA."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "server/site"


def audit(code):
    bundle = json.loads((SITE / "assets/locales" / (code + ".json")).read_text(encoding="utf-8"))
    messages = bundle["messages"]
    errors = []
    checks = 0
    pages = []
    for original in [SITE / name for name in ("index.html", "classes.html", "seasons.html")]:
        target = SITE / code / original.name
        document = html.document_fromstring(target.read_text(encoding="utf-8"))
        pages.append(str(target.relative_to(ROOT)))
        if document.get("lang") != code or document.get("dir") != bundle["direction"]:
            errors.append({"page": original.name, "kind": "language_metadata"})
        for element in document.iter():
            if not isinstance(element.tag, str):
                continue
            for source, attribute in [("data-en", "content"), ("data-alt-en", "alt"), ("data-aria-en", "aria-label")]:
                key = element.get(source)
                if not key:
                    continue
                checks += 1
                if source == "data-en":
                    actual = element.get("content") if element.tag == "meta" else element.text_content()
                else:
                    actual = element.get(attribute)
                if key not in messages or actual != messages.get(key):
                    errors.append({"page": original.name, "kind": "translation", "source": key, "attribute": attribute})
            extra = element.get("data-l10n-extra")
            if extra:
                checks += 1
                if element.text_content() != messages.get(extra):
                    errors.append({"page": original.name, "kind": "static_caption", "source": extra})
            for attribute in ["href", "src"]:
                url = element.get(attribute, "")
                parsed = urlsplit(url)
                if not url or parsed.netloc or parsed.scheme or not parsed.path.startswith("/"):
                    continue
                checks += 1
                file = SITE / unquote(parsed.path).lstrip("/")
                if file.is_dir():
                    file = file / "index.html"
                if not file.is_file():
                    errors.append({"page": original.name, "kind": "broken_local_link", "url": url})
                elif attribute == "href" and parsed.fragment and file.suffix == ".html":
                    linked = html.document_fromstring(file.read_text(encoding="utf-8"))
                    anchor = unquote(parsed.fragment)
                    if not linked.xpath('//*[@id=$anchor or @data-class-panel=$anchor]', anchor=anchor):
                        errors.append({"page": original.name, "kind": "broken_anchor", "url": url})
    files = [SITE / "assets/site.js", SITE / "assets/site.css", SITE / "assets/locales" / (code + ".json")]
    files += [ROOT / page for page in pages]
    return {"locale": code, "static_ok": not errors, "static_checks": checks,
            "errors": errors, "pages": pages, "browser_layout_ok": False,
            "browser_status": "RequiresSeparateBrowserValidation",
            "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    codes = args.locale or [p.stem for p in sorted((ROOT / "config/site_locales").glob("*.json"))]
    registry = json.loads((ROOT / "client/data/localization_registry.json").read_text(encoding="utf-8"))["languages"]
    manifest = json.loads((SITE / "assets/locales/manifest.json").read_text(encoding="utf-8"))["languages"]
    expected = {"zh" if code == "zh-CN" else code for code, item in registry.items() if item["status"] in ("baseline", "released")}
    if expected != {item["code"] for item in manifest} or len(manifest) != len(expected):
        raise ValueError("Website and game language registries differ")
    results = [audit(code) for code in codes]
    report = {"static_ok": all(r["static_ok"] for r in results), "locales": results,
              "whole_visual_acceptance": False, "independent_review_passed": False}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"static_ok": report["static_ok"], "checks": sum(r["static_checks"] for r in results),
                      "errors": [e for r in results for e in r["errors"]],
                      "browser_layout_ok": False}, ensure_ascii=True))
    return 0 if report["static_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
