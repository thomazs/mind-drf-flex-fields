"""
Tests for the optional `mind-drf-flex-fields-compat` shim (in `compat/`).

The shim provides the old `rest_flex_fields` import path so that a project can
swap the dependency without rewriting anything yet - the dependency change and
the code change no longer have to land together.

The shim is a separate distribution and is not installed in the dev
environment, so these tests put `compat/` on `sys.path` explicitly. The boot
scenarios run in subprocesses to keep `rest_flex_fields` out of this process's
`sys.modules`.
"""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from django.test import SimpleTestCase

COMPAT_DIR = Path(__file__).resolve().parent.parent / "compat"
REPO_ROOT = Path(__file__).resolve().parent.parent

#: The shim is its own distribution and is pruned from the main sdist, so
#: these tests only run from a source checkout.
requires_compat_source = unittest.skipUnless(
    (COMPAT_DIR / "rest_flex_fields" / "__init__.py").is_file(),
    "compat/ is only present in a source checkout",
)


def run_snippet(body: str) -> subprocess.CompletedProcess:
    """Run `body` in a subprocess that can see the shim and the library."""
    script = textwrap.dedent("""
        import django
        from django.conf import settings

        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            USE_TZ=True,
            REST_FLEX_FIELDS={"EXPAND_PARAM": "expand"},
            REST_FRAMEWORK={
                "DEFAULT_FILTER_BACKENDS": (
                    "rest_flex_fields.filter_backends.FlexFieldsFilterBackend",
                ),
            },
        )
        django.setup()
        """) + textwrap.dedent(body)

    return subprocess.run(
        [sys.executable, "-W", "ignore::DeprecationWarning", "-c", script],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": f"{COMPAT_DIR}:{REPO_ROOT}",
        },
    )


@requires_compat_source
class ShimPackagingTests(SimpleTestCase):
    def test_shim_ships_every_public_submodule(self):
        shipped = {p.stem for p in (COMPAT_DIR / "rest_flex_fields").glob("*.py")}
        self.assertEqual(
            shipped,
            {"__init__", "serializers", "views", "utils", "filter_backends"},
        )

    def test_shim_is_a_separate_distribution(self):
        """
        It must not be part of the main wheel: installing the library should
        never hijack the `rest_flex_fields` name.
        """
        main_pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        self.assertNotIn("rest_flex_fields", main_pyproject)
        self.assertIn(
            "mind-drf-flex-fields-compat",
            (COMPAT_DIR / "pyproject.toml").read_text(),
        )


@requires_compat_source
class ShimResolutionTests(SimpleTestCase):
    def test_legacy_dotted_settings_path_resolves(self):
        """The failure that stopped projects booting at all."""
        result = run_snippet("""
            from rest_framework.settings import api_settings
            import mind_flex_fields.filter_backends as real

            backend = api_settings.DEFAULT_FILTER_BACKENDS[0]
            assert backend is real.FlexFieldsFilterBackend, backend
            print("OK", backend.__module__)
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK mind_flex_fields.filter_backends", result.stdout)

    def test_legacy_imports_yield_the_same_objects(self):
        result = run_snippet("""
            import mind_flex_fields
            from rest_flex_fields import (
                FlexFieldsModelSerializer,
                FlexFieldsSerializerMixin,
                FlexFieldsModelViewSet,
                is_expanded,
                is_included,
                split_levels,
                EXPAND_PARAM,
            )

            assert FlexFieldsModelSerializer is mind_flex_fields.FlexFieldsModelSerializer
            assert FlexFieldsSerializerMixin is mind_flex_fields.FlexFieldsSerializerMixin
            assert FlexFieldsModelViewSet is mind_flex_fields.FlexFieldsModelViewSet
            assert is_expanded is mind_flex_fields.is_expanded
            assert is_included is mind_flex_fields.is_included
            assert split_levels is mind_flex_fields.split_levels
            assert EXPAND_PARAM == "expand"
            print("OK")
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_legacy_submodule_imports(self):
        result = run_snippet("""
            import mind_flex_fields.serializers
            import mind_flex_fields.utils
            import mind_flex_fields.views
            from rest_flex_fields.serializers import FlexFieldsModelSerializer
            from rest_flex_fields.utils import split_levels
            from rest_flex_fields.views import FlexFieldsMixin

            assert FlexFieldsModelSerializer is (
                mind_flex_fields.serializers.FlexFieldsModelSerializer
            )
            assert split_levels is mind_flex_fields.utils.split_levels
            assert FlexFieldsMixin is mind_flex_fields.views.FlexFieldsMixin
            print("OK")
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_unknown_attribute_still_raises_attribute_error(self):
        result = run_snippet("""
            import rest_flex_fields.filter_backends as shim
            try:
                shim.NoSuchThing
            except AttributeError as exc:
                print("OK", exc)
            else:
                raise SystemExit("expected AttributeError")
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("has no attribute 'NoSuchThing'", result.stdout)

    def test_importing_the_shim_warns(self):
        result = subprocess.run(
            [
                sys.executable,
                "-W",
                "error::DeprecationWarning",
                "-c",
                "import django;from django.conf import settings;"
                "settings.configure(INSTALLED_APPS=[],DATABASES={},USE_TZ=True);"
                "django.setup();import rest_flex_fields",
            ],
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": f"{COMPAT_DIR}:{REPO_ROOT}",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compatibility shim", result.stderr)


@requires_compat_source
class ShimEndToEndTests(SimpleTestCase):
    def test_serialization_works_through_the_legacy_path(self):
        result = run_snippet("""
            from django.db import connection, models
            from rest_flex_fields import FlexFieldsModelSerializer

            class Author(models.Model):
                name = models.CharField(max_length=50)
                class Meta:
                    app_label = "compatcheck"

            class Book(models.Model):
                title = models.CharField(max_length=50)
                author = models.ForeignKey(Author, on_delete=models.CASCADE)
                class Meta:
                    app_label = "compatcheck"

            class AuthorSerializer(FlexFieldsModelSerializer):
                class Meta:
                    model = Author
                    fields = ["id", "name"]

            class BookSerializer(FlexFieldsModelSerializer):
                class Meta:
                    model = Book
                    fields = ["id", "title", "author"]
                    expandable_fields = {"author": AuthorSerializer}

            with connection.schema_editor() as se:
                se.create_model(Author)
                se.create_model(Book)

            a = Author.objects.create(name="Clarice")
            b = Book.objects.create(title="A Hora da Estrela", author=a)

            assert BookSerializer(b).data["author"] == a.id
            expanded = BookSerializer(b, expand=["author"]).data
            assert expanded["author"] == {"id": a.id, "name": "Clarice"}
            print("OK")
            """)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)
