# Spiteware Releases Arbeitsregeln

Vor Änderungen [Projekt README](readme.md) und die betroffenen eigenen Fachdocs lesen.
Die Dokumentation ist bei jeder Projektänderung im selben Arbeitsgang mitzupflegen.
Buildbefehle, Pfade, Konfiguration, Funktionen, offene Fehler und Quellenstand
müssen zu den geänderten Quellen passen. Implementierung, Plan und datierte
Prüfnachweise trennen; ein Build belegt keinen Runtime-/Hardware-/Live-Erfolg.
Veraltete Ist-Aussagen ersetzen, lokale Links prüfen und historische Testbelege
nicht rückwirkend verändern. Keine Secrets dokumentieren.

## Test-Workflow (lokales Testen ohne Veröffentlichung)

Dieser Ablauf heißt seit 25.10.2026 **Test-Workflow** und ist der Standard für
Gameplay-Tests neuer Cheat-Builds. Produkt-READMEs sollen ihn unter diesem
Namen referenzieren.

Der Debug-Loader `SpitewareLoader_Debug.exe` (Quelle: `cs2/loader`, Debug-Build
mit `DEBUG_LOCAL`) lädt keine Mods vom Server und macht kein Self-Update; er
startet die lokalen EXEs aus `mods/` neben sich selbst. Damit können lokal
gebaute Cheats im Spiel getestet werden, ohne dieses Repo zu committen oder zu
pushen. Veröffentlicht wird erst mit Commit/Push dieses Repos über den
Workflow `release-on-main.yml`; solange nur getestet wird, wird nicht
committet.

Ablauf für einen Spieltest neuer Cheat-Builds:

1. Produkt-Repos bauen und die Quellexen unter `kernel-*/build/Spiteware/`
   prüfen (nur verifizierte Compilergebnisse übernehmen).
2. Vor dem Tausch SHA256 der vorhandenen `mods/*.exe` notieren und
   Sicherungskopien anlegen (z. B. unter Temp).
3. Nur die flachen `mods/cs2_kernel_*.exe` ersetzen. Root-EXEs,
   `mods/<Display Name>/`-Konfigurationen (`default.cfg`, `Data/`) und
   `cs2_kernel_obsidian.exe` bleiben unangetastet, bis der Test besteht.
4. `SpitewareLoader_Debug.exe` aus dem `cs2/builds`-Root starten (der Loader
   resolved `mods/` relativ zu sich selbst), einloggen, lokalen Mod starten.
5. Nach dem Test Sicherung/Hashstand dokumentieren; Root-Artefakte ersetzt der
   offizielle Refresh (`refresh_builds.bat`, Preview; Apply nur mit geprüftem
   `--approved-manifest`), wenn wirklich ein Release vorbereitet wird.

Seit 26.10.2026 sind der Debug-Loader und der gesamte `mods/`-Ordner
**ungetrackt** (siehe `.gitignore`): Die Dateien bleiben lokal für den Test da,
erscheinen aber nicht mehr im Git-Status. Ein Spieltest kann deshalb parallel
zu einem Release laufen, ohne die Publishbarkeit zu blockieren. Der
Debug-Loader wird außerdem nicht mehr veröffentlicht (vier Root-Artefakte);
fehlt er lokal, baut er sich frisch aus `cs2/loader/build/debug/`.

Bekannte Grenze: Der Debug-Loader in diesem Ordner kann ein älterer Build als
die reparierten Quellen in `cs2/loader` sein. Bei Problemen dient der frische
Debug-Build aus `cs2/loader/build/debug/` als Ersatz – dann aber als bewusster
Root-Tausch behandeln und Hashes notieren.

Im gemeinsamen clar1ty-Bestand gelten zusätzlich [zentrale Arbeitsregeln](../../AGENTS.md),
[Projektkarte](../../PROJECTS.md) und [Doc-Index](../../docs/README.md).
Bei eigenständigem Checkout bleibt die lokale Pflegepflicht bestehen.
Subagents nur GPT-6.1 Sol mit Extra High, maximal 11 gleichzeitig.
