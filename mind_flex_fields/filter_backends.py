from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import QuerySet
from rest_framework.filters import BaseFilterBackend

if TYPE_CHECKING:  # pragma: no cover
    # Imported for type annotations only.
    #
    # Importing `rest_framework.viewsets` (or `.request`) at module scope
    # deadlocks the documented installation: listing this backend in
    # DEFAULT_FILTER_BACKENDS makes DRF import it from the body of
    # `GenericAPIView`, i.e. while `rest_framework.viewsets` is still
    # initialising, so `GenericViewSet` does not exist yet and Django refuses
    # to start. Annotations below are strings for the same reason.
    from rest_framework.request import Request
    from rest_framework.viewsets import GenericViewSet

from mind_flex_fields import (
    EXPAND_PARAM,
    FIELDS_PARAM,
    OMIT_PARAM,
    WILDCARD_VALUES,
)
from mind_flex_fields.serializers import (
    FlexFieldsModelSerializer,
    FlexFieldsSerializerMixin,
)
from mind_flex_fields.utils import get_expandable_fields

WILDCARD_VALUES_JOINED = ",".join(WILDCARD_VALUES or [])


def is_forward_single_relation(model_field: models.Field) -> bool:
    """
    Whether `model_field` is a relation a single JOIN can follow.

    A forward `ForeignKey` and a forward `OneToOneField` both point at exactly
    one row and keep their column on this table, so `select_related()` follows
    them and `only()` has to list them. Django flags the first `many_to_one`
    and the second `one_to_one`, so testing `many_to_one` alone leaves forward
    one-to-one fields out: the column gets deferred and the relation is sent to
    `prefetch_related()`, which costs an extra query for a plain join. It also
    breaks an unrelated `select_related("<that field>")` the view may have put
    on the queryset, because Django refuses a field that is "both deferred and
    traversed using select_related at the same time".

    Everything else is either not single-valued (many-to-many, reverse
    foreign key) or not concrete (reverse relations, `GenericForeignKey`), and
    belongs to `prefetch_related()`.
    """
    return (
        model_field.is_relation
        and (model_field.many_to_one or model_field.one_to_one)
        and model_field.concrete
    )


class FlexFieldsDocsFilterBackend(BaseFilterBackend):
    """
    A dummy filter backend only for schema/documentation purposes.

    It advertises the ``fields``, ``omit`` and ``expand`` query parameters to
    DRF's OpenAPI schema generation (``rest_framework.schemas.openapi``) and to
    third-party generators that follow the same protocol, such as
    drf-spectacular.
    """

    def filter_queryset(self, request, queryset, view):
        return queryset

    @staticmethod
    @lru_cache()
    def _get_field(field_name: str, model: models.Model) -> Optional[models.Field]:
        try:
            # noinspection PyProtectedMember
            return model._meta.get_field(field_name)
        except FieldDoesNotExist:
            return None

    @staticmethod
    def _get_expandable_fields(serializer_class: FlexFieldsModelSerializer) -> list:
        expandable_fields = list(get_expandable_fields(serializer_class).items())
        expand_list = []

        while expandable_fields:
            key, cls = expandable_fields.pop()
            # An entry may be `(serializer, options)`; a plain string is a lazy
            # reference, which is not resolved here (see the note below).
            if isinstance(cls, (tuple, list)):
                cls = cls[0]

            expand_list.append(key)

            if not isinstance(cls, type) or not issubclass(
                cls, FlexFieldsSerializerMixin
            ):
                continue

            # Looked up through the helper so that a nested serializer
            # declaring its mapping on `_meta` is traversed as well.
            next_layer = get_expandable_fields(cls)
            if next_layer:
                expandable_fields.extend(
                    (f"{key}.{nested_key}", nested_cls)
                    for nested_key, nested_cls in next_layer.items()
                )

        return expand_list

    @staticmethod
    def _get_fields(serializer_class):
        fields = getattr(serializer_class.Meta, "fields", [])
        return ",".join(fields)

    def get_schema_operation_parameters(self, view):
        serializer_class = view.get_serializer_class()
        if not issubclass(serializer_class, FlexFieldsSerializerMixin):
            return []

        fields = self._get_fields(serializer_class)
        expandable_fields = self._get_expandable_fields(serializer_class)
        if WILDCARD_VALUES:
            expandable_fields.extend(WILDCARD_VALUES)

        fields_example = fields or "field1,field2,nested.field"
        if WILDCARD_VALUES_JOINED:
            fields_example = f"{fields_example},{WILDCARD_VALUES_JOINED}"

        parameters = [
            {
                "name": FIELDS_PARAM,
                "required": False,
                "in": "query",
                "description": "Specify required fields by comma",
                "schema": {
                    "title": "Selected fields",
                    "type": "string",
                },
                "example": fields_example,
            },
            {
                "name": OMIT_PARAM,
                "required": False,
                "in": "query",
                "description": "Specify omitted fields by comma",
                "schema": {
                    "title": "Omitted fields",
                    "type": "string",
                },
                "example": fields_example,
            },
            {
                "name": EXPAND_PARAM,
                "required": False,
                "in": "query",
                "description": "Select fields to expand",
                "style": "form",
                "explode": False,
                "schema": {
                    "title": "Expanded fields",
                    "type": "array",
                    "items": {"type": "string", "enum": expandable_fields},
                },
            },
        ]

        return parameters


