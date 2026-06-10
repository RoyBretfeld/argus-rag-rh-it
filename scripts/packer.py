#!/usr/bin/env python3
"""
Universal Packer - Einheitlicher Dump-Generator für alle Projekte
==========================================================

Unterstützt 5 Dump-Typen:
- DUMP_NANO (~50KB) - Sehr kompakt, nur essentielle Files
- DUMP_LIGHT - Architektur + Signaturen (kein voller Code)
- DUMP_FULL - Kompletter Code
- DUMP_DOMAIN_<name> - Domain-spezifisch (z.B. agents, fts, voice, etc.)
- DUMP_PROJECT - Projekt-spezifisch (z.B. NSI-RAGsystem)

Aufruf: python scripts/packer.py [--nano|--light|--full|--domain <name>|--all]
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# =============================================================================
# Konfiguration - Projekt-spezifische Einstellungen
# =============================================================================

# Projekte mit ihren Einstellungen
PROJECTS = {
    "NSI-RAGsystem": {
        "path": Path("E:/Projekte/01_Aktiv/NSI-RAGsystem"),
        "dump_stem": "NSI_RAGsystem",
        "domains": {
            "agent": ["core/agent/"],
            "ingestor": ["core/ingestor/"],
            "llm": ["core/llm/"],
            "rag": ["core/rag/"],
            "search": ["core/search/"],
            "reasoning": ["core/reasoning/"],
            "api": ["api/"],
            "frontend": ["frontend/src/"],
        },
    },
    "Modul-Registry": {
        "path": Path("E:/Projekte/01_Aktiv/___Modul-Registry"),
        "dump_stem": "_AEGIS-Projekt",
        "domains": {
            "agents": ["agents/"],
            "fts": ["aegis_security_testsuite/", "agents/fts_"],
            "voice": ["agents/voice", "src/voice/"],
            "webgui": ["agents/webgui", "src/gui/", "src/api/"],
            "forge": ["agents/forge", "src/training/"],
            "tests": ["tests/"],
            "docs": ["docs/"],
        },
    },
}



# Nano-Dump Zielgröße
NANO_TARGET_BYTES = 50_000

# Excluded Directories
EXCLUDE_DIRS: dict[str, str] = {
    ".git": "VCS-Metadaten",
    ".dart_tool": "Build-Tooling",
    ".idea": "IDE-Metadaten",
    ".metadata": "Editor-Metadaten",
    "build": "Build-Artefakte",
    "dist": "Build-Artefakte",
    ".next": "Framework-Build",
    "__pycache__": "Python-Cache",
    ".venv": "Virtuelle Umgebung",
    "venv": "Virtuelle Umgebung",
    "node_modules": "Abhängigkeiten",
    ".pnpm": "Abhängigkeiten",
    "android": "Plattformspezifisch",
    "ios": "Plattformspezifisch",
    "linux": "Plattformspezifisch",
    "macos": "Plattformspezifisch",
    "windows": "Plattformspezifisch",
    "_rb_dumps": "Dump-Ziel",
    "library": "Bibliotheksspiegel",
    "memory": "Laufzeitdaten",
    "logs": "Laufzeitlogs",
    ".claude": "Tooling-Metadaten",
    "models": "Modelldateien",
    "_gemini": "Tooling-Metadaten",
    ".pytest_cache": "Test-Cache",
}

# Verzeichnisse für die nur Struktur (keine Inhalte)
STRUCTURE_ONLY_DIRS: dict[str, str] = {
    "data": "Nur Struktur, keine Betriebsdaten im Dump",
    "certs": "Nur Struktur, keine sensiblen Zertifikatsinhalte",
}

# Dateitypen, die ausgeschlossen werden
EXCLUDE_SUFFIXES: dict[str, str] = {
    ".log": "Logdatei",
}

# Erweiterungen pro Projekt-Typ
_DART_EXT = {".dart", ".yaml", ".json", ".md"}
_JS_EXT = {".js", ".ts", ".tsx", ".jsx", ".mjs", ".json", ".md", ".yaml", ".yml", ".env.example"}
_PY_EXT = {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".cfg", ".ini", ".env.example"}
_DEFAULT_EXT = {".py", ".js", ".ts", ".dart", ".md", ".yaml", ".yml", ".toml", ".json", ".html", ".css", ".ps1", ".env.example"}


# =============================================================================
# Datenstrukturen
# =============================================================================

@dataclass(slots=True)
class DumpResult:
    label: str
    path: Path
    size_bytes: int
    element_count: int
    missing_paths: list[str]


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def detect_extensions(root: Path) -> set[str]:
    """Erkennt Projekt-Typ und entsprechende Datei-Erweiterungen."""
    if (root / "pubspec.yaml").exists():
        return _DART_EXT
    if (root / "package.json").exists():
        return _JS_EXT
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return _PY_EXT
    return _DEFAULT_EXT


def is_markdown(path: Path) -> bool:
    """Prüft ob Datei Markdown ist."""
    return path.suffix.lower() == ".md"


def is_config(path: Path) -> bool:
    """Prüft ob Datei Konfigurationsdatei ist."""
    return path.suffix.lower() in {".yaml", ".yml", ".json", ".toml"} or path.name == ".env.example"


def should_skip_rel(rel: Path) -> str | None:
    """Prüft ob Datei/Ordner ausgeschlossen werden soll."""
    for part in rel.parts:
        if part in EXCLUDE_DIRS:
            return EXCLUDE_DIRS[part]
        if part in STRUCTURE_ONLY_DIRS:
            return STRUCTURE_ONLY_DIRS[part]
    if rel.suffix.lower() in EXCLUDE_SUFFIXES:
        return EXCLUDE_SUFFIXES[rel.suffix.lower()]
    return None


def collect_files(root: Path, extensions: set[str]) -> tuple[list[Path], dict[str, str]]:
    """Sammelt alle relevanten Dateien im Projekt."""
    files: list[Path] = []
    omitted: dict[str, str] = {}
    for path in root.rglob("*"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        reason = should_skip_rel(rel)
        if reason:
            omitted[str(rel).replace("\\", "/")] = reason
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in extensions or is_markdown(path) or is_config(path):
            files.append(path)
        else:
            omitted[str(rel).replace("\\", "/")] = "Nicht im Dump-Profil"
    return sorted(files), omitted


def generate_tree(root: Path, files: list[Path], max_depth: int = 4) -> str:
    """Generiert Dateibaum als ASCII-Art."""
    file_set = {str(file.relative_to(root)).replace("\\", "/") for file in files}
    lines = [root.name + "/"]

    def walk(current: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except OSError:
            return
        visible: list[Path] = []
        for entry in entries:
            rel = entry.relative_to(root)
            rel_text = str(rel).replace("\\", "/")
            if should_skip_rel(rel):
                continue
            if entry.is_dir():
                if any(candidate.startswith(rel_text + "/") for candidate in file_set):
                    visible.append(entry)
            elif rel_text in file_set:
                visible.append(entry)
        for index, entry in enumerate(visible):
            connector = "└── " if index == len(visible) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if index == len(visible) - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)

    walk(root, "", 1)
    return "\n".join(lines)


def lang_for(path: Path) -> str:
    """Gibt Sprache für Syntax-Highlighting zurück."""
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".dart": "dart",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".json": "json",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".ps1": "powershell",
    }.get(path.suffix.lower(), "")


def read_text(path: Path) -> str:
    """Liest Textdatei mit Fehlerbehandlung."""
    return path.read_text(encoding="utf-8", errors="replace")


def is_docstring_expr(node: ast.AST) -> bool:
    """Prüft ob AST-Node eine Docstring-Expression ist."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(getattr(node, "value", None), ast.Constant)
        and isinstance(node.value.value, str)
    )


