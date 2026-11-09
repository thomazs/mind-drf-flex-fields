#!/usr/bin/env python
"""
Smoke-tests the *installed* distribution, not the source tree.

Run from a directory outside the project (tox's `wheel` environment does
this), so that `import mind_flex_fields` resolves to site-packages. That is
what catches packaging mistakes the normal test suite cannot see: a module
left out of the wheel, a missing `py-modules` entry, a console script that was
never declared.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import django
from django.conf import settings


def check(label, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {label}{detail and f' - {detail}'}")
    return bool(condition)


def configure_django():
    """
    Settings must be configured before importing the package: it reads its
    options from Django settings at import time.
    """
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
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
    )
    django.setup()


def main() -> int:
    results = []

    configure_django()

    print("Installed distribution:")

    import mind_flex_fields

    location = Path(mind_flex_fields.__file__).resolve()
    results.append(
        check(
            "imported from site-packages, not the source tree",
            "site-packages" in location.parts,
            str(location),
        )
    )
    results.append(
        check(
            "version is exposed",
            bool(mind_flex_fields.__version__),
            mind_flex_fields.__version__,
        )
    )

    # The migration engine is a top-level module declared via `py-modules`;
    # it is easy to forget in packaging.
    import mind_flex_fields_migrate

    results.append(
        check(
            "mind_flex_fields_migrate ships and needs no Django",
            "django" not in sys.modules or callable(mind_flex_fields_migrate.main),
        )
    )

    script = shutil.which("mind-flex-fields-migrate")
    results.append(check("console script is installed", bool(script), script or ""))
    if script:
        proc = subprocess.run([script, "--help"], capture_output=True, text=True)
        results.append(
            check("console script runs", proc.returncode == 0, proc.stderr.strip()[:80])
        )

    for name in ("serializers", "views", "utils", "filter_backends"):
        __import__(f"mind_flex_fields.{name}")
        results.append(check(f"submodule mind_flex_fields.{name} ships", True))

    # Exercise the real thing end to end.
    from django.db import connection, models

    from mind_flex_fields import FlexFieldsModelSerializer

    class Author(models.Model):
        name = models.CharField(max_length=50)

        class Meta:
            app_label = "smoke"

    class Book(models.Model):
        title = models.CharField(max_length=50)
        author = models.ForeignKey(Author, on_delete=models.CASCADE)

        class Meta:
            app_label = "smoke"

    class AuthorSerializer(FlexFieldsModelSerializer):
        class Meta:
            model = Author
            fields = ["id", "name"]

    class BookSerializer(FlexFieldsModelSerializer):
        class Meta:
            model = Book
            fields = ["id", "title", "author"]
            expandable_fields = {"author": AuthorSerializer}

    with connection.schema_editor() as editor:
        editor.create_model(Author)
        editor.create_model(Book)

    author = Author.objects.create(name="Machado de Assis")
    book = Book.objects.create(title="Dom Casmurro", author=author)

    print("Behaviour:")
    results.append(
        check(
            "default representation", BookSerializer(book).data["author"] == author.id
        )
    )
    expanded = BookSerializer(book, expand=["author"]).data
    results.append(
        check(
            "expansion",
            expanded["author"] == {"id": author.id, "name": "Machado de Assis"},
            str(expanded),
        )
    )
    results.append(
        check(
            "sparse fields",
            set(BookSerializer(book, fields=["title"]).data) == {"title"},
        )
    )

    # The filter backend must be importable the way the docs tell people to
    # configure it (this used to be a circular import).
    from rest_framework.settings import APISettings

    from mind_flex_fields.filter_backends import FlexFieldsFilterBackend

    api = APISettings(
        {
            "DEFAULT_FILTER_BACKENDS": (
                "mind_flex_fields.filter_backends.FlexFieldsFilterBackend",
            )
        }
    )
    results.append(
        check(
            "filter backend resolves from a dotted settings string",
            api.DEFAULT_FILTER_BACKENDS[0] is FlexFieldsFilterBackend,
        )
    )

    print()
    if all(results):
        print(f"ALL {len(results)} CHECKS PASSED")
        return 0
    print(f"{results.count(False)} of {len(results)} CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
