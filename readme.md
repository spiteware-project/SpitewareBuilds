# SpitewareBuilds

Release artifact store for [spiteware-project/SpitewareBuilds](https://github.com/spiteware-project/SpitewareBuilds). This repository contains copies of executables compiled in the sibling source projects. The loader receives their download URLs through the website's KeyAuth integration.

**Reviewed: 09.10.2026.** Public release URLs were reachable, but the three kernel copies did not match the local September build outputs. A successful release job does not establish a successful source build or game launch. No refresh, publication, setup script, or executable was run during the release audit.

## Artifacts and sources

| Root artifact | Source relative to `cs2/` |
|---|---|
| `SpitewareLoader.exe` | `loader/build/release/SpitewareLoader.exe` |
| `SpitewareLoader_Debug.exe` | `loader/build/debug/SpitewareLoader.exe` |
| `cs2_kernel_pro.exe` | `kernel-pro/build/Spiteware/cs2_kernel_pro.exe` |
| `cs2_kernel_esp.exe` | `kernel-esp/build/Spiteware/cs2_kernel_esp.exe` |
| `cs2_kernel_obsidian.exe` | `kernel-obsidian/build/Spiteware/cs2_kernel_obsidian.exe` |

There are **five root artifacts**, including the debug loader. `mods/` also contains flat copies of the three kernel executables. Each `mods/CS2 Kernel {Pro,ESP,Obsidian}/` directory contains `default.cfg` and `Data/{buttons,client_dll,gamedata,offsets}.json`; no executable was present inside those named directories at review time.

The [workflow](.github/workflows/release-on-main.yml) uploads executable files only. It does not package default configurations or `Data/` directories. Those snapshots differ from the website's offsets and need separate maintenance if retained for manual distribution.

## Dated release snapshot

On 09.10.2026, GitHub's latest-release endpoint returned [build-77](https://github.com/spiteware-project/SpitewareBuilds/releases/tag/build-77), published **14.08.2026 at 05:22:08 UTC**. Its [release job](https://github.com/spiteware-project/SpitewareBuilds/actions/runs/31772762549) completed successfully on 14.08.2026. These observations do not establish that later source changes have been published.

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

[refresh_builds.bat](refresh_builds.bat), lines 7–20, copies the five sources above into **this repository's root only**. It does not update `mods/` executables or `Data/` snapshots. Missing sources and copy failures stop the script, but earlier copies may already have changed. Each target is deleted before its replacement is copied.

**Refreshing alone is currently insufficient to prepare a reliable release.** The workflow's recursive search on line 22 copies every `.exe` outside `dist/` into one flat directory. Root and `mods/` executables share basenames, so the copy encountered last overwrites the other. Refreshing the root leaves old `mods/` binaries eligible for publication.

Before the next publication:

1. Resolve duplicate selection, preferably with an explicit workflow allowlist of the four root production executables. Decide explicitly whether to distribute the debug loader.
2. Check all sources before replacing targets, then compare intended artifacts by full SHA256. Maintain or remove duplicates consistently with the chosen layout.
3. Review the diff, binary versions, download URLs, and KeyAuth variable names together. Under the checked workflow, any push to `main` is a publication trigger.
4. After an authorized publication, inspect that job and its assets, compare digests, and test the actual loader flow.

These are pending changes and checks, not fixes implemented by this README update.

### GitHub Actions

The checked [workflow](.github/workflows/release-on-main.yml) declares a `push` trigger for `main`, checks out this artifact repository, prepares the recursive collection above, and invokes `softprops/action-gh-release@v2`. It grants `contents: write` to the job. The intended tag is `build-${{ github.run_number }}` and assets are `dist/*.exe`. It does not compile sources, check artifact freshness, or update KeyAuth variables.

`build-<N>` is a workflow run identifier, separate from executable versions and KeyAuth `*_version` values. A documentation-only push can publish the same binaries under a new tag. Future job success and external settings require fresh verification.

### Manual helper

[auto_commit.bat](auto_commit.bat) runs `git add .`, `git commit`, and `git push`; it is a publishing helper, not a build or validation command. Its European date parsing swaps day and month, as historical commit messages show. It lacks error checks between the Git commands and stages all changes in this artifact repository. Review the working tree before using it; it was not run during this audit.

`SpitewareLoader_Debug.exe` is already tracked and was included in build-77. The matching [.gitignore](.gitignore) entry does not remove a tracked artifact or exclude it from the workflow.

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

All three kernel products fetch the website's `offsets.json`, `buttons.json`, `client_dll.json`, and `gamedata.json`. The [dumper README](../../tools/cs2-dumper/README.md) documents the current updater defects: copying before `git pull --rebase`, missing `info.json` → `gamedata.json` mapping, and incompatible client/server version fields. Neither refresh nor the release workflow updates these JSON files.

## Related projects and documentation upkeep

- [Loader README](../loader/README.md): build, authentication, downloads, and self-update.
- [Kernel Pro README](../kernel-pro/README.md), [Kernel ESP README](../kernel-esp/README.md), [Obsidian README](../kernel-obsidian/README.md): source build pipelines.
- [Website README](../../platform/spiteware/README.md): loader backend and offset hosting.
- [Project map](../../PROJECTS.md): repository boundaries and cross-project dependencies.

Update this README in the same task as changes to artifact names, source paths, refresh behavior, workflow selection, release/KeyAuth contracts, or offset distribution. Record the review date and source or verification command; distinguish source-defined behavior, dated results, and unverified external settings. Documentation maintenance follows project changes; no periodic automation is configured here.
