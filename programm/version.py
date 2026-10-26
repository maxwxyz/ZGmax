"""Programmversion und Aenderungshistorie.

Quelle ist CHANGELOG.json: "unreleased" sammelt die Eintraege seit der letzten Version (deutsch und englisch),
"releases" die veroeffentlichten Versionen (neueste zuerst). Eine neue Version erzeugt packaging/release.py.
"""
import html
import json
import os
import sys

_HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
CHANGELOG = os.path.join(_HERE, "CHANGELOG.json")


def changelog():
    try:
        with open(CHANGELOG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"unreleased": {"de": [], "en": []}, "releases": []}


def _version():
    rel = changelog().get("releases") or []
    return rel[0]["version"] if rel else "0.0"


VERSION = _version()


# Bis Oktober 2026 hiessen die Versionen 2.0-2.2; sie wurden auf 0.5-0.7 umbenannt (erste Version 0.8). Aeltere
# Projekte und Einstellungen tragen noch die alten Nummern - so werden sie richtig eingeordnet.
OLD_NUMBERS = {"2.0": "0.5", "2.1": "0.6", "2.2": "0.7"}


def version_key(v):
    """'2.10' > '2.9': Versionen als Zahlentupel vergleichen."""
    v = OLD_NUMBERS.get(str(v), str(v))
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def fmt_date(iso, lang="de"):
    """'2026-10-25' -> '25.10.2026' (de) bzw. unveraendert (en, ISO)."""
    try:
        y, m, d = iso.split("-")
        return f"{int(d)}.{int(m)}.{y}" if lang == "de" else iso
    except (AttributeError, ValueError):
        return iso or ""


def changes_html(lang="de", since=None, unreleased=False):
    """Aenderungshistorie als HTML (fuer "Was ist neu"); since = nur Versionen neuer als diese."""
    data = changelog()
    head = {"de": ("Version {} vom {}", "In Arbeit (noch nicht veröffentlicht)"),
            "en": ("Version {} of {}", "In progress (not released yet)")}[lang if lang == "en" else "de"]
    out = []
    blocks = []
    if unreleased and data.get("unreleased", {}).get(lang):
        blocks.append((head[1], data["unreleased"][lang]))
    for r in data.get("releases", []):
        if since is not None and version_key(r["version"]) <= version_key(since):
            continue
        blocks.append((head[0].format(r["version"], fmt_date(r.get("date", ""), lang)), r.get(lang) or r.get("de") or []))
    for title, items in blocks:
        out.append(f"<h3>{html.escape(title)}</h3><ul>")
        out += [f"<li>{html.escape(t)}</li>" for t in items]
        out.append("</ul>")
    return "\n".join(out)
