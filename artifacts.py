"""Validate and stage the four deliberately distributed artifacts; never execute them."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

# The debug loader is deliberately absent: it is a local test tool only
# (DEBUG_LOCAL, no server downloads) and is not distributed through releases
# since 26.10.2026. It stays available untracked in the repository root for
# the local test workflow.
ARTIFACTS = {
    "SpitewareLoader.exe": "loader/build/release/SpitewareLoader.exe",
    "cs2_kernel_pro.exe": "kernel-pro/build/Spiteware/cs2_kernel_pro.exe",
    "cs2_kernel_esp.exe": "kernel-esp/build/Spiteware/cs2_kernel_esp.exe",
    "cs2_kernel_obsidian.exe": "kernel-obsidian/build/Spiteware/cs2_kernel_obsidian.exe",
}


def pe_version(data):
    """Check PE headers/section bounds and read VS_FIXEDFILEINFO, if present."""
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ValueError("truncated PE structure")
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ValueError("missing DOS signature")
    pe = unpack("<I", 0x3c)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    machine, sections, _, _, _, optional_size, _ = unpack("<HHIIIHH", pe + 4)
    optional = pe + 24
    if machine != 0x8664 or not 1 <= sections <= 96 or optional_size < 112:
        raise ValueError("expected an x64 executable with valid sections")
    if unpack("<H", optional)[0] != 0x20b:
        raise ValueError("expected PE32+")
    unpack(f"<{optional_size}s", optional)
    regions = []
    for index in range(sections):
        section = optional + optional_size + index * 40
        unpack("<40s", section)
        virtual_size, rva, raw_size, raw = unpack("<IIII", section + 8)
        if raw_size and (raw < optional + optional_size + sections * 40 or raw + raw_size > len(data)):
            raise ValueError("PE section exceeds file bounds")
        regions.append((rva, max(virtual_size, raw_size), raw, raw_size))

    def rva_offset(rva, size):
        for start, _, raw, raw_size in regions:
            delta = rva - start
            if 0 <= delta and delta + size <= raw_size:
                return raw + delta
        raise ValueError("PE resource outside a mapped section")

    directory_count = unpack("<I", optional + 108)[0]
    if directory_count < 3:
        return None
    if optional_size < 136:
        raise ValueError("truncated resource directory")
    resource_rva, resource_size = unpack("<II", optional + 128)
    if resource_rva == 0 and resource_size == 0:
        return None
    base = rva_offset(resource_rva, resource_size)

    def resource_entries(relative):
        if relative < 0 or relative + 16 > resource_size:
            raise ValueError("invalid resource directory")
        named, ids = unpack("<HH", base + relative + 12)
        if relative + 16 + (named + ids) * 8 > resource_size:
            raise ValueError("invalid resource entries")
        return [unpack("<II", base + relative + 16 + i * 8) for i in range(named + ids)]

    def values(relative, depth):
        if depth > 2:
            raise ValueError("unexpected resource nesting")
        for _, child in resource_entries(relative):
            address = child & 0x7fffffff
            if child & 0x80000000:
                yield from values(address, depth + 1)
            else:
                if address + 16 > resource_size:
                    raise ValueError("invalid resource data entry")
                rva, size, _, _ = unpack("<IIII", base + address)
                offset = rva_offset(rva, size)
                yield data[offset:offset + size]

    versions = []
    for kind, child in resource_entries(0):
        if kind != 16:
            continue
        if not child & 0x80000000:
            raise ValueError("invalid version resource directory")
        for value in values(child & 0x7fffffff, 0):
            key = "VS_VERSION_INFO\0".encode("utf-16le")
            if len(value) < 6 + len(key) or value[6:6 + len(key)] != key:
                raise ValueError("invalid version resource key")
            fixed = (6 + len(key) + 3) & ~3
            if len(value) < fixed + 52 or struct.unpack_from("<I", value, fixed)[0] != 0xfeef04bd:
                raise ValueError("invalid version resource value")
            ms, ls = struct.unpack_from("<II", value, fixed + 8)
            versions.append(".".join(map(str, (ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff))))
    if len(set(versions)) > 1:
        raise ValueError("conflicting file versions in resources")
    return versions[0] if versions else None


def describe(name, data):
    try:
        version = pe_version(data)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from error
    return {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "file_version": version}


def read_artifacts(directory, source_root=None):
    payloads, entries = {}, []
    for name, source in ARTIFACTS.items():
        path = (source_root / source) if source_root is not None else (directory / name)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or unsafe artifact: {path}")
        data = path.read_bytes()
        entry = describe(name, data)
        if source_root is not None:
            entry["source"] = source
            old = directory / name
            if old.is_symlink() or (old.exists() and not old.is_file()):
                raise ValueError(f"unsafe destination: {old}")
            entry["previous_sha256"] = hashlib.sha256(old.read_bytes()).hexdigest() if old.exists() else None
        payloads[name] = data
        entries.append(entry)
    return payloads, {"schema_version": 1, "purpose": "refresh" if source_root else "release",
                      "artifacts": entries}


def atomic_replace_files(directory, payloads, expected=None):
    """Stage all files first. Atomic per-file replacement with rollback on handled errors."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"destination directory missing: {directory}")
    previous = {}
    for name in payloads:
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ValueError(f"unsafe target name: {name}")
        target = directory / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(f"unsafe destination: {target}")
        previous[name] = target.read_bytes() if target.exists() else None
        digest = hashlib.sha256(previous[name]).hexdigest() if previous[name] is not None else None
        if expected is not None and digest != expected[name]:
            raise ValueError(f"destination changed after review: {target}")
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=directory))
    applied, rollback_failed = [], False
    try:
        recovery = {"schema_version": 1, "files": []}
        for index, (name, data) in enumerate(payloads.items()):
            with (stage / f"new-{index}").open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if previous[name] is not None:
                with (stage / f"old-{index}").open("xb") as stream:
                    stream.write(previous[name])
                    stream.flush()
                    os.fsync(stream.fileno())
            recovery["files"].append({"name": name, "staged": f"new-{index}",
                                      "backup": f"old-{index}" if previous[name] is not None else None,
                                      "sha256": hashlib.sha256(data).hexdigest(),
                                      "previous_sha256": hashlib.sha256(previous[name]).hexdigest()
                                      if previous[name] is not None else None})
        with (stage / "transaction.json").open("x", encoding="utf-8") as stream:
            json.dump(recovery, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            for index, name in enumerate(payloads):
                target = directory / name
                now = target.read_bytes() if target.exists() else None
                if now != previous[name] or target.is_symlink():
                    raise ValueError(f"destination changed during staging: {target}")
                os.replace(stage / f"new-{index}", target)
                applied.append((index, name))
        except BaseException:
            for index, name in reversed(applied):
                try:
                    if previous[name] is None:
                        (directory / name).unlink()
                    else:
                        os.replace(stage / f"old-{index}", directory / name)
                except OSError:
                    rollback_failed = True
            if rollback_failed:
                print(f"Rollback incomplete; recovery files retained at {stage}", file=sys.stderr)
            raise
    finally:
        if not rollback_failed and stage.parent == directory and stage.name.startswith(".stage-"):
            shutil.rmtree(stage)


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"git {args[0]} failed (exit {result.returncode})")
    return result.stdout.rstrip("\r\n")


