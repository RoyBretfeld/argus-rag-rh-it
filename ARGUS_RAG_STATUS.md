# Argus RAG — Status

**Version:** 0.4.0
**Erstellt:** 2026-06-01
**Letztes Update:** 2026-06-07
**TESTS_GREEN:** TRUE


## Aktueller Stand

- [x] M1: Projektstruktur + Registry-Specs
- [x] M2: Ingestion-Pipeline (4 Ingestoren)
- [x] M3: SearXNG Client + WebContentFetcher + WebSearchPipeline
- [x] M4: ChromaDB + ModelRouter
- [x] M5: RAG-Pipeline
- [x] M6: ChatHandler (Modus-Router: Wissensbasis / Internet / Beides)
- [x] M7: Argus-Branding + Upload Panel + Chat Panel
- [x] M8: main.py Integration
- [x] M9: Tests grün (6 Test-Dateien)
- [x] M10: Entwickler-Footer integriert
- [/] M11: Advanced RAG (Hybrid Search, Metadaten-Filter, Re-Ranking)
- [x] M12: Quellen-Vertrauenssystem (Confidence, Widersprüche, Review-Flag)
- [x] M13: Argus-Systemprofil (Identität, Rolle, Autonomiegrenzen)
- [x] M14: Deterministische NAS-Ingestion (Pfadsortierung, Sequenz, Metadaten)

## NAS-Ingestion

- Bis zu 10.000 Dateien pro Browser-Queue
- Natürliche Sortierung anhand des vollständigen relativen Pfads
- Sequenzielle Verarbeitung, genau eine Datei gleichzeitig
- Fortschrittsanzeige in nachvollziehbaren 100er-Batches
- Streaming-Upload in 1-MB-Blöcken bei maximal 200MB pro Datei
- `source_path`, `ingest_order`, `source_chunk_order` und `total_files` in ChromaDB
- Strikter Read-only-Quellschutz mit SHA-256-Prüfung vor und nach jedem Parserlauf
- Keine Schreib-, Verschiebe-, Umbenennungs- oder Löschoperationen auf Originaldateien

## Starten

### 1. SearXNG (einmalig)
```bash
docker run -d -p 8080:8080 --name searxng --restart always searxng/searxng
```

### 2. Ollama Modelle
```bash
ollama pull mistral
ollama pull moondream
ollama pull nomic-embed-text
ollama pull mistral-embed
```

### 3. Abhängigkeiten
```bash
pip install -r requirements.txt
```

### 4. Konfiguration
```bash
cp .env.example .env
# .env nach Bedarf anpassen (OLLAMA_CLOUD_URL eintragen)
```

### 5. WebApp starten
Es gibt zwei Wege, die Anwendung zu starten:

#### A. Mit dem automatischen Launcher (Windows)
Doppelklick auf `start_nsi_rag.bat` startet Backend und Frontend automatisch.

#### B. Manuell in separaten Terminalfenstern
*   **Backend:**
    ```bash
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ```
*   **Frontend:**
    ```bash
    cd frontend
    npm run dev -- --host 0.0.0.0 --port 5173
    ```

### 6. Browser aufrufen
- **Frontend:** http://localhost:5173
- **Backend-API:** http://localhost:8000

## Stack

- **Python 3.12** / **FastAPI** / **React + Vite** / **ChromaDB embedded**
- **Ollama lokal:** mistral + moondream + nomic-embed-text
- **Ollama Cloud EU:** mistral-large-2512 + mistral-embed
- **SearXNG:** Lokale Websuche
- **Kein Docker** / **Kein API-Key**

## Module

| Modul | Datei | Status |
|-------|-------|--------|
| **RAG-System** ||
| DocumentTypeRouter | core/ingestor/document_type_router.py | ✅ |
| PDFMultimodalIngestor | core/ingestor/pdf_multimodal_ingestor.py | ✅ |
| OfficeIngestor | core/ingestor/office_ingestor.py | ✅ |
| ImageIngestor | core/ingestor/image_ingestor.py | ✅ |
| DataIngestor | core/ingestor/data_ingestor.py | ✅ |
| ChromaStore | core/vectordb/chroma_store.py | ✅ |
| OllamaClient | core/llm/ollama_client.py | ✅ |
| ModelRouter | core/llm/model_router.py | ✅ |
| RAGPipeline | core/rag/rag_pipeline.py | ✅ |
| ArgusProfile | core/agent/argus_profile.py | ✅ |
| SourceVerifier | core/reasoning/source_verifier.py | ✅ |
| **Web-Suche** ||
| SearXNGClient | core/search/searxng_client.py | ✅ |
| WebContentFetcher | core/search/web_content_fetcher.py | ✅ |
| WebSearchPipeline | core/search/web_search_pipeline.py | ✅ |
| **App** ||
| UploadHandler | app/upload_handler.py | ✅ |
| ChatHandler | app/chat_handler.py | ✅ |
| Upload Panel | app/components/upload_panel.py | ✅ |
| Chat Panel | app/components/chat_panel.py | ✅ |
| WebApp | app/main.py | ✅ |
