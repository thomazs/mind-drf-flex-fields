"""
Tests for `get_expandable_fields` and the configurable attribute name.

`EXPANDABLE_FIELDS_ATTRIBUTE` is read at import time, like the package's other
options, so the cases that change it run in a subprocess.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

from django.test import SimpleTestCase
from rest_framework import serializers

from mind_flex_fields import (
    EXPANDABLE_FIELDS_ATTRIBUTE,
    FlexFieldsModelSerializer,
    expandable_fields_attribute_name,
    get_expandable_fields,
)
from tests.testapp.models import Company, Pet
from tests.testapp.serializers import CompanySerializer

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

    from mind_flex_fields import (
        EXPANDABLE_FIELDS_ATTRIBUTE,
        expandable_fields_attribute_name,
        get_expandable_fields,
    )

    class Holder:
        class Meta:
            pass

    setattr(Holder.Meta, EXPANDABLE_FIELDS_ATTRIBUTE, {{"a": 1}})

    print(EXPANDABLE_FIELDS_ATTRIBUTE, expandable_fields_attribute_name(), end=" ")
    print(get_expandable_fields(Holder))
    """)


def run_with_settings(setting: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", SCRIPT.format(setting=setting)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class AttributeNameTests(SimpleTestCase):
    def test_defaults_to_expandable_fields(self):
        self.assertEqual(EXPANDABLE_FIELDS_ATTRIBUTE, "expandable_fields")
        self.assertEqual(expandable_fields_attribute_name(), "expandable_fields")

    def test_configurable_through_mind_flex_fields(self):
        result = run_with_settings(
            'MIND_FLEX_FIELDS={"EXPANDABLE_FIELDS_ATTRIBUTE": "expand_map"},'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "expand_map expand_map {'a': 1}")

    def test_legacy_top_level_setting_is_honoured(self):
        """The option's first iteration was a top-level Django setting."""
        result = run_with_settings('MIND_EXPANDABLE_FIELDS_ATT="legacy_map",')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "legacy_map legacy_map {'a': 1}")

    def test_mind_flex_fields_wins_over_the_legacy_setting(self):
        result = run_with_settings(
            'MIND_FLEX_FIELDS={"EXPANDABLE_FIELDS_ATTRIBUTE": "new_map"}, '
            'MIND_EXPANDABLE_FIELDS_ATT="legacy_map",'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("new_map new_map", result.stdout)

    def test_rejects_a_non_string(self):
        result = run_with_settings(
            'MIND_FLEX_FIELDS={"EXPANDABLE_FIELDS_ATTRIBUTE": 123},'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("should be a string", result.stderr)

    def test_rejects_something_that_is_not_an_attribute_name(self):
        result = run_with_settings(
            'MIND_FLEX_FIELDS={"EXPANDABLE_FIELDS_ATTRIBUTE": "not an attr"},'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("valid attribute name", result.stderr)


class GetExpandableFieldsTests(SimpleTestCase):
    def test_reads_the_mapping_from_meta(self):
        class WithMeta:
            class Meta:
                expandable_fields = {"employer": CompanySerializer}

        self.assertEqual(
            get_expandable_fields(WithMeta), {"employer": CompanySerializer}
        )

    def test_reads_the_mapping_from_underscore_meta(self):
        """Some projects keep their serializer options on `_meta`."""

        class Options:
            expandable_fields = {"employer": CompanySerializer}

        class WithUnderscoreMeta:
            _meta = Options

        self.assertEqual(
            get_expandable_fields(WithUnderscoreMeta),
            {"employer": CompanySerializer},
        )

    def test_underscore_meta_takes_precedence(self):
        class Options:
            expandable_fields = {"from": "_meta"}

        class Both:
            _meta = Options

            class Meta:
                expandable_fields = {"from": "Meta"}

        self.assertEqual(get_expandable_fields(Both), {"from": "_meta"})

    def test_falls_through_to_meta_when_underscore_meta_is_silent(self):
        """
        `_meta` existing does not mean it declares the mapping - a Django
        model's `_meta`, for instance, never does.
        """

        class Unrelated:
            pass

        class Both:
            _meta = Unrelated

            class Meta:
                expandable_fields = {"from": "Meta"}

        self.assertEqual(get_expandable_fields(Both), {"from": "Meta"})

    def test_works_on_instances_as_well_as_classes(self):
        serializer = CompanySerializer()
        self.assertEqual(
            get_expandable_fields(serializer),
            get_expandable_fields(CompanySerializer),
        )

    def test_returns_an_empty_dict_when_nothing_is_declared(self):
        class Bare:
            pass

        self.assertEqual(get_expandable_fields(Bare), {})

    def test_honours_an_explicit_default(self):
        class Bare:
            pass

        sentinel = object()
        self.assertIs(get_expandable_fields(Bare, default=sentinel), sentinel)

    def test_distinguishes_declared_empty_from_not_declared(self):
        class DeclaredEmpty:
            class Meta:
                expandable_fields = {}

        class NotDeclared:
            class Meta:
                pass

        sentinel = object()
        self.assertEqual(get_expandable_fields(DeclaredEmpty, default=sentinel), {})
        self.assertIs(get_expandable_fields(NotDeclared, default=sentinel), sentinel)


class SerializerResolutionTests(SimpleTestCase):
    """How `_expandable_fields` combines Meta with the class attribute."""

    def test_meta_declaration_is_used(self):
        class PetSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Pet
                fields = ["name"]
                expandable_fields = {"owner": CompanySerializer}

        self.assertEqual(
            PetSerializer()._expandable_fields, {"owner": CompanySerializer}
        )

    def test_legacy_class_attribute_is_used_when_meta_is_silent(self):
        class PetSerializer(FlexFieldsModelSerializer):
            expandable_fields = {"owner": CompanySerializer}

            class Meta:
                model = Pet
                fields = ["name"]

        self.assertEqual(
            PetSerializer()._expandable_fields, {"owner": CompanySerializer}
        )

    def test_empty_meta_declaration_disables_expansion(self):
        """
        Emptying the Meta mapping is how a subclass turns expansion off. It
        must not fall through to an inherited class attribute - testing the
        mapping for truthiness instead of presence used to re-enable it.
        """

        class Base(FlexFieldsModelSerializer):
            expandable_fields = {"owner": CompanySerializer}

            class Meta:
                model = Pet
                fields = ["name"]

        class Disabled(Base):
            class Meta(Base.Meta):
                expandable_fields = {}

        self.assertEqual(Base()._expandable_fields, {"owner": CompanySerializer})
        self.assertEqual(Disabled()._expandable_fields, {})

    def test_empty_meta_declaration_is_honoured_end_to_end(self):
        company = Company(id=1, name="McDonalds")

        class Base(FlexFieldsModelSerializer):
            expandable_fields = {"employer": CompanySerializer}

            class Meta:
                model = Company
                fields = ["name"]

        class Disabled(Base):
            class Meta(Base.Meta):
                expandable_fields = {}

        self.assertEqual(list(Disabled(company, expand=["employer"]).data), ["name"])


class FilterBackendTraversalTests(SimpleTestCase):
    """The schema backend walks nested mappings through the same helper."""

    def test_traverses_nested_serializers_declared_on_underscore_meta(self):
        from mind_flex_fields.filter_backends import FlexFieldsDocsFilterBackend

        class LeafSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Company
                fields = ["name"]

        class MiddleOptions:
            expandable_fields = {"leaf": LeafSerializer}

        class MiddleSerializer(FlexFieldsModelSerializer):
            _meta = MiddleOptions

            class Meta:
                model = Company
                fields = ["name"]

        class RootSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Company
                fields = ["name"]
                expandable_fields = {"middle": MiddleSerializer}

        found = FlexFieldsDocsFilterBackend._get_expandable_fields(RootSerializer)

        self.assertIn("middle", found)
        self.assertIn("middle.leaf", found)

    def test_lazy_string_references_do_not_break_traversal(self):
        from mind_flex_fields.filter_backends import FlexFieldsDocsFilterBackend

        class RootSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Company
                fields = ["name"]
                expandable_fields = {
                    "lazy": "tests.testapp.serializers.CompanySerializer",
                    "lazy_many": (
                        "tests.testapp.serializers.CompanySerializer",
                        {"many": True},
                    ),
                    "method": serializers.SerializerMethodField,
                }

        found = FlexFieldsDocsFilterBackend._get_expandable_fields(RootSerializer)

        self.assertEqual(sorted(found), ["lazy", "lazy_many", "method"])
