"""
Regression test for the documented installation of the filter backends.

Listing a backend in DRF's `DEFAULT_FILTER_BACKENDS` makes DRF import it from
the class body of `GenericAPIView`, which runs while `rest_framework.viewsets`
is still initialising. A module-scope `from rest_framework.viewsets import
GenericViewSet` in the backend therefore prevents Django from starting at all.

Upstream drf-flex-fields has that import, so this configuration crashes there.
These tests run in a subprocess because the failure happens during
`django.setup()`.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

from django.test import SimpleTestCase

#: See the note in tests/test_settings_compat.py - the subprocess needs the
#: repo root as its working directory to import the library from source.
REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPT = textwrap.dedent("""
    import django
    from django.conf import settings

    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "rest_framework",
        ],
        DATABASES={{}},
        USE_TZ=True,
        REST_FRAMEWORK={{
            "DEFAULT_FILTER_BACKENDS": ("{backend}",),
        }},
    )
    django.setup()

    # Force DRF to resolve the setting, exactly as GenericAPIView does.
    from rest_framework.settings import api_settings
    backends = api_settings.DEFAULT_FILTER_BACKENDS
    import rest_framework.generics  # noqa: F401
    import rest_framework.viewsets  # noqa: F401

    print(backends[0].__name__)
    """)


#: Which DRF module the project happens to import first. This is the axis the
#: original regression test missed: reaching our package first is the only
#: order that used to work, and that is the order the test happened to use.
FIRST_IMPORTS = {
    "viewsets": "from rest_framework import viewsets",
    "generics": "from rest_framework import generics",
    "serializers": "from rest_framework import serializers\nfrom rest_framework import viewsets",
    "our_package_first": "import mind_flex_fields\nfrom rest_framework import viewsets",
}

BOOT_SCRIPT = textwrap.dedent("""
    import django
    from django.conf import settings

    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "rest_framework",
        ],
        DATABASES={{}},
        USE_TZ=True,
        REST_FRAMEWORK={{
            "DEFAULT_FILTER_BACKENDS": ("{backend}",),
        }},
    )
    django.setup()
    {first_import}
    print("OK")
    """)


class BootWithBackendInSettingsTests(SimpleTestCase):
    """
    Starting Django must work whatever order the imports happen in.

    Importing this package used to drag in `.views`, which subclasses
    `viewsets.ModelViewSet` at module scope - impossible while DRF is still
    initialising, which is when DRF resolves DEFAULT_FILTER_BACKENDS.
    """

    def _boot(self, backend: str, first_import: str):
        return subprocess.run(
            [
                sys.executable,
                "-c",
                BOOT_SCRIPT.format(backend=backend, first_import=first_import),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    def test_every_import_order_starts_cleanly(self):
        backends = (
            "mind_flex_fields.filter_backends.FlexFieldsFilterBackend",
            "mind_flex_fields.filter_backends.FlexFieldsDocsFilterBackend",
        )
        for backend in backends:
            for label, first_import in FIRST_IMPORTS.items():
                with self.subTest(backend=backend.rsplit(".", 1)[-1], first=label):
                    result = self._boot(backend, first_import)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("OK", result.stdout)

    def test_importing_the_package_does_not_load_drf_viewsets(self):
        """The property that keeps the import order from mattering."""
        script = textwrap.dedent("""
            import django
            from django.conf import settings

            settings.configure(
                INSTALLED_APPS=["django.contrib.contenttypes"],
                DATABASES={},
                USE_TZ=True,
            )
            django.setup()

            import sys
            import mind_flex_fields

            assert "rest_framework.viewsets" not in sys.modules, "viewsets leaked"
            assert "rest_framework.serializers" not in sys.modules, "serializers leaked"

            # ...and the names still resolve on demand.
            assert mind_flex_fields.FlexFieldsModelViewSet is not None
            assert "rest_framework.viewsets" in sys.modules
            print("OK")
            """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_unknown_attribute_still_raises_attribute_error(self):
        import mind_flex_fields

        with self.assertRaises(AttributeError):
            mind_flex_fields.NoSuchThing

    def test_lazy_names_are_listed_by_dir(self):
        import mind_flex_fields

        for name in (
            "FlexFieldsModelSerializer",
            "FlexFieldsSerializerMixin",
            "FlexFieldsMixin",
            "FlexFieldsModelViewSet",
        ):
            self.assertIn(name, dir(mind_flex_fields))


class FilterBackendAsDefaultTests(SimpleTestCase):
    def _boot(self, backend: str):
        return subprocess.run(
            [sys.executable, "-c", SCRIPT.format(backend=backend)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    def test_query_optimizing_backend_can_be_a_default(self):
        result = self._boot("mind_flex_fields.filter_backends.FlexFieldsFilterBackend")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "FlexFieldsFilterBackend")

    def test_docs_backend_can_be_a_default(self):
        result = self._boot(
            "mind_flex_fields.filter_backends.FlexFieldsDocsFilterBackend"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "FlexFieldsDocsFilterBackend")

    def test_module_does_not_import_viewsets_at_module_scope(self):
        """The import must stay behind `TYPE_CHECKING`."""
        from pathlib import Path

        import mind_flex_fields.filter_backends as module

        source = Path(module.__file__).read_text()
        import_line = "from rest_framework.viewsets import GenericViewSet"

        self.assertIn(import_line, source)
        # It must appear only inside the TYPE_CHECKING block.
        before = source.split(import_line)[0]
        self.assertIn("if TYPE_CHECKING:", before)
        self.assertNotIn("GenericViewSet", vars(module))