class FlexFieldsFilterBackend(FlexFieldsDocsFilterBackend):
    def filter_queryset(
        self,
        request: "Request",
        queryset: QuerySet,
        view: "GenericViewSet",
    ):
        if (
            not issubclass(view.get_serializer_class(), FlexFieldsSerializerMixin)
            or request.method != "GET"
        ):
            return queryset

        auto_remove_fields_from_query = getattr(
            view, "auto_remove_fields_from_query", True
        )
        auto_select_related_on_query = getattr(
            view, "auto_select_related_on_query", True
        )
        required_query_fields = list(getattr(view, "required_query_fields", []))

        serializer = view.get_serializer(  # type: FlexFieldsSerializerMixin
            context=view.get_serializer_context()
        )

        serializer.apply_flex_fields(
            serializer.fields, serializer._flex_options_rep_only
        )
        serializer._flex_fields_rep_applied = True

        model_fields = []
        nested_model_fields = []
        for field in serializer.fields.values():
            model_field = self._get_field(field.source, queryset.model)
            if model_field:
                model_fields.append(model_field)
                if field.field_name in serializer.expanded_fields or (
                    model_field.is_relation
                    and not is_forward_single_relation(model_field)
                ):  # Include GenericForeignKey
                    nested_model_fields.append(model_field)

        if auto_remove_fields_from_query:
            only_fields = required_query_fields + [
                model_field.name
                for model_field in model_fields
                if not model_field.is_relation
                or is_forward_single_relation(model_field)
            ]
            # `only()` with no arguments is a no-op at best; skip it entirely.
            if only_fields:
                queryset = queryset.only(*only_fields)

        if auto_select_related_on_query and nested_model_fields:
            select_related_fields = [
                model_field.name
                for model_field in nested_model_fields
                if is_forward_single_relation(model_field)
                # Exclude GenericForeignKey
            ]

            prefetch_related_fields = [
                model_field.name
                for model_field in nested_model_fields
                if model_field.is_relation
                and not is_forward_single_relation(model_field)
                # Include GenericForeignKey
            ]

            # Both calls must be skipped when there is nothing to follow:
            # `select_related()` with no arguments means "follow every non-null
            # foreign key", which is never what we want here, and Django
            # deprecated that call style in 6.1.
            if select_related_fields:
                queryset = queryset.select_related(*select_related_fields)

            if prefetch_related_fields:
                queryset = queryset.prefetch_related(*prefetch_related_fields)

        return queryset

    @staticmethod
    @lru_cache()
    def _get_field(field_name: str, model: models.Model) -> Optional[models.Field]:
        try:
            # noinspection PyProtectedMember
            return model._meta.get_field(field_name)
        except FieldDoesNotExist:
            return None
