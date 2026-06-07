# FORGE_INIT — Projekt-Start Checkliste

> Jedes neue Projekt beginnt hier. Abgearbeitet = durchgestrichen.

---

## Erste Schritte — Checkliste

- [ ] **Ziel definieren** — Ein Satz: Was soll dieses Projekt tun?
- [ ] **Namenskonvention prüfen** → FunktionFunktion, kein Projektname, kein "und" im Zweck-Satz
- [ ] **Modul-Registry prüfen** — Brauche ich ein Modul das schon existiert?
- [ ] **Spec schreiben** — Neue Spec in `specs/<modulname>.spec.md`
- [ ] **Index aktualisieren** — Eintrag in `modules.index.md`
- [x] **Repo anlegen** — `git init`, `.gitignore`, Remote: https://github.com/RoyBretfeld/argus-rag-rh-it.git
- [ ] **README schreiben** — Zweck, Setup, Nutzung
- [ ] **Status-Datei anlegen** — `[PROJEKT]_STATUS.md` nach SessionUpdater-Schema
- [ ] **Packer einrichten** — `DUMP_FULL` + `DUMP_LIGHT` nach `_rb_dumps/`
- [ ] **Erste Session** — Claude Code öffnen, Spec + Kontext reinwerfen, bauen

---

## Pflicht-Standards

| Standard | Beschreibung |
|----------|--------------|
| **Registry-Pflicht** | Vor jedem neuen Modul: Registry prüfen. Name = FunktionFunktion. Kein Projektname. Zweck ohne "und". |
| **Status-Datei** | Jedes Projekt hat genau eine `[PROJEKT]_STATUS.md` — die einzige Statusdatei die zählt. |
| **Packer** | Jedes Projekt baut `DUMP_FULL` + `DUMP_LIGHT`. Beide nach `_rb_dumps/`. |
| **Logging** | Structlog JSON, rotierend, audit-tauglich. |
| **Test-Status** | Unit-Test + Integrationstest vor "Stabil"-Status. |

---

## Projekt-Typen

| Typ | Beispiel | Besonderheit |
|-----|----------|--------------|
| **Agent** | AssistantFramework, CoreSystem | Soul.md, Session-Memory, Tool-Registry |
| **Service** | RoutingSystem-Router, CRM | API, mTLS, Docker |
| **Tool** | Packer, Sentinels | CLI, konfigurierbar, wiederverwendbar |
| **UI** | Atlas, WebStatusDashboard | Streamlit / FastAPI + Jinja2, Dark Theme |

---

## Nach dem ersten PoC

- [ ] Spec-Status auf `PoC` setzen
- [ ] Tests schreiben
- [ ] README aktualisieren
- [ ] `modules.index.md` Status auf `Implementiert`
- [ ] DUMP_FULL + DUMP_LIGHT bauen

---

*Letzte Änderung: 2026-05-16 — Namenskonvention v2.0 eingeführt*

