# Argus RAG

Lokales, hochsicheres und allsehendes RAG-System.

**Repository:** https://github.com/RoyBretfeld/argus-rag-rh-it.git

![Status](https://img.shields.io/badge/status-production-green) ![Python](https://img.shields.io/badge/python-3.12+-blue) ![FastAPI](https://img.shields.io/badge/fastapi-0.110+-teal) ![React](https://img.shields.io/badge/react-18.0+-blue)

## Überblick

**Argus RAG** ist eine moderne, hoch-performante Web-Anwendung (React Frontend & FastAPI Backend) für intelligenten Dokumenten-Upload, multimodale Ingestion und RAG-basierte Chat-Abfragen mit lokal-first Fokus.

**Features:**
- 📄 PDF-Upload mit Bild-, OCR- und Formel-Extraktion
- 📊 Office-Dokumente (DOCX, PPTX, XLSX) und Textdateien
- 🖼️ Bilder (JPG, PNG, GIF, TIFF) mit lokaler Vision-Beschreibung via `moondream`
- 📈 Technische Daten (CSV, XML, JSON, EML)
- 🛡️ DSGVO-konform (lokale Verarbeitung mit Nomic-Embeddings, Zero-Cloud)
- 🌐 Cloud-Support mit robustem lokalen Fallback
- 🖥️ Hardware- & VRAM-Status direkt in der Sidebar
- 🧭 Quellen-Vertrauenssystem mit Confidence, Widerspruchserkennung und Review-Flag
- 🧠 Argus-Systemprofil mit stabiler Identität, Rolle und Autonomiegrenzen

## Setup

### 1. Ollama installieren und Modelle pullen

```bash
# Ollama herunterladen und installieren
# https://ollama.com/download

# Modelle pullen
ollama pull mistral
ollama pull moondream
ollama pull nomic-embed-text
ollama pull mistral-embed
```

### 2. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 3. Frontend-Abhängigkeiten installieren

```bash
cd frontend
npm install
cd ..
```

### 4. Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
# .env nach Bedarf anpassen
```

### 5. Anwendung starten

#### A. Unter Windows (Launcher)
Doppelklick auf die Datei `start_nsi_rag.bat` startet das FastAPI-Backend (Port 8000) und das React-Frontend (Port 5173) parallel in separaten Konsolenfenstern.

#### B. Manuell starten
*   **Backend (FastAPI):**
    ```bash
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ```
*   **Frontend (React/Vite):**
    ```bash
    cd frontend
    npm run dev -- --host 0.0.0.0 --port 5173
    ```

## Anwendung

1. **Dokumente hochladen** im Sidebar-Menü (Unterstützt Mehrfachauswahl und Ordner-Upload)
   - Bis zu 10.000 Dateien in einer NAS-Queue
   - Deterministische natürliche Sortierung nach relativem Ordnerpfad
   - Sequenzielle Verarbeitung in nachvollziehbaren 100er-Batches
   - Unterordnerpfad und Ingestionsposition bleiben als ChromaDB-Metadaten erhalten
   - Maximal 200MB pro Datei
2. **Vertraulichkeit wählen**
   - ✅ Vertrauliches Dokument → Lokale Datenbank (768-dim, Offline)
   - ❌ Öffentliches Dokument → Cloud-Datenbank (1536-dim)
3. **Chat starten**
   - Fragen im Chat-Interface stellen (Wissensbasis / Internet / Beides)
   - System- & VRAM-Auslastung live in der Sidebar ablesen

## Projekt-Struktur

```
api/
├── main.py              # FastAPI Web-Einstieg
├── upload_handler.py    # Ingestions-Handler
└── routes/
    ├── chat.py          # Chat-Endpunkt
    ├── upload.py        # Upload-Endpunkt (Mehrfachauswahl)
    └── system.py        # Hardware- & ChromaDB-Status-Endpunkte

frontend/
├── src/
│   ├── App.tsx          # React-Wurzelkomponente
│   ├── components/
│   │   ├── UploadPanel.tsx # Sidebar, Hardware-Widgets & Upload UI (mit Argus-Auge SVG)
│   │   └── ChatPanel.tsx   # Chat UI
│   └── index.css        # NABU-grünes Sleek-Design CSS

core/
├── ingestor/
│   ├── document_type_router.py    # Dateityp erkennen
│   ├── pdf_multimodal_ingestor.py # PDF (Text + EasyOCR + Vision)
│   ├── office_ingestor.py        # DOCX, PPTX, XLSX
│   ├── image_ingestor.py         # Bilder
│   └── data_ingestor.py          # CSV, XML, JSON, EML
├── vectordb/
│   └── chroma_store.py   # ChromaDB Wrapper & Reset-Logik
├── llm/
│   ├── ollama_client.py  # Ollama Client
│   └── model_router.py   # 3-Tier Routing
└── rag/
    └── rag_pipeline.py   # LlamaIndex Pipeline

data/
├── chroma_local/  # Lokale Datenbank (DSGVO)
└── chroma_cloud/  # Cloud Datenbank

tests/
└── test_*.py      # Unit-Tests
```

## Tests ausführen

```bash
pytest tests/ -v
```

## Lizenz

Argus RAG 2026
