#!/usr/bin/env python3
"""Interview-/Transkript-Artefakte an eine Stelle anbinden.

Claude-in-the-Loop erzeugt Briefings (Skill interview-vorbereiten → Briefing-HTML) und
Transkripte (manuell eingefügt oder später Hedy). Dieser Modul registriert sie
deterministisch in der DB, sodass die Web-App sie am Job-Detail verlinkt.

CLI:
    cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.interview <interview.json>

interview.json — alle Teile optional außer job_id:
    {
      "job_id": 1,
      "interview": {"runde": 1, "art": "HR-Screen", "scheduled_at": "2026-07-15T14:00",
                     "interviewer": "…", "status": "Geplant", "notes": "…"},   # legt NEUES Interview an
      "interview_id": 3,                       # ODER bestehendes Interview adressieren
      "prep_path": "data/interview_prep/2026_07_10_Briefing_Job1_R1.html",   # setzt prep_path am Interview
      "transcript": {"file_path": "data/transcripts/…md", "title": "…", "summary": "…",
                      "todos_json": "[…]", "recorded_at": "2026-07-15", "language": "DE", "source": "manuell"},
      "set_status": "Absolviert",              # optional: Interview-Status setzen
      "job_next_step": "Follow-up-Mail senden",        # optional → Job.next_step
      "job_follow_up_date": "2026-07-18"               # optional → Job.follow_up_date
    }
"""
import datetime
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Application, Interview, Job, Transcript

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Bewerbung_Mgmt_System/


def _rel(path):
    """Pfad relativ zum Projekt-Root speichern (portabel)."""
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(p)
    return str(path)


def register(job_id, interview=None, interview_id=None, prep_path=None,
             transcript=None, set_status=None, job_next_step=None, job_follow_up_date=None):
    init_db()
    now = datetime.datetime.utcnow
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            raise SystemExit(f"Job {job_id} nicht gefunden")
        application = s.exec(select(Application).where(Application.job_id == job_id)).first()
        out = {"job_id": job_id}

        # Interview: neu anlegen ODER bestehendes adressieren
        iv = None
        if interview:
            fields = {"runde", "art", "scheduled_at", "interviewer", "status", "notes"}
            data = {k: v for k, v in interview.items() if k in fields}
            if not data.get("runde"):
                existing = s.exec(select(Interview).where(Interview.job_id == job_id)).all()
                data["runde"] = max((i.runde for i in existing), default=0) + 1
            iv = Interview(
                job_id=job_id,
                company_id=job.company_id,
                application_id=application.id if application else None,
                **data,
            )
            s.add(iv)
            s.flush()
            out["interview_id"] = iv.id
        elif interview_id:
            iv = s.get(Interview, interview_id)
            if not iv:
                raise SystemExit(f"Interview {interview_id} nicht gefunden")
            out["interview_id"] = iv.id

        if iv is not None:
            if prep_path:
                iv.prep_path = _rel(prep_path)
                out["prep_path"] = iv.prep_path
            if set_status:
                iv.status = set_status
            iv.updated_at = now()
            s.add(iv)

        # Transkript-Row (Datei liegt bereits, hier nur registrieren)
        if transcript:
            row = Transcript(
                job_id=job_id,
                interview_id=iv.id if iv is not None else None,
                application_id=application.id if application else None,
                source=transcript.get("source", "manuell"),
                title=transcript.get("title"),
                file_path=_rel(transcript.get("file_path")),
                summary=transcript.get("summary"),
                todos_json=transcript.get("todos_json"),
                recorded_at=transcript.get("recorded_at"),
                language=transcript.get("language"),
            )
            s.add(row)
            s.flush()
            out["transcript_id"] = row.id

        if job_next_step:
            job.next_step = job_next_step
        if job_follow_up_date:
            job.follow_up_date = job_follow_up_date
        job.updated_at = now()
        s.add(job)
        s.commit()
        return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Nutzung: python -m pipeline.interview <interview.json>")
    with open(sys.argv[1], encoding="utf-8") as fh:
        d = json.load(fh)
    print(json.dumps(register(
        d["job_id"], d.get("interview"), d.get("interview_id"), d.get("prep_path"),
        d.get("transcript"), d.get("set_status"), d.get("job_next_step"), d.get("job_follow_up_date"),
    ), ensure_ascii=False))
