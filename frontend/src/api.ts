const BASE = '/api'

/** Fehler einer API-Antwort — trägt den Klartext aus FastAPIs `detail` und den Status. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T = any>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!r.ok) {
    // Ohne das hier verpufft jede sorgfältige Server-Meldung ("Tagesbudget erreicht …")
    // und der Nutzer sieht nur "409 Conflict".
    let detail = ''
    try { detail = (await r.json())?.detail || '' } catch { /* kein JSON-Body */ }
    throw new ApiError(r.status, detail || `${r.status} ${r.statusText}`)
  }
  return r.json() as Promise<T>
}

/** P2-67 — Multipart-Upload per POST. Bewusst NICHT über `api()`: Das setzt den JSON-Kopf, den
 *  multipart nicht verträgt. Liefert Antwort und gelesenen JSON-Body (leer, wenn keiner da ist),
 *  die Fehlerbehandlung der Status bleibt beim Aufrufer. */
export async function apiUpload(url: string, fd: FormData): Promise<{ res: Response; body: any }> {
  const res = await fetch(url, { method: 'POST', body: fd })
  const body = await res.json().catch(() => ({}))
  return { res, body }
}

// ── shared types ──────────────────────────────────────────────
export interface JobRow {
  id: number
  company_name: string | null
  title: string
  seniority: string | null
  location: string | null
  work_model: string | null
  tab: string | null
  plan_ab: string | null
  portal: string | null
  url: string | null
  match_score: number | null
  status: string | null
  next_step: string | null
  found_date: string | null
  salary: string | null
  follow_up_date: string | null
  /** Phase 74 — Beworben-Check (wöchentliche Verfügbarkeitsprüfung). */
  availability_status?: 'offen' | 'karriereseite_offen' | 'offline' | 'unklar' | null
  availability_checked_at?: string | null
  /** P2-42 — liefert /api/jobs schon lange mit; die Liste liest daraus die Etiketten
   *  „Dublette?“ und „Neuausschreibung“ (Parser in components/ui.tsx). */
  verify_note?: string | null
}

export interface AgentTaskRow {
  id: number
  kind: string
  label: string
  chain_id: string | null
  chain_label: string | null
  chain_pos: number | null
  depends_on: number | null
  job_id: number | null
  /** Firma/Titel der verknüpften Stelle statt der internen Job-Id (Task-Center-Anzeige). */
  company_name: string | null
  job_title: string | null
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  prompt: string | null
  error: string | null
  exit_code: number | null
  duration_s: number | null
  num_turns: number | null
  cost_usd: number | null
  /** P2-86 — neue Token des Laufs (Eingabe ohne Cache plus Ausgabe). Nur ChatGPT meldet sie; unter
   *  Claude leer oder 0, dort zählt `cost_usd`. */
  tokens?: number | null
  retry_count: number
  /** 0 = diese Task-Art wird nie wiederholt (nicht idempotent). */
  max_retries: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  log_path: string | null
  result: string | null
  log?: string[]
}

// ── Profil-Datei (GET/PUT /api/profil/identitaet, P2-69; Vertrag A der Bau-Spec) ──────────
// Die Karte „Identität und Suchstrategie“ liest und schreibt config/profil.md. `stand` ist der
// SHA-256 des Dateiinhalts (leer, wenn die Datei fehlt) und geht beim Speichern unverändert
// zurück; passt er nicht mehr, antwortet der Server mit 409.
/** Eine Feldzeile `- **Schlüssel:** Wert`; der Schlüssel ist fest, nur der Wert wird bearbeitet. */
export interface ProfilFeld {
  schluessel: string
  wert: string
}

export interface ProfilIdentitaet {
  name: string
  positionierung: string
  anschrift: string
  email: string
  telefon: string
  linkedin: string
  aktuell: string
  weitere: ProfilFeld[]
}

/** Der bearbeitbare Teil — zugleich der PUT-Body (zusammen mit `stand`). */
export interface ProfilIdentitaetInhalt {
  identitaet: ProfilIdentitaet
  kurzprofil: string
  zielrolle: ProfilFeld[]
  rahmenbedingungen: string
  skill_gaps: string
}

export interface ProfilIdentitaetBody extends ProfilIdentitaetInhalt {
  stand: string
}

export interface ProfilIdentitaetAntwort extends ProfilIdentitaetInhalt {
  vorhanden: boolean
  stand: string
  /** Überschriften der Abschnitte, die die Karte nicht anfasst (z. B. Empirie). */
  unveraendert: string[]
  /** Nicht blockierende Hinweise in Klartext (Sie-Form, vom Server formuliert). */
  hinweise: string[]
  /** Nur nach dem Speichern: Pfad der Sicherungskopie der alten Datei, sonst null/fehlt. */
  papierkorb?: string | null
}

