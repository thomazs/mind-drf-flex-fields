import subprocess
import sys
import textwrap
from pathlib import Path

from django.test import RequestFactory, TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from mind_flex_fields import is_included, is_expanded, WILDCARD_ALL, WILDCARD_ASTERISK


class MockRequest(object):
    def __init__(self, query_params=None, method="GET"):
        if query_params is None:
            query_params = {}
        self.query_params = query_params
        self.method = method


class TestUtils(TestCase):
    def test_should_be_included(self):
        request = MockRequest(query_params={})
        self.assertTrue(is_included(request, "name"))

    def test_should_not_be_included(self):
        request = MockRequest(query_params={"omit": "name,address"})
        self.assertFalse(is_included(request, "name"))

    def test_should_not_be_included_and_due_to_omit_and_has_dot_notation(self):
        request = MockRequest(query_params={"omit": "friend.name,address"})
        self.assertFalse(is_included(request, "name"))

    def test_should_not_be_included_and_due_to_fields_and_has_dot_notation(self):
        request = MockRequest(query_params={"fields": "hobby,address"})
        self.assertFalse(is_included(request, "name"))

    def test_should_be_expanded(self):
        request = MockRequest(query_params={"expand": "name,address"})
        self.assertTrue(is_expanded(request, "name"))

    def test_should_not_be_expanded(self):
        request = MockRequest(query_params={"expand": "name,address"})
        self.assertFalse(is_expanded(request, "hobby"))

    def test_dot_notation_expands_the_path_not_the_bare_name(self):
        """
        Upstream #48: this used to answer True for "name", because every
        dotted path was flattened into its segments.
        """
        request = MockRequest(query_params={"expand": "person.name,address"})

        self.assertTrue(is_expanded(request, "person"))
        self.assertTrue(is_expanded(request, "person.name"))
        self.assertTrue(is_expanded(request, "address"))
        self.assertFalse(is_expanded(request, "name"))

    def test_all_should_be_expanded(self):
        request = MockRequest(query_params={"expand": WILDCARD_ALL})
        self.assertTrue(is_expanded(request, "name"))

    def test_asterisk_should_be_expanded(self):
        request = MockRequest(query_params={"expand": WILDCARD_ASTERISK})
        self.assertTrue(is_expanded(request, "name"))


class IsExpandedWildcardTests(TestCase):
    """
    Wildcards are optional: the settings table documents `WILDCARD_VALUES:
    None` as the way to disable them. `is_expanded` used to do
    `field in WILDCARD_VALUES` unguarded and raised TypeError in that case.
    """

    def _request(self, query: str):
        return Request(APIRequestFactory().get(f"/things/?{query}"))

    def test_wildcard_counts_as_expanded(self):
        self.assertTrue(is_expanded(self._request("expand=*"), "owner"))
        self.assertTrue(is_expanded(self._request("expand=~all"), "owner"))

    def test_named_field_is_expanded(self):
        self.assertTrue(is_expanded(self._request("expand=owner"), "owner"))
        self.assertFalse(is_expanded(self._request("expand=owner"), "other"))

    def test_nothing_expanded(self):
        self.assertFalse(is_expanded(self._request(""), "owner"))


class WildcardsDisabledTests(TestCase):
    """
    `WILDCARD_VALUES: None` is the documented way to turn wildcards off. The
    setting is read at import time, so this runs in a subprocess - and it has
    to, because `is_expanded` used to raise TypeError in that configuration.
    """

    SCRIPT = textwrap.dedent("""
        import django
        from django.conf import settings

        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
            ],
            DATABASES={},
            USE_TZ=True,
            MIND_FLEX_FIELDS={"WILDCARD_VALUES": None},
        )
        django.setup()

        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        from mind_flex_fields import WILDCARD_VALUES, is_expanded, is_included

        assert WILDCARD_VALUES is None, WILDCARD_VALUES

        factory = APIRequestFactory()
        expanded = Request(factory.get("/things/?expand=owner"))
        wildcard = Request(factory.get("/things/?expand=*&fields=*"))

        # Named lookups keep working...
        assert is_expanded(expanded, "owner") is True
        assert is_expanded(expanded, "other") is False
        # ...and a wildcard is just another name once they are disabled.
        assert is_expanded(wildcard, "owner") is False
        assert is_included(wildcard, "name") is False

        print("OK")
        """)

    def test_utilities_work_with_wildcards_disabled(self):
        result = subprocess.run(
            [sys.executable, "-c", self.SCRIPT],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)


