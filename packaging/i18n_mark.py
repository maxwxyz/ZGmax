#!/usr/bin/env python3
"""Hilfswerkzeug fuer Entwickler: markiert Anzeigetexte in Python-Dateien mit tr(...) und listet sie auf.

  python packaging/i18n_mark.py --apply programm/ui_layout.py ...   Texte markieren (Datei wird geaendert)
  python packaging/i18n_mark.py --list  programm/*.py              alle tr("...")-Texte ausgeben (fuer i18n_en.json)

Technische Zeichenketten bleiben unberuehrt: Docstrings, Schluessel (klein geschriebene Bezeichner), Farben,
Tastenkuerzel, Stylesheets, regulaere Ausdruecke, Pfade sowie Texte in Vergleichen, Indizes und Dict-Schluesseln.
"""
import ast
import json
import re
import sys

SKIP_FUNCS = {"value", "setValue", "get", "setProperty", "property", "setObjectName", "startswith", "endswith",
              "split", "join", "replace", "findChild", "findChildren", "findData", "getattr", "hasattr", "setattr",
              "open", "QKeySequence", "QColor", "QFont", "getLogger", "environ", "setdefault", "remove", "tr",
              "QStandardPaths", "glob", "isfile", "isdir", "exists", "basename", "splitext", "rstrip", "lstrip",
              "strip", "encode", "decode", "match", "search", "fullmatch", "sub", "compile", "finditer", "findall",
              "imwrite", "imencode", "cvtColor", "save", "insert_text", "set_metadata", "new_page", "add_freetext_annot",
              "QIcon", "icon", "setStyleSheet", "Path", "dump", "load", "loads", "dumps", "pop", "index", "count",
              "isinstance", "setdefault", "setOrganizationName", "setApplicationName", "QSettings", "setCurrentText",
              "debug", "error", "exception", "SetCurrentProcessExplicitAppUserModelID", "startDetached", "run",
              "Popen", "check_output", "format", "rfind", "find", "lower", "upper", "ljust", "rjust", "zfill"}


def is_ui_text(s):
    if len(s.strip()) < 2 or not re.search(r"[A-Za-zÄÖÜäöüß]", s):
        return False
    if re.fullmatch(r"[a-z_][a-z0-9_.\-]*", s):                     # Schluessel/Bezeichner
        return False
    if re.fullmatch(r"(Ctrl|Shift|Alt|Meta)\+.*|F\d+|Delete|Escape|Space|Return", s):
        return False
    if s.startswith(("#", "*", "&#", "<?xml", "%", "/", "\\")) or s.endswith((".py", ".html", ".png", ".json")):
        return False
    if "\\" in s or "(?" in s or "{{" in s and ";" in s:            # Regex, Stylesheet
        return False
    if any(k in s for k in ("font-size", "background:", "border:", "padding:", "QToolButton", "QPushButton",
                            "QFrame#", "QLabel#")):
        return False
    if re.fullmatch(r"[A-Z0-9_]{1,4}", s):                           # A, B, OK-Kuerzel
        return False
    return True


def collect(tree):
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant):
                skip.add(id(b.value))
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            skip.add(id(n.value))
        if isinstance(n, ast.Subscript):
            for c in ast.walk(n.slice):
                skip.add(id(c))
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if k is not None:
                    skip.add(id(k))
        if isinstance(n, ast.Compare):
            for c in [n.left] + n.comparators:
                for cc in ast.walk(c):
                    skip.add(id(cc))
        if isinstance(n, ast.Call):
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name in SKIP_FUNCS:
                for a in n.args:
                    for c in ast.walk(a):
                        skip.add(id(c))
            for kw in n.keywords:
                if kw.arg in ("objectName", "fontname", "filetype", "colorspace", "encoding", "interpolation",
                              "anchor", "joint", "mode", "flags", "kind", "type", "typ", "ext", "style"):
                    for c in ast.walk(kw.value):
                        skip.add(id(c))
        if isinstance(n, ast.JoinedStr):
            for v in n.values:
                skip.add(id(v))
                if isinstance(v, ast.FormattedValue) and v.format_spec is not None:
                    for c in ast.walk(v.format_spec):
                        skip.add(id(c))
    out = []
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and is_ui_text(n.value):
            out.append(n)
        elif isinstance(n, ast.JoinedStr):
            const = "".join(v.value for v in n.values if isinstance(v, ast.Constant))
            if is_ui_text(const) and not any(isinstance(v, ast.FormattedValue) and v.format_spec is not None and
                                             any(isinstance(x, ast.FormattedValue) for x in v.format_spec.values)
                                             for v in n.values):
                out.append(n)
    return out


def template(n, src):
    parts, args = [], []
    for v in n.values:
        if isinstance(v, ast.Constant):
            parts.append(v.value.replace("{", "{{").replace("}", "}}"))
        else:
            conv = "" if v.conversion == -1 else "!" + chr(v.conversion)
            spec = ":" + "".join(c.value for c in v.format_spec.values) if v.format_spec is not None else ""
            parts.append("{" + conv + spec + "}")
            args.append(ast.get_source_segment(src, v.value))
    return "".join(parts), args


def apply(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    nodes = collect(tree)
    lines = src.encode("utf-8").split(b"\n")
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln) + 1)
    data = src.encode("utf-8")
    reps = []
    spans = [(offs[n.lineno - 1] + n.col_offset, offs[n.end_lineno - 1] + n.end_col_offset) for n in nodes]
    nodes = [n for n, (a0, b0) in zip(nodes, spans)                 # nichts ersetzen, was in einem anderen Text liegt
             if not any(a1 <= a0 and b0 <= b1 and (a1, b1) != (a0, b0) for a1, b1 in spans)]
    for n in nodes:
        a = offs[n.lineno - 1] + n.col_offset
        b = offs[n.end_lineno - 1] + n.end_col_offset
        seg = data[a:b].decode("utf-8")
        if isinstance(n, ast.Constant):
            new = "tr(" + seg + ")"
        else:
            tpl, args = template(n, src)
            new = "tr(" + json.dumps(tpl, ensure_ascii=False) + ").format(" + ", ".join(args) + ")"
        reps.append((a, b, new.encode("utf-8")))
    for a, b, new in sorted(reps, reverse=True):
        data = data[:a] + new + data[b:]
    out = data.decode("utf-8")
    if reps and "from i18n import tr" not in out:                 # Import nach dem Modul-Docstring
        t = ast.parse(out)
        first = t.body[1] if (isinstance(t.body[0], ast.Expr) and isinstance(t.body[0].value, ast.Constant)) else t.body[0]
        L = out.split("\n")
        L.insert(first.lineno - 1, "from i18n import tr")
        out = "\n".join(L)
    ast.parse(out)                                                # muss gueltiges Python bleiben
    open(path, "w", encoding="utf-8").write(out)
    return len(reps)


def listing(paths):
    keys = {}
    for p in paths:
        tree = ast.parse(open(p, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args and \
                    isinstance(n.args[0], ast.Constant):
                keys.setdefault(n.args[0].value, p)
    return keys


if __name__ == "__main__":
    mode, files = sys.argv[1], sys.argv[2:]
    if mode == "--apply":
        for f in files:
            print(f, apply(f))
    else:
        print(json.dumps(sorted(listing(files)), ensure_ascii=False, indent=0))
