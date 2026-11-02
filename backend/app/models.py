"""SQLModel data model — the single source of truth for the Bewerbungs-Mgmt-System.

Relations:
    Company 1─* Job 1─* Application 1─* Email
    Company/Job 1─* Contact
    Job 1─* CVVersion
    Run = protocol of each daily search / email-check.

Messy real-world values (status, situation, seniority) are stored twice:
a normalized field for filtering/analytics + a *_raw field preserving the original text.
"""
from datetime import datetime

from app.zeit import UtcZeit
from typing import Optional

from sqlmodel import SQLModel, Field


class Company(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    domain: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    situation: Optional[str] = None          # normalized code: BUILD/CARVE-OUT/POST-MERGER/PE/SCALE-UP/RESTRUCT/RUN/UNKLAR
    situation_raw: Optional[str] = None
    restructuring_signal: Optional[str] = None
    rebuild_or_cut: Optional[str] = None     # Rebuild / Abbau / Unklar
    is_radar: bool = Field(default=False)    # from Restructuring Radar tab
    radar_role_open: Optional[str] = None
    radar_next_step: Optional[str] = None
    notes: Optional[str] = None
    fit_analysis_path: Optional[str] = None  # path to company-fit HTML dashboard
    fit_ampel: Optional[str] = None          # gruen|gelb|rot — Phase 24 F, strukturiert statt nur im HTML
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Job(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    company_name: Optional[str] = None       # denormalized for quick display
    title: str
    seniority: Optional[str] = None          # normalized: normalize.SENIORITAETEN oder Sonstige, z. B. Director/...
    seniority_raw: Optional[str] = None
    location: Optional[str] = None
    work_model: Optional[str] = None         # Remote/Hybrid/Onsite/Unbekannt
    relocation_needed: Optional[str] = None
    tab: Optional[str] = None                # search bucket: Remote/Deutschlandweit/<Stadt> +<km>km
                                              # (s. pipeline.suchprofil.umkreis_label, P2-51 V7)
    plan_ab: Optional[str] = None            # A / B / C
    portal: Optional[str] = None             # LinkedIn/Indeed/StepStone/Xing/Company/News/...
    url: Optional[str] = Field(default=None, index=True)
    career_url: Optional[str] = None         # Phase 73: Karriereseiten-Fallback bei geschlossenem Portal
    # Phase 73: Karriereseiten-Fallback bei geschlossenem Portal. sa_column_kwargs=server_default
    # NOETIG (nicht nur Python-Field-default=0): ohne echten SQL-DEFAULT erzeugt create_all() eine
    # NOT-NULL-Spalte OHNE Vorgabewert -- jedes rohe INSERT, das die Spalte ausspart (z. B. Alt-
    # Schema-/Migrations-Tests), wuerde an der NOT-NULL-Constraint scheitern. Mit server_default
    # deckungsgleich zum additiven Migrations-Eintrag "INTEGER DEFAULT 0" in db.py::_ADD_COLUMNS.
    portal_closed: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    # Phase 74 — Beworben-Check (wöchentliche Verfügbarkeitsprüfung): Ergebnis der letzten Prüfung,
    # ob eine beworbene Stelle noch ausgeschrieben ist. Werte: offen/karriereseite_offen/offline/
    # unklar (main.py::ALLOWED_AVAILABILITY), Datum als ISO "YYYY-MM-DD". Beide nullable TEXT ohne
    # SQL-DEFAULT — anders als portal_closed KEIN NOT-NULL-Feld, jedes Alt-Insert bleibt gültig.
    availability_status: Optional[str] = None
    availability_checked_at: Optional[str] = None
    salary: Optional[str] = None
    published_date: Optional[str] = None
    found_date: Optional[str] = None
    # 1-5 = „Zielstellen-Fit" (so heißt es seit 13.08.2026 überall in UI, Digest und Doku):
    # Stelle gegen Zielprofil, Bewertungsraster in config/scoring_rubrik.md. NICHT verwechseln mit
    # CVVersion.match_score100 (0-100) — das ist der CV-Match-Score, Dokument gegen Anzeige.
    # Feldname bleibt `match_score`: DB-Spalte, API-Feld und Skill-JSON hängen daran.
    match_score: Optional[int] = None        # 1-5
    match_rationale: Optional[str] = None
    gut_feeling: Optional[int] = None        # 1-5, subjektives Bauchgefühl des Nutzers (ergänzt den Zielstellen-Fit)
    status: Optional[str] = None             # normalized: Neu/Prüfen/Beworben/Absage/Keine Rückmeldung/Kein Match/Nicht verfügbar/Geparkt
    status_raw: Optional[str] = None
    next_step: Optional[str] = None
    follow_up_date: Optional[str] = None     # ISO-Datum (YYYY-MM-DD): wann der nächste Schritt fällig ist
    notes: Optional[str] = None              # freie Notizen / dokumentierte Zwischenstände (vom Nutzer)
    source_note: Optional[str] = None
    freshness_note: Optional[str] = None
    verified_at: Optional[str] = None        # ISO: Zeitpunkt der letzten URL-Verifikation (Phase 14)
    # Kurzbefund "{status}: {beleg}" der Vier-Augen-Prüfung (Präfix BESTÄTIGT/KORRIGIERT/QUELLE_VERTRAUT
    # → Badge im Frontend). Phase 21: Quellen-KONFLIKTE werden hier als Anhang dokumentiert (KEINE
    # Schema-Änderung, EIN kanonischer Ort). Festes Schlüsselwort `KONFLIKT`, Format:
    #   "{Badge-Präfix}: {beleg} | KONFLIKT <Feld>: <Quelle A sagt X> vs. <Quelle B sagt Y> — im
    #    Gespräch klären (geprüft <JJJJ-MM-TT>)"
    # Beispiel (geprüft 11.07.2026): work_model=Remote (Anzeigentext „Remote-first across
    # Europe"), aber LinkedIn-Workplace-Chip „On-site" (Musterstadt) →
    #   "… | KONFLIKT Arbeitsmodell: Anzeigentext ‚Remote-first across Europe' vs. LinkedIn-Chip
    #    ‚On-site (Musterstadt)' — im Gespräch klären (geprüft 2026-07-11)".
    # Mehrere Konflikte = mehrere " | KONFLIKT …"-Anhänge. Das Badge-Präfix bleibt IMMER vorne.
    # Phase 44 (20.07.2026): Repost-Verdacht (Text-Ähnlichkeits-Dedup, pipeline/dedup_text.py)
    # nutzt dasselbe Anhang-Muster, festes Schlüsselwort `DUBLETTE?`, vom Ingest-Hook gesetzt:
    #   " | DUBLETTE? Job <id> „<Titel, ≤ 40 Zeichen>“ — Text-Ähnlichkeit <XX> % (geprüft <ISO>)"
    #   (Titel seit P2-42 an der Wortgrenze gekürzt, mit „…“ — s. ingest._titel_kurz; ältere
    #   Vermerke (Phase 44 bis 08.09.2026) schließen den Titel mit ASCII-Quote, der Parser in ui.tsx darf sich
    #   deshalb NICHT am schließenden Anführungszeichen festhalten.)
    # NIE automatisch verworfen/geparkt (Human-in-the-Loop) — der Job wird trotzdem angelegt,
    # der Anhang ist nur ein Hinweis fürs Review. Frontend parst das Schlüsselwort → amber
    # Badge „Dublette? → Job <id>" (Muster identisch zur KONFLIKT-Anzeige oben).
    verify_note: Optional[str] = None
    posting_snapshot_path: Optional[str] = None  # Snapshot der Stellenausschreibung (Phase 18), data/job_postings/…
    # Phase 32 B — Soft-Delete-Tombstone (ISO-Timestamp). Die Row bleibt bewusst erhalten (Muster
    # Phase 28 A): dedup_key/URL/Firma+Titel wirken weiter gegen Wieder-Ingest desselben Treffers.
    deleted_at: Optional[str] = None
    dedup_key: str = Field(index=True)
    raw_json: Optional[str] = None           # original tracker row, preserved
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class JobLog(UtcZeit, SQLModel, table=True):
    """Chronologisches Notizen-/Änderungs-Log je Job (Phase 24 A). Analog zu OutreachLog:
    PATCH-Feldänderungen (next_step/follow_up_date/notes/status/salary/url) schreiben
    automatisch EINEN Eintrag je PATCH (art='auto'), der Nutzer kann zusätzlich frei notieren
    (art='manuell')."""
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    eintrag: str
    art: Optional[str] = Field(default="manuell")   # auto (aus Feldänderungen) / manuell / ki-chat
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Application(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    applied_date: Optional[str] = None
    channel: Optional[str] = None            # E-Mail / Portal / Recruiter
    cv_version_id: Optional[int] = Field(default=None, foreign_key="cvversion.id")
    cover_letter_path: Optional[str] = None
    cover_letter_pdf_path: Optional[str] = None    # PDF-Export des Anschreibens (pipeline.cv_export cover)
    cover_letter_language: Optional[str] = None     # DE/EN — fürs Namens-Suffix + Anzeige
    cover_letter_text: Optional[str] = None   # Klartext-Fließtext (Phase 48) — Quelle fürs Inline-Textfenster + Word/PDF-Rendering
    status: Optional[str] = None
    last_status_change: Optional[datetime] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None   # Absagegrund (aus Absage-Mail extrahiert oder manuell; gepflegt von absagen-analyse)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Email(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    gmail_thread_id: Optional[str] = Field(default=None, index=True)
    gmail_message_id: Optional[str] = Field(default=None, index=True)
    direction: Optional[str] = None          # incoming / outgoing
    from_addr: Optional[str] = None
    to_addr: Optional[str] = None
    subject: Optional[str] = None
    snippet: Optional[str] = None
    received_at: Optional[datetime] = None
    is_response: bool = Field(default=False)
    response_time_hours: Optional[float] = None
    category: Optional[str] = None           # Eingangsbestätigung/Einladung/Absage/Rückfrage/Angebot/Sonstige
    needs_reply: bool = Field(default=False)
    reply_draft_at: Optional[str] = None     # ISO-Zeitpunkt: Antwort-Entwurf liegt in Gmail (Phase 27) —
                                              # NICHT "beantwortet"; needs_reply bleibt ehrlich True bis Versand
    # P2-52 — Tombstone gegen Neu-Import (NICHT Review-/Gelesen-Status, Phase 36 hatte "kein neues
    # Flag-Feld" entschieden; bewusste Revision auf Wunsch, s. main.py::inbox()): gesetzt,
    # wenn der Nutzer eine Mail OHNE Stelle in der App ausblendet. Gmail bleibt unberuehrt. Wert wie
    # deleted_at (datetime.utcnow().isoformat()). Invariante: archived_at gesetzt ⇒ job_id und
    # application_id sind leer (main.py::archive_email/assign_email haelt das ein).
    archived_at: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Contact(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    name: Optional[str] = None
    role: Optional[str] = None               # Recruiter / Hiring Manager / ...
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CVVersion(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None, foreign_key="job.id", index=True)
    language: Optional[str] = None           # DE / EN
    kind: Optional[str] = None               # base / tailored
    file_path: Optional[str] = None          # die angepasste .docx
    pdf_path: Optional[str] = None           # PDF-Export der .docx (pipeline.cv_export)
    ats_score: Optional[int] = None
    match_score100: Optional[int] = None     # CV-Match-Score 0-100 aus cv-job-match (Dokument vs. Anzeige)
    match_dashboard_path: Optional[str] = None  # Match-Dashboard HTML
    ats_scan_path: Optional[str] = None      # ATS-Scan HTML
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Phase 46 Stufe B — Editier-Checkpoint: cv-match legt "entwurf" an (Match-Dashboard fertig,
    # aber KEIN PDF/ATS), cv-erstellen macht daraus "fertig" (Umbenennen+PDF+ATS, s. Design-
    # Entscheidung 3). Default "fertig" (SQL-DEFAULT in db.py::_ADD_COLUMNS) — Altbestand vor
    # dieser Phase durchlief immer den kompletten Ein-Klick-Flow, gilt also rückwirkend als fertig.
    status: Optional[str] = Field(default="fertig")   # entwurf | fertig
    entwurf_text: Optional[str] = None       # JSON [{i, style, text}], nur bei status=entwurf gefüllt
    # Keyword-Protokoll Methodik v2, Phase 55 — geschrieben von cv-match, gelesen von cv-erstellen.
    keywords_json: Optional[str] = None


class Outreach(UtcZeit, SQLModel, table=True):
    """Networking-/Outreach-Tracker — gespiegelt aus 2026_Job_Search_Tracker_Max_Mustermann.xlsx
    (Google Drive). 'Tage seit Kontakt' wird NICHT gespeichert (Formel im Excel/berechnet)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    datum: Optional[str] = None               # Datum des Kontakts (ISO)
    kontakt: Optional[str] = None             # Name
    unternehmen: Optional[str] = None
    typ: Optional[str] = None                 # Inner Circle / Warmer Kontakt / Headhunter / ...
    kanal: Optional[str] = None               # LinkedIn / E-Mail / Telefon / ...
    template: Optional[str] = None
    antwort: Optional[str] = None             # Ja / Nein
    antwort_datum: Optional[str] = None
    next_step: Optional[str] = None
    next_action_datum: Optional[str] = None
    status: Optional[str] = None              # Initiated / Responded / In Dialogue / ...
    # Phase 69 — ISO-Datum: Bewerbung über diesen Netzwerk-Kontakt (Gesamtprozess-KPI
    # "Bewerbungen gesamt", Netzwerk-Split, s. app/gesamtprozess.py). Pflege-Regel (KEINE
    # Automatik): NUR setzen, wenn zur selben Bewerbung KEINE Application-Row existiert — sonst
    # zählt dieselbe Bewerbung doppelt (einmal hier, einmal als Application). Im Zweifel gewinnt
    # die Application-Row.
    bewerbung_datum: Optional[str] = None
    notizen: Optional[str] = None
    position: Optional[str] = None
    dedup_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OutreachLog(UtcZeit, SQLModel, table=True):
    """Chronologisches Aktivitäten-Log je Outreach-Kontakt. Rein app-seitig —
    bewusst NICHT Teil des Excel-Round-Trips (der nur das Outreach-Blatt füllt)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    outreach_id: int = Field(foreign_key="outreach.id", index=True)
    eintrag: str
    art: Optional[str] = Field(default="manuell")   # auto (aus Feldänderungen) / manuell
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TargetCompany(UtcZeit, SQLModel, table=True):
    """Blatt 'Target Companies' aus dem Google-Drive-Tracker (kuratierte Zielfirmen-Liste)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    company: Optional[str] = Field(default=None, index=True)
    industry: Optional[str] = None
    size_ma: Optional[str] = None
    revenue: Optional[str] = None
    location_hq: Optional[str] = None
    ownership: Optional[str] = None
    tier: Optional[str] = None
    scenario: Optional[str] = None
    key_contact: Optional[str] = None
    connection_status: Optional[str] = None
    last_update: Optional[str] = None
    website: Optional[str] = None
    wachstumssignal: Optional[str] = None
    ki_readiness: Optional[str] = None
    einschaetzung: Optional[str] = None
    ranking: Optional[str] = None
    karriere_url: Optional[str] = None       # Phase 26 B — gecachter Karriere-/Jobs-Link
    last_career_check: Optional[str] = None  # Phase 26 B — Rotation: NULL zuerst, dann aufsteigend
    deleted_at: Optional[str] = None         # Phase 28 A — Soft-Delete-Tombstone, ISO-Timestamp
    dedup_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Headhunter(UtcZeit, SQLModel, table=True):
    """Blatt 'Headhunters' aus dem Google-Drive-Tracker."""
    id: Optional[int] = Field(default=None, primary_key=True)
    firma: Optional[str] = None
    ansprechpartner: Optional[str] = None
    fokus: Optional[str] = None
    region: Optional[str] = None
    kanal: Optional[str] = None
    linkedin_gefolgt: Optional[str] = None
    letzter_kontakt: Optional[str] = None
    status: Optional[str] = None
    notizen: Optional[str] = None
    webseite: Optional[str] = None           # Phase 26 A
    karriere_url: Optional[str] = None       # Phase 26 B — gecachter Karriere-/Jobs-Link
    last_career_check: Optional[str] = None  # Phase 26 B — Rotation: NULL zuerst, dann aufsteigend
    deleted_at: Optional[str] = None         # Phase 28 A — Soft-Delete-Tombstone, ISO-Timestamp
    dedup_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class NetworkContact(UtcZeit, SQLModel, table=True):
    """Blatt 'Network Contacts' aus dem Google-Drive-Tracker."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    beziehung: Optional[str] = None
    unternehmen: Optional[str] = None
    rolle: Optional[str] = None
    letzter_kontakt: Optional[str] = None
    kanal: Optional[str] = None
    prioritaet: Optional[str] = None
    notizen: Optional[str] = None
    next_action: Optional[str] = None        # nächste geplante Aktion (Freitext, Phase 22)
    next_action_date: Optional[str] = None   # ISO-Datum YYYY-MM-DD, wird überwacht (Phase 22)
    deleted_at: Optional[str] = None         # Phase 28 A — Soft-Delete-Tombstone, ISO-Timestamp
    dedup_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentTask(UtcZeit, SQLModel, table=True):
    """Ein headless Agent-Lauf, aus der Web-App gestartet (Phase 8).

    Der Runner spawnt `claude -p "<Trigger-Satz>"` im Projekt-Root; der Lauf nutzt die
    BESTEHENDEN Skills und schreibt wie bisher über pipeline-Module/API in DB + data/.

    ARCHITEKTUR-REGEL (Phase 42, 18.07.2026, s. tasks/lessons.md): AgentTask ist DAS EINE
    Aktivitäts-Log des Systems — nicht nur für den Runner. Jede neue Hintergrund-Aktivität,
    egal ob Runner-Prozess oder In-Server-Engine (Vorbild: `backend/beirat_engine.py`), pflegt
    ihre eigene Row selbst (queued/running → done/failed/cancelled, mit Log/Dauer/Kosten/
    Ergebnis). Keine Parallel-Buchführung, die am Task-Center vorbeiläuft.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)                 # firma-pruefen | cv-match | cv-erstellen | …
    job_id: Optional[int] = Field(default=None, foreign_key="job.id", index=True)
    params_json: Optional[str] = None             # zusätzliche Parameter (JSON)
    # Ketten ("Rezepte"): deterministisch verkettete Tasks, kein Orchestrator-Agent.
    chain_id: Optional[str] = Field(default=None, index=True)   # gemeinsame ID aller Schritte
    chain_label: Optional[str] = None                            # z. B. "Bewerbungspaket"
    chain_pos: Optional[int] = None                              # 1-basierter Schritt
    depends_on: Optional[int] = Field(default=None, foreign_key="agenttask.id")
    prompt: Optional[str] = None                  # tatsächlich gesendeter Trigger-Satz
    status: str = Field(default="queued", index=True)  # queued/running/done/failed/cancelled
    # Phase 63B (P1-3): BEZEICHNER für die Log-Datei, seither KEIN direkt verwendbarer Pfad
    # mehr — nie selbst zu einem Pfad zusammenbauen, immer über `agent_runner.resolve_log_path()`
    # auflösen (Docstring dort für die volle Begründung/D3). Zeilen von vor der Migration
    # tragen noch den wörtlichen alten Pfad "data/agent_logs/task_<id>.jsonl" (unverändert,
    # D3 — keine DB-Migration); neue Zeilen tragen nur noch den Basename "task_<id>.jsonl".
    log_path: Optional[str] = None
    result_json: Optional[str] = None             # letztes result-Event des Laufs
    error: Optional[str] = None
    exit_code: Optional[int] = None
    duration_s: Optional[float] = None
    num_turns: Optional[int] = None
    cost_usd: Optional[float] = None
    tokens: Optional[int] = None                  # P2-86: neu verbrauchte Token eines ChatGPT-Laufs (Codex meldet kein USD)
    # Wiederholungen (Phase 8.4). Nur für idempotente Task-Arten, s. PROMPTS[...]["retryable"].
    retry_count: int = Field(default=0)
    # Phase 65 (P1-6): PID des laufenden Subprozesses — NUR gültig, solange status="running".
    # Gesetzt direkt nach dem Spawn, geleert bei jedem Abschluss (done/failed/cancelled) und vor
    # jedem Retry-Requeue. KEIN dauerhafter Ausweis: nach einem Server-Neustart MUSS jede
    # Verwendung dieses Werts erst über agent_runner._ist_unser_prozess() bestätigt werden, bevor
    # irgendetwas mit ihm passiert (insbesondere: bevor er beendet wird) — die Nummer kann
    # inzwischen einem fremden Programm gehören (PID-Wiederverwendung).
    pid: Optional[int] = None
    # ACHTUNG: naives UTC (utcnow), NICHT lokale Zeit. Tagesgrenzen daher über
    # agent_runner._tagesbeginn_utc() rechnen, nie über date.today().
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobChat(UtcZeit, SQLModel, table=True):
    """KI-Chat am Job-Detail (Phase 28 D) — Frage/Antwort-Verlauf je Job, chronologisch. Fragen
    laufen über den bestehenden Agent-Runner (kind=job-frage, Sonnet/high, keine Web-Tools,
    s. agent_runner.PROMPTS): user-Rows entstehen synchron am POST, die ki-Row schreibt der
    Skill selbst (Python-Einzeiler, Muster gespraech-debrief) inkl. Verweis auf den beantwortenden
    AgentTask (task_id) — für die Kosten-/Modell-Fußnote in der UI."""
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    rolle: str                                     # "user" | "ki"
    text: str
    task_id: Optional[int] = Field(default=None, foreign_key="agenttask.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Run(UtcZeit, SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_type: Optional[str] = None           # jobsearch / email_check / tageslauf
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    portals: Optional[str] = None
    jobs_found: int = Field(default=0)
    jobs_new: int = Field(default=0)
    emails_checked: int = Field(default=0)
    responses_found: int = Field(default=0)
    summary: Optional[str] = None


class Interview(UtcZeit, SQLModel, table=True):
    """Ein Gespräch/Call zu einer Stelle (HR-Screen, Fachgespräch, …). Mehrere pro Job möglich."""
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id")
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    runde: int = Field(default=1)             # 1. Gespräch, 2. Gespräch, …
    art: Optional[str] = None                 # HR-Screen / Fachgespräch / Hiring Manager / Panel / Final / Sonstiges
    scheduled_at: Optional[str] = None        # ISO "YYYY-MM-DDTHH:MM" (Input type=datetime-local)
    interviewer: Optional[str] = None         # Freitext: "Anna Meier (Head of CS), Ben Roth (CTO)"
    status: Optional[str] = Field(default="Geplant")  # Geplant / Absolviert / Abgesagt
    prep_path: Optional[str] = None           # Briefing-HTML (Stufe B), projekt-root-relativ
    hedy_topic_id: Optional[str] = None       # für spätere Hedy-Anbindung, bleibt vorerst leer
    hedy_session_id: Optional[str] = None
    notes: Optional[str] = None
    # Phase 69 — Gesamtprozess-KPI "Gespräche gesamt" (s. app/gesamtprozess.py). `gegenueber`:
    # Recruiter / Hiring Manager / Fachbereich / Headhunter / Sonstige; NULL = ungepflegt
    # (deterministischer Backfill aus `art` lief einmalig, s. tasks/spec_phase69_...md
    # Entscheidung 3 — HR-Screen -> Recruiter, "Hiring Manager" in art -> Hiring Manager, sonst
    # NULL). `vor_ort`: persönlich getroffen statt Call/Video — Querschnitt für die
    # "davon vor Ort"-Zeile im Dashboard.
    gegenueber: Optional[str] = None
    vor_ort: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Netzwerk-Gespräche ohne Stelle (Phase 69) ──────────────────────────────────────────
class NetzwerkGespraech(UtcZeit, SQLModel, table=True):
    """Gespräch/Call OHNE zugehörige Stelle — Pendant zu `Interview`, das zwingend `job_id`
    verlangt. Schließt eine der drei Datenlücken aus Phase 69 (Gesamtprozess-KPIs): Netzwerk-
    Calls und Headhunter-Gespräche (z. B. ein Gespräch mit einem Headhunter) ohne Ausschreibung zählten bislang
    NIRGENDS als Gespräch. Gleiche `gegenueber`-Werteliste wie `Interview`, hier zusätzlich
    der Wert "Netzwerk" erlaubt (reiner Netzwerk-Kontakt statt Recruiter/HM/Headhunter).

    KEIN Soft-Delete (bewusste Entscheidung 3 der Spec): ein geführtes Gespräch ist ein Fakt,
    kein Entwurf. Löschen läuft — falls nötig — hart über das bestehende Bestätigungs-UI-Muster.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    datum: str                                # ISO-Datum, Pflicht
    person: Optional[str] = None
    unternehmen: Optional[str] = None
    gegenueber: Optional[str] = None          # Recruiter/Hiring Manager/Fachbereich/Headhunter/Sonstige/Netzwerk
    vor_ort: bool = Field(default=False)
    outreach_id: Optional[int] = Field(default=None, foreign_key="outreach.id")
    headhunter_id: Optional[int] = Field(default=None, foreign_key="headhunter.id")
    notiz: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Transcript(UtcZeit, SQLModel, table=True):
    """Gesprächs-Transkript/-Mitschrift. Mehrere pro Job/Interview möglich (Quelle egal: Teams, Zoom, Notizen, später Hedy)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    interview_id: Optional[int] = Field(default=None, foreign_key="interview.id", index=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id")
    source: Optional[str] = Field(default="manuell")  # manuell / hedy
    title: Optional[str] = None               # z. B. "1. Gespräch — HR-Screen"
    file_path: Optional[str] = None           # data/transcripts/…, projekt-root-relativ
    summary: Optional[str] = None             # Kurz-Zusammenfassung (Skill oder Hand)
    todos_json: Optional[str] = None          # JSON-Array offener Punkte/To-dos
    recorded_at: Optional[str] = None         # ISO-Datum des Gesprächs "YYYY-MM-DD"
    language: Optional[str] = None            # DE / EN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Phase 11 (additiv über _ADD_COLUMNS)
    kontakt: Optional[str] = None             # Gesprächspartner
    gespraechsart: Optional[str] = None       # Telefonat / Video-Call / Vor-Ort-Gespräch
    debrief_path: Optional[str] = None        # data/transcripts/…html — Auswertung des Gesprächs (Altbestand)
    # Phase 30 (additiv über _ADD_COLUMNS): EIN vollwertiger Report je Transkript (Headline →
    # Findings → Original-Text). Ersetzt debrief_path für NEUE Transkripte; debrief_path bleibt nur
    # für den Altbestand stehen (Migration folgt in Phase 31).
    report_path: Optional[str] = None         # data/transcripts/…html — Transkript-Report (Basis/Vollversion)


# ── Dateien am Job (Phase 11) ─────────────────────────────────────────────────────────
class JobFile(UtcZeit, SQLModel, table=True):
    """Eine an eine Stelle angehängte Datei (Transkript, Stellenbeschreibung, Präsentation, …).

    EINE generische Tabelle für alle Dateien. Ein Upload mit kind="Transkript" erzeugt ZUSÄTZLICH
    eine verknüpfte `Transcript`-Row auf dieselbe Datei — so bleiben Debrief-Skill, Briefings und
    die bestehende UI kompatibel, ohne dass es zwei Wahrheiten gibt.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    transcript_id: Optional[int] = Field(default=None, foreign_key="transcript.id")
    kind: str = Field(default="Sonstiges")    # Transkript / Stellenbeschreibung / Präsentation / Sonstiges
    filename: str                             # Original-Dateiname (Anzeige)
    file_path: str                            # data/job_files/job_<id>/…, projekt-root-relativ
    mime: Optional[str] = None
    size_bytes: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Profil (Phase 45) ─────────────────────────────────────────────────────────────────
# Kandidaten-Substanz für Matching/Anschreiben — bewusst getrennt von `config/profil.md`
# (das besitzt die SUCH-STRATEGIE: Zielrolle, harte Grenzen, Empirie aus absagen-analyse).
# Keine Richtung überschreibt die andere automatisch; die abgeleitete, skill-lesbare Sicht
# `config/profil_struktur.md` wird bei jedem Save deterministisch neu erzeugt (Stufe D).
class Profile(UtcZeit, SQLModel, table=True):
    """Singleton (id=1), lazy angelegt beim ersten GET /api/profil."""
    id: Optional[int] = Field(default=None, primary_key=True)
    linkedin_url: Optional[str] = None
    headline: Optional[str] = None
    standort: Optional[str] = None
    positionierung: Optional[str] = None            # Prosa-Block
    linkedin_eingelesen_am: Optional[str] = None     # ISO — letzter erfolgreicher Import (ZIP oder URL)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProfileSkill(UtcZeit, SQLModel, table=True):
    """Ein Skill-Chip, nach `bereich` gruppiert (Freitext-Kategorie, z. B. 'Strategie & Führung').
    `quelle` unterscheidet manuell gepflegte von LinkedIn-importierten Skills — beide Wege sind
    additiv, keiner überschreibt den anderen (Design-Entscheidung 4, Phase 45)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    bereich: str = Field(index=True)
    name: str
    note: Optional[str] = None                       # z. B. "schwächer, ~40-50%"
    quelle: str = Field(default="manuell")            # manuell | linkedin
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CareerEntry(UtcZeit, SQLModel, table=True):
    """Werdegang — Rollen, Ausbildung, Zertifizierungen, Projekte in EINER Tabelle über `art`
    (Muster JobFile: eine generische Tabelle statt mehrerer Parallel-Modelle)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    art: str = Field(default="Beruf", index=True)     # Beruf | Ausbildung | Zertifizierung | Projekt | Sonstiges
    firma: Optional[str] = None
    rolle: Optional[str] = None
    ort: Optional[str] = None
    von: Optional[str] = None
    bis: Optional[str] = None
    beschreibung: Optional[str] = None
    referenzgeber: Optional[str] = None
    referenzdatum: Optional[str] = None
    notiz: Optional[str] = None
    quelle: str = Field(default="manuell")            # manuell | linkedin
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProfileFile(UtcZeit, SQLModel, table=True):
    """Zeugnisse/Zertifikat-Dateien am Profil (Muster JobFile — dessen `job_id` ist aber NOT
    NULL, deshalb eigene Tabelle statt Wiederverwendung)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(default="Sonstiges")            # Zeugnis | Zertifikat | Sonstiges
    filename: str                                     # Original-Dateiname (Anzeige)
    file_path: str                                    # data/profil/dateien/…, projekt-root-relativ
    mime: Optional[str] = None
    size_bytes: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Budget (Phase 10) ─────────────────────────────────────────────────────────────────
class ApiCost(UtcZeit, SQLModel, table=True):
    """Ein Kosten-Eintrag pro Dienst und Tag (sync/metered) — Basis des Budget-Reports.

    `date` ist der LOKALE Verbrauchstag (YYYY-MM-DD), nicht UTC: der Nutzer denkt in lokalen Tagen,
    und die Tages-Guardrails aus Phase 8.4 rechnen ebenso (s. agent_runner._tagesbeginn_utc).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)          # apify / claude / hedy / … (perplexity nur Altbestand, P2-78)
    date: str = Field(index=True)              # ISO "YYYY-MM-DD" (Verbrauchstag, lokal)
    cost_usd: float = Field(default=0.0)
    calls: Optional[int] = None                # Requests/Runs an dem Tag (falls bekannt)
    quantity_note: Optional[str] = None        # z. B. "12.4k in / 3.1k out Tokens" oder Actor-Name
    source: str = Field(default="metered")     # sync / metered / fix
    detail_json: Optional[str] = None          # Roh-Aufschlüsselung (JSON)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetLimit(UtcZeit, SQLModel, table=True):
    """Editierbares Budget-Limit je Verbrauchs-Dienst — die STEUERUNG des Budget-Moduls.

    Limits leben bewusst in der DB, nicht in YAML: die App muss sie per PATCH ändern können.
    Fixkosten (Abos) stehen dagegen in `config/budgets.yaml` und werden nie blockiert.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True, unique=True)
    label: Optional[str] = None                # Anzeigename, z. B. "Apify (Job-Scraper)"
    daily_limit_usd: Optional[float] = None    # None = kein Tageslimit
    monthly_limit_usd: Optional[float] = None  # None = kein Monatslimit
    enforcement: str = Field(default="hart")   # hart = blockieren / weich = nur warnen
    active: bool = Field(default=True)         # False = Dienst pausiert (jeder Aufruf blockiert)
    max_runs_per_day: Optional[int] = None     # nur provider="claude" relevant (Phase 54)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Sucheinstellungen (Phase 49) ────────────────────────────────────────────────────────
class SuchEinstellung(UtcZeit, SQLModel, table=True):
    """Singleton (id=1): grundsätzliche Jobsuche-Parameter, editierbar über /einstellungen.

    Config lebt bewusst in der DB (Muster BudgetLimit), nicht in YAML: die App muss sie per
    PATCH ändern können. `config/suchprofile.yaml` wird bei jedem Save daraus regeneriert
    (Muster Profile → `_profil_struktur_schreiben`, s. `pipeline/suchprofil.py`).
    """
    id: Optional[int] = Field(default=None, primary_key=True)          # immer 1
    min_mitarbeiter: int = Field(default=100)                          # globale Firmengröße
    suchbereich_json: str = Field(default="{}")                        # globaler Suchbereich (Remote/Deutschlandweit/Umkreis)
    plaene_json: str = Field(default="[]")                             # Liste der 3 Pläne A/B/C
    # Phase 50 (Aliase seit P2-51 in agent_runner.MODELLE, s. dort) — Dict {funktion: Alias}
    # über die 6 Kern-Funktionen (Jobsuche, Company Fit, Beirat, CV Match, ATS Scan,
    # Anschreiben); fehlende Funktion ⇒ Default agent_runner.MODELL_STANDARD.
    modelle_json: str = Field(default="{}")
    ki_anbieter: str = Field(default="claude")                         # P2-86: claude | chatgpt (app/ki_anbieter.py)
    # Phase 87 — Liste der Suchportale (Name/URL/Zugriffsart/aktiv), editierbar über
    # /einstellungen. Leerer Default: der erste GET seedet aus suchprofil.PORTALE_DEFAULT.
    portale_json: str = Field(default="[]")
    # P2-41 — Standardumfang des Bewerbungspakets (Dict {Baustein: bool}, aktuell nur
    # "anschreiben"), editierbar über /einstellungen (Karte „Bewerbungspaket — Standardumfang“).
    # KEIN Such-Parameter: fließt NICHT in config/suchprofile.yaml ein (Muster modelle_json).
    unterlagen_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AlertMail(UtcZeit, SQLModel, table=True):
    """Verarbeitungs-Protokoll für Job-Alert-Mails — garantiert Einmal-Verarbeitung (Phase 13)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    gmail_message_id: str = Field(index=True, unique=True)
    sender: Optional[str] = None
    subject: Optional[str] = None
    received_at: Optional[str] = None         # ISO
    postings_found: Optional[int] = None      # nach Verarbeitung gesetzt
    processed_at: Optional[datetime] = None   # None = eingesammelt, aber noch nicht verarbeitet
    created_at: datetime = Field(default_factory=datetime.utcnow)
