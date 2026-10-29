"""P2-63 (Paket U): Umbenennungs-Werkzeug `pipeline.namen_umstellen`.

Alles unter `tmp_path` mit EIGENER DB und EIGENEM Projekt-Root (`projekt_root`/`daten_dir` als
Parameter) — nie die globale Test-DB, nie echte Daten. App-Module nur in Funktionen (conftest-Regel).
Erwartete Zielnamen werden mit den Helfern aus `app.naming` gebildet (Vertrag N: Datum JJJJMMTT,
Typ-Wörter Anzeige/Auswertung/Beirat) — dieselbe Quelle wie im Werkzeug, aber die Regeln des
Vertrags (Datumsformat, Typ-Wort) prüfen die Tests zusätzlich wörtlich.
Firmen und Personen sind erfunden.
"""
import datetime
import hashlib
import json
import sqlite3
import urllib.parse
from pathlib import Path

import pytest

FIRMA = "Beispielwerk GmbH"
TITEL = "Head of Platform Delivery (m/w/d)"
KONTAKT = "Anna Meier"


# ── Hilfen ───────────────────────────────────────────────────────────────────────────────
def _schreibe(root: Path, rel: str, inhalt="x") -> Path:
    p = (root / rel) if not rel.startswith("data/") else (root / rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(inhalt, bytes):
        p.write_bytes(inhalt)
    else:
        p.write_text(inhalt, encoding="utf-8")
    return p


def _snap(root: Path, ohne=("data/backups", "data/bewerbung.sqlite")) -> dict:
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            if any(rel.startswith(o) for o in ohne):
                continue
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _dbdump(daten: Path) -> str:
    con = sqlite3.connect(daten / "bewerbung.sqlite")
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def _welt(tmp_path: Path) -> dict:
    """Synthetische Welt: ein Feld je Typ, gekoppelte Paare, Beirat, Transkript-Upload,
    Ausnahme-Ordner. Rückgabe: Pfade und Ids."""
    from sqlmodel import Session, SQLModel, create_engine
    from app import models as m

    root = tmp_path / "projekt"
    daten = root / "data"
    daten.mkdir(parents=True)
    eng = create_engine(f"sqlite:///{daten / 'bewerbung.sqlite'}")
    SQLModel.metadata.create_all(eng)

    dateien = {
        "fit": "data/company_fit/2026_07_09_CompanyFit_Beispielwerk_GmbH.html",
        "anzeige": "data/job_postings/Stellenausschreibung_2026_08_29_Beispielwerk_Head.html",
        "cl_docx": "outputs/anschreiben/CoverLetter_Alt_Beispielwerk_Head_DE.docx",
        "cl_pdf": "outputs/anschreiben/CoverLetter_Alt_Beispielwerk_Head_DE.pdf",
        "cv_docx": "outputs/cv/CV_Alt_Beispielwerk_Head_EN.docx",
        "cv_pdf": "outputs/cv/CV_Alt_Beispielwerk_Head_EN.pdf",
        "match": "data/company_fit/2026_07_10_Match_Beispielwerk_Head.html",
        "ats": "data/company_fit/2026_07_10_ATSscan_Beispielwerk_Head.html",
        "prep": "data/interview_prep/2026_07_09_Briefing_Job1_R2_Beispielwerk.html",
        "t_md": "data/transcripts/Transkript_2026_07_09_Anna_Beispielwerk_Head_R2.md",
        "t_report": "data/transcripts/2026_07_09_TranskriptReport_Beispielwerk_Head_R2.html",
        "t_debrief": "data/transcripts/Debrief_2026_07_09_Job1_T1.html",
        "t_upload": "data/job_files/job_1/Transkript_2026_07_11_Ben_Beispielwerk_Head.txt",
        "beirat": "data/beirat/2026_08_01_BeiratsCheck_Beispielwerk_Head.html",
        "beirat_roh": "data/beirat/2026_08_01_BeiratsCheck_Beispielwerk_Head_rohdaten.json",
        "debatte": "data/beirat/debatte_20260801_abc.json",
        "upload": "data/job_files/job_1/2026_07_09_Zeugnis.pdf",
        "profil": "data/profil/dateien/2026_06_01_Zertifikat.pdf",
        "export": "data/exports/2026_07_09_Tracker.xlsx",
        "digest": "data/digests/2026_09_01_Digest.html",
        "analyse": "data/analysen/2026_09_01_Absagen_Analyse.html",
        "pk": "data/papierkorb/2026_07_09_alt_Beispielwerk.html",
        "backup": "data/backups/2026_07_09_sicherung.zip",
        "tmp": "data/tmp/CV_Entwurf_2026_07_09.docx",
        "cv_basis": "data/cv_basis/CV_Basis_2026_07_09_DE.docx",
        "entwurf": "outputs/cv_entwuerfe/2026_07_09_Entwurf.docx",
        "geloescht": "data/job_files/_geloescht/2026_07_09_alt.pdf",
        "persona": "data/beirat/personas_backup/2026_07_09_persona.html",
    }
    for k, rel in dateien.items():
        _schreibe(root, rel, f"inhalt-{k}")
    # Debatten-JSON zeigt auf die Beirat-HTML; Analyse und Digest verlinken auf alte Pfade.
    _schreibe(root, dateien["debatte"],
              json.dumps({"id": "20260801_abc", "dashboard_pfad": dateien["beirat"]}))
    _schreibe(root, dateien["persona"], f'<a href="{dateien["fit"]}">p</a>')   # darf nicht angefasst werden
    fit_q = urllib.parse.quote(dateien["fit"], safe="")
    _schreibe(root, dateien["analyse"],
              f'<a href="{dateien["fit"]}">a</a> <a href="/api/artifact?path={fit_q}">b</a> '
              f'<a href="/api/artifact?path={urllib.parse.quote(dateien["anzeige"], safe="/")}">c</a> '
              f'<a href="data/company_fit/unbekannt.html">d</a>')
    _schreibe(root, dateien["digest"], f'<a href="{dateien["analyse"]}">x</a>')

    with Session(eng) as s:
        c = m.Company(name=FIRMA, fit_analysis_path=dateien["fit"])
        s.add(c); s.commit(); s.refresh(c)
        j = m.Job(company_id=c.id, company_name=FIRMA, title=TITEL, dedup_key="k1",
                  posting_snapshot_path=dateien["anzeige"])
        s.add(j); s.commit(); s.refresh(j)
        a = m.Application(job_id=j.id, cover_letter_path=dateien["cl_docx"],
                          cover_letter_pdf_path=dateien["cl_pdf"], cover_letter_language="DE")
        s.add(a)
        cv = m.CVVersion(job_id=j.id, language="EN", kind="tailored", file_path=dateien["cv_docx"],
                         pdf_path=dateien["cv_pdf"], match_dashboard_path=dateien["match"],
                         ats_scan_path=dateien["ats"])
        s.add(cv)
        iv = m.Interview(job_id=j.id, company_id=c.id, runde=2, prep_path=dateien["prep"])
        s.add(iv); s.commit(); s.refresh(iv)
        t1 = m.Transcript(job_id=j.id, interview_id=iv.id, file_path=dateien["t_md"],
                          report_path=dateien["t_report"], debrief_path=dateien["t_debrief"],
                          kontakt=KONTAKT, recorded_at="2026-07-09")
        t2 = m.Transcript(job_id=j.id, file_path=dateien["t_upload"], kontakt="Ben Roth",
                          recorded_at="2026-07-11")
        s.add(t1); s.add(t2); s.commit(); s.refresh(t2)
        jf_t = m.JobFile(job_id=j.id, transcript_id=t2.id, kind="Transkript",
                         filename="Transkript_2026_07_11_Ben_Beispielwerk_Head.txt",
                         file_path=dateien["t_upload"])
        jf_b = m.JobFile(job_id=j.id, kind="Beirats-Check",
                         filename="2026_08_01_BeiratsCheck_Beispielwerk_Head.html",
                         file_path=dateien["beirat"])
        jf_u = m.JobFile(job_id=j.id, kind="Sonstiges", filename="Zeugnis.pdf",
                         file_path=dateien["upload"])
        # Ausnahmen: DB zeigt in Papierkorb/tmp/cv_basis/Entwürfe — bleibt liegen
        jf_pk = m.JobFile(job_id=j.id, kind="Sonstiges", filename="alt.html", file_path=dateien["pk"])
        s.add(m.JobFile(job_id=j.id, kind="Sonstiges", filename="alt.pdf", file_path=dateien["geloescht"]))
        cv_b = m.CVVersion(job_id=None, language="DE", kind="base", file_path=dateien["cv_basis"])
        cv_e = m.CVVersion(job_id=j.id, language="DE", kind="entwurf", file_path=dateien["entwurf"],
                           pdf_path=dateien["tmp"])
        pf = m.ProfileFile(kind="Zertifikat", filename="Zertifikat.pdf", file_path=dateien["profil"])
        for x in (jf_t, jf_b, jf_u, jf_pk, cv_b, cv_e, pf):
            s.add(x)
        s.commit()
        ids = {"company": c.id, "job": j.id, "app": a.id, "cv": cv.id, "iv": iv.id,
               "t1": t1.id, "t2": t2.id, "jf_t": jf_t.id, "jf_b": jf_b.id, "jf_u": jf_u.id,
               "pf": pf.id, "jf_pk": jf_pk.id}
    eng.dispose()
    return {"root": root, "daten": daten, "d": dateien, "ids": ids}


def _zeile(daten: Path, sql: str, *args):
    con = sqlite3.connect(daten / "bewerbung.sqlite")
    try:
        return con.execute(sql, args).fetchone()
    finally:
        con.close()


def _erwartet(w: dict) -> dict:
    """Zielpfade nach Vertrag N, gebildet mit den naming-Helfern."""
    from app.naming import (cover_letter_filename, cv_filename, report_filename,
                            transcript_filename)
    d = datetime.date
    def r(typ, datum, runde=None, rolle=True):
        return report_filename(typ, FIRMA, TITEL if rolle else None, when=datum, runde=runde)
    cl = cover_letter_filename(FIRMA, TITEL, "DE")
    cv = cv_filename(FIRMA, TITEL, "EN")
    return {
        "fit": f"data/company_fit/{r('CompanyFit', d(2026, 7, 9), rolle=False)}.html",
        "anzeige": f"data/job_postings/{r('Anzeige', d(2026, 8, 29))}.html",
        "cl_docx": f"outputs/anschreiben/{cl}.docx", "cl_pdf": f"outputs/anschreiben/{cl}.pdf",
        "cv_docx": f"outputs/cv/{cv}.docx", "cv_pdf": f"outputs/cv/{cv}.pdf",
        "match": f"data/company_fit/{r('Match', d(2026, 7, 10))}.html",
        "ats": f"data/company_fit/{r('ATSscan', d(2026, 7, 10))}.html",
        "prep": f"data/interview_prep/{r('Briefing', d(2026, 7, 9), 2)}.html".replace(
            "20260709", "20260709"),
        "t_md": "data/transcripts/" + transcript_filename(
            "Transkript", "2026-07-09", KONTAKT, FIRMA, TITEL, runde=2) + ".md",
        "t_report": f"data/transcripts/{r('Auswertung', d(2026, 7, 9), 2)}.html",
        "t_debrief": f"data/transcripts/{r('Debrief', d(2026, 7, 9), 2)}.html",
        "t_upload": "data/job_files/job_1/" + transcript_filename(
            "Transkript", "2026-07-11", "Ben Roth", FIRMA, TITEL) + ".txt",
        "beirat": f"data/beirat/{r('Beirat', d(2026, 8, 1))}.html",
        "upload": "data/job_files/job_1/20260709_Zeugnis.pdf",
        "profil": "data/profil/dateien/20260601_Zertifikat.pdf",
        "export": "data/exports/20260709_Tracker.xlsx",
        "digest": "data/digests/20260901_Digest.html",
        "analyse": "data/analysen/20260901_Absagen_Analyse.html",
    }


def _lauf(w: dict, **kw):
    from pipeline import namen_umstellen as nu
    return nu.ausfuehren(w["root"], w["daten"], **kw)


# ── Vertrag-N-Regeln wörtlich (Datum, Typ-Wörter) ────────────────────────────────────────
def test_zielnamen_folgen_vertrag_n(tmp_path):
    w = _welt(tmp_path)
    e = _erwartet(w)
    name = Path(e["t_report"]).name
    assert name.startswith("20260709_Auswertung_"), name
    assert Path(e["anzeige"]).name.startswith("20260829_Anzeige_")
    assert Path(e["beirat"]).name.startswith("20260801_Beirat_")
    assert "_" not in Path(e["upload"]).name.split("_", 1)[0]      # Datum ohne Unterstriche


# ── Feldtypen, Paare, Kopplungen ─────────────────────────────────────────────────────────
def test_jeder_feldtyp_wird_umbenannt(tmp_path):
    w = _welt(tmp_path)
    e = _erwartet(w)
    r = _lauf(w)
    assert not r.get("fehler") and not r.get("abgebrochen"), r
    root, d = w["root"], w["d"]
    for k, neu in e.items():
        assert (root / neu).is_file(), f"{k}: {neu} fehlt"
        if neu != d[k]:
            assert not (root / d[k]).exists(), f"{k}: alte Datei {d[k]} liegt noch"
    ids, daten = w["ids"], w["daten"]
    assert _zeile(daten, "select fit_analysis_path from company")[0] == e["fit"]
    assert _zeile(daten, "select posting_snapshot_path from job")[0] == e["anzeige"]
    assert _zeile(daten, "select cover_letter_path, cover_letter_pdf_path from application") == (
        e["cl_docx"], e["cl_pdf"])
    assert _zeile(daten, "select file_path, pdf_path, match_dashboard_path, ats_scan_path "
                         "from cvversion where id=?", ids["cv"]) == (
        e["cv_docx"], e["cv_pdf"], e["match"], e["ats"])
    assert _zeile(daten, "select prep_path from interview")[0] == e["prep"]
    assert _zeile(daten, "select file_path, report_path, debrief_path from transcript where id=?",
                  ids["t1"]) == (e["t_md"], e["t_report"], e["t_debrief"])
    assert _zeile(daten, "select file_path from profilefile")[0] == e["profil"]
    # Anzeigename (Original) bleibt, Pfad zieht mit
    assert _zeile(daten, "select filename, file_path from jobfile where id=?", ids["jf_u"]) == (
        "Zeugnis.pdf", e["upload"])


def test_paare_teilen_den_stamm(tmp_path):
    w = _welt(tmp_path)
    _lauf(w)
    e = _erwartet(w)
    assert Path(e["cv_docx"]).stem == Path(e["cv_pdf"]).stem
    assert Path(e["cl_docx"]).stem == Path(e["cl_pdf"]).stem
    assert (w["root"] / e["cv_docx"]).is_file() and (w["root"] / e["cv_pdf"]).is_file()
    assert (w["root"] / e["cl_docx"]).is_file() and (w["root"] / e["cl_pdf"]).is_file()
    assert Path(e["cv_docx"]).name.startswith("CV_") and Path(e["cl_docx"]).name.startswith("CoverLetter_")


def test_beirat_kopplung(tmp_path):
    w = _welt(tmp_path)
    _lauf(w)
    e = _erwartet(w)
    root = w["root"]
    html = root / e["beirat"]
    roh = root / (e["beirat"][:-5] + "_rohdaten.json")
    assert html.is_file() and roh.is_file()
    assert not (root / w["d"]["beirat_roh"]).exists()
    assert _zeile(w["daten"], "select filename, file_path from jobfile where id=?",
                  w["ids"]["jf_b"]) == (Path(e["beirat"]).name, e["beirat"])
    assert json.loads((root / w["d"]["debatte"]).read_text())["dashboard_pfad"] == e["beirat"]
    assert (root / w["d"]["debatte"]).is_file()           # Name der Debatten-JSON bleibt


def test_transkript_upload_doppelzeile(tmp_path):
    w = _welt(tmp_path)
    _lauf(w)
    e = _erwartet(w)
    ids, daten = w["ids"], w["daten"]
    assert _zeile(daten, "select file_path from transcript where id=?", ids["t2"])[0] == e["t_upload"]
    assert _zeile(daten, "select file_path, filename from jobfile where id=?", ids["jf_t"]) == (
        e["t_upload"], Path(e["t_upload"]).name)
    assert (w["root"] / e["t_upload"]).is_file()
    assert not (w["root"] / w["d"]["t_upload"]).exists()


def test_html_links_werden_ersetzt(tmp_path):
    w = _welt(tmp_path)
    e = _erwartet(w)
    r = _lauf(w)
    text = (w["root"] / e["analyse"]).read_text()
    assert w["d"]["fit"] not in text and e["fit"] in text
    assert urllib.parse.quote(e["fit"], safe="") in text            # kodiert bleibt kodiert
    assert urllib.parse.quote(e["anzeige"], safe="/") in text
    assert "data/company_fit/unbekannt.html" in text                 # Unbekanntes bleibt
    assert e["analyse"] in (w["root"] / e["digest"]).read_text()
    assert r["links"]["ersetzungen"] >= 4 and r["links"]["dateien"] >= 2


def test_ausnahmen_bleiben_unberuehrt(tmp_path):
    w = _welt(tmp_path)
    vorher = {k: _snap(w["root"], ohne=()).get(w["d"][k]) for k in ("pk", "backup", "tmp", "cv_basis", "entwurf", "geloescht", "persona")}
    assert all(vorher.values())
    _lauf(w)
    nachher = _snap(w["root"], ohne=())
    for k in ("pk", "backup", "tmp", "cv_basis", "entwurf", "geloescht", "persona"):
        assert nachher.get(w["d"][k]) == vorher[k], f"{k} wurde angefasst"
    # DB-Verweis in den Papierkorb bleibt unverändert
    assert _zeile(w["daten"], "select file_path from jobfile where id=?", w["ids"]["jf_pk"])[0] == w["d"]["pk"]


def test_bereits_neuer_name_mit_nummer_bleibt_stehen(tmp_path):
    """Ein gültiger Name mit `_2` wird nicht auf den (freien) Grundnamen zurückgezogen."""
    w = _welt(tmp_path)
    neu = _erwartet(w)["anzeige"]
    stehen = neu[:-5] + "_2.html"
    (w["root"] / w["d"]["anzeige"]).rename(w["root"] / stehen)
    con = sqlite3.connect(w["daten"] / "bewerbung.sqlite")
    con.execute("update job set posting_snapshot_path=?", (stehen,))
    con.commit(); con.close()
    _lauf(w)
    assert (w["root"] / stehen).is_file() and not (w["root"] / neu).exists()
    assert _zeile(w["daten"], "select posting_snapshot_path from job")[0] == stehen


def test_fehlende_datei_laesst_db_unveraendert(tmp_path):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    (w["root"] / w["d"]["prep"]).unlink()
    b = nu.probe(w["root"], w["daten"])
    assert any(f["pfad"] == w["d"]["prep"] for f in b["fehlend"])
    _lauf(w)
    assert _zeile(w["daten"], "select prep_path from interview")[0] == w["d"]["prep"]


def test_kollisionen_bekommen_nummer(tmp_path):
    from sqlmodel import Session, create_engine
    from app import models as m
    w = _welt(tmp_path)
    # zweiter Job derselben Firma und Rolle mit eigener Anzeige gleichen Datums
    zweite = "data/job_postings/Stellenausschreibung_2026_08_29_Beispielwerk_Head_zweite.html"
    _schreibe(w["root"], zweite, "zweite")
    eng = create_engine(f"sqlite:///{w['daten'] / 'bewerbung.sqlite'}")
    with Session(eng) as s:
        s.add(m.Job(company_name=FIRMA, title=TITEL, dedup_key="k2", posting_snapshot_path=zweite))
        s.commit()
    eng.dispose()
    _lauf(w)
    e = _erwartet(w)["anzeige"]
    zweit = e[:-5] + "_2.html"
    assert (w["root"] / e).read_text() == "inhalt-anzeige"
    assert (w["root"] / zweit).read_text() == "zweite"


def test_idempotenz(tmp_path):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    assert _lauf(w)["geaendert"] > 0
    nach_eins = _snap(w["root"])
    db_eins = _dbdump(w["daten"])
    r2 = _lauf(w)
    assert r2["geaendert"] == 0 and not r2.get("fehler")
    b = nu.probe(w["root"], w["daten"])
    assert b["umbenennungen"] == [] and b["db_aenderungen"] == [] and b["links"]["ersetzungen"] == 0
    assert _snap(w["root"]) == nach_eins and _dbdump(w["daten"]) == db_eins


def test_idempotenz_mit_kollision(tmp_path):
    """Die Nummer `_2` bleibt im zweiten Lauf stehen (kein Zurückspringen auf den Grundnamen)."""
    from sqlmodel import Session, create_engine
    from app import models as m
    w = _welt(tmp_path)
    zweite = "data/job_postings/Stellenausschreibung_2026_08_29_Beispielwerk_Head_zweite.html"
    _schreibe(w["root"], zweite, "zweite")
    eng = create_engine(f"sqlite:///{w['daten'] / 'bewerbung.sqlite'}")
    with Session(eng) as s:
        s.add(m.Job(company_name=FIRMA, title=TITEL, dedup_key="k2", posting_snapshot_path=zweite))
        s.commit()
    eng.dispose()
    _lauf(w)
    eins = _snap(w["root"])
    assert _lauf(w)["geaendert"] == 0
    assert _snap(w["root"]) == eins


def test_probe_aendert_nichts(tmp_path):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    vorher = _snap(w["root"], ohne=())
    bericht = tmp_path / "bericht.json"
    b = nu.probe(w["root"], w["daten"], bericht=bericht)
    assert len(b["umbenennungen"]) >= 15 and b["links"]["ersetzungen"] >= 4
    assert b["summen_je_ordner"]["data/company_fit"] >= 3
    nachher = _snap(w["root"], ohne=())
    assert nachher == vorher                       # inkl. DB-Datei und ohne neue Dateien
    gelesen = json.loads(bericht.read_text())
    assert gelesen["umbenennungen"][0].keys() >= {"alt", "neu"}


def test_probe_oeffnet_db_nur_lesend(tmp_path, monkeypatch):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    urls = []
    echt = sqlite3.connect
    def spion(*a, **k):
        urls.append(str(a[0]))
        return echt(*a, **k)
    monkeypatch.setattr(nu.sqlite3, "connect", spion)
    nu.probe(w["root"], w["daten"])
    assert urls and all("mode=ro" in u for u in urls), urls


def test_fehler_mitten_im_lauf_rollt_alles_zurueck(tmp_path, monkeypatch):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    dateien_vorher = _snap(w["root"])
    db_vorher = _dbdump(w["daten"])
    echt = nu._umbenennen
    zaehler = {"n": 0}
    def kaputt(von, nach):
        zaehler["n"] += 1
        if zaehler["n"] == 6:
            raise OSError("Platte voll (Test)")
        return echt(von, nach)
    monkeypatch.setattr(nu, "_umbenennen", kaputt)
    r = _lauf(w)
    assert r.get("fehler") and zaehler["n"] == 6
    assert _snap(w["root"]) == dateien_vorher
    assert _dbdump(w["daten"]) == db_vorher


def test_fehler_im_db_schritt_rollt_dateien_und_db_zurueck(tmp_path, monkeypatch):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    dateien_vorher = _snap(w["root"])
    db_vorher = _dbdump(w["daten"])
    echt = nu._db_schreiben
    def halb(con, aenderungen):
        echt(con, aenderungen[: max(1, len(aenderungen) // 2)])
        raise RuntimeError("DB-Fehler (Test)")
    monkeypatch.setattr(nu, "_db_schreiben", halb)
    assert _lauf(w).get("fehler")
    assert _snap(w["root"]) == dateien_vorher
    assert _dbdump(w["daten"]) == db_vorher


def test_fehler_beim_links_ersetzen_rollt_zurueck(tmp_path, monkeypatch):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    dateien_vorher = _snap(w["root"])
    db_vorher = _dbdump(w["daten"])
    echt = nu._links
    def kaputt(root, daten, karte, schreiben=False, sichern=None):
        if schreiben:                    # nur das echte Ersetzen scheitert, nicht die Vorab-Zählung
            echt(root, daten, karte, schreiben=True, sichern=sichern)   # erst teilweise geschrieben
            raise ValueError("Link-Fehler (Test)")
        return echt(root, daten, karte, schreiben=schreiben, sichern=sichern)
    monkeypatch.setattr(nu, "_links", kaputt)
    r = _lauf(w)
    assert r.get("fehler")
    assert _snap(w["root"]) == dateien_vorher and _dbdump(w["daten"]) == db_vorher


def test_zurueck_stellt_ausgangszustand_her(tmp_path):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    dateien_vorher = _snap(w["root"])
    db_vorher = _dbdump(w["daten"])
    r = _lauf(w)
    assert _snap(w["root"]) != dateien_vorher
    z = nu.zurueck(r["protokoll"], w["root"], w["daten"])
    assert not z["warnungen"], z
    assert _snap(w["root"]) == dateien_vorher          # Dateien byte-identisch, Links inklusive
    assert _dbdump(w["daten"]) == db_vorher
    prot = json.loads(Path(r["protokoll"]).read_text())
    assert prot["status"] == "zurueckgenommen"


def test_ausfuehren_legt_sicherungen_und_protokoll_an(tmp_path):
    w = _welt(tmp_path)
    r = _lauf(w)
    import zipfile
    assert Path(r["db_sicherung"]).is_file()
    with zipfile.ZipFile(r["zip"]) as z:
        namen = set(z.namelist())
    assert w["d"]["fit"] in namen and w["d"]["cv_docx"] in namen and w["d"]["beirat"] in namen
    assert not any(n.startswith("data/papierkorb") for n in namen)
    prot = json.loads(Path(r["protokoll"]).read_text())
    assert prot["status"] == "fertig" and len(prot["umbenennungen"]) == r["geaendert"]


def test_offene_aufgabe_bricht_ab(tmp_path):
    from sqlmodel import Session, create_engine
    from app import models as m
    w = _welt(tmp_path)
    eng = create_engine(f"sqlite:///{w['daten'] / 'bewerbung.sqlite'}")
    with Session(eng) as s:
        s.add(m.AgentTask(kind="firma-pruefen", status="running"))
        s.commit()
    eng.dispose()
    vorher = _snap(w["root"], ohne=())
    db_vorher = _dbdump(w["daten"])
    r = _lauf(w)
    assert r["abgebrochen"] and "Aufgabe" in r["grund"]
    assert _snap(w["root"], ohne=()) == vorher and _dbdump(w["daten"]) == db_vorher


def test_cli_exitcodes(tmp_path, capsys):
    from pipeline import namen_umstellen as nu
    w = _welt(tmp_path)
    basis = ["--projekt-root", str(w["root"]), "--daten-dir", str(w["daten"])]
    assert nu.main(["--probe", *basis]) == 0
    assert "nichts geändert" in capsys.readouterr().out
    assert nu.main(["--ausfuehren", *basis]) == 0
    out = capsys.readouterr().out
    assert "Fertig:" in out
    assert nu.main(["--ausfuehren", *basis]) == 0
    assert "0 Änderungen" in capsys.readouterr().out
