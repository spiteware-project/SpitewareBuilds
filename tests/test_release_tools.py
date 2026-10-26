import hashlib
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BUILDS = Path(__file__).resolve().parents[1]
ROOT = BUILDS.parents[1]
SOURCES = {
    'SpitewareLoader.exe': 'loader/build/release/SpitewareLoader.exe',
    'cs2_kernel_pro.exe': 'kernel-pro/build/Spiteware/cs2_kernel_pro.exe',
    'cs2_kernel_esp.exe': 'kernel-esp/build/Spiteware/cs2_kernel_esp.exe',
    'cs2_kernel_obsidian.exe': 'kernel-obsidian/build/Spiteware/cs2_kernel_obsidian.exe',
}


def pe(marker):
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x22)
    struct.pack_into('<H', data, 0x98, 0x20b)
    struct.pack_into('<I', data, 0x98 + 108, 16)
    section = 0x98 + 240
    data[section:section + 8] = b'.text\0\0\0'
    struct.pack_into('<IIII', data, section + 8, 512, 0x1000, 512, 512)
    data[512:512 + len(marker)] = marker
    return bytes(data)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spiteware-release-test-')
        self.root = Path(self.tmp.name) / 'cs2'
        self.directory = self.root / 'builds'
        self.directory.mkdir(parents=True)
        self.old = {name: pe(b'old-' + name.encode()) for name in SOURCES}
        for name, source in SOURCES.items():
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pe(b'new-' + name.encode()))
            (self.directory / name).write_bytes(self.old[name])
        shutil.copy2(BUILDS / 'refresh_builds.bat', self.directory)
        if (BUILDS / 'artifacts.py').exists():
            shutil.copy2(BUILDS / 'artifacts.py', self.directory)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(BUILDS / 'artifacts.py'), *map(str, args)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {name: (self.directory / name).read_bytes() for name in SOURCES}

    @unittest.skipUnless(os.name == 'nt', 'Windows batch wrapper')
    def test_dry_run_does_not_replace_existing_artifacts(self):
        result = subprocess.run(['cmd', '/c', str(self.directory / 'refresh_builds.bat'), '--dry-run'],
                                cwd=self.directory, input='\n', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), self.old)

    def test_missing_last_source_cannot_partially_refresh(self):
        (self.root / SOURCES['cs2_kernel_obsidian.exe']).unlink()
        result = self.run_tool('refresh', '--source-root', self.root, '--directory', self.directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), self.old)

    def test_release_uses_only_root_allowlist_and_writes_hash_manifest(self):
        mods = self.directory / 'mods'
        mods.mkdir()
        (mods / 'cs2_kernel_pro.exe').write_bytes(pe(b'stale-duplicate'))
        (self.directory / 'unrelated.exe').write_bytes(pe(b'unrelated'))
        output = self.directory / 'dist'
        result = self.run_tool('stage-release', '--directory', self.directory, '--output-dir', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name for p in output.iterdir()}, set(SOURCES) | {'manifest.json'})
        manifest = json.loads((output / 'manifest.json').read_text())
        for entry in manifest['artifacts']:
            self.assertEqual((output / entry['name']).read_bytes(), self.old[entry['name']])
            self.assertEqual(entry['sha256'], hashlib.sha256(self.old[entry['name']]).hexdigest())
            self.assertIn('file_version', entry)

    def test_invalid_pe_blocks_release_before_output_is_created(self):
        (self.directory / 'cs2_kernel_obsidian.exe').write_bytes(b'MZ not a PE')
        output = self.directory / 'dist'
        result = self.run_tool('stage-release', '--directory', self.directory, '--output-dir', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_apply_requires_matching_reviewed_manifest(self):
        plan = self.run_tool('refresh', '--source-root', self.root, '--directory', self.directory)
        self.assertEqual(plan.returncode, 0, plan.stderr)
        approved = self.directory / 'review.json'
        approved.write_text(plan.stdout)
        (self.root / SOURCES['cs2_kernel_pro.exe']).write_bytes(pe(b'changed-after-review'))
        result = self.run_tool('refresh', '--source-root', self.root, '--directory', self.directory,
                               '--apply', '--approved-manifest', approved)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), self.old)

    def test_reviewed_refresh_replaces_all_four_in_a_fixture(self):
        plan = self.run_tool('refresh', '--source-root', self.root, '--directory', self.directory)
        approved = Path(self.tmp.name) / 'review.json'
        approved.write_text(plan.stdout)
        result = self.run_tool('refresh', '--source-root', self.root, '--directory', self.directory,
                               '--apply', '--approved-manifest', approved)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, source in SOURCES.items():
            self.assertEqual((self.directory / name).read_bytes(), (self.root / source).read_bytes())
        self.assertFalse(list(self.directory.glob('.stage-*')))

    def test_publish_wrapper_is_a_preview_by_default(self):
        if os.name != 'nt':
            self.skipTest('Windows batch wrapper')
        shutil.copy2(BUILDS / 'auto_commit.bat', self.directory)
        result = subprocess.run(['cmd', '/c', str(self.directory / 'auto_commit.bat')],
                                cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), self.old)
        self.assertFalse((self.directory / '.git').exists())

    def test_refresh_rollback_restores_all_targets_on_replace_failure(self):
        self.assertTrue((BUILDS / 'artifacts.py').exists(), 'transaction helper missing')
        module = load(BUILDS / 'artifacts.py', 'release_artifact_test_module')
        real_replace = os.replace
        calls = 0

        def fail_once(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated locked destination')
            return real_replace(source, target)

        with patch.object(module.os, 'replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                module.atomic_replace_files(self.directory, {name: pe(b'new') for name in SOURCES})
        self.assertEqual(self.snapshot(), self.old)

    def test_failed_rollback_retains_named_recovery_manifest_and_backup(self):
        module = load(BUILDS / 'artifacts.py', 'release_recovery_test_module')
        real_replace = os.replace
        calls = 0

        def fail_after_first(source, target):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError('fixture filesystem still locked')
            return real_replace(source, target)

        with patch.object(module.os, 'replace', side_effect=fail_after_first), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(OSError):
                module.atomic_replace_files(self.directory, {name: pe(b'new') for name in SOURCES})
        stage, = self.directory.glob('.stage-*')
        recovery = json.loads((stage / 'transaction.json').read_bytes())
        entry = recovery['files'][0]
        self.assertEqual((stage / entry['backup']).read_bytes(), self.old[entry['name']])
        self.assertEqual(entry['previous_sha256'], hashlib.sha256(self.old[entry['name']]).hexdigest())

    def test_artifact_publication_is_scoped_and_explicit_in_local_fixture(self):
        module = load(BUILDS / 'artifacts.py', 'release_publish_test_module')

        def git(repo, *args):
            result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        remote = Path(self.tmp.name) / 'fixture-remote.git'
        remote.mkdir()
        git(remote, 'init', '--bare', '--initial-branch=main')
        git(self.directory, 'init', '--initial-branch=main')
        git(self.directory, 'config', 'user.name', 'Fixture')
        git(self.directory, 'config', 'user.email', 'fixture@example.invalid')
        git(self.directory, 'add', '.')
        git(self.directory, 'commit', '-m', 'Fixture baseline')
        git(self.directory, 'remote', 'add', 'origin', str(remote))
        git(self.directory, 'push', '-u', 'origin', 'main')
        for name in SOURCES:
            (self.directory / name).write_bytes(pe(b'reviewed-new-' + name.encode()))
        _, manifest = module.read_artifacts(self.directory)
        approved = Path(self.tmp.name) / 'publish-review.json'
        approved.write_text(json.dumps(manifest))
        with contextlib.redirect_stdout(io.StringIO()):
            result = module.main(['publish', '--directory', str(self.directory), '--publish',
                                  '--approved-manifest', str(approved)])
        self.assertEqual(result, 0)
        self.assertEqual(git(self.directory, 'rev-parse', 'HEAD'), git(self.directory, 'rev-parse', '@{u}'))
        self.assertEqual(set(git(self.directory, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()),
                         set(SOURCES))


class OffsetTests(unittest.TestCase):
    def setUp(self):
        self.module = load(ROOT / 'update-offsets.py', 'offset_test_module')
        self.tmp = tempfile.TemporaryDirectory(prefix='spiteware-offset-test-')
        self.directory = Path(self.tmp.name)
        self.output = self.directory / 'dump'
        self.output.mkdir()
        fixture = {
            'buttons.json': {'client.dll': {'jump': 4096}},
            'offsets.json': {'client.dll': {'dwEntityList': 8192}, 'engine2.dll': {'dwBuildNumber': 42}},
            'client_dll.json': {'client.dll': {'classes': {'C_BaseEntity': {'fields': {'m_iHealth': 16}}}}},
            'info.json': {'build_number': 12345, 'timestamp': '2026-10-09T12:34:56+00:00'},
        }
        for name, value in fixture.items():
            (self.output / name).write_text(json.dumps(value))

    def tearDown(self):
        self.tmp.cleanup()

    def test_metadata_is_mapped_to_gamedata_from_the_same_dump(self):
        function = getattr(self.module, 'validate_bundle', None)
        self.assertTrue(callable(function), 'validated metadata mapping missing')
        payloads = function(self.output)
        self.assertEqual(set(payloads), {'buttons.json', 'offsets.json', 'client_dll.json', 'gamedata.json'})
        metadata = json.loads(payloads['gamedata.json'])
        self.assertEqual(metadata['build_number'], 12345)
        self.assertEqual(metadata['timestamp'], '2026-10-09T12:34:56+00:00')

    def test_generation_manifest_binds_exact_bytes_and_preserves_extra_metadata(self):
        info = json.loads((self.output / 'info.json').read_bytes())
        info['additional_metadata'] = {'note': 'preserve'}
        (self.output / 'info.json').write_text(json.dumps(info))
        payloads = self.module.validate_bundle(self.output)
        metadata = json.loads(payloads['gamedata.json'])
        self.assertEqual(metadata['additional_metadata'], info['additional_metadata'])
        self.assertEqual(metadata['offset_manifest'], {'schema_version': 1, 'sha256': {
            name: hashlib.sha256(payloads[name]).hexdigest()
            for name in ('offsets.json', 'buttons.json', 'client_dll.json')}})

    def test_bad_schema_is_rejected_before_any_copy(self):
        function = getattr(self.module, 'validate_bundle', None)
        self.assertTrue(callable(function), 'schema validation missing')
        (self.output / 'client_dll.json').write_text('{"client.dll":{"classes":[]}}')
        with self.assertRaises(ValueError):
            function(self.output)

    def test_default_preview_has_no_website_or_git_side_effects(self):
        function = getattr(self.module, 'main_with_args', None)
        self.assertTrue(callable(function), 'safe preview CLI missing')
        repo = self.directory / 'website'
        repo.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(function(['--output-dir', str(self.output), '--repo-dir', str(repo)]), 0)
        self.assertEqual(list(repo.iterdir()), [])

    def git(self, repo, *args):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def repository(self):
        remote = self.directory / 'fixture-remote.git'
        remote.mkdir()
        self.git(remote, 'init', '--bare', '--initial-branch=main')
        seed = self.directory / 'seed'
        seed.mkdir()
        self.git(seed, 'init', '--initial-branch=main')
        self.git(seed, 'config', 'user.name', 'Fixture')
        self.git(seed, 'config', 'user.email', 'fixture@example.invalid')
        destination = seed / 'public' / 'offsets'
        destination.mkdir(parents=True)
        for name in self.module.FILES:
            (destination / name).write_bytes(b'{"previous":true}\n')
        self.git(seed, 'add', '.')
        self.git(seed, 'commit', '-m', 'Fixture baseline')
        self.git(seed, 'remote', 'add', 'origin', str(remote))
        self.git(seed, 'push', '-u', 'origin', 'main')
        repo = self.directory / 'website'
        self.git(self.directory, 'clone', str(remote), str(repo))
        self.git(repo, 'config', 'user.name', 'Fixture')
        self.git(repo, 'config', 'user.email', 'fixture@example.invalid')
        return seed, repo

    def invoke(self, repo, *flags):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.module.main_with_args(['--output-dir', str(self.output), '--repo-dir', str(repo), *flags])

    def test_dirty_checkout_is_rejected_before_any_offset_is_changed(self):
        _, repo = self.repository()
        destination = repo / 'public' / 'offsets'
        before = {p.name: p.read_bytes() for p in destination.iterdir()}
        (repo / 'user-note.txt').write_text('keep me')
        self.assertEqual(self.invoke(repo, '--apply'), 1)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, before)
        self.assertEqual((repo / 'user-note.txt').read_text(), 'keep me')

    def test_pull_is_completed_before_local_install_and_default_does_not_commit(self):
        seed, repo = self.repository()
        (seed / 'synced.txt').write_text('remote change')
        (seed / 'public' / 'offsets' / 'offsets.json').write_bytes(b'{"remote":true}')
        self.git(seed, 'add', '.')
        self.git(seed, 'commit', '-m', 'Fixture upstream change')
        self.git(seed, 'push')
        remote_head = self.git(seed, 'rev-parse', 'HEAD')
        self.assertEqual(self.invoke(repo, '--apply'), 0)
        self.assertTrue((repo / 'synced.txt').exists())
        self.assertEqual(self.git(repo, 'rev-parse', 'HEAD'), remote_head)
        self.assertEqual(self.git(repo, 'diff', '--cached', '--name-only'), '')
        expected = self.module.validate_bundle(self.output)
        for name, data in expected.items():
            self.assertEqual((repo / 'public' / 'offsets' / name).read_bytes(), data)

    def test_publish_is_explicit_and_scoped_to_four_offset_files_in_local_fixture(self):
        _, repo = self.repository()
        before = self.git(repo, 'rev-parse', 'HEAD')
        self.assertEqual(self.invoke(repo, '--publish'), 0)
        after = self.git(repo, 'rev-parse', 'HEAD')
        self.assertNotEqual(before, after)
        self.assertEqual(self.git(repo, 'rev-parse', '@{u}'), after)
        paths = self.git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines()
        self.assertEqual(set(paths), {f'public/offsets/{name}' for name in self.module.FILES})

    def test_non_main_publish_refuses_before_install(self):
        _, repo = self.repository()
        self.git(repo, 'checkout', '-b', 'codex/repair-fixture')
        self.git(repo, 'branch', '--set-upstream-to=origin/main')
        before = (repo / 'public' / 'offsets' / 'offsets.json').read_bytes()
        self.assertEqual(self.invoke(repo, '--publish'), 1)
        self.assertEqual((repo / 'public' / 'offsets' / 'offsets.json').read_bytes(), before)


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell/Cargo wrapper')
class DumperWrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spiteware-wrapper-test-')
        self.directory = Path(self.tmp.name)
        shutil.copy2(ROOT / 'tools' / 'cs2-dumper' / 'build.ps1', self.directory)
        bin_dir = self.directory / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'rustc.cmd').write_text('@echo off\necho fake rustc\nexit /b 0\n')
        (bin_dir / 'cargo.cmd').write_text(
            '@echo off\necho %*>>"%TEST_CARGO_LOG%"\n'
            'if "%~1"=="--version" exit /b 0\n'
            'if "%~1"=="clean" exit /b 0\n'
            'if not "%TEST_CARGO_EXIT%"=="0" exit /b %TEST_CARGO_EXIT%\n'
            'if "%TEST_CARGO_OMIT_OUTPUT%"=="1" exit /b 0\n'
            'set profile=debug\nfor %%a in (%*) do if "%%a"=="--release" set profile=release\n'
            'if not exist target\\%profile% mkdir target\\%profile%\n'
            'echo fake-output>target\\%profile%\\cs2-dumper.exe\nexit /b 0\n')
        self.env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                        TEST_CARGO_LOG=str(self.directory / 'cargo.log'), TEST_CARGO_EXIT='0')

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapper(self, *args):
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                               str(self.directory / 'build.ps1'), *args], env=self.env,
                              capture_output=True, text=True)

    def test_debug_parameter_builds_locked_dev_profile_and_prints_its_path(self):
        result = self.run_wrapper('-Debug', '-Clean')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.directory / 'cargo.log').read_text().splitlines(),
                         ['--version', 'clean', 'build --locked'])
        self.assertIn('target\\debug\\cs2-dumper.exe', result.stdout)

    def test_default_build_uses_locked_release_profile(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.directory / 'cargo.log').read_text().splitlines(),
                         ['--version', 'build --locked --release'])

    def test_cargo_failure_is_propagated(self):
        self.env['TEST_CARGO_EXIT'] = '23'
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_success_without_output_is_rejected(self):
        self.env['TEST_CARGO_OMIT_OUTPUT'] = '1'
        self.assertNotEqual(self.run_wrapper().returncode, 0)


