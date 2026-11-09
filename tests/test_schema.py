"""
Tests covering OpenAPI schema generation.

The upstream project exposed the `fields`, `omit` and `expand` query
parameters through CoreAPI (`get_schema_fields`), which was removed from
Django REST Framework in 3.15. These tests assert that the parameters are
still documented through the OpenAPI path (`get_schema_operation_parameters`).
"""

import unittest

from django.test import TestCase
from rest_framework.schemas.openapi import SchemaGenerator

from mind_flex_fields.filter_backends import (
    FlexFieldsDocsFilterBackend,
    FlexFieldsFilterBackend,
)
from tests.testapp.views import PetViewSet, TaggedItemViewSet

try:  # pragma: no cover - optional dependencies of DRF's schema generator
    import inflection  # noqa: F401
    import uritemplate  # noqa: F401

    SCHEMA_DEPS_INSTALLED = True
except ImportError:  # pragma: no cover
    SCHEMA_DEPS_INSTALLED = False


class TestFilterBackendsAreCoreApiFree(TestCase):
    def test_backends_do_not_define_coreapi_schema_fields(self):
        """
        CoreAPI support was dropped: neither backend may implement
        `get_schema_fields`. Older DRF releases still define it on
        `BaseFilterBackend`, so we check our own classes only.
        """
        self.assertNotIn("get_schema_fields", FlexFieldsDocsFilterBackend.__dict__)
        self.assertNotIn("get_schema_fields", FlexFieldsFilterBackend.__dict__)

    def test_module_does_not_import_coreapi(self):
        import mind_flex_fields.filter_backends as module

        source_names = vars(module).keys()
        self.assertNotIn("coreapi", source_names)
        self.assertNotIn("coreschema", source_names)


class TestSchemaOperationParameters(TestCase):
    def setUp(self):
        self.backend = FlexFieldsDocsFilterBackend()

    def _make_view(self, view_class):
        view = view_class()
        view.request = None
        view.format_kwarg = None
        return view

    def test_exposes_flex_fields_query_params(self):
        params = self.backend.get_schema_operation_parameters(
            self._make_view(PetViewSet)
        )

        self.assertEqual([p["name"] for p in params], ["fields", "omit", "expand"])
        for param in params:
            self.assertEqual(param["in"], "query")
            self.assertFalse(param["required"])

    def test_expand_param_enumerates_expandable_fields(self):
        params = self.backend.get_schema_operation_parameters(
            self._make_view(PetViewSet)
        )
        expand = next(p for p in params if p["name"] == "expand")
        enum = expand["schema"]["items"]["enum"]

        self.assertIn("owner", enum)
        self.assertIn("sold_from", enum)
        self.assertIn("*", enum)
        self.assertIn("~all", enum)

    def test_fields_param_example_lists_serializer_fields(self):
        params = self.backend.get_schema_operation_parameters(
            self._make_view(PetViewSet)
        )
        fields = next(p for p in params if p["name"] == "fields")

        self.assertIn("name", fields["example"])
        self.assertEqual(fields["schema"]["type"], "string")

    def test_serializer_without_expandable_fields_only_lists_wildcards(self):
        params = self.backend.get_schema_operation_parameters(
            self._make_view(TaggedItemViewSet)
        )
        # TaggedItemSerializer is a flex serializer, but has no expandable fields.
        self.assertEqual([p["name"] for p in params], ["fields", "omit", "expand"])
        expand = next(p for p in params if p["name"] == "expand")
        self.assertEqual(expand["schema"]["items"]["enum"], ["~all", "*"])


@unittest.skipUnless(
    SCHEMA_DEPS_INSTALLED,
    "requires the `openapi` extra (uritemplate + inflection)",
)
class TestFullOpenApiSchemaGeneration(TestCase):
    def test_schema_generation_includes_flex_params(self):
        original_backends = PetViewSet.filter_backends
        PetViewSet.filter_backends = [FlexFieldsFilterBackend]
        try:
            generator = SchemaGenerator(title="Test API", version="1.0.0")
            schema = generator.get_schema(request=None, public=True)
        finally:
            PetViewSet.filter_backends = original_backends

        params = schema["paths"]["/pets/"]["get"]["parameters"]
        names = [p["name"] for p in params]

        self.assertIn("fields", names)
        self.assertIn("omit", names)
        self.assertIn("expand", names)
