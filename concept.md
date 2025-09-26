Hier ist dein Konzept – **unverändert in Struktur & Inhalt**, aber mit dem Bibliotheksnamen **`lib_layered_config`** durchgängig aktualisiert.

---

# IDEE

Wir wollen eine konfigurierbare Schichtbibliothek für Anwendungen entwickeln.

* Sie soll Konfigurationsdateien aus mehreren Ebenen (System, Host, User) zusammenführen.
* Die Zusammenführung erfolgt key-weise, spätere Ebenen überschreiben frühere.
* Unterstützte Formate: TOML (Standard), JSON, optional YAML.
* `.env`-Dateien und Prozess-Umgebungsvariablen sind integrierte Ebenen.
* Jede Einstellung soll nachvollziehen können, aus welcher Ebene/Datei sie stammt (Provenienz).
* Die Bibliothek soll reines Python (Stdlib) im Kern einsetzen und sowohl auf Linux, macOS als auch Windows laufen.
* Entwickler:innen sollen Beispielkonfigurationen generieren können.
* Die API muss typed/immutabel sein und eine klare Fehlerhierarchie besitzen.

Strukturiere diesen Fragenkatalog und ergänze sinnvolle Aspekte.

---

## A) Ziele & Scope

1. **Primärziele**

* [ ] Deterministische Zusammenführung aus den Ebenen `app → host → user → dotenv → env`.
* [ ] Unterstützung der Formate TOML/JSON (Core) plus optional YAML.
* [ ] Immutable Value Objects inkl. Provenienz je Key.
* [ ] Saubere Clean-Architecture-Schichten (Domain, Application, Adapter, Composition Root).
* [ ] Kontext-ID für Logging (Traceability) ohne Logging im Domain-/Application-Layer.
* [ ] Beispieldateien pro Ebene generieren (`config.toml`, `.env.example`).

2. **Nichtziele**

* Keine Validierung komplexer Schemas (optional via Plugins später).
* Keine Framework-spezifischen Integrationen (reine Library).

## B) Architektur & Organisation

1. **Domain Layer**
   - `Config` VO (immutable, Mapping, `get`, `as_dict`, `to_json`, `origin`, `with_overrides`).
   - Fehlerhierarchie `ConfigError`, `InvalidFormat`, `ValidationError`, `NotFound`.

2. **Application Layer**
   - Ports (Protocols) für `PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`.
   - Merge-Use-Case (`merge_layers`) mit Provenienztracking.

3. **Adapters**
   - Pfadresolver pro OS (Linux XDG, macOS, Windows) mit Test-Overrides via ENV.
   - File-Loader für TOML/JSON/YAML (optional) mit Fehlerlogging.
   - Dotenv-Parser (Upward search, `__`-Nesting) und Env-Loader samt Typkonversion.
   - Structured Logging via `observability` (NullHandler, Trace-ID, Debug/Info/Error Events).

4. **Composition Root**
   - `read_config`, `read_config_raw` orchestrieren alle Adapter und liefern `Config`/rohe Daten.
   - Optionaler `prefer`-Parameter, Startverzeichnis für `.env`-Suche.

## C) Tests & Qualität

* Unit-Tests für Domain (`Config`), Adapter (File/DotEnv/Env), Merge-Logik.
* Property-basierte Tests (Hypothesis) für Merge-Associativity und „last layer wins“.
* E2E-Test (`tests/e2e/test_read_config.py`) mit echten Dateien & ENV-Overrides.
* Doctests (README, ggf. Modul-Docstrings) für `Config.get`, `default_env_prefix` etc.
* Import-Linter-Contracts sichern Schichtentrennung.
* Coverage ≥90% (`pyproject.toml`).

## D) Toolchain & Automation

* `pyproject.toml` mit Python ≥3.12, dev extras (pytest, pytest-asyncio, ruff, pyright, bandit, pip-audit, hypothesis, coverage, mypy).
* `Makefile`-Targets: `test`, `build`, `run`, `push`, `bump`, `clean`.
* CI (`.github/workflows/ci.yml`): Matrix 3.12/3.13, Ruff, import-linter, Pyright, pytest (coverage), build, pipx/uv install, Conda/Nix packaging, Notebook execution.
* Release Workflow: Build + Upload via Twine (`release.yml`).

## E) Beispiele & Docs

* README: Präzedenz-Tabelle, OS-Pfade, API-Exportliste, doctest-Beispiele.
* Notebook `notebooks/Quickstart.ipynb`: Demonstriert Prefix, Example Generation, `read_config` mit temp Dateien.
* Beispielgenerator (`examples.generate`) erzeugt `app/config.toml`, `hosts/<hostname>.toml`, `user/config.toml`, `.env.example`.

## F) Follow-up / Backlog

* CLI (`configctl`) zum Anzeigen der effektiven Config.
* Validierung via externen Validatoren (Pydantic, JSON Schema) als optionale Adapter.
* Watches für File-Änderungen (dev only).