class IsIncludedWildcardTests(TestCase):
    """
    `is_included` has to agree with the serializer, since it is used to decide
    on `select_related`/`only` before serialization happens.
    """

    def _request(self, query: str):
        return Request(APIRequestFactory().get(f"/things/?{query}"))

    def test_wildcard_in_fields_includes_everything(self):
        request = self._request("fields=*")
        self.assertTrue(is_included(request, "name"))
        self.assertTrue(is_included(request, "toys"))

    def test_wildcard_alongside_named_fields(self):
        request = self._request("fields=*,owner.name")
        self.assertTrue(is_included(request, "species"))

    def test_sparse_fields_still_exclude(self):
        request = self._request("fields=name")
        self.assertTrue(is_included(request, "name"))
        self.assertFalse(is_included(request, "toys"))

    def test_omit_still_excludes(self):
        request = self._request("omit=toys")
        self.assertFalse(is_included(request, "toys"))
        self.assertTrue(is_included(request, "name"))

    def test_wildcard_is_not_applied_to_omit(self):
        """The serializer matches `omit` by exact name, so this must too."""
        request = self._request("omit=*")
        self.assertTrue(is_included(request, "name"))


class RepeatedQueryParamTests(TestCase):
    """
    `?expand=a&expand=b` is a form the serializer already understands, because
    it reads parameters with `getlist()`. The utilities used `.get()`, which
    returns only the last value, so they disagreed with it (upstream #137).
    """

    def _request(self, query: str):
        return Request(APIRequestFactory().get(f"/things/?{query}"))

    def test_repeated_expand_parameters(self):
        request = self._request("expand=owner&expand=sold_from")
        self.assertTrue(is_expanded(request, "owner"))
        self.assertTrue(is_expanded(request, "sold_from"))

    def test_bracketed_expand_parameters(self):
        request = self._request("expand[]=owner&expand[]=sold_from")
        self.assertTrue(is_expanded(request, "owner"))
        self.assertTrue(is_expanded(request, "sold_from"))

    def test_comma_separated_still_works(self):
        request = self._request("expand=owner,sold_from")
        self.assertTrue(is_expanded(request, "owner"))
        self.assertTrue(is_expanded(request, "sold_from"))

    def test_repeated_fields_parameters(self):
        request = self._request("fields=name&fields=toys")
        self.assertTrue(is_included(request, "name"))
        self.assertTrue(is_included(request, "toys"))
        self.assertFalse(is_included(request, "species"))

    def test_repeated_omit_parameters(self):
        request = self._request("omit=name&omit=toys")
        self.assertFalse(is_included(request, "name"))
        self.assertFalse(is_included(request, "toys"))
        self.assertTrue(is_included(request, "species"))

    def test_utilities_agree_with_the_serializer(self):
        """
        The guarantee worth holding on to: the helpers must answer what the
        serializer actually did, for each supported parameter form.
        """
        from tests.testapp.models import Company, Person, Pet
        from tests.testapp.serializers import PetSerializer

        company = Company.objects.create(name="McDonalds")
        person = Person.objects.create(name="Fred", hobbies="sailing", employer=company)
        pet = Pet.objects.create(
            name="Garfield", toys="paper ball", species="cat", owner=person
        )

        for query in (
            "expand=owner",
            "expand=owner&expand=sold_from",
            "expand[]=owner&expand[]=sold_from",
            "expand=owner,sold_from",
        ):
            with self.subTest(query=query):
                request = self._request(query)
                data = PetSerializer(pet, context={"request": request}).data
                serializer_expanded = isinstance(data.get("owner"), dict)
                self.assertEqual(
                    is_expanded(request, "owner"),
                    serializer_expanded,
                    f"is_expanded disagrees with the serializer for ?{query}",
                )


