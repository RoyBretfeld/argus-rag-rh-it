import { useCallback, useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

type RootInfo = {
  id: string;
  path: string;
  available: boolean;
  read_only: boolean;
};

type IngestionJob = {
  id: string;
  root_id: string;
  relative_path: string;
  status: "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";
  total_files: number;
  processed_files: number;
  failed_files: number;
  total_chunks: number;
  current_file?: string | null;
  last_error?: string | null;
  progress_percent: number;
};

type IdleStatus = {
  idle_seconds: number;
  idle_minutes: number;
  is_idle: boolean;
};

const statusLabels: Record<IngestionJob["status"], string> = {
  queued: "WARTET",
  running: "LAEUFT",
  paused: "PAUSIERT",
  completed: "FERTIG",
  failed: "FEHLER",
  cancelled: "ABGEBROCHEN",
};

const statusColors: Record<IngestionJob["status"], string> = {
  queued: "bg-gray-500 text-white",
  running: "bg-blue-500 text-white",
  paused: "bg-yellow-500 text-black",
  completed: "bg-green-500 text-white",
  failed: "bg-red-500 text-white",
  cancelled: "bg-gray-400 text-white",
};

export default function NightQueuePanel() {
  const [roots, setRoots] = useState<RootInfo[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [rootId, setRootId] = useState("");
  const [relativePath, setRelativePath] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [idleStatus, setIdleStatus] = useState<IdleStatus | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Idle-Status abrufen
  const fetchIdleStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/system/idle`);
      if (response.ok) {
        const data = await response.json() as IdleStatus;
        setIdleStatus(data);
      }
    } catch {
      // Ignoriere Errors
    }
  }, []);

  // Idle-Status alle 30 Sekunden aktualisieren
  useEffect(() => {
    fetchIdleStatus();
    const interval = setInterval(fetchIdleStatus, 30000);
    return () => clearInterval(interval);
  }, [fetchIdleStatus]);

  const refresh = useCallback(async () => {
    try {
      const [rootsResponse, jobsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/jobs/roots`),
        fetch(`${API_BASE_URL}/api/jobs?limit=50`),
      ]);
      if (rootsResponse.ok) {
        const data = await rootsResponse.json() as { roots: RootInfo[] };
        setRoots(data.roots);
        if (!rootId) {
          setRootId(data.roots.find(root => root.available)?.id || "");
        }
      }
      if (jobsResponse.ok) {
        const data = await jobsResponse.json() as { jobs: IngestionJob[] };
        setJobs(data.jobs);
      }
    } catch {
      setStatus("Jobdienst nicht erreichbar.");
    }
  }, [rootId]);

  // Auto-Refresh alle 10 Sekunden wenn ein Job läuft
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === "running");
    setAutoRefresh(hasRunning);

    if (hasRunning) {
      const interval = setInterval(refresh, 10000);
      return () => clearInterval(interval);
    }
  }, [jobs, refresh]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(initialRefresh);
  }, [refresh]);

  // "Jetzt ausführen" - erstellt Jobs für alle verfügbaren Roots
  const executeNow = async () => {
    if (roots.length === 0) {
      setStatus("Keine NAS-Freigabe konfiguriert.");
      return;
    }
    setIsSubmitting(true);
    setStatus("Erstelle Jobs für alle verfügbaren Roots...");

    const results: string[] = [];
    for (const root of roots) {
      if (root.available) {
        try {
          const response = await fetch(`${API_BASE_URL}/api/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              root_id: root.id,
              relative_path: "",
              category: "dokumente",
              confidential: true,
            }),
          });
          const data = await response.json() as { detail?: string };
          if (!response.ok) {
            results.push(`${root.id}: ${data.detail || "Fehler"}`);
          } else {
            results.push(`${root.id}: Job angelegt`);
          }
        } catch (error) {
          results.push(`${root.id}: Verbindungsfehler`);
        }
      } else {
        results.push(`${root.id}: Offline (übersprungen)`);
      }
    }

    setStatus(results.join(" | "));
    await refresh();
    setIsSubmitting(false);
  };

  const changeJob = async (jobId: string, action: "pause" | "resume" | "cancel") => {
    const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/${action}`, {
      method: "POST",
    });
    if (!response.ok) {
      const data = await response.json() as { detail?: string };
      setStatus(data.detail || "Statuswechsel fehlgeschlagen.");
    }
    await refresh();
  };

  return (
    <div className="glass-panel night-queue-panel">
      <div className="panel-title">
        <span>2. NIGHT INGESTION</span>
        <strong>PERSISTENT</strong>
      </div>

      {/* Idle-Status-Badge oben */}
      {idleStatus && (
        <div className="idle-status-badge mb-2">
          <span className={`inline-block px-3 py-1 text-xs font-bold rounded ${idleStatus.is_idle ? "bg-green-500 text-white" : "bg-gray-500 text-white"}`}>
            System: {idleStatus.is_idle ? "IDLE" : "AKTIV"}
          </span>
          <span className="text-xs text-gray-600 ml-2">
            {idleStatus.idle_minutes.toFixed(1)} min
          </span>
        </div>
      )}

      <div className="flex flex-col gap-3 mb-4">
        <button
          className="upload-command bg-indigo-600 hover:bg-indigo-700 text-white py-2 px-4 rounded"
          onClick={executeNow}
          disabled={isSubmitting || roots.length === 0}
        >
          {isSubmitting ? "Erstelle Jobs..." : "Jetzt ausführen"}
        </button>
      </div>

      {roots.length === 0 ? (
        <div className="queue-empty">
          Keine NAS-Freigabe konfiguriert. ARGUS_NAS_ROOTS in der .env setzen.
        </div>
      ) : (
        <>
          <label className="queue-field">
            <span>FREIGABE</span>
            <select
              value={rootId}
              onChange={(event) => setRootId(event.target.value)}
              disabled={isSubmitting}
            >
              {roots.map(root => (
                <option key={root.id} value={root.id} disabled={!root.available}>
                  {root.id}{root.available ? "" : " (offline)"}
                </option>
              ))}
            </select>
          </label>
          <label className="queue-field">
            <span>UNTERORDNER</span>
            <input
              type="text"
              value={relativePath}
              onChange={(event) => setRelativePath(event.target.value)}
              placeholder="z.B. 01_Kunden/Projekt_A"
              disabled={isSubmitting}
            />
          </label>
          <button
            className="upload-command"
            onClick={createJob}
            disabled={!rootId || isSubmitting}
          >
            {isSubmitting ? "Inventarisierung..." : "Nachtjob starten"}
          </button>
        </>
      )}

      {status && <div className="upload-status">{status}</div>}

      <div className="job-list">
        {jobs.map(job => (
          <div className="job-row" key={job.id}>
            <div className="job-row-head">
              <span title={job.relative_path || job.root_id}>
                {job.relative_path || job.root_id}
              </span>
              <strong className={`job-status ${job.status} ${statusColors[job.status]}`}>
                {statusLabels[job.status]}
              </strong>
            </div>
            <div className="upload-progress slim">
              <div className="upload-progress-bar" style={{ width: `${job.progress_percent}%` }} />
            </div>
            <div className="job-meta">
              {job.processed_files}/{job.total_files} Dateien · {job.total_chunks} Chunks
              {job.failed_files > 0 ? ` · ${job.failed_files} Fehler` : ""}
            </div>
            {job.current_file && (
              <div className="job-current" title={job.current_file}>{job.current_file}</div>
            )}
            <div className="job-actions">
              {job.status === "running" || job.status === "queued" ? (
                <button title="Job pausieren" onClick={() => changeJob(job.id, "pause")}>Pause</button>
              ) : null}
              {job.status === "paused" || job.status === "failed" ? (
                <button title="Job fortsetzen" onClick={() => changeJob(job.id, "resume")}>Weiter</button>
              ) : null}
              {["queued", "running", "paused", "failed"].includes(job.status) ? (
                <button title="Job abbrechen" onClick={() => changeJob(job.id, "cancel")}>Stopp</button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  function createJob() {
    if (!rootId) return;
    setIsSubmitting(true);
    setStatus("Ordner wird inventarisiert...");
    (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/jobs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            root_id: rootId,
            relative_path: relativePath,
            category: "dokumente",
            confidential: true,
          }),
        });
        const data = await response.json() as IngestionJob & { detail?: string };
        if (!response.ok) {
          throw new Error(data.detail || "Job konnte nicht angelegt werden.");
        }
        setStatus(`${data.total_files} Dateien sicher in die Nacht-Queue aufgenommen.`);
        await refresh();
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Unbekannter Jobfehler.");
      } finally {
        setIsSubmitting(false);
      }
    })();
  }
}