// ── Budget (Phase 10) ─────────────────────────────────────────
export interface BudgetLimitBlock {
  daily_limit_usd: number | null
  monthly_limit_usd: number | null
  enforcement: 'hart' | 'weich'
  active: boolean
  heute_prozent: number | null
  monat_prozent: number | null
  status: 'ok' | 'warn' | 'over' | 'pausiert'
  rest_heute_usd: number | null
  rest_monat_usd: number | null
  /** Phase 54 — nur provider="claude-runs" relevant. */
  max_runs_per_day: number | null
}

export interface BudgetProvider {
  provider: string
  label: string
  /** 'verbrauch' = pay-per-call (steuerbar) · 'abo' = Fixkosten (nie blockiert) */
  art: 'verbrauch' | 'abo'
  hinweis?: string | null
  heute_usd: number; monat_usd: number; jahr_usd?: number
  jahr_prognose_usd: number; geschaetzt: boolean
  heute_eur: number; monat_eur: number; jahr_prognose_eur: number
  calls_monat?: number | null
  /** Phase 54 — nur provider="claude-runs" relevant (Task-Anzahl heute). */
  runs_heute?: number | null
  limit: BudgetLimitBlock | null
}

export interface BudgetReport {
  providers: BudgetProvider[]
  totals: {
    heute_usd: number; monat_usd: number; jahr_prognose_usd: number
    heute_eur: number; monat_eur: number; jahr_prognose_eur: number
    fix_monat_usd: number; fix_monat_eur: number
  }
  letzter_sync: string | null
  usd_eur_rate: number
}

/** Guardrail-Stand des Agent-Runners (GET /api/agent-status). */
export interface AgentStatus {
  spent_today: number
  daily_budget: number
  tasks_today: number
  max_tasks: number
  per_run_budget: number | null
  max_parallel: number
  day_start_utc: string
  /** Phase 54 — Budget-Steuerung greift jetzt aus der DB (BudgetLimit, provider=claude-runs). */
  enforcement: 'hart' | 'weich'
  active: boolean
  /** Text bei weicher Überschreitung (Lauf durfte trotzdem starten), sonst null. */
  warnung: string | null
}

export interface FollowUp {
  id: number
  company_name: string | null
  title: string
  status: string | null
  match_score: number | null
  next_step: string | null
  notes: string | null
  follow_up_date: string
  overdue: boolean
}

// ── Sucheinstellungen (Phase 49) ──────────────────────────────
export interface Plan {
  plan: 'A' | 'B' | 'C'
  label: string
  aktiv: boolean
  prioritaet: number
  titel: string[]
  senioritaet: string[]
  branche: string[]
}

// Phase 87 — Suchportale (Name/URL/Zugriffsart/aktiv), editierbar über /einstellungen. `zugriff`
// steuert, wie der jobsuche-Skill das Portal nutzt: "websearch" sucht per WebSearch mit
// Domain-Anker (Bot-Schutz), "fetch" ruft die URL mit ersetzten Platzhaltern direkt ab.
export interface Portal {
  key: string
  name: string
  url: string
  zugriff: 'websearch' | 'fetch'
  aktiv: boolean
  /** true = eines der sechs vorbelegten Standard-Portale, false = die zwei Freizeilen. */
  standard: boolean
}

// Phase 90 — Beiratsbesetzung: Die sieben `.claude/agents/beirat-*.md`-Dateien bleiben die
// einzige Quelle der Wahrheit (Farbe/Vorsitz stehen im Frontmatter, nicht in der DB).
// `beschreibung` bleibt die auf 300 Zeichen gekürzte Fassung für die Live-Ansicht,
// `perspektive` ist die volle `description` aus dem Frontmatter — Basis für PATCH und
// „Neu besetzen" in den Einstellungen.
export interface BeiratMitglied {
  id: string
  anzeige: string
  beschreibung: string
  perspektive: string
  farbe: string
  model: string
  vorsitz: boolean
}

