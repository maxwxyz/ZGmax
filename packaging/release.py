"""Neue Programmversion veroeffentlichen und die Aenderungshistorie erzeugen.

Ablauf: Jede sichtbare Aenderung bekommt beim Committen einen Eintrag in programm/CHANGELOG.json unter "unreleased"
(deutsch und englisch, gleiche Reihenfolge). Fuer ein Release:
    .venv/bin/python packaging/release.py minor      (oder patch / major)
verschiebt die Eintraege in eine neue Version mit Datum, erhoeht die Versionsnummer (die App liest sie aus
CHANGELOG.json) und schreibt CHANGELOG.md (deutsch) und CHANGELOG_EN.md. Mit --git wird committet und ein Tag
v<version> gesetzt. Danach die Apps bauen (GitHub: Actions -> "Apps bauen").
    .venv/bin/python packaging/release.py --draft    Commits seit dem letzten Tag als Vorlage fuer Eintraege
    .venv/bin/python packaging/release.py --md       nur CHANGELOG.md / CHANGELOG_EN.md neu schreiben
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "programm"))
from version import fmt_date  # noqa: E402
CL = os.path.join(ROOT, "programm", "CHANGELOG.json")
TITLE = {"de": ("Änderungshistorie", "Version {} vom {}", "In Arbeit"),
         "en": ("Change history", "Version {} of {}", "In progress")}


def load():
    with open(CL, encoding="utf-8") as f:
        return json.load(f)


def save(data):
    with open(CL, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1))


def write_md(data):
    for lang, name in (("de", "CHANGELOG.md"), ("en", "CHANGELOG_EN.md")):
        t = TITLE[lang]
        out = [f"# ZGmax – {t[0]}", ""]
        if data["unreleased"].get(lang):
            out += [f"## {t[2]}", ""] + [f"- {e}" for e in data["unreleased"][lang]] + [""]
        for r in data["releases"]:
            out += [f"## {t[1].format(r['version'], fmt_date(r['date'], lang))}", ""] + [f"- {e}" for e in r[lang]] + [""]
        with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
            f.write("\n".join(out))


def bump(v, part):
    n = [int(x) for x in v.split(".")] + [0, 0]
    major, minor, patch = n[:3]
    if part == "major":
        return f"{major + 1}.0"
    if part == "minor":
        return f"{major}.{minor + 1}"
    return f"{major}.{minor}.{patch + 1}"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part", nargs="?", choices=("major", "minor", "patch"))
    ap.add_argument("--draft", action="store_true", help="Commits seit dem letzten Versions-Tag zeigen")
    ap.add_argument("--md", action="store_true", help="nur die Markdown-Dateien neu schreiben")
    ap.add_argument("--git", action="store_true", help="committen und Tag setzen")
    a = ap.parse_args()
    data = load()
    if a.draft:
        try:
            last = git("describe", "--tags", "--abbrev=0", "--match", "v*").strip()
            rng = f"{last}..HEAD"
        except subprocess.CalledProcessError:
            rng = "HEAD"
        print(git("log", "--no-merges", "--format=- %s", rng))
        return 0
    if a.md:
        write_md(data)
        return 0
    if not a.part:
        ap.print_help()
        return 1
    de, en = data["unreleased"].get("de", []), data["unreleased"].get("en", [])
    if not de or len(de) != len(en):
        print("Fehler: 'unreleased' braucht deutsche und englische Eintraege in gleicher Anzahl.", file=sys.stderr)
        return 1
    old = data["releases"][0]["version"] if data["releases"] else "0.0"
    new = bump(old, a.part)
    data["releases"].insert(0, {"version": new, "date": dt.date.today().isoformat(), "de": de, "en": en})
    data["unreleased"] = {"de": [], "en": []}
    save(data)
    write_md(data)
    print(f"Version {old} -> {new}")
    if a.git:
        git("add", CL, os.path.join(ROOT, "CHANGELOG.md"), os.path.join(ROOT, "CHANGELOG_EN.md"))
        git("commit", "-m", f"Version {new}")
        git("tag", f"v{new}")
        print(f"Commit und Tag v{new} angelegt; pushen mit: git push && git push origin v{new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
