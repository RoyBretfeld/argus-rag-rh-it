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

const statusLabels: Record<IngestionJob["status"], string> = {
  queued: "WARTET",
  running: "LAEUFT",
  paused: "PAUSIERT",
  completed: "FERTIG",
  failed: "FEHLER",
  cancelled: "ABGEBROCHEN",
};

export default function NightQueuePanel() {
  const [roots, setRoots] = useState<RootInfo[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [rootId, setRootId] = useState("");
  const [relativePath, setRelativePath] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [rootsResponse, jobsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/jobs/roots`),
        fetch(`${API_BASE_URL}/api/jobs?limit=5`),
      ]);
      if (rootsResponse.ok) {
        const data = await rootsResponse.json() as { roots: RootInfo[] };
        setRoots(data.roots);
        setRootId(current => current || data.roots.find(root => root.available)?.id || "");
      }
      if (jobsResponse.ok) {
        const data = await jobsResponse.json() as { jobs: IngestionJob[] };
        setJobs(data.jobs);
      }
    } catch {
      setStatus("Jobdienst nicht erreichbar.");
    }
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(refresh, 0);
    const interval = window.setInterval(refresh, 3000);
    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const createJob = async () => {
    if (!rootId) return;
    setIsSubmitting(true);
    setStatus("Ordner wird inventarisiert...");
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

      {roots.length === 0 ? (
        <div className="queue-empty">
          Keine NAS-Freigabe konfiguriert. ARGUS_NAS_ROOTS in der .env setzen.
        </div>
      ) : (
        <>
          <label className="queue-field">
            <span>FREIGABE</span>
            <select value={rootId} onChange={(event) => setRootId(event.target.value)}>
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
              <strong className={`job-status ${job.status}`}>
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
}
