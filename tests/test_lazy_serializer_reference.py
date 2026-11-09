"""
Tests for how `expandable_fields` values are resolved into serializers:
classes, lazy dotted strings, callables (upstream #138) and field classes.
"""

from django.test import RequestFactory, TestCase
from rest_framework import serializers

from mind_flex_fields import FlexFieldsModelSerializer
from tests.testapp.models import Company, Person
from tests.testapp.serializers import CompanySerializer


def company_serializer_factory():
    """Stands in for a project's own loader, e.g. `get_api_class(...)`."""
    return CompanySerializer


class LazyReferenceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="McDonalds")
        self.person = Person.objects.create(
            name="Fred", hobbies="sailing", employer=self.company
        )

    def _expanded(self, serializer_class):
        return serializer_class(self.person, expand=["employer"]).data["employer"]

    def test_direct_class_reference(self):
        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {"employer": CompanySerializer}

        self.assertEqual(
            self._expanded(PersonSerializer), {"name": "McDonalds", "public": False}
        )

    def test_lazy_string_reference(self):
        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {
                    "employer": "tests.testapp.serializers.CompanySerializer"
                }

        self.assertEqual(
            self._expanded(PersonSerializer), {"name": "McDonalds", "public": False}
        )

    def test_callable_reference(self):
        """A factory that returns the serializer class."""

        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {"employer": company_serializer_factory}

        self.assertEqual(
            self._expanded(PersonSerializer), {"name": "McDonalds", "public": False}
        )

    def test_callable_reference_with_options(self):
        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {
                    "employer": (company_serializer_factory, {"fields": ["name"]})
                }

        self.assertEqual(self._expanded(PersonSerializer), {"name": "McDonalds"})

    def test_lambda_reference(self):
        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {"employer": lambda: CompanySerializer}

        self.assertEqual(
            self._expanded(PersonSerializer), {"name": "McDonalds", "public": False}
        )

    def test_field_classes_are_not_called_as_factories(self):
        """
        `SerializerMethodField` is a callable class and a supported value; the
        callable branch must leave it alone.
        """

        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name"]
                expandable_fields = {"nickname": serializers.SerializerMethodField}

            def get_nickname(self, obj):
                return obj.name.upper()

        data = PersonSerializer(self.person, expand=["nickname"]).data
        self.assertEqual(data["nickname"], "FRED")


class PlainRequestInContextTests(TestCase):
    """
    Building a serializer by hand with a plain Django request in the context
    used to raise `AttributeError: 'WSGIRequest' object has no attribute
    'query_params'` (upstream #128).
    """

    def setUp(self):
        self.company = Company.objects.create(name="McDonalds")
        self.person = Person.objects.create(
            name="Fred", hobbies="sailing", employer=self.company
        )

        class PersonSerializer(FlexFieldsModelSerializer):
            class Meta:
                model = Person
                fields = ["name", "hobbies"]
                expandable_fields = {"employer": CompanySerializer}

        self.serializer_class = PersonSerializer

    def test_expansion_from_a_plain_django_request(self):
        request = RequestFactory().get("/people/?expand=employer")

        data = self.serializer_class(self.person, context={"request": request}).data

        self.assertEqual(data["employer"], {"name": "McDonalds", "public": False})

    def test_sparse_fields_from_a_plain_django_request(self):
        request = RequestFactory().get("/people/?fields=name")

        data = self.serializer_class(self.person, context={"request": request}).data

        self.assertEqual(list(data), ["name"])

    def test_repeated_parameters_from_a_plain_django_request(self):
        request = RequestFactory().get("/people/?omit=hobbies&omit=name")

        data = self.serializer_class(self.person, context={"request": request}).data

        self.assertEqual(list(data), [])

    def test_a_drf_request_still_behaves_the_same(self):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        plain = RequestFactory().get("/people/?expand=employer")
        drf = Request(APIRequestFactory().get("/people/?expand=employer"))

        self.assertEqual(
            self.serializer_class(self.person, context={"request": plain}).data,
            self.serializer_class(self.person, context={"request": drf}).data,
        )
