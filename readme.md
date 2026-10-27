# SpitewareBuilds

Release artifact store for [spiteware-project/SpitewareBuilds](https://github.com/spiteware-project/SpitewareBuilds). This repository contains copies of executables compiled in the sibling source projects. The loader receives their download URLs through the website's KeyAuth integration.

**Reviewed: 09.10.2026.** Public release URLs were reachable, but the three kernel copies did not match the local September build outputs. A successful release job does not establish a successful source build or game launch. No refresh, publication, setup script, or executable was run during the release audit.

## Artifacts and sources

| Root artifact | Source relative to `cs2/` |
|---|---|
| `SpitewareLoader.exe` | `loader/build/release/SpitewareLoader.exe` |
| `cs2_kernel_pro.exe` | `kernel-pro/build/Spiteware/cs2_kernel_pro.exe` |
| `cs2_kernel_esp.exe` | `kernel-esp/build/Spiteware/cs2_kernel_esp.exe` |
| `cs2_kernel_obsidian.exe` | `kernel-obsidian/build/Spiteware/cs2_kernel_obsidian.exe` |

There are **four root artifacts**. Changed 26.10.2026: the debug loader is no
longer part of the release set. It is a local test tool (`DEBUG_LOCAL`, no
server downloads, no self-update) that no KeyAuth link ever referenced; an
untracked copy may remain in the repository root for the local
[test workflow](AGENTS.md), and a fresh one is built from
`cs2/loader/build/debug/` when needed.

Changed the same day: everything under `mods/` is untracked local game-test
state (flat kernel copies, `default.cfg`, `Data/*.json`, loader-generated
`offsets-snapshot.json`), covered by [.gitignore](.gitignore). The loader writes
those files at runtime, so tracking them made every game test dirty the tree
and blocked publication; a test can now run while a release is published. The
workflow uploads executable files only and packages no configurations or
`Data/` directories.

## Dated release snapshot

On 09.10.2026, GitHub's latest-release endpoint returned [build-77](https://github.com/spiteware-project/SpitewareBuilds/releases/tag/build-77), published **14.08.2026 at 05:22:08 UTC**. Its [release job](https://github.com/spiteware-project/SpitewareBuilds/actions/runs/31772762549) completed successfully on 14.08.2026. These observations do not establish that later source changes have been published.

**Current release (checked 26.10.2026): `build-80` = Pro `1.1.0`.** Published through `release.mjs --publish`; the shipped asset was verified by SHA256 against the approved binary `2DF51BF6A09DC2B4827C134BBA683ADAE3E7F1E76E5026C704FAEF4715FA571B`, KeyAuth `cs2_kernel_pro_version` read back as `1.1.0`, and the Supabase version override cleared. Loader (1.0.0.5), ESP and Obsidian were unchanged. `build-79` was a structure-only release (five to four artifacts, binaries unchanged). The `build-80` tag exists only on the remote; local tags stop at `build-79`. Chronology: [Chronik](docs/CHRONIK.md); open items: [Roadmap](docs/ROADMAP.md).

| Artifact | Root/release bytes | Local source bytes | Root/release SHA256 prefix | Local source SHA256 prefix |
|---|---:|---:|---|---|
| Loader | 13,592,576 | 13,592,576 | `A97E794F` | `A97E794F` |
| Debug loader | 17,775,104 | 17,775,104 | `320C94AE` | `320C94AE` |
| Pro | 3,076,096 | 3,076,608 | `C4F4D10E` | `D8FABAE0` |
| ESP | 2,529,792 | 2,529,792 | `A43B18BB` | `EB0ABF90` |
| Obsidian | 3,082,752 | 3,082,752 | `21C423B5` | `7AD74366` |

Full local hashes were compared with `Get-FileHash -Algorithm SHA256` and GitHub asset digests. Both loader sources were dated 02.06.2026; the three kernel sources were dated 13.09.2026. Root kernel artifacts and flat `mods/` copies were dated 25.06.2026. Equal size or PE version is insufficient: ESP and Obsidian have equal sizes but different hashes.

All five names were present in release metadata. GET requests with `Range: 0-1` to the four production assets returned HTTP 206, two bytes, curl exit 0. Debug-asset presence was checked through metadata. The older setup URL under `theabstractx/builds` also returned HTTP 206 through redirects; new references should use the canonical organization above. Downloaded binaries were not executed. A follow-up verified all four actual KeyAuth links read-only: they select the matching executable through GitHub `latest` and currently redirect to `build-77`.

## Refresh and release process

**Repaired and checked: 09.10.2026; artifact set reduced to four on 26.10.2026.** [artifacts.py](artifacts.py) is the validator and staging helper. The four root executables are preserved; the formerly tracked `mods/` copies and debug loader are untracked since 26.10.2026 and stay on disk as local test state. Tests used synthetic PE files and local temporary Git repositories; no real refresh or publication occurred.

[refresh_builds.bat](refresh_builds.bat) previews all four sibling sources by default. Explicit apply updates this repository's **root only**, leaving `mods/` and `Data/` snapshots untouched:

```powershell
.\refresh_builds.bat --dry-run --manifest "$env:TEMP\spiteware-refresh.json"
# After independent review of artifacts and source validation:
.\refresh_builds.bat --apply --approved-manifest "$env:TEMP\spiteware-refresh.json"
```

All four sources must exist and pass x64 PE32+ header, section/resource-bound checks before the first target write. The manifest records lowercase SHA256, size, nullable PE `file_version`, source path relative to `cs2/`, and previous target digest. Missing version resources produce `null`; no KeyAuth version is inferred. Changed sources or destinations invalidate the approval manifest.

All replacements are staged on the target filesystem, then replaced atomically per file. Handled failures roll back prior replacements; recovery files and a named `transaction.json` mapping remain in `.stage-*/` if rollback fails. This is not a crash-atomic multi-file transaction. Hashes establish identity, not source freshness or runtime compatibility.

Before repair, refresh deleted targets first and could leave a partial update. The dated original audit also found recursive flattening of stale `mods/` copies onto matching root basenames. The helper and current workflow address those findings.

### GitHub Actions

The [workflow](.github/workflows/release-on-main.yml) still publishes on pushes to `main`. `python3 artifacts.py stage-release --output-dir dist` selects exactly the four root artifacts. The debug loader, other root executables and `mods/` are excluded.

All four pass PE checks before staging. Explicit asset paths and `fail_on_unmatched_files: true` prevent silent omissions. The release includes four executables plus `manifest.json`: `schema_version: 1`, `purpose: "release"`, and `artifacts` entries with `name`, `size`, lowercase `sha256`, and nullable `file_version`.

The job uses `softprops/action-gh-release@v2`, `contents: write`, and tag `build-${{ github.run_number }}`. It does not compile sources or update KeyAuth. `build-<N>` is separate from PE and KeyAuth versions. A documentation-only push can still publish unchanged binaries. The repaired workflow was checked locally; no new GitHub run is claimed.

### Manual publishing helper

[auto_commit.bat](auto_commit.bat) is now a preview by default:

```powershell
.\auto_commit.bat --manifest "$env:TEMP\spiteware-publish.json"
# Only after installed artifact/release review:
.\auto_commit.bat --publish --approved-manifest "$env:TEMP\spiteware-publish.json"
```

Publication requires `main` with a remote `main` upstream, no pre-existing staged changes, no unrelated working-tree changes, and no unpublished local commits. Git synchronization must succeed before staging; artifacts must still match the approval afterward. Only the four filenames are staged/committed. UTC ISO timestamps avoid Windows locale ambiguity. Git exit statuses and remote HEAD are checked; identical artifacts cause no commit/push. Git confirmation does not prove release-job success or CDN contents.

The debug loader is untracked since 26.10.2026 and no longer distributed; [.gitignore](.gitignore) keeps it and the whole `mods/` directory out of the working tree, so a running game test does not block publication. Older releases (up to `build-78`) still carry a debug-loader asset; the KeyAuth links never referenced it. Root [SpitewareSetup.bat](../../SpitewareSetup.bat) now uses the canonical `spiteware-project/SpitewareBuilds/releases/latest/download/SpitewareLoader.exe` URL. Downloads are staged beside the target, PE-validated, then replaced. Only its download fragment was tested with fake responses; full setup/system changes were not run.

### Local verification

From the workspace root: `py -3 -B -m unittest discover -s cs2/builds/tests -v`. Tests cover preview preservation, missing/invalid inputs, changed manifests, rollback, root-only release selection, offset Git order/dirty refusal/scoped publication, generation hashes, dummy Cargo, and setup downloads. Fixtures do not launch real executables or use network remotes.

## Loader and KeyAuth contract

The [website auth handler](../../platform/spiteware/server/loader/index.js), lines 279–312, fetches KeyAuth variables and forwards them to the loader. Its fallback includes all three products and the loader. The [loader login implementation](../loader/SpitewareLoader/src/ui/ui_login.cpp) expects:

| Component | Download variable | Version variable |
|---|---|---|
| Loader | `loader_link` | `loader_version` |
| Pro | `cs2_kernel_pro_link` | `cs2_kernel_pro_version` |
| ESP | `cs2_kernel_esp_link` | `cs2_kernel_esp_version` |
| Obsidian | `cs2_kernel_obsidian_link` | `cs2_kernel_obsidian_version` |

Use **`*_link`**, not `*_url`. No credentials are recorded here. Login currently downloads owned mods from their links. Loader self-update triggers on any version mismatch; it does not select an older GitHub release itself. The live loader version matches the source, so no self-update or downgrade is currently demonstrated. A newer local test binary can still be replaced by an older published asset if the version values differ. Keep the intended binary and its version declaration consistent before updating server variables.

On 09.10.2026, public `/api/config` returned HTTP 200 with all three product-version fields populated and a loader version matching the source constant. A subsequent eight-variable read-only KeyAuth check confirmed versions and all four `latest` links: loader `1.0.0.5`, ESP/Pro `1.0.0.2`, Obsidian `1.0.0.0`. Subscriptions, successful OAuth login, and a complete download/start flow remain unverified.

Follow-up release comparison: all five assets in August's `build-77` have the same SHA256 as June's `build-76`; the `build-77` source commit changed only `readme.md`. `latest` therefore serves the newest published release, containing unchanged June binaries. Different local September kernel hashes show different files, not by themselves a proven functional regression. Publication freshness should be addressed after source and runtime validation.

## Offset dependency

All three kernel products fetch the website's `offsets.json`, `buttons.json`, `client_dll.json`, and `gamedata.json`. The [dumper README](../../tools/cs2-dumper/README.md) documents the repaired preview/apply/publish interface, Git synchronization before installation, and `info.json` → `gamedata.json` mapping with exact-byte SHA256 generation hashes. Running-game/build compatibility still requires client and runtime validation. Neither refresh nor the release workflow updates these JSON files.

## Related projects and documentation upkeep

- [Loader README](../loader/README.md): build, authentication, downloads, and self-update.
- [Kernel Pro README](../kernel-pro/README.md), [Kernel ESP README](../kernel-esp/README.md), [Obsidian README](../kernel-obsidian/README.md): source build pipelines.
- [Website README](../../platform/spiteware/README.md): loader backend and offset hosting.
- [Project map](../../PROJECTS.md): repository boundaries and cross-project dependencies.

Update this README in the same task as changes to artifact names, source paths, refresh behavior, workflow selection, release/KeyAuth contracts, or offset distribution. Record the review date and source or verification command; distinguish source-defined behavior, dated results, and unverified external settings. Documentation maintenance follows project changes; no periodic automation is configured here.