def publish(directory, manifest):
    """Explicit publication only; commit precisely the reviewed four artifacts."""
    if git(directory, "branch", "--show-current") != "main":
        raise ValueError("publication requires the reviewed main branch")
    if git(directory, "diff", "--cached", "--name-only"):
        raise ValueError("publication refused: pre-existing staged changes")
    remote = git(directory, "config", "branch.main.remote")
    ref = git(directory, "config", "branch.main.merge")
    if ref != "refs/heads/main" or remote == ".":
        raise ValueError("publication requires a configured remote main branch")
    changed = git(directory, "status", "--porcelain", "--untracked-files=all")
    for row in changed.splitlines():
        if row[3:] not in ARTIFACTS:
            raise ValueError("publication refused: unrelated working-tree changes")
    git(directory, "fetch", remote)
    if git(directory, "rev-list", "--count", "@{u}..HEAD") != "0":
        raise ValueError("publication refused: local commits not on upstream")
    git(directory, "pull", "--ff-only")
    _, after = read_artifacts(directory)
    if after != manifest:
        raise ValueError("artifacts changed during Git synchronization; review again")
    names = list(ARTIFACTS)
    git(directory, "add", "--", *names)
    if not git(directory, "diff", "--cached", "--name-only", "--", *names):
        print("No artifact changes; no commit or push.")
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git(directory, "commit", "--only", "-m", f"Update reviewed artifacts {timestamp}", "--", *names)
    git(directory, "push", remote, f"HEAD:{ref}")
    rows = git(directory, "ls-remote", remote, ref).splitlines()
    if len(rows) != 1 or rows[0].split()[0] != git(directory, "rev-parse", "HEAD"):
        raise ValueError("push verification failed: remote main does not match local commit")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("manifest", "stage-release", "refresh", "publish"):
        cli = sub.add_parser(command)
        cli.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
        cli.add_argument("--manifest", type=Path, help="write the preview manifest to this path")
        if command in {"refresh", "publish"}:
            cli.add_argument("--dry-run", action="store_true")
            cli.add_argument("--approved-manifest", type=Path)
            cli.add_argument("--apply" if command == "refresh" else "--publish", action="store_true")
        if command == "refresh":
            cli.add_argument("--source-root", type=Path)
        if command == "stage-release":
            cli.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        directory = args.directory.resolve()
        source = (args.source_root or directory.parent).resolve() if args.command == "refresh" else None
        payloads, manifest = read_artifacts(directory, source)
        serialized = json.dumps(manifest, indent=2) + "\n"
        mutation = getattr(args, "apply", False) or getattr(args, "publish", False)
        if mutation:
            if args.dry_run or args.approved_manifest is None:
                raise ValueError("apply/publish requires --approved-manifest and excludes --dry-run")
            approved = json.loads(args.approved_manifest.read_text(encoding="utf-8-sig"))
            if approved != manifest:
                raise ValueError("manifest no longer matches current artifact inputs and targets")
        if args.manifest:
            if args.manifest.suffix.lower() != ".json" or args.manifest.resolve().is_relative_to(directory):
                raise ValueError("write review manifests outside the artifact repository")
            args.manifest.write_text(serialized, encoding="utf-8")
        if args.command == "stage-release":
            output = args.output_dir.resolve()
            if output.exists():
                raise ValueError("release staging directory must not already exist")
            output.mkdir(parents=True)
            try:
                atomic_replace_files(output, {**payloads, "manifest.json": serialized.encode()})
            except BaseException:
                if not any(output.iterdir()):
                    output.rmdir()
                raise
        elif args.command == "refresh" and mutation:
            expected = {row["name"]: row["previous_sha256"] for row in manifest["artifacts"]}
            atomic_replace_files(directory, payloads, expected)
        elif args.command == "publish" and mutation:
            publish(directory, manifest)
        print(serialized, end="")
        return 0
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