export interface Einstellungen {
  min_mitarbeiter: number
  suchbereich: {
    remote: { aktiv: boolean }
    deutschlandweit: { aktiv: boolean }
    umkreis: { aktiv: boolean; stadt: string; umkreis_km: number }
  }
  plaene: Plan[]
  modelle: Record<string, string>
  portale: Portal[]
  // P2-41 — Standardumfang Bewerbungspaket: welche optionalen Bausteine vorbelegt sind.
  unterlagen: { anschreiben: boolean }
  // P2-51 — Umkreis-Bezeichnung fürs Frontend (V7, null ohne gepflegte Stadt) und die
  // Modellwahl-Optionen; Anzeigenamen der Modell-Aliase werden nur noch vom Backend gepflegt
  // (agent_runner.py::MODELLE), die frühere feste Liste hier entfällt damit.
  umkreis_label: string | null
  modell_optionen: { alias: string; label: string }[]
  modell_standard: string
  // P2-86 — welche KI die Läufe ausführt. `modell_optionen` gehört zum gewählten Anbieter und
  // ändert sich mit ihm (gespeichert bleiben die Stufen opus, sonnet, haiku).
  ki_anbieter: KiAnbieter
  ki_anbieter_optionen: { wert: KiAnbieter; label: string }[]
}

// P2-86 — GET /api/ki-status: je Anbieter, ob das Programm da ist und ob die Anmeldung steht.
// `angemeldet: null` heißt „nicht bekannt“ (Programm fehlt oder keine Antwort), nicht „nein“.
export type KiAnbieter = 'claude' | 'chatgpt'
export interface KiAnbieterStatus {
  label: string
  installiert: boolean
  angemeldet: boolean | null
}
export type KiStatus = Record<KiAnbieter, KiAnbieterStatus>

// P2-51 — nur in der PATCH-Antwort von /api/einstellungen, nur wenn der Umkreis (Stadt/Radius)
// beim Speichern umbenannt wurde; das Backend stellt dabei alle betroffenen Stellen/Firmen in
// derselben Transaktion um (V6 in der Bau-Spec).
export interface Umkreisumbenennung {
  von: string
  nach: string
  jobs: number
  firmen: number
}

// P2-51 — Programmversion (GET /api/version, s. backend/app/version.py). `installation`
// unterscheidet eine Paket-Installation beim Kunden (Manifest vorhanden) von einer
// Git-Arbeitskopie; `entwicklungsstand` ist nur bei "git" gesetzt.
export interface VersionLetztesUpdate {
  zeitpunkt: string
  von: string | null
  nach: string
}

export interface VersionInfo {
  version: string | null
  freigabe: boolean
  commit: string | null
  datum: string | null
  installation: 'paket' | 'git' | 'unbekannt'
  entwicklungsstand: string | null
  betriebssystem: 'mac' | 'windows' | 'linux'
  installationsordner: string
  letztes_update: VersionLetztesUpdate | null
  aenderungen: string | null
}

// P2-82 — Update-Auskunft (GET /api/version/neueste, s. backend/app/update_pruefen.py). Die Antwort
// ist immer 200; `installiert` kommt aus GET /api/version (dort kann die Version fehlen), alle
// übrigen Felder sind null, wenn die Abfrage bei GitHub scheiterte (dann steht der Grund als
// Kundentext in `fehler`). `aenderungen` ist reiner Text (höchstens 4000 Zeichen, „- “-Zeilen),
// `seite` nur eine Adresse im eigenen Repository.
export interface NeuesteVersion {
  installiert: string | null
  neueste: string | null
  neuer: boolean | null
  /** ISO-Datum (JJJJ-MM-TT) der Veröffentlichung. */
  veroeffentlicht: string | null
  seite: string | null
  aenderungen: string | null
  fehler: string | null
}

// P2-59 — Dokumentationsseite (GET /api/doku, s. backend/app/doku.py). Die Liste enthält nur
// Dokumente, deren Datei in dieser Installation vorhanden ist: `intern` erscheint damit nur in
// der Entwicklungsinstallation, weil das Kundenpaket diese Dateien nicht enthält. Die Seite
// selbst liefert GET /api/doku/<id> als fertiges HTML.
export interface DokuEintrag {
  id: string
  titel: string
  gruppe: 'kunde' | 'intern'
}

// P2-52 — Datensicherung (GET/PATCH /api/sicherung, s. backend/app/sicherung.py, Vertrag V4).
// `letzte` ist die neueste Datei der eigenen automatischen Reihe (`null` ohne eine bisher),
// `weitere` zählt nur Alt-Sicherungen direkt in data/backups (die die App nie anfasst).
export interface SicherungDatei {
  datei: string
  zeitpunkt: string
  groesse: number
}

export interface SicherungFehler {
  zeitpunkt: string
  meldung: string
}

export interface SicherungStatus {
  aktiv: boolean
  taeglich: number
  woechentlich: number
  monatlich: number
  ordner: string
  letzte: SicherungDatei | null
  anzahl: number
  gesamtgroesse: number
  weitere: { anzahl: number; gesamtgroesse: number }
  laeuft: boolean
  letzter_fehler: SicherungFehler | null
  warnung: string | null
}