@unittest.skipUnless(os.name == 'nt', 'Windows setup download helper')
class SetupDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spiteware-setup-test-')
        self.directory = Path(self.tmp.name)
        self.target = self.directory / 'SpitewareLoader.exe'
        self.target.write_bytes(pe(b'previous-loader'))
        self.fixture = self.directory / 'response.bin'
        source = (ROOT / 'SpitewareSetup.bat').read_text(encoding='utf-8')
        section = source.split('\n:DO_DOWNLOAD\n', 1)[1].split('\n:DL_FAILED\n', 1)[0]
        prefix = 'powershell -NoProfile -Command "'
        command = next(line for line in section.splitlines() if line.startswith(prefix))
        self.command = command[len(prefix):-1].replace("'%LOADER_URL%'", '$env:LOADER_URL').replace(
            "'%LOADER_PATH%'", '$env:LOADER_PATH')

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, failure=False):
        stub = "function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing) "
        stub += "if ($env:TEST_DOWNLOAD_FAIL -eq '1') { throw 'fixture network failure' }; "
        stub += "[IO.File]::WriteAllBytes($OutFile,[IO.File]::ReadAllBytes($env:TEST_RESPONSE)) }; "
        script = self.directory / 'helper.ps1'
        script.write_text(stub + self.command)
        env = dict(os.environ, LOADER_PATH=str(self.target), LOADER_URL='https://example.invalid/fixture',
                   TEST_RESPONSE=str(self.fixture), TEST_DOWNLOAD_FAIL='1' if failure else '0')
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                              env=env, capture_output=True, text=True)

    def test_invalid_download_preserves_previous_loader(self):
        self.fixture.write_bytes(b'MZ invalid payload')
        before = self.target.read_bytes()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.target.read_bytes(), before)

    def test_failed_download_preserves_previous_loader(self):
        before = self.target.read_bytes()
        self.assertNotEqual(self.invoke(failure=True).returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)

    def test_valid_download_replaces_only_after_validation(self):
        self.fixture.write_bytes(pe(b'validated-loader'))
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.fixture.read_bytes())
        self.assertEqual(list(self.directory.glob('*.download-*')), [])

    def test_first_install_and_paths_with_spaces_and_apostrophes(self):
        folder = self.directory / "Michael's fixture path"
        folder.mkdir()
        self.target = folder / 'SpitewareLoader.exe'
        self.fixture.write_bytes(pe(b'first-install'))
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.fixture.read_bytes())


if __name__ == '__main__':
    unittest.main()
