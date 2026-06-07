# NSI-RAGsystem Packer
# DualDumpPackager für DUMP_FULL + DUMP_LIGHT
# (ohne externe Abhängigkeiten)

import os
from pathlib import Path
from datetime import datetime


class DualDumpPackager:
    """Erstellt DUMP_FULL und DUMP_LIGHT nach _rb_dumps/."""

    def __init__(self, project_path: str = None):
        self.project_path = Path(project_path or os.getcwd())
        self.output_path = self.project_path / "_rb_dumps"
        self.output_path.mkdir(exist_ok=True)

        # Project-Info
        self.project_name = "NSI_RAGsystem"
        self.version = "0.1.0"
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Files für Dumps
        self.source_files = self._collect_source_files()

    def _collect_source_files(self) -> list[dict]:
        """Sammelt alle relevanten Source-Files."""
        files = []
        core_path = self.project_path / "core"
        app_path = self.project_path / "app"

        if core_path.exists():
            for f in (core_path / "agent").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "agent"})
            for f in (core_path / "ingestor").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "ingestor"})
            for f in (core_path / "vectordb").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "vectordb"})
            for f in (core_path / "llm").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "llm"})
            for f in (core_path / "rag").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "rag"})
            for f in (core_path / "reasoning").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "reasoning"})

        if app_path.exists():
            for f in app_path.glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "app"})
            for f in (app_path / "components").glob("*.py"):
                files.append({"path": str(f.relative_to(self.project_path)), "type": "components"})

        specs_path = Path("E:/Projekte/01_Aktiv/___Modul-Registry/specs")
        if specs_path.exists():
            for f in specs_path.glob("*.md"):
                files.append({"path": str(f.relative_to(Path("E:/Projekte/01_Aktiv/___Modul-Registry"))), "type": "spec"})

        return sorted(files, key=lambda x: x["path"])

    def _create_dump_header(self, dump_type: str) -> str:
        """Erstellt den Header für einen Dump."""
        line = "=" * (24 + len(dump_type))
        return f"""# NSI-RAGsystem - {dump_type} Dump
# Project: NSI-RAGsystem
# Version: {self.version}
# Created: {self.created_at}
# Type: {dump_type}
{line}

"""

    def _create_dump_light(self) -> str:
        """Erstellt DUMP_LIGHT (kompakt)."""
        dump = self._create_dump_header("LIGHT")

        dump += "## Project Structure\n\n"
        dump += "```\n"
        dump += "NSI-RAGsystem/\n"
        dump += "├── app/\n"
        dump += "│   ├── main.py\n"
        dump += "│   ├── upload_handler.py\n"
        dump += "│   └── components/\n"
        dump += "├── core/\n"
        dump += "│   ├── ingestor/\n"
        dump += "│   ├── vectordb/\n"
        dump += "│   ├── agent/\n"
        dump += "│   ├── llm/\n"
        dump += "│   ├── rag/\n"
        dump += "│   └── reasoning/\n"
        dump += "└── tests/\n"
        dump += "```\n\n"

        dump += "## Key Files\n\n"
        for f in self.source_files:
            if f["type"] in ["app", "agent", "ingestor", "rag", "reasoning"]:
                dump += f"- `{f['path']}`\n"

        dump += "\n## Stack\n\n"
        dump += "- Python 3.12+\n"
        dump += "- Streamlit (WebApp)\n"
        dump += "- LlamaIndex (RAG-Orchestrierung)\n"
        dump += "- ChromaDB embedded\n"
        dump += "- Ollama (Local + Cloud)\n"

        dump += "\n## Features\n\n"
        dump += "- PDF Multimodal Ingestion (Text + Bilder)\n"
        dump += "- Office-Dokumente (DOCX, PPTX, XLSX)\n"
        dump += "- Bilder (JPG, PNG, GIF, TIFF)\n"
        dump += "- Technische Daten (CSV, XML, JSON, EML)\n"
        dump += "- 3-Tier LLM Routing (lokal/cloud)\n"
        dump += "- DSGVO-konform (lokal)\n"

        return dump

    def _create_dump_full(self) -> str:
        """Erstellt DUMP_FULL (komplett)."""
        dump = self._create_dump_header("FULL")

        dump += "## Project Structure\n\n"
        dump += "```\n"
        dump += self._tree_str(self.project_path, indent=0)
        dump += "```\n\n"

        dump += "## Files Content\n\n"

        # Jede Source-File inkludieren
        for f in self.source_files:
            file_path = self.project_path / f["path"].replace("specs/", "../___Modul-Registry/specs/")
            try:
                content = file_path.read_text(encoding="utf-8")
                dump += f"### {f['path']}\n\n"
                dump += f"#### Type: {f['type']}\n\n"
                dump += "```python\n" if f['path'].endswith('.py') else ""
                dump += content[:10000]  # max 10k Zeichen pro File
                dump += "\n```\n\n"
            except Exception as e:
                dump += f"### {f['path']}\n\n"
                dump += f"_File not found or error: {e}_\n\n"

        dump += "## Config Files\n\n"

        # requirements.txt
        req_file = self.project_path / "requirements.txt"
        if req_file.exists():
            dump += "### requirements.txt\n\n"
            dump += "```\n"
            dump += req_file.read_text(encoding="utf-8")
            dump += "\n```\n\n"

        # .env.example
        env_file = self.project_path / ".env.example"
        if env_file.exists():
            dump += "### .env.example\n\n"
            dump += "```\n"
            dump += env_file.read_text(encoding="utf-8")
            dump += "\n```\n\n"

        dump += "## Registry Specs\n\n"
        specs_path = Path("E:/Projekte/01_Aktiv/___Modul-Registry/specs")
        if specs_path.exists():
            for spec in specs_path.glob("*.md"):
                dump += f"### {spec.name}\n\n"
                dump += spec.read_text(encoding="utf-8")[:2000]
                dump += "\n\n"

        dump += "## Tests\n\n"
        test_path = self.project_path / "tests"
        if test_path.exists():
            for test_file in test_path.glob("test_*.py"):
                dump += f"### {test_file.name}\n\n"
                dump += "```python\n"
                dump += test_file.read_text(encoding="utf-8")[:5000]
                dump += "\n```\n\n"

        return dump

    def _tree_str(self, path: Path, indent: int = 0) -> str:
        """Erstellt Baum-String für Project-Struktur."""
        result = ""
        prefix = "  " * indent

        try:
            items = sorted(path.iterdir())
            for i, item in enumerate(items):
                if item.is_dir():
                    if i == len(items) - 1:
                        result += f"{prefix}├── {item.name}/\n"
                        result += self._tree_str(item, indent + 1)
                    else:
                        result += f"{prefix}├── {item.name}/\n"
                        result += self._tree_str(item, indent + 1)
                else:
                    result += f"{prefix}├── {item.name}\n"
        except PermissionError:
            pass

        return result

    def run(self):
        """Führt den Packer aus."""
        print(f"packer.start - Project: {self.project_name}")

        # DUMP_LIGHT
        light_content = self._create_dump_light()
        light_path = self.output_path / f"{self.project_name}_DUMP_LIGHT.md"
        light_path.write_text(light_content, encoding="utf-8")
        print(f"packer.dump_created - {light_path} (LIGHT)")

        # DUMP_FULL
        full_content = self._create_dump_full()
        full_path = self.output_path / f"{self.project_name}_DUMP_FULL.md"
        full_path.write_text(full_content, encoding="utf-8")
        print(f"packer.dump_created - {full_path} (FULL)")

        return {
            "dump_light": str(light_path),
            "dump_full": str(full_path),
            "files_processed": len(self.source_files),
        }


if __name__ == "__main__":
    project_path = Path(__file__).parent.parent
    packer = DualDumpPackager(project_path=str(project_path))
    result = packer.run()
    print(f"Dumps erstellt:")
    print(f"  - {result['dump_light']}")
    print(f"  - {result['dump_full']}")
    print(f"Files processed: {result['files_processed']}")