class PlainHttpRequestTests(TestCase):
    """
    A plain Django HttpRequest has `GET`, not `query_params`. Reading the
    latter unguarded raised AttributeError (upstream #128).
    """

    def test_utilities_accept_a_plain_django_request(self):
        request = RequestFactory().get("/things/?expand=owner&fields=name")

        self.assertTrue(is_expanded(request, "owner"))
        self.assertTrue(is_included(request, "name"))
        self.assertFalse(is_included(request, "toys"))

    def test_request_without_query_parameters_at_all(self):
        class Bare:
            pass

        self.assertFalse(is_expanded(Bare(), "owner"))
        self.assertTrue(is_included(Bare(), "owner"))


class IsExpandedNestedPathTests(TestCase):
    """
    `is_expanded` matches expansion *paths* (upstream #48).

    Flattening every dotted path made the helper unable to tell a nested
    field from a top-level one: `?expand=a.b` reported `b` as expanded and
    `a.b` as not expanded - both answers wrong.
    """

    def _request(self, query: str):
        return Request(APIRequestFactory().get(f"/things/?{query}"))

    def test_table_from_the_issue(self):
        # (query string, field, expected)
        cases = [
            # A single level.
            ("expand=a", "a", True),
            ("expand=a", "b", False),
            # Two levels: the path and its ancestor are expanded, the bare
            # leaf name is not.
            ("expand=a.b", "a", True),
            ("expand=a.b", "a.b", True),
            ("expand=a.b", "b", False),
            ("expand=a.b", "b.a", False),
            # Three levels: every ancestor counts, nothing else does.
            ("expand=a.b.c", "a", True),
            ("expand=a.b.c", "a.b", True),
            ("expand=a.b.c", "a.b.c", True),
            ("expand=a.b.c", "b", False),
            ("expand=a.b.c", "c", False),
            ("expand=a.b.c", "b.c", False),
            ("expand=a.b.c", "a.c", False),
            # Several paths at once, comma-separated and repeated.
            ("expand=a.b,c", "a.b", True),
            ("expand=a.b,c", "c", True),
            ("expand=a.b,c", "b", False),
            ("expand=a.b&expand=c.d", "a.b", True),
            ("expand=a.b&expand=c.d", "c.d", True),
            ("expand=a.b&expand=c.d", "d", False),
            # Nothing requested.
            ("", "a", False),
        ]

        for query, field, expected in cases:
            with self.subTest(query=query, field=field):
                self.assertIs(is_expanded(self._request(query), field), expected)

    def test_wildcard_expands_one_level_only(self):
        """
        A wildcard expands the top level, so it must not claim that an
        arbitrary nested path is expanded - the other half of #48.
        """
        for wildcard in (WILDCARD_ALL, WILDCARD_ASTERISK):
            with self.subTest(wildcard=wildcard):
                request = self._request(f"expand={wildcard}")

                self.assertTrue(is_expanded(request, "owner"))
                self.assertTrue(is_expanded(request, "anything"))
                self.assertFalse(is_expanded(request, "owner.address"))
                self.assertFalse(is_expanded(request, "a.b.c"))

    def test_wildcard_alongside_an_explicit_nested_path(self):
        request = self._request(f"expand={WILDCARD_ALL},owner.address")

        self.assertTrue(is_expanded(request, "owner"))
        self.assertTrue(is_expanded(request, "owner.address"))
        self.assertFalse(is_expanded(request, "owner.toys"))

    def test_agrees_with_what_the_serializer_expands(self):
        """
        The helper's answers must match what the serializer actually
        expanded, at both levels.
        """
        from tests.testapp.models import Company, Person, Pet
        from tests.testapp.serializers import PetSerializer

        company = Company.objects.create(name="McDonalds")
        person = Person.objects.create(name="Fred", hobbies="sailing", employer=company)
        pet = Pet.objects.create(
            name="Garfield", toys="paper ball", species="cat", owner=person
        )

        request = self._request("expand=owner.employer")
        data = PetSerializer(pet, context={"request": request}).data

        # `owner` and `owner.employer` were both replaced by nested objects.
        self.assertIsInstance(data["owner"], dict)
        self.assertTrue(is_expanded(request, "owner"))

        self.assertIsInstance(data["owner"]["employer"], dict)
        self.assertTrue(is_expanded(request, "owner.employer"))

        # `employer` only exists below `owner`, so it is not expanded at the
        # top level - which is what the flattening got wrong.
        self.assertNotIn("employer", data)
        self.assertFalse(is_expanded(request, "employer"))