# =============================================================================
# Dump-Builder (Projekt-unabhängig)
# =============================================================================

def format_meta_block(dump_type: str, timestamp: str, omitted: dict[str, str]) -> str:
    """Formatiert Meta-Block für Dump-Header."""
    omitted_items = [f"{path} ({reason})" for path, reason in sorted(omitted.items())[:10]]
    omitted_text = ", ".join(omitted_items) if omitted_items else "keine"
    return "\n".join(
        [
            "═══ DUMP META ═══",
            f"Typ:           {dump_type}",
            f"Generiert:     {timestamp}",
            f"Ausgelassen:   {omitted_text}",
            "═════════════════",
        ]
    )


def dump_header(root: Path, dump_type: str, timestamp: str, files: list[Path], omitted: dict[str, str]) -> str:
    """Erstellt Header für Dump."""
    return "\n".join(
        [
            f"# {root.name} — {dump_type}",
            "",
            "## Dateibaum",
            "",
            "```",
            generate_tree(root, files, max_depth=4),
            "```",
            "",
            format_meta_block(dump_type, timestamp, omitted),
            "",
            "---",
            "",
        ]
    )


def build_full(root: Path, files: list[Path], timestamp: str, omitted: dict[str, str]) -> tuple[str, int]:
    """Erstellt DUMP_FULL (kompletter Code)."""
    parts = [dump_header(root, "DUMP_FULL", timestamp, files, omitted)]
    for path in files:
        rel = path.relative_to(root).as_posix()
        parts.extend([f"### `{rel}`", "", f"```{lang_for(path)}", read_text(path).rstrip(), "```", ""])
    return "\n".join(parts).strip() + "\n", len(files)


