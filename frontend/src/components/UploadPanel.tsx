import { useState, useRef, useEffect } from 'react';
import type { ChangeEvent, DragEvent, InputHTMLAttributes } from 'react';

interface SystemStats {
  database: { nsi_local: number; nsi_cloud: number };
  gpu: { available: boolean; name: string; total_vram_mb: number; used_vram_mb: number; free_vram_mb: number; method: string };
  ram: { total_gb: number; used_gb: number; available_gb: number; percent: number };
}

type UploadResponse = {
  message?: string;
  chunks_erstellt?: number;
  error?: string;
  detail?: string;
  errors?: string[] | null;
};

type UploadFile = File & {
  webkitRelativePath?: string;
};

type DirectoryInputProps = InputHTMLAttributes<HTMLInputElement> & {
  webkitdirectory?: string;
  directory?: string;
};

const directoryInputProps: DirectoryInputProps = {
  webkitdirectory: "",
  directory: "",
};

const getErrorMessage = (error: unknown) => (
  error instanceof Error ? error.message : 'Unbekannter Fehler'
);

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const MAX_BATCH_FILES = 100;
const MAX_QUEUE_FILES = 10000;
const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set([
  ".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".xml", ".json", ".eml",
  ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff",
]);

const getFileExtension = (filename: string) => {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
};

const pathCollator = new Intl.Collator("de", {
  numeric: true,
  sensitivity: "base",
});

const getRelativePath = (file: UploadFile) => (
  (file.webkitRelativePath || file.name).replaceAll("\\", "/")
);

const sortFilesByPath = (items: UploadFile[]) => (
  [...items].sort((left, right) => (
    pathCollator.compare(getRelativePath(left), getRelativePath(right))
  ))
);

