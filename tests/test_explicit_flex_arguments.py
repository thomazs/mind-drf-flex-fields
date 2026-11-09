"""
Explicitly passed `expand` / `fields` / `omit` win over the query string.

Upstream #108: the arguments were tested for truthiness, so an empty list -
a caller saying "expand nothing" - was indistinguishable from not passing the
argument at all, and the request's query parameters took over. They now
default to `None`, and only `None` means "the caller said nothing".
"""

from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from tests.testapp.models import Company, Person, Pet
from tests.testapp.serializers import PetSerializer


def request_for(query: str):
    return Request(APIRequestFactory().get(f"/pets/?{query}"))


class ExplicitFlexArgumentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="McDonalds")
        cls.person = Person.objects.create(
            name="Fred", hobbies="sailing", employer=cls.company
        )
        cls.pet = Pet.objects.create(
            name="Garfield", toys="paper ball", species="cat", owner=cls.person
        )

    def serialize(self, query: str, **kwargs):
        context = {"request": request_for(query)}
        return PetSerializer(self.pet, context=context, **kwargs).data

    # -- expand ------------------------------------------------------------

    def test_empty_expand_turns_expansion_off(self):
        data = self.serialize("expand=owner", expand=[])

        self.assertEqual(data["owner"], self.person.pk)

    def test_omitted_expand_still_honours_the_query_parameter(self):
        data = self.serialize("expand=owner")

        self.assertIsInstance(data["owner"], dict)

    def test_explicit_expand_replaces_the_query_parameter(self):
        data = self.serialize("expand=owner", expand=["sold_from"])

        self.assertEqual(data["owner"], self.person.pk)
        self.assertIsNone(data["sold_from"])

    def test_empty_expand_also_turns_off_a_wildcard(self):
        data = self.serialize("expand=~all", expand=[])

        self.assertEqual(data["owner"], self.person.pk)

    def test_empty_expand_without_any_query_parameter(self):
        data = self.serialize("", expand=[])

        self.assertEqual(data["owner"], self.person.pk)

    def test_explicit_expand_works_without_a_request(self):
        data = PetSerializer(self.pet, expand=["owner"]).data

        self.assertIsInstance(data["owner"], dict)

    # -- fields ------------------------------------------------------------

    def test_empty_fields_cancels_the_sparse_selection(self):
        """
        An empty `fields` means "I am not restricting anything", so every
        field stays - the query parameter must not restrict it instead.
        """
        data = self.serialize("fields=name", fields=[])

        self.assertEqual(
            set(data.keys()),
            {"owner", "name", "toys", "species", "diet", "sold_from"},
        )

    def test_omitted_fields_still_honours_the_query_parameter(self):
        data = self.serialize("fields=name")

        self.assertEqual(set(data.keys()), {"name"})

    def test_explicit_fields_replaces_the_query_parameter(self):
        data = self.serialize("fields=name", fields=["species"])

        self.assertEqual(set(data.keys()), {"species"})

    # -- omit --------------------------------------------------------------

    def test_empty_omit_cancels_the_omission(self):
        data = self.serialize("omit=name", omit=[])

        self.assertIn("name", data)

    def test_omitted_omit_still_honours_the_query_parameter(self):
        data = self.serialize("omit=name")

        self.assertNotIn("name", data)

    def test_explicit_omit_replaces_the_query_parameter(self):
        data = self.serialize("omit=name", omit=["species"])

        self.assertIn("name", data)
        self.assertNotIn("species", data)

    # -- the three together, and the recorded options ----------------------

    def test_all_three_empty_at_once(self):
        data = self.serialize(
            "expand=owner&fields=name&omit=species",
            **{
                "expand": [],
                "fields": [],
                "omit": [],
            },
        )

        self.assertEqual(data["owner"], self.person.pk)
        self.assertEqual(
            set(data.keys()),
            {"owner", "name", "toys", "species", "diet", "sold_from"},
        )

    def test_empty_arguments_are_recorded_as_a_decision(self):
        """
        The distinction lives in `_flex_options_rep_only`: an explicit value
        leaves nothing for the query parameters to contribute.
        """
        serializer = PetSerializer(
            self.pet,
            context={"request": request_for("expand=owner&fields=name&omit=toys")},
            expand=[],
            fields=[],
            omit=[],
        )

        self.assertEqual(
            serializer._flex_options_rep_only,
            {"expand": [], "fields": [], "omit": []},
        )
        self.assertEqual(
            serializer._flex_options_base,
            {"expand": [], "fields": [], "omit": []},
        )

    def test_nothing_passed_leaves_the_query_parameters_in_charge(self):
        serializer = PetSerializer(
            self.pet,
            context={"request": request_for("expand=owner&fields=name&omit=toys")},
        )

        self.assertEqual(
            serializer._flex_options_rep_only,
            {"expand": ["owner"], "fields": ["name"], "omit": ["toys"]},
        )

    def test_a_non_list_iterable_is_still_accepted(self):
        """
        The arguments used to be passed through `list()`; tuples and other
        iterables must keep working.
        """
        data = self.serialize("", expand=("owner",))

        self.assertIsInstance(data["owner"], dict)