def python_nano_excerpt(content: str) -> str:
    """Kürzt Python-Code auf Klassen- und Funktionsdefinitionen."""
    lines = content.splitlines()
    excerpt: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("class ", "def ", "async def ")):
            excerpt.append(line)
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()
                if next_line.startswith('"""') or next_line.startswith("'''"):
                    excerpt.append(lines[index + 1])
    return "\n".join(excerpt).strip()


def generic_light_excerpt(content: str) -> str:
    """Allgemeiner Light-Excerpt (erste 800 Zeichen)."""
    return content[:800] + ("\n... (truncated)" if len(content) > 800 else "")


def python_light_excerpt(content: str) -> str:
    """Kürzt Python-Code auf Signatur und Docstrings."""
    try:
        module = ast.parse(content)
    except SyntaxError:
        return content

    lines = content.splitlines()
    out: list[str] = []

    def append_segment(start: int, end: int) -> None:
        if start < 1 or end < start:
            return
        out.extend(lines[start - 1:end])

    def render_node(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            start = min([node.lineno, *[decorator.lineno for decorator in node.decorator_list]] or [node.lineno])
            body_start = node.body[0].lineno if node.body else node.end_lineno or node.lineno
            append_segment(start, max(start, body_start - 1))
            if node.body and is_docstring_expr(node.body[0]):
                append_segment(node.body[0].lineno, node.body[0].end_lineno or node.body[0].lineno)
            for child in node.body:
                if is_docstring_expr(child):
                    continue
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    render_node(child)
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno, *[decorator.lineno for decorator in node.decorator_list]] or [node.lineno])
            end = node.end_lineno or node.lineno
            if end - start + 1 < 20:
                append_segment(start, end)
                return
            body_start = node.body[0].lineno if node.body else end
            append_segment(start, max(start, body_start - 1))
            cursor = body_start
            if node.body and is_docstring_expr(node.body[0]):
                append_segment(node.body[0].lineno, node.body[0].end_lineno or node.body[0].lineno)
                cursor = (node.body[0].end_lineno or node.body[0].lineno) + 1
            for line_no in range(cursor, end + 1):
                if lines[line_no - 1].strip().startswith("#"):
                    append_segment(line_no, line_no)

    first_code_line = min(
        (getattr(node, "lineno", len(lines) + 1) for node in module.body),
        default=len(lines) + 1,
    )
    for line_no in range(1, first_code_line):
        stripped = lines[line_no - 1].strip()
        if not stripped or stripped.startswith(("#", "import ", "from ")):
            append_segment(line_no, line_no)

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            render_node(node)
    return "\n".join(out).strip()


def build_light(root: Path, files: list[Path], timestamp: str, omitted: dict[str, str]) -> tuple[str, int]:
    """Erstellt DUMP_LIGHT (Architektur + Signaturen)."""
    parts = [dump_header(root, "DUMP_LIGHT", timestamp, files, omitted)]
    count = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        content = read_text(path)
        if is_config(path) or is_markdown(path):
            excerpt = content
        elif path.suffix.lower() == ".py":
            excerpt = python_light_excerpt(content)
        else:
            excerpt = generic_light_excerpt(content)
        parts.extend([f"### `{rel}`", "", f"```{lang_for(path)}", excerpt.rstrip(), "```", ""])
        count += 1
    return "\n".join(parts).strip() + "\n", count


