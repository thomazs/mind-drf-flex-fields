"""
How the query optimizer treats each kind of relation.

`FlexFieldsFilterBackend` narrows the queryset with `only()` and follows
single-valued relations with `select_related()`, leaving the rest to
`prefetch_related()`. Django flags a forward `ForeignKey` as `many_to_one` but
a forward `OneToOneField` as `one_to_one`, so code that tests `many_to_one`
alone treats a one-to-one as multi-valued: its column is left out of `only()`
and the relation is handed to `prefetch_related()`.

That is wrong twice over. It spends a query where a JOIN would do, and - the
reason these tests exist - it makes Django reject a `select_related()` the view
put on its own queryset, because a field cannot be deferred and traversed with
`select_related` at the same time.
"""

from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from mind_flex_fields.filter_backends import (
    FlexFieldsFilterBackend,
    is_forward_single_relation,
)
from tests.testapp.models import Account, Company, Profile
from tests.testapp.views import ProfileViewSet


def _filtered(query_string=""):
    """Run the backend over `ProfileViewSet`'s queryset, as DRF would."""
    http_request = APIRequestFactory().get("/profiles/", query_string)
    request = Request(http_request)

    view = ProfileViewSet()
    view.request = request
    view.format_kwarg = None
    view.kwargs = {}
    view.action = "list"

    return FlexFieldsFilterBackend().filter_queryset(request, view.get_queryset(), view)


class ForwardSingleRelationTests(TestCase):
    def test_classifies_each_relation_kind(self):
        casos = {
            "owner": True,  # forward OneToOneField
            "employer": True,  # forward ForeignKey
        }
        for nome, esperado in casos.items():
            with self.subTest(field=nome):
                campo = Profile._meta.get_field(nome)
                self.assertIs(is_forward_single_relation(campo), esperado)

    def test_reverse_one_to_one_is_not_a_forward_relation(self):
        """A reverse one-to-one has no column here, so it cannot be `only()`d."""
        campo = Account._meta.get_field("profile")
        self.assertTrue(campo.one_to_one)
        self.assertFalse(is_forward_single_relation(campo))

    def test_reverse_foreign_key_is_not_a_forward_relation(self):
        """`Company.person` is the reverse side of `Person.employer`."""
        campo = Company._meta.get_field("person")
        self.assertTrue(campo.one_to_many)
        self.assertFalse(is_forward_single_relation(campo))

    def test_forward_many_to_many_is_not_a_forward_single_relation(self):
        """
        A forward m2m keeps no column on this table - it is a prefetch, not a
        JOIN. Note that `concrete` is False for it, so the cardinality test is
        what rules it out here, not `concrete`.
        """
        campo = Profile._meta.get_field("collaborators")
        self.assertTrue(campo.many_to_many)
        self.assertFalse(is_forward_single_relation(campo))


class OneToOneIsNotDeferredTests(TestCase):
    def test_only_lists_the_one_to_one_column(self):
        queryset = _filtered()
        nomes, defer = queryset.query.deferred_loading

        self.assertFalse(defer, "the backend narrows with only(), not defer()")
        self.assertIn("owner", nomes)

    def test_select_related_set_by_the_view_survives(self):
        """The regression: deferring `owner` made this queryset uncompilable."""
        queryset = _filtered()

        self.assertEqual(queryset.query.select_related, {"owner": {}})
        str(queryset.query)  # raises FieldError if `owner` is deferred

    def test_expanding_the_one_to_one_joins_instead_of_prefetching(self):
        queryset = _filtered({"expand": "owner"})

        self.assertIn("owner", queryset.query.select_related)
        self.assertEqual(
            [lookup for lookup in queryset._prefetch_related_lookups],
            [],
            "a forward one-to-one is a JOIN, not a prefetch",
        )
        str(queryset.query)
