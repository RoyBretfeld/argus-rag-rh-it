# NSI-RAGsystem Registry Modules

Diese Module stammen aus der globalen Modul-Registry unter:
`E:\Projekte\01_Aktiv\___Modul-Registry`

## Verfügbare Module:
- LocalLLMClient → Ollama-Inference mit Multi-Endpoint-Fallback
- ChromaBatchIngestor → ChromaDB Batch-Ingestion
- MultiTierLLMRouter → 3-Tier Lokal/Cloud-Routing mit DSGVO-Flag
- VRAMModelSelector → Modellauswahl je VRAM
- PromptInjectionBlocker → läuft immer vor jeder Verarbeitung
- StructuredAuditLogger → JSONL append-only, jeder Schritt geloggt
- RotatingFileLogger → Rotating-Log-Manager
- DualDumpPackager → DUMP_FULL + DUMP_LIGHT nach _rb_dumps/