def is_nano_mandatory(path: Path, root: Path) -> bool:
    """Prüft ob Datei im Nano-Dump enthalten sein muss."""
    rel = path.relative_to(root)
    rel_text = rel.as_posix()
    if rel_text == ".agent.md":
        return True
    if rel_text == "pyproject.toml":
        return True
    if rel_text == "_PROJECT_CORE/project_summary.md":
        return True
    if len(rel.parts) == 1 and is_markdown(path):
        return True
    if len(rel.parts) >= 2 and rel.parts[0] == "docs" and rel.parts[1] == "_rb" and is_markdown(path):
        return True
    return False


def build_nano(root: Path, files: list[Path], timestamp: str, omitted: dict[str, str]) -> tuple[str, int]:
    """Erstellt DUMP_NANO (max 50KB, essentiellste Files)."""
    parts = [dump_header(root, "DUMP_NANO", timestamp, files, omitted)]
    count = 0
    optional_blocks: list[tuple[str, str]] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        content = read_text(path)
        if is_nano_mandatory(path, root):
            parts.extend([f"### `{rel}`", "", f"```{lang_for(path)}", content.rstrip(), "```", ""])
            count += 1
            continue
        if path.suffix.lower() == ".py":
            excerpt = python_nano_excerpt(content)
            if excerpt:
                optional_blocks.append((rel, excerpt))
    assembled = "\n".join(parts).strip() + "\n"
    budget_left = max(0, NANO_TARGET_BYTES - len(assembled.encode("utf-8")))
    for rel, excerpt in optional_blocks:
        block = "\n".join([f"### `{rel}`", "", "```python", excerpt.rstrip(), "```", ""])
        block_bytes = len((block + "\n").encode("utf-8"))
        if block_bytes > budget_left:
            omitted[f"{rel} [nano]"] = "Aus Budgetgründen im NANO ausgelassen"
            continue
        assembled += block + "\n"
        budget_left -= block_bytes
        count += 1
    return assembled, count


def build_domain(root: Path, files: list[Path], timestamp: str, omitted: dict[str, str], domain: str, domain_markers: list[str]) -> tuple[str, int, list[str]]:
    """Erstellt DUMP_DOMAIN_<name> (domain-spezifisch)."""
    missing_paths = [marker for marker in domain_markers if not (root / marker).exists()]
    nano_content, _ = build_nano(root, files, timestamp, dict(omitted))
    selected = [
        path
        for path in files
        if any(path.relative_to(root).as_posix().startswith(marker.rstrip("/")) for marker in domain_markers)
    ]
    domain_omitted = dict(omitted)
    for marker in missing_paths:
        domain_omitted[f"[domain-missing] {marker}"] = "Pfad nicht gefunden"
    parts = [
        f"# {root.name} — DUMP_DOMAIN_{domain}",
        "",
        "## NANO Header",
        "",
        nano_content.rstrip(),
        "",
        "---",
        "",
        "## Domain Volltext",
        "",
        format_meta_block(f"DUMP_DOMAIN_{domain}", timestamp, domain_omitted),
        "",
    ]
    for path in selected:
        rel = path.relative_to(root).as_posix()
        parts.extend([f"### `{rel}`", "", f"```{lang_for(path)}", read_text(path).rstrip(), "```", ""])
    return "\n".join(parts).strip() + "\n", len(selected), missing_paths


def build_all_domains(root: Path, files: list[Path], timestamp: str, omitted: dict[str, str], project_domains: dict[str, list[str]]) -> tuple[str, int, list[str]]:
    """Erstellt einen einzigen DUMP_DOMAIN mit ALLEN Domains zusammengefasst."""
    parts = [
        f"# {root.name} — DUMP_DOMAIN (Alle Domains)",
        "",
        "---",
        "",
    ]
    total_count = 0
    missing_paths = []

    for domain_name, domain_markers in project_domains.items():
        missing = [marker for marker in domain_markers if not (root / marker).exists()]
        if missing:
            missing_paths.extend(missing)

        # selected files für diese Domain
        selected = [
            path
            for path in files
            if any(path.relative_to(root).as_posix().startswith(marker.rstrip("/")) for marker in domain_markers)
        ]

        parts.extend([
            f"## Domain: {domain_name}",
            "",
        ])
        for path in selected:
            rel = path.relative_to(root).as_posix()
            parts.extend([f"### `{rel}`", "", f"```{lang_for(path)}", read_text(path).rstrip(), "```", ""])
            total_count += 1

    return "\n".join(parts).strip() + "\n", total_count, missing_paths


