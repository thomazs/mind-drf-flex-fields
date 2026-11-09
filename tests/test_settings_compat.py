"""
Tests for settings resolution.

`mind_flex_fields` reads its options at import time, so each case runs in a
fresh subprocess with its own Django settings.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

from django.test import SimpleTestCase

#: Subprocesses must import the library from the source tree, so they run
#: with the repo root as their working directory - resolved from this file
#: rather than inherited, so it does not matter where pytest was invoked.
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
        {setting}
    )
    django.setup()

    import mind_flex_fields as m

    print(m.EXPAND_PARAM, m.FIELDS_PARAM, m.OMIT_PARAM, m.MAXIMUM_EXPANSION_DEPTH)
    """)


class SettingsResolutionTests(SimpleTestCase):
    def _resolve(self, setting: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT.format(setting=setting)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_defaults_when_nothing_is_configured(self):
        self.assertEqual(self._resolve(""), "expand fields omit None")

    def test_reads_mind_flex_fields(self):
        self.assertEqual(
            self._resolve('MIND_FLEX_FIELDS={"EXPAND_PARAM": "include"},'),
            "include fields omit None",
        )

    def test_falls_back_to_legacy_rest_flex_fields(self):
        """Projects migrating from drf-flex-fields keep their settings."""
        self.assertEqual(
            self._resolve(
                'REST_FLEX_FIELDS={"EXPAND_PARAM": "legacy", '
                '"MAXIMUM_EXPANSION_DEPTH": 3},'
            ),
            "legacy fields omit 3",
        )

    def test_mind_flex_fields_takes_precedence_over_legacy(self):
        self.assertEqual(
            self._resolve(
                'MIND_FLEX_FIELDS={"EXPAND_PARAM": "new"}, '
                'REST_FLEX_FIELDS={"EXPAND_PARAM": "legacy"},'
            ),
            "new fields omit None",
        )

    def test_rejects_non_dict_setting(self):
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT.format(setting='MIND_FLEX_FIELDS="nope",')],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("should be a dict", result.stderr)
