#!/usr/bin/env python
"""
Smoke-tests the compatibility shim with both distributions actually installed.

The unit tests in `tests/test_compat_shim.py` point PYTHONPATH at `compat/`;
this script instead uses `mind-drf-flex-fields` and
`mind-drf-flex-fields-compat` as a user would install them, from outside the
source tree. tox's `shim` environment runs it.
"""

import sys
import warnings
from pathlib import Path

import django
from django.conf import settings


def check(label, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {label}{detail and f' - {detail}'}")
    return bool(condition)


def main() -> int:
    results = []

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
        # Legacy names, left exactly as an unmigrated project would have them.
        REST_FLEX_FIELDS={"EXPAND_PARAM": "expand"},
        REST_FRAMEWORK={
            "DEFAULT_FILTER_BACKENDS": (
                "rest_flex_fields.filter_backends.FlexFieldsFilterBackend",
            )
        },
    )
    django.setup()

    print("Installed shim:")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import rest_flex_fields

    results.append(
        check(
            "importing the shim warns",
            any(issubclass(w.category, DeprecationWarning) for w in caught),
        )
    )

    location = Path(rest_flex_fields.__file__).resolve()
    results.append(
        check(
            "shim comes from site-packages",
            "site-packages" in location.parts,
            str(location),
        )
    )

    import mind_flex_fields

    results.append(
        check(
            "shim hands out the same objects",
            rest_flex_fields.FlexFieldsModelSerializer
            is mind_flex_fields.FlexFieldsModelSerializer,
        )
    )

    # The failure that stopped unmigrated projects from booting at all.
    from rest_framework.settings import api_settings

    import mind_flex_fields.filter_backends as real

    backend = api_settings.DEFAULT_FILTER_BACKENDS[0]
    results.append(
        check(
            "legacy dotted settings path resolves",
            backend is real.FlexFieldsFilterBackend,
            f"{backend.__module__}.{backend.__name__}",
        )
    )

    from django.db import connection, models

    from rest_flex_fields import FlexFieldsModelSerializer

    class Tag(models.Model):
        name = models.CharField(max_length=50)

        class Meta:
            app_label = "shimsmoke"

    class Post(models.Model):
        title = models.CharField(max_length=50)
        tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

        class Meta:
            app_label = "shimsmoke"

    class TagSerializer(FlexFieldsModelSerializer):
        class Meta:
            model = Tag
            fields = ["id", "name"]

    class PostSerializer(FlexFieldsModelSerializer):
        class Meta:
            model = Post
            fields = ["id", "title", "tag"]
            expandable_fields = {"tag": TagSerializer}

    with connection.schema_editor() as editor:
        editor.create_model(Tag)
        editor.create_model(Post)

    tag = Tag.objects.create(name="livros")
    post = Post.objects.create(title="Dom Casmurro", tag=tag)

    print("Behaviour through the legacy path:")
    expanded = PostSerializer(post, expand=["tag"]).data
    results.append(
        check(
            "expansion works",
            expanded["tag"] == {"id": tag.id, "name": "livros"},
            str(expanded),
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