# =============================================================================
# Dump-Verwaltung
# =============================================================================

def local_dump_dir(root: Path) -> Path:
    """Gibt lokales Dump-Verzeichnis zurück."""
    target = root / "_rb_dumps"
    target.mkdir(parents=True, exist_ok=True)
    return target


def dump_filename(dump_type: str, domain: str | None = None, dump_stem: str = "_AEGIS-Projekt") -> str:
    """Erstellt Dump-Dateinamen mit Projekt-Stem."""
    if dump_type == "FULL":
        return f"{dump_stem}_DUMP.md"
    if dump_type == "LIGHT":
        return f"{dump_stem}_DUMP_LIGHT.md"
    if dump_type == "NANO":
        return f"{dump_stem}_DUMP_NANO.md"
    return f"{dump_stem}_DUMP_DOMAIN_{domain}.md"


def write_dump(root: Path, dump_type: str, content: str, domain: str | None = None, dump_stem: str = "_AEGIS-Projekt") -> Path:
    """Schreibt Dump nur in lokales Projekt-Verzeichnis."""
    local_dir = local_dump_dir(root)
    filename = dump_filename(dump_type, domain, dump_stem)
    local_path = local_dir / filename
    local_path.write_text(content, encoding="utf-8")
    return local_path


# =============================================================================
# Argument Parsing
# =============================================================================

def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse Kommandozeilen-Argumente."""
    parser = argparse.ArgumentParser(
        description="Universal Packer - Einheitlicher Dump-Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python scripts/packer.py --all              # Alle Dumps für aktuelles Projekt
  python scripts/packer.py --nano             # Nur NANO-Dump
  python scripts/packer.py --light            # Nur LIGHT-Dump
  python scripts/packer.py --full             # Nur FULL-Dump
  python scripts/packer.py --domain agents    # Nur agents-Domain
  python scripts/packer.py --project nsi      # Für NSI-RAGsystem
  python scripts/packer.py --project modul    # Für Modul-Registry

Projekte:
  nsi    = NSI-RAGsystem (E:/Projekte/01_Aktiv/NSI-RAGsystem)
  modul  = Modul-Registry (E:/Projekte/01_Aktiv/___Modul-Registry)
        """
    )
    parser.add_argument("project_dir", nargs="?", default=".", help="Projektverzeichnis (default: aktuelles)")
    parser.add_argument("--project", "-p", choices=["nsi", "modul"], help="Vordefiniertes Projekt")
    parser.add_argument("--nano", action="store_true", help="Nur DUMP_NANO")
    parser.add_argument("--light", action="store_true", help="Nur DUMP_LIGHT")
    parser.add_argument("--full", action="store_true", help="Nur DUMP_FULL")
    parser.add_argument("--domain", choices=["agents", "fts", "voice", "webgui", "forge", "tests", "docs", "agent", "ingestor", "llm", "rag", "search", "reasoning", "api", "frontend"], help="Nur DUMP_DOMAIN für diese Domain")
    parser.add_argument("--all", action="store_true", help="FULL + LIGHT + NANO + alle Domains")
    return parser.parse_args(argv)


def get_project_root(project_name: str | None, project_dir: str) -> Path:
    """Holt Projekt-Root basierend auf --project oder aktuellem Verzeichnis."""
    if project_name:
        if project_name == "nsi":
            return PROJECTS["NSI-RAGsystem"]["path"]
        if project_name == "modul":
            return PROJECTS["Modul-Registry"]["path"]
    return Path(project_dir).resolve()


def get_project_config(project_root: Path) -> dict:
    """Holt Projekt-Konfiguration basierend auf Root-Pfad."""
    for name, config in PROJECTS.items():
        if config["path"].resolve() == project_root.resolve():
            return config
    # Fallback: erzeugt Konfiguration für unbekannte Projekte
    return {
        "path": project_root,
        "dump_stem": project_root.name,
        "domains": {},
    }


# =============================================================================
# Main
# =============================================================================

