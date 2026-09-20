import { useEffect, useRef, useState } from "react";
import {
  cleanBuildCache,
  detectBuildCaches,
  getUserErrorMessage,
  type DetectedBuildCache,
} from "../ipc/client";

interface BuildCacheCardProps {
  projectId: number;
  projectPath: string;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function crateDirLabel(projectPath: string, manifestPath: string): string {
  const relDir = manifestPath.replace(/\/?Cargo\.toml$/, "");
  if (!relDir) return projectPath;
  return `${projectPath.replace(/[\\/]+$/, "")}/${relDir}`;
}

/**
 * Small improvement (audit "Clean Rust target cache"): for any registered
 * project that turns out to contain a Cargo crate, offer a one-click,
 * confirmation-gated way to run `cargo clean` on its target/ directory.
 * Renders nothing for a non-Rust project (the common case).
 */
export function BuildCacheCard({ projectId, projectPath }: BuildCacheCardProps) {
  const [caches, setCaches] = useState<DetectedBuildCache[] | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<DetectedBuildCache | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // M9 (found during re-audit): mirrors AppShell's selectedIdRef pattern —
  // handleClean is async (a real cargo clean can take seconds); without this,
  // switching projects mid-clean applied the finished operation's notice/
  // cache-list update to whatever project the user had since switched to.
  const projectIdRef = useRef(projectId);

  useEffect(() => {
    projectIdRef.current = projectId;
    let cancelled = false;
    setCaches(null);
    setConfirmTarget(null);
    setCleaning(false);
    setError(null);
    setNotice(null);
    void detectBuildCaches(projectId)
      .then((result) => {
        if (!cancelled) setCaches(result.caches);
      })
      .catch(() => {
        // Detection failure is non-critical for this low-priority convenience
        // feature — show nothing rather than an alarming error.
        if (!cancelled) setCaches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Keep rendering after a successful clean empties the list, so the "Freed
  // X" notice stays visible instead of vanishing along with the last row.
  if ((!caches || caches.length === 0) && !notice) {
    return null;
  }

  const handleClean = async () => {
    if (!confirmTarget) return;
    const cleaningForProjectId = projectId;
    setCleaning(true);
    setError(null);
    try {
      const result = await cleanBuildCache(projectId, confirmTarget.manifest_path);
      if (projectIdRef.current !== cleaningForProjectId) {
        // The clean genuinely ran (cargo already did its work) — just don't
        // apply its result to whatever project is now on screen.
        return;
      }
      const cleanedPath = confirmTarget.manifest_path;
      setCaches((prev) => (prev ?? []).filter((c) => c.manifest_path !== cleanedPath));
      setNotice(`Freed ${formatBytes(result.cache.size_bytes)} from ${result.cache.target_path}.`);
      setConfirmTarget(null);
    } catch (err) {
      if (projectIdRef.current !== cleaningForProjectId) return;
      setError(getUserErrorMessage(err));
    } finally {
      if (projectIdRef.current === cleaningForProjectId) {
        setCleaning(false);
      }
    }
  };

  return (
    <div className="build-cache-card">
      {notice ? (
        <p className="build-cache-card__notice" role="status">
          {notice}
        </p>
      ) : null}
      {(caches ?? []).map((cache) => (
        <div key={cache.manifest_path} className="build-cache-card__row">
          <div>
            <p className="build-cache-card__title">Build cache detected: {cache.target_path}</p>
            <p className="build-cache-card__size">
              Estimated size: {formatBytes(cache.size_bytes)}
            </p>
          </div>
          <button type="button" onClick={() => setConfirmTarget(cache)}>
            Clean build cache…
          </button>
        </div>
      ))}

      {confirmTarget ? (
        <div
          className="build-cache-overlay"
          role="dialog"
          aria-labelledby="build-cache-dialog-title"
        >
          <div className="build-cache-dialog">
            <h2 id="build-cache-dialog-title">Delete Rust build cache?</h2>
            <p>
              This will run <code>cargo clean</code> in:
              <br />
              <code>{crateDirLabel(projectPath, confirmTarget.manifest_path)}</code>
            </p>
            <p className="muted">
              Frees ~{formatBytes(confirmTarget.size_bytes)}. Safe — Cargo regenerates this on
              next build.
            </p>
            {error ? <p className="error-text">{error}</p> : null}
            <div className="build-cache-dialog__actions">
              <button type="button" disabled={cleaning} onClick={() => void handleClean()}>
                {cleaning ? "Cleaning…" : "Clean now"}
              </button>
              <button type="button" disabled={cleaning} onClick={() => setConfirmTarget(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
