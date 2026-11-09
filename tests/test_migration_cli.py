"""
Tests for the migration engine and its CLI (`mind_flex_fields_migrate`).

The migration is deliberately *not* a management command: a management command
needs Django to boot, and half-way through the migration it cannot. A project
whose settings still name `rest_flex_fields.filter_backends` dies during
`django.setup()`, because that module fails to import on current DRF - and
installing the old package alongside does not help, since it is the old module
itself that is broken. So the tool must work without Django.
"""

import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

import mind_flex_fields_migrate as migration

#: Resolved from this file, not the working directory, so the test does not
#: depend on where pytest was invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent


class MigrationTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_cli(self, *args):
        """Run the CLI against the temp project; returns (code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = migration.main(["--path", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()


class EngineApiTests(MigrationTestCase):
    """The engine is importable and usable as a library."""

    def test_plan_reports_changes_without_writing(self):
        path = self.write("app.py", "from rest_flex_fields import x\n")

        changes, skipped = migration.plan(self.root)

        self.assertEqual(skipped, [])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].path, path.resolve())
        self.assertEqual(changes[0].total, 1)
        self.assertEqual(path.read_text(), "from rest_flex_fields import x\n")

    def test_apply_writes_planned_changes(self):
        path = self.write("app.py", "from rest_flex_fields import x\n")

        changes, _ = migration.plan(self.root)
        written, errors = migration.apply(changes)

        self.assertEqual((written, errors), (1, []))
        self.assertEqual(path.read_text(), "from mind_flex_fields import x\n")

    def test_engine_does_not_import_django(self):
        """The module must stay usable when Django cannot be configured."""
        source = Path(migration.__file__).read_text()
        self.assertNotIn("import django", source)
        self.assertNotIn("from django", source)

    def test_lives_outside_the_package(self):
        """
        Inside `mind_flex_fields` it would be unusable: that package's
        `__init__` reads Django settings at import time.
        """
        self.assertEqual(migration.__name__, "mind_flex_fields_migrate")
        self.assertNotIn(".", migration.__name__)


class ImportRewritingTests(MigrationTestCase):
    def test_rewrites_import_statements(self):
        path = self.write(
            "api/serializers.py",
            "from rest_flex_fields import FlexFieldsModelSerializer\n"
            "from rest_flex_fields.serializers import FlexFieldsSerializerMixin\n"
            "import rest_flex_fields\n",
        )

        self.run_cli("--noinput")

        self.assertEqual(
            path.read_text(),
            "from mind_flex_fields import FlexFieldsModelSerializer\n"
            "from mind_flex_fields.serializers import FlexFieldsSerializerMixin\n"
            "import mind_flex_fields\n",
        )

    def test_rewrites_dotted_strings(self):
        """The settings reference that breaks a project mid-migration."""
        path = self.write(
            "settings.py",
            'BACKENDS = ("rest_flex_fields.filter_backends.FlexFieldsFilterBackend",)\n',
        )

        self.run_cli("--noinput")

        self.assertIn("mind_flex_fields.filter_backends", path.read_text())

    def test_does_not_touch_similarly_named_packages(self):
        """`rest_flex_fields_extra` is a different package; leave it alone."""
        path = self.write(
            "api/other.py",
            "import rest_flex_fields_extra\n" "from my_rest_flex_fields import thing\n",
        )

        self.run_cli("--noinput")

        self.assertEqual(
            path.read_text(),
            "import rest_flex_fields_extra\n" "from my_rest_flex_fields import thing\n",
        )

    def test_is_idempotent(self):
        path = self.write("api/views.py", "from rest_flex_fields import x\n")

        self.run_cli("--noinput")
        first = path.read_text()
        _, out, _ = self.run_cli("--noinput")

        self.assertEqual(path.read_text(), first)
        self.assertIn("Nothing to migrate", out)

    def test_nothing_to_do_on_a_clean_project(self):
        self.write("app.py", "from mind_flex_fields import x\n")

        code, out, _ = self.run_cli("--noinput")

        self.assertEqual(code, 0)
        self.assertIn("Nothing to migrate", out)


class ExtensionTests(MigrationTestCase):
    def test_only_rewrites_python_by_default(self):
        template = self.write("api/page.html", "rest_flex_fields\n")

        self.run_cli("--noinput")

        self.assertEqual(template.read_text(), "rest_flex_fields\n")

    def test_extension_option(self):
        template = self.write("api/page.html", "rest_flex_fields\n")

        self.run_cli("--extension", "html", "--noinput")

        self.assertEqual(template.read_text(), "mind_flex_fields\n")


class ExclusionTests(MigrationTestCase):
    def test_skips_noise_directories(self):
        paths = [
            self.write(f"{d}/x.py", "from rest_flex_fields import x\n")
            for d in (".git", "__pycache__", ".venv", "node_modules", "dist")
        ]

        self.run_cli("--noinput")

        for path in paths:
            self.assertEqual(
                path.read_text(),
                "from rest_flex_fields import x\n",
                f"{path} should have been skipped",
            )

    def test_exclude_option(self):
        path = self.write("legacy/x.py", "from rest_flex_fields import x\n")

        self.run_cli("--exclude", "legacy", "--noinput")

        self.assertEqual(path.read_text(), "from rest_flex_fields import x\n")

    def test_never_rewrites_its_own_package(self):
        """
        Running over this repo must never list a file belonging to the library
        itself, even though its test suite mentions the old name. Kept as a dry
        run so the check cannot damage the working tree.
        """
        import mind_flex_fields

        package_dir = Path(mind_flex_fields.__file__).resolve().parent
        repo_root = package_dir.parent

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            migration.main(["--path", str(repo_root), "--dry-run"])

        listed = out.getvalue()
        self.assertNotIn(f"{package_dir.name}/", listed)


class DryRunTests(MigrationTestCase):
    def test_dry_run_writes_nothing(self):
        path = self.write("app.py", "from rest_flex_fields import x\n")

        code, out, _ = self.run_cli("--dry-run")

        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(), "from rest_flex_fields import x\n")
        self.assertIn("Dry run", out)
        self.assertIn("1 replacement(s) across 1 file(s)", out)

    def test_diff_output(self):
        self.write("app.py", "from rest_flex_fields import x\n")

        _, out, _ = self.run_cli("--dry-run", "--diff")

        self.assertIn("-from rest_flex_fields import x", out)
        self.assertIn("+from mind_flex_fields import x", out)


class RequirementsTests(MigrationTestCase):
    def test_requirements_untouched_by_default(self):
        path = self.write("requirements.txt", "drf-flex-fields==1.0.2\n")

        self.run_cli("--noinput")

        self.assertEqual(path.read_text(), "drf-flex-fields==1.0.2\n")

    def test_include_requirements_renames_distribution(self):
        path = self.write("requirements.txt", "Django>=5.2\ndrf-flex-fields\n")

        self.run_cli("--include-requirements", "--noinput")

        self.assertEqual(path.read_text(), "Django>=5.2\nmind-drf-flex-fields\n")

    def test_include_requirements_handles_pyproject(self):
        path = self.write("pyproject.toml", 'dependencies = ["drf-flex-fields>=1.0"]\n')

        self.run_cli("--include-requirements", "--noinput")

        self.assertIn("mind-drf-flex-fields>=1.0", path.read_text())

    def test_does_not_double_prefix_already_migrated_name(self):
        path = self.write("requirements.txt", "mind-drf-flex-fields==1.0\n")

        self.run_cli("--include-requirements", "--noinput")

        self.assertEqual(path.read_text(), "mind-drf-flex-fields==1.0\n")

    def test_stale_pin_detection(self):
        self.write("requirements.txt", "drf-flex-fields==1.0.2\n")

        changes, _ = migration.plan(self.root, include_requirements=True)

        self.assertEqual(changes[0].stale_pins(), ["mind-drf-flex-fields==1.0.2"])

    def test_warns_about_stale_pin(self):
        self.write("requirements.txt", "drf-flex-fields==1.0.2\n")

        _, out, _ = self.run_cli("--include-requirements", "--noinput")

        self.assertIn("Check these version specifiers", out)
        self.assertIn("mind-drf-flex-fields==1.0.2", out)

    def test_no_pin_warning_without_specifier(self):
        self.write("requirements.txt", "drf-flex-fields\n")

        _, out, _ = self.run_cli("--include-requirements", "--noinput")

        self.assertNotIn("Check these version specifiers", out)


class SettingsRenameTests(MigrationTestCase):
    def test_setting_kept_by_default(self):
        """`REST_FLEX_FIELDS` still works, so it is not renamed unasked."""
        path = self.write("settings.py", 'REST_FLEX_FIELDS = {"a": 1}\n')

        _, out, _ = self.run_cli("--noinput")

        self.assertEqual(path.read_text(), 'REST_FLEX_FIELDS = {"a": 1}\n')
        self.assertIn("Nothing to migrate", out)

    def test_rename_settings_option(self):
        path = self.write("settings.py", 'REST_FLEX_FIELDS = {"a": 1}\n')

        self.run_cli("--rename-settings", "--noinput")

        self.assertEqual(path.read_text(), 'MIND_FLEX_FIELDS = {"a": 1}\n')


class ConfirmationTests(MigrationTestCase):
    def test_aborts_when_user_declines(self):
        path = self.write("app.py", "from rest_flex_fields import x\n")

        with patch("builtins.input", return_value="n"):
            code, out, _ = self.run_cli()

        self.assertEqual(code, 1)
        self.assertEqual(path.read_text(), "from rest_flex_fields import x\n")
        self.assertIn("Aborted", out)

    def test_writes_when_user_accepts(self):
        path = self.write("app.py", "from rest_flex_fields import x\n")

        with patch("builtins.input", return_value="y"):
            code, _, _ = self.run_cli()

        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(), "from mind_flex_fields import x\n")


class ErrorHandlingTests(MigrationTestCase):
    def test_missing_directory_exits_with_error(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = migration.main(["--path", str(self.root / "nope")])

        self.assertEqual(code, 2)
        self.assertIn("is not a directory", err.getvalue())

    def test_skips_undecodable_files(self):
        (self.root / "blob.py").write_bytes(b"\xff\xfe\x00rest_flex_fields")
        self.write("app.py", "from rest_flex_fields import x\n")

        code, out, err = self.run_cli("--noinput")

        self.assertEqual(code, 0)
        self.assertIn("Skipped", err)
        self.assertIn("Rewrote 1 file(s)", out)


class WithoutDjangoTests(MigrationTestCase):
    """
    The reason this is a CLI and not a management command: it must work in a
    process that has no DJANGO_SETTINGS_MODULE at all.
    """

    def test_runs_as_module_without_django_settings(self):
        self.write("app.py", "from rest_flex_fields import x\n")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mind_flex_fields_migrate",
                "--path",
                str(self.root),
                "--noinput",
            ],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Rewrote 1 file(s)", result.stdout)
        self.assertEqual(
            (self.root / "app.py").read_text(),
            "from mind_flex_fields import x\n",
        )
