# Chronik — Releases und Auslieferung

Datierte Release- und Automatisierungsnachweise. Neueste Einträge oben.
Der laufende Ablauf steht in [Release-Workflow](../../../docs/release-workflow.md)
und in [readme.md](../readme.md).

**Changelog-Veröffentlichung (`platform/spiteware/scripts/changelog.mjs`,
26.10.2026):** Aus dem Briefing formuliert die KI die beiden Kundentexte und
zeigt sie Michael; erst nach dessen Freigabe wird mit `--publish` veröffentlicht:
Upsert nach `changelog_entries` (kein Duplikat), IndexNow und Discord-Post
nach `#announcements` als Bot **Spiteware Manager** über die Discord-REST-API
(Bot-Token aus `platform/keyauth-bot/.env`, kein laufender Bot-Prozess nötig,
Kanal `1564104431543390218`). Der Discord-Post wird im Briefing notiert, ein
Wiederholungslauf postet nicht doppelt (`--force-discord` erzwingt es). Ohne
`--publish` ist der Lauf read-only und zeigt beide Texte. Textregeln: keine
Fachdetails, die nicht beeindrucken; der Website-Body wird ohne Markdown und
ohne Zeilenumbrüche gerendert. Erster Einsatz am 26.10.2026 für Pro 1.1.0
(beide Kanäle live). Verifizierte Live-Stände und der Ablauf stehen im
[Release-Workflow](../../../docs/release-workflow.md).

**Versions-Sync (26.10.2026):** KeyAuth (`cs2_kernel_*_version`) ist die
einzige Versionsquelle; Website und Loader lesen sie zur Laufzeit. Ein
eigener Schritt in `release.mjs` verifiziert die Kette bei jedem Publish
(Read-Back, `/api/config` mit Retry wegen 5-Minuten-Cache, Supabase-Override-
Abfrage) und zieht beide Fallback-Quellen automatisch nach: `src/config/
products.js` und `SpitewareLoader/src/mods/cs2_kernel_*.cpp`, alle drei
Produkte. Fallback-Dateien werden nur lokal committet, wenn ihr Repo vorher
sauber war, und nie gepusht (der Deploy bleibt ein freigegebener Schritt).
Erster Durchgang am 26.10.2026: alle Fallbacks von `2.1.0`/`1.4.0`/`1.0.0`
auf die KeyAuth-Werte `1.1.0`/`1.0.0.2`/`1.0.0.0` angleichen (Loader lokal
gecommittet `cf4db45`, `products.js` bewusst uncommittet wegen fremder
Arbeit in diesem Repo), der letzte Version-Override (Obsidian) geleert; danach
war die gesamte Kette live verifiziert synchron. Ein im Preflight-Block
enthaltener read-only Fallback-Abgleich zeigt die Drift bereits im
Trockenlauf.

**Release-Automation (26.10.2026 implementiert):**
`platform/spiteware/scripts/release.mjs` führt einen Produkt-Release in einem
Befehl aus: Preflight, Binary-Staging (`--artifact` nimmt das getestete EXE),
Reproduzierbarkeitsprüfung gegen den Comittstand, Hosttests und
Launcher-Regression, Tree-Prep von `cs2/builds` (nur übrige Root-Artefakte aus
einem abgebrochenen Lauf werden wiederhergestellt; andere trackte Änderungen
sind ein Blocker, der zum Committen auffordert, statt sie still zu revertern),
Refresh-Review gegen einen Snapshot (fremde Artefakte müssen unverändert
bleiben, sonst Blocker), Publish ausschließlich über `artifacts.py`, Warten auf
das GitHub-Release inklusive SHA256-Verifikation des Assets, KeyAuth-Version
per neuer Seller-API-Methoden `addVariable`/`editVariable` in
`server/_utils/keyauth-class.js` mit Read-Back-Verifikation, Aufräumen des
Supabase-Overrides `product_overrides.version` und am Ende ein
Changelog-Briefing (Commits seit der Binary-Change-Baseline). Ohne
`--publish` nur Trockenlauf (Exit 2 bei Blockern).

**Erster Release: Pro 1.1.0 (26.10.2026):** Mit `release.mjs --publish`
veröffentlicht und vollständig nachgewiesen: `build-80`, getestetes Binary
`2DF51BF6A09DC2B4827C134BBA683ADAE3E7F1E76E5026C704FAEF4715FA571B` (identisch
mit der `mods/`-Kopie aus dem bestandenen Spieltest), KeyAuth
`cs2_kernel_pro_version = 1.1.0` per Read-Back verifiziert, Supabase-Override
`product_overrides.version` geleert, das ausgelieferte GitHub-Asset per SHA256
gegen das freigegebene Binary geprüft; `loader_version` (1.0.0.5), ESP und
Obsidian blieben unverändert. Vorbereitend wurde der Artefakt-Satz von fünf auf
vier reduziert (`cs2/builds` `b2206e7`, gepusst): Der Debug-Loader wird nicht
mehr veröffentlicht, `mods/` ist ungetrackt, sodass ein während des Laufs
laufender Spieltest den Publish nicht blockierte (`build-79` ist das
zugehörige Struktur-Release mit unveränderten Binaries). Danach behoben und
noch nicht durch einen zweiten Release geprüft: Changelog-Baseline über die
Binary-Change-Kette statt des letzten Releases, SHA256-Verifikation des Assets
vor dem KeyAuth-Update.
