"""Background import jobs with pollable / streamable progress.

An import can take a while (acquire + parse many files), so it runs in a worker
thread. Progress events emitted by the pipeline are buffered on the job so the
GUI can poll ``GET /api/sync/{id}`` or follow the SSE stream. Only one import
runs at a time -- starting again returns the in-flight job.
"""

from __future__ import annotations

import datetime as _dt
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.config import Config
from core.pipeline import import_activities


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()
    )
    finished_at: str | None = None

    def snapshot(self) -> dict[str, Any]:
        """A JSON-able view of the job's current state."""
        last = self.events[-1] if self.events else {}
        return {
            "job_id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "current": last.get("current", 0),
            "total": last.get("total", 0),
            "phase": last.get("phase"),
            "filename": last.get("filename"),
            "summary": self.summary,
            "error": self.error,
        }


class JobManager:
    """Tracks import jobs. Thread-safe; runs at most one import at a time."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._active_id: str | None = None
        self._lock = threading.Lock()

    def active(self) -> Job | None:
        with self._lock:
            if self._active_id is None:
                return None
            return self._jobs.get(self._active_id)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, cfg: Config) -> Job:
        """Start an import, or return the already-running job if one exists."""
        with self._lock:
            if self._active_id is not None:
                active = self._jobs.get(self._active_id)
                if active and active.status == "running":
                    return active
            job = Job(id=uuid.uuid4().hex)
            self._jobs[job.id] = job
            self._active_id = job.id

        thread = threading.Thread(
            target=self._run, args=(job, cfg), name=f"import-{job.id}", daemon=True
        )
        thread.start()
        return job

    def _run(self, job: Job, cfg: Config) -> None:
        def on_progress(event: dict[str, Any]) -> None:
            with self._lock:
                job.events.append(event)

        try:
            summary = import_activities(cfg, on_progress=on_progress)
            with self._lock:
                job.summary = summary.as_dict()
                job.status = "done"
        except Exception as exc:  # surface, don't crash the server
            with self._lock:
                job.status = "error"
                job.error = str(exc)
        finally:
            with self._lock:
                job.finished_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
                if self._active_id == job.id:
                    self._active_id = None