def main(argv: list[str] | None = None) -> int:
    """Hauptfunktion."""
    args = parse_args(argv or sys.argv[1:])
    root = get_project_root(args.project, args.project_dir)

    if not root.exists() or not root.is_dir():
        print(f"Fehler: '{root}' ist kein gültiges Verzeichnis.")
        return 1

    # Projekt-Konfiguration holen
    config = get_project_config(root)
    dump_stem = config.get("dump_stem", root.name)

    # Extensions ermitteln
    extensions = detect_extensions(root)
    files, omitted = collect_files(root, extensions)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    results: list[DumpResult] = []

    # Get domains for this project
    project_domains = config.get("domains", {})

    # Dump-Typ basierend auf Argumenten wählen
    if args.nano:
        content, count = build_nano(root, files, timestamp, dict(omitted))
        path = write_dump(root, "NANO", content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_NANO", path, path.stat().st_size, count, []))
    elif args.light:
        content, count = build_light(root, files, timestamp, dict(omitted))
        path = write_dump(root, "LIGHT", content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_LIGHT", path, path.stat().st_size, count, []))
    elif args.full:
        content, count = build_full(root, files, timestamp, dict(omitted))
        path = write_dump(root, "FULL", content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_FULL", path, path.stat().st_size, count, []))
    elif args.domain:
        # Domain-Marker holen
        domain_markers = project_domains.get(args.domain, [f"{args.domain}/"])
        content, count, missing = build_domain(root, files, timestamp, dict(omitted), args.domain, domain_markers)
        path = write_dump(root, "DOMAIN", content, args.domain, dump_stem=dump_stem)
        results.append(DumpResult(f"DUMP_DOMAIN:{args.domain}", path, path.stat().st_size, count, missing))
    elif args.all:
        # Alle Dumps erstellen
        full_content, full_count = build_full(root, files, timestamp, dict(omitted))
        path = write_dump(root, "FULL", full_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_FULL", path, path.stat().st_size, full_count, []))

        light_content, light_count = build_light(root, files, timestamp, dict(omitted))
        path = write_dump(root, "LIGHT", light_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_LIGHT", path, path.stat().st_size, light_count, []))

        nano_content, nano_count = build_nano(root, files, timestamp, dict(omitted))
        path = write_dump(root, "NANO", nano_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_NANO", path, path.stat().st_size, nano_count, []))

        # Alle Domains in einem DUMP_DOMAIN File zusammenfassen
        domain_content, domain_count, missing = build_all_domains(root, files, timestamp, dict(omitted), project_domains)
        path = write_dump(root, "DOMAIN", domain_content, "all", dump_stem=dump_stem)
        results.append(DumpResult(f"DUMP_DOMAIN:all", path, path.stat().st_size, domain_count, missing))
    else:
        # Standard: FULL + LIGHT + NANO + Domains
        full_content, full_count = build_full(root, files, timestamp, dict(omitted))
        path = write_dump(root, "FULL", full_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_FULL", path, path.stat().st_size, full_count, []))

        light_content, light_count = build_light(root, files, timestamp, dict(omitted))
        path = write_dump(root, "LIGHT", light_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_LIGHT", path, path.stat().st_size, light_count, []))

        nano_content, nano_count = build_nano(root, files, timestamp, dict(omitted))
        path = write_dump(root, "NANO", nano_content, dump_stem=dump_stem)
        results.append(DumpResult("DUMP_NANO", path, path.stat().st_size, nano_count, []))

        # Alle Domains in einem DUMP_DOMAIN File zusammenfassen
        domain_content, domain_count, missing = build_all_domains(root, files, timestamp, dict(omitted), project_domains)
        path = write_dump(root, "DOMAIN", domain_content, "all", dump_stem=dump_stem)
        results.append(DumpResult(f"DUMP_DOMAIN:all", path, path.stat().st_size, domain_count, missing))

    # Ergebnisse ausgeben
    full_size = next((item.size_bytes for item in results if item.label == "DUMP_FULL"), 0)

    print(f"\n=== DUMP ERSTELLT FÜR: {root.name} ===\n")

    for item in results:
        kb = item.size_bytes / 1024
        ratio = f"  [{round((item.size_bytes / full_size) * 100)}% von FULL]" if full_size and item.label != "DUMP_FULL" else ""
        print(f"[{item.label}] {kb:10.1f} KB  {item.element_count:4d} Elemente{ratio}")
        if item.label == "DUMP_NANO" and item.size_bytes > NANO_TARGET_BYTES:
            print("  Warnung: DUMP_NANO liegt über 50 KB; der Pflichtinhalt war in diesem Projekt größer als das Ziel.")
        if item.missing_paths:
            print(f"  Nicht gefundene Domain-Pfade: {', '.join(item.missing_paths)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