export default function UploadPanel() {
  const [dragActive, setDragActive] = useState(false);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [category, setCategory] = useState('dokumente');
  const [isConfidential, setIsConfidential] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/system/stats`);
        if (res.ok) {
          const data = await res.json();
          setSystemStats(data);
        }
      } catch (err) {
        console.error("Fehler beim Abrufen der Systemstatistiken", err);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const addFiles = (incomingFiles: UploadFile[]) => {
    const supportedFiles = incomingFiles.filter(file => {
      const extension = getFileExtension(file.name);
      return ALLOWED_EXTENSIONS.has(extension) && file.size <= MAX_FILE_SIZE_BYTES;
    });

    setFiles(previousFiles => {
      const knownPaths = new Set(previousFiles.map(getRelativePath));
      const uniqueIncoming = supportedFiles.filter(file => {
        const relativePath = getRelativePath(file);
        if (knownPaths.has(relativePath)) return false;
        knownPaths.add(relativePath);
        return true;
      });
      const availableSlots = Math.max(MAX_QUEUE_FILES - previousFiles.length, 0);
      return sortFilesByPath([
        ...previousFiles,
        ...uniqueIncoming.slice(0, availableSlots),
      ]);
    });

    const unsupportedCount = incomingFiles.length - supportedFiles.length;
    if (unsupportedCount > 0) {
      setUploadStatus(
        `${unsupportedCount} Dateien ausgelassen: Dateityp nicht unterstützt oder größer als 200MB.`
      );
      return;
    }
    if (files.length + supportedFiles.length > MAX_QUEUE_FILES) {
      setUploadStatus(`Queue auf ${MAX_QUEUE_FILES} Dateien begrenzt.`);
      return;
    }
    setUploadStatus(null);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files) {
      addFiles(Array.from(e.target.files));
    }
    e.target.value = "";
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setIsUploading(true);
    setUploadProgress(0);
    setUploadStatus("Lade hoch...");
    
    try {
      let processedCount = 0;
      let totalChunks = 0;
      const errors: string[] = [];

      for (const [index, file] of files.entries()) {
        const relativePath = getRelativePath(file);
        const batchNumber = Math.floor(index / MAX_BATCH_FILES) + 1;
        const batchCount = Math.ceil(files.length / MAX_BATCH_FILES);
        setUploadStatus(
          `Batch ${batchNumber}/${batchCount} - Datei ${index + 1}/${files.length}: ${relativePath}`
        );

        const formData = new FormData();
        formData.append("files", file);
        formData.append("kategorie", category);
        formData.append("vertraulich", isConfidential.toString());
        formData.append("source_path", relativePath);
        formData.append("ingest_order", (index + 1).toString());
        formData.append("total_files", files.length.toString());

        const response = await fetch(`${API_BASE_URL}/api/upload`, {
          method: "POST",
          body: formData,
        });
        const data = await response.json() as UploadResponse;

        if (response.ok) {
          processedCount += 1;
          totalChunks += data.chunks_erstellt || 0;
          if (data.errors?.length) {
            errors.push(...data.errors);
          }
        } else {
          errors.push(`${relativePath}: ${data.error || data.detail || 'Unbekannter Fehler'}`);
        }
        setUploadProgress(Math.round(((index + 1) / files.length) * 100));
      }

      setFiles([]);
      const statsRes = await fetch(`${API_BASE_URL}/api/system/stats`);
      if (statsRes.ok) {
        setSystemStats(await statsRes.json());
      }

      if (errors.length > 0) {
        setUploadStatus(`${processedCount}/${files.length} Dateien verarbeitet, ${errors.length} Fehler. ${errors[0]}`);
      } else {
        setUploadStatus(`Erfolgreich ${processedCount} Dateien verarbeitet. ${totalChunks} Chunks erstellt.`);
      }
    } catch (error: unknown) {
      setUploadStatus(`Upload abgebrochen: API nicht erreichbar oder Datei blockiert (${getErrorMessage(error)}).`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleResetDB = async () => {
    if (!window.confirm("Bist du sicher, dass du die gesamte ChromaDB-Datenbank zurücksetzen und alle Chunks löschen möchtest? Dies kann nicht rückgängig gemacht werden!")) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/system/reset`, {
        method: "POST"
      });
      if (res.ok) {
        alert("Datenbank erfolgreich zurückgesetzt!");
        const statsRes = await fetch(`${API_BASE_URL}/api/system/stats`);
        if (statsRes.ok) {
          setSystemStats(await statsRes.json());
        }
      } else {
        const data = await res.json() as UploadResponse;
        alert(`Fehler beim Zurücksetzen: ${data.detail || 'Unbekannt'}`);
      }
    } catch (err: unknown) {
      alert(`Verbindungsfehler beim Zurücksetzen: ${getErrorMessage(err)}`);
    }
  };

  return (
    <div className="sidebar">
      <div className="brand">
        <div className="argus-symbol">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="40" height="40" fill="currentColor">
            <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="6,4"/>
            <path d="M15 50 Q50 20 85 50 Q50 80 15 50 Z" fill="none" stroke="currentColor" strokeWidth="3"/>
            <circle cx="50" cy="50" r="16" fill="none" stroke="currentColor" strokeWidth="2"/>
            <circle cx="50" cy="50" r="8" fill="currentColor"/>
            <circle cx="50" cy="18" r="3" fill="currentColor"/>
            <circle cx="50" cy="82" r="3" fill="currentColor"/>
            <circle cx="18" cy="50" r="3" fill="currentColor"/>
            <circle cx="82" cy="50" r="3" fill="currentColor"/>
            <circle cx="28" cy="28" r="2.5" fill="currentColor"/>
            <circle cx="72" cy="28" r="2.5" fill="currentColor"/>
            <circle cx="28" cy="72" r="2.5" fill="currentColor"/>
            <circle cx="72" cy="72" r="2.5" fill="currentColor"/>
          </svg>
        </div>
        <div>
          <div className="brand-kicker">[ARGUS] KNOWLEDGE CORE</div>
          <h1>A.R.G.U.S.</h1>
          <p>Document Intelligence System</p>
        </div>
      </div>

      <div className="glass-panel intake-panel">
        <div className="panel-title">
          <span>1. KNOWLEDGE INTAKE</span>
          <strong>READY</strong>
        </div>
        <div className="segmented-control category-control">
          <button className={`segment-btn ${category === 'dokumente' ? 'active' : ''}`} onClick={() => setCategory('dokumente')}>Dokumente</button>
          <button className={`segment-btn ${category === 'bilder' ? 'active' : ''}`} onClick={() => setCategory('bilder')}>Bilder</button>
          <button className={`segment-btn ${category === 'technische_daten' ? 'active' : ''}`} onClick={() => setCategory('technische_daten')}>Tech Daten</button>
        </div>

        <div 
          className={`dropzone ${dragActive ? 'active' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input 
            ref={inputRef}
            type="file" 
            multiple
            style={{ display: "none" }} 
            onChange={handleChange} 
          />
          <input 
            ref={folderInputRef}
            type="file" 
            {...directoryInputProps}
            style={{ display: "none" }} 
            onChange={handleChange} 
          />
          <div className="dropzone-glyph">DOC</div>
          <strong>Knowledge Payload Drop</strong>
          <p>NAS-Queue bis 10.000 Dateien - sequenziell in 100er-Batches - 200MB je Datei</p>
          <div className="dropzone-actions" onClick={(e) => e.stopPropagation()}>
            <button 
              className="mini-action"
              onClick={() => inputRef.current?.click()}
            >
              Dateien wählen
            </button>
            <button 
              className="mini-action"
              onClick={() => folderInputRef.current?.click()}
            >
              Ordner wählen
            </button>
          </div>
        </div>

        {files.length > 0 && (
          <div className="file-list">
            <div className="file-list-header">
              <span>Ausgewählt ({files.length}):</span>
              <span 
                className="file-reset"
                onClick={() => setFiles([])}
              >
                Zurücksetzen
              </span>
            </div>
            {files.slice(0, 3).map((f) => (
              <div key={getRelativePath(f)} className="file-row" title={getRelativePath(f)}>
                {getRelativePath(f)}
              </div>
            ))}
            {files.length > 3 && (
              <div className="file-more">
                und {files.length - 3} weitere...
              </div>
            )}
          </div>
        )}

        <label className="checkbox-wrapper">
          <input 
            type="checkbox" 
            checked={isConfidential} 
            onChange={(e) => setIsConfidential(e.target.checked)} 
          />
          Vertrauliches Dokument (DSGVO)
        </label>

        <button 
          className="upload-command"
          onClick={handleUpload}
          disabled={files.length === 0 || isUploading}
        >
          {isUploading ? 'Ingestion läuft...' : 'Ingestion starten'}
        </button>

        {isUploading && (
          <div className="upload-progress">
            <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }}></div>
          </div>
        )}
        
        {uploadStatus && !isUploading && (
          <div className={`upload-status ${uploadStatus.includes('Fehler') ? 'error' : ''}`}>
            {uploadStatus}
          </div>
        )}
      </div>

      {systemStats && (
        <div className="glass-panel telemetry-panel">
          <div className="panel-title">
            <span>2. SYSTEM TELEMETRY</span>
            <strong>SECURE</strong>
          </div>
          <div className="telemetry-stack">
            <div className="truncate" title={systemStats.gpu.name}>
              <strong>GPU:</strong> {systemStats.gpu.name}
            </div>
            {systemStats.gpu.available ? (
              <>
                <div className="metric-row">
                  <span>VRAM: {Math.round(systemStats.gpu.used_vram_mb)} / {Math.round(systemStats.gpu.total_vram_mb)} MB</span>
                  <span>{Math.round((systemStats.gpu.used_vram_mb / systemStats.gpu.total_vram_mb) * 100)}%</span>
                </div>
                <div className="upload-progress slim">
                  <div 
                    className="upload-progress-bar" 
                    style={{ 
                      width: `${(systemStats.gpu.used_vram_mb / systemStats.gpu.total_vram_mb) * 100}%`,
                      transition: 'width 0.5s ease-in-out'
                    }}
                  ></div>
                </div>
              </>
            ) : (
              <div className="muted-small">CPU-Modus (kein VRAM verfügbar)</div>
            )}
            <div className="metric-row">
              <span>Sys-RAM: {systemStats.ram.used_gb} / {systemStats.ram.total_gb} GB</span>
              <span>{systemStats.ram.percent}%</span>
            </div>
          </div>

          <hr className="panel-divider" />

          <div className="panel-title compact">
            <span>3. VECTOR STORE</span>
            <strong>CONNECTED</strong>
          </div>
          <div className="telemetry-stack">
            <div className="metric-row">
              <span>Lokale Chunks:</span>
              <strong>{systemStats.database.nsi_local}</strong>
            </div>
            <div className="metric-row">
              <span>Cloud Chunks:</span>
              <strong>{systemStats.database.nsi_cloud}</strong>
            </div>
          </div>

        </div>
      )}

      <div className="maintenance-zone">
        <div>
          <span>MAINTENANCE</span>
          <strong>LOCAL ONLY</strong>
        </div>
        <button 
          className="danger-command"
          onClick={handleResetDB}
        >
          Datenbank zurücksetzen
        </button>
      </div>

      <div className="product-footer">
        NODE: <a href="https://rh-automation-dresden.de" target="_blank" rel="noopener noreferrer">rh-automation-dresden.de</a>
        <span>rh-it Dresden</span>
      </div>
    </div>
  );
}