// Phase 69 (Stufe B) — Gesamtprozess seit Beginn, additiver Dashboard-Block (app/gesamtprozess.py).
// `rows` nur bei "keine_reaktion" befüllt (Payload der anderen drei KPIs klein halten).
export interface GesamtprozessRow {
  id: number
  label: string | null
  kanal: string
  tage: number | null
}
export interface GesamtprozessKPI {
  wert: number
  splits: Record<string, number>
}
export interface GesamtprozessKeineReaktion extends GesamtprozessKPI {
  rows: GesamtprozessRow[]
}

// Phase 70 (Stufe A/B) — Funnel-Block unter gesamtprozess.funnel (app/gesamtprozess.py::funnel_kpi).
// EINE Quelle für /api/dashboard UND den Excel-Export (pipeline/export_excel.py::_funnel_sheet) --
// kein Drift, s. Spec-Fallstrick.
export interface GesamtprozessFunnelStufe {
  stufe: string
  anzahl: number
  vs_vorstufe: number | null
  vs_start: number | null
  kommentar: string
}
export interface GesamtprozessFunnelGroessterVerlust {
  stufe: string
  prozent: number
  text: string
}
export interface GesamtprozessFunnelEngstellen {
  screening: number | null
  bewerbungsquote: number | null
  antwortquote: number | null
  interview_konversion: number | null
  ende_zu_ende: number | null
  groesster_verlust: GesamtprozessFunnelGroessterVerlust | null
}
export interface GesamtprozessFunnel {
  stufen: GesamtprozessFunnelStufe[]
  engstellen: GesamtprozessFunnelEngstellen
}

export interface Dashboard {
  totals: {
    jobs: number
    companies: number
    radar_companies: number
    applications: number
    active_applications: number
    /** Phase 74 — Beworbene Stellen (Beworben/Interview) mit availability_status="offline". */
    applied_offline: number
    emails: number
    responses: number
    avg_response_hours: number | null
    response_rate: number | null
    top_matches: number
    followups_overdue: number
    followups_open: number
    netzwerk_overdue: number
    netzwerk_open: number
  }
  by_status: Record<string, number>
  by_score: Record<string, number>
  by_portal: Record<string, number>
  by_tab: Record<string, number>
  by_situation: Record<string, number>
  by_situation_plan: Record<'A' | 'B' | 'C' | 'ohne', Record<string, number>>
  funnel: Record<string, number>
  gesamtprozess: {
    bewerbungen: GesamtprozessKPI
    gespraeche: GesamtprozessKPI
    absagen: GesamtprozessKPI
    keine_reaktion: GesamtprozessKeineReaktion
    funnel: GesamtprozessFunnel
  }
}

// P2-62: Netzwerk-Listen per Datei importieren (app/netzwerk_import.py, Vertrag V2 und V3).
// Vorschau und Import liefern dieselben Zähler, damit die Oberfläche nach dem Schreiben dieselbe
// Zahlenzeile zeigen kann wie davor.
export type NetzwerkImportListe = 'zielfirmen' | 'headhunter' | 'kontakte'
export type NetzwerkImportAktion = 'neu' | 'ergaenzt' | 'unveraendert' | 'geloescht' | 'fehler'

export interface NetzwerkImportAnzahl {
  zeilen: number
  neu: number
  ergaenzt: number
  unveraendert: number
  /** In der App gelöscht: wird übersprungen und nicht wieder angelegt. */
  geloescht: number
  fehler: number
}

export interface NetzwerkImportZeile {
  /** Zeilennummer in der Datei, die Kopfzeile mitgezählt. */
  nr: number
  aktion: NetzwerkImportAktion
  anzeige: string
  /** Modellfelder, die bei „ergaenzt“ einen Wert bekommen. */
  felder_ergaenzt: string[]
  meldung: string | null
}

export interface NetzwerkImportVorschau {
  liste: NetzwerkImportListe
  format: 'csv' | 'xlsx' | 'linkedin'
  /** Name des gelesenen Excel-Blatts, sonst null. */
  blatt: string | null
  spalten: {
    erkannt: { spalte: string; feld: string; label: string }[]
    ignoriert: string[]
  }
  anzahl: NetzwerkImportAnzahl
  /** Alle Fehler- und Gelöscht-Zeilen plus die ersten 100 übrigen, in Dateireihenfolge. */
  zeilen: NetzwerkImportZeile[]
  zeilen_gekuerzt: boolean
  hinweise: string[]
}

export interface NetzwerkImportErgebnis {
  anzahl: NetzwerkImportAnzahl
  /** Dateiname der Sicherung vor dem Schreiben, null wenn nichts zu schreiben war. */
  sicherung: string | null
}
