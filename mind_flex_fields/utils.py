from collections.abc import Iterable

from mind_flex_fields import (
    EXPAND_PARAM,
    EXPANDABLE_FIELDS_ATTRIBUTE,
    FIELDS_PARAM,
    OMIT_PARAM,
    WILDCARD_VALUES,
)

__all__ = [
    "expandable_fields_attribute_name",
    "query_param_values",
    "request_query_params",
    "get_expandable_fields",
    "is_expanded",
    "is_included",
    "split_levels",
]

#: Distinguishes "not declared" from "declared empty"; see
#: `get_expandable_fields`.
_UNSET = object()


def _contains_wildcard(values) -> bool:
    """
    Whether any of `values` stands in for every field name.

    `WILDCARD_VALUES` is `None` when wildcards are disabled, so this must not
    assume it is iterable.
    """
    if not WILDCARD_VALUES:
        return False
    return not set(values).isdisjoint(WILDCARD_VALUES)


def request_query_params(request):
    """
    The query parameters of `request`, or None when it carries none.

    DRF's request wrapper exposes `query_params`; a plain Django `HttpRequest`
    - which you get in a management command, a non-DRF view, or when building
    a serializer by hand - only has `GET`. Both are `QueryDict`s, so either
    works from here on.
    """
    params = getattr(request, "query_params", None)
    if params is None:
        params = getattr(request, "GET", None)
    return params


def query_param_values(request, param: str) -> list:
    """
    The values of `param`, read the same way the serializer reads them.

    Supports `?p=a,b`, the repeated `?p=a&p=b` form and the `?p[]=a&p[]=b`
    form. Kept deliberately identical to
    `FlexFieldsSerializerMixin._get_query_param_value` so the utilities below
    cannot answer differently from the serializer: a single value is split on
    commas, several values are taken as given.
    """
    params = request_query_params(request)
    if params is None:
        return []

    getlist = getattr(params, "getlist", None)
    if getlist is None:
        # A plain mapping, e.g. a hand-built test double.
        value = params.get(param)
        values = [value] if value else []
    else:
        values = getlist(param) or getlist(f"{param}[]")

    if values and len(values) == 1:
        values = values[0].split(",")

    return [value for value in values if value]


def _leaf_names(values) -> list:
    """Every dotted path flattened into its individual segments."""
    names = []
    for value in values:
        names.extend(value.split("."))
    return names


def _expanded_paths(values) -> set:
    """
    Every requested expansion path, together with its ancestors.

    `?expand=a.b.c` expands `a`, then `a.b` inside it, then `a.b.c`, so all
    three paths are expanded - but `b` and `c` on their own are not.
    """
    paths = set()
    for value in values:
        segments = value.split(".")
        for depth in range(1, len(segments) + 1):
            paths.add(".".join(segments[:depth]))
    return paths


def is_expanded(request, field: str) -> bool:
    """
    Whether `field` is expanded by this request.

    `field` is matched as a path, not as a bare name: for `?expand=a.b`,
    `is_expanded(request, "a.b")` is True and `is_expanded(request, "b")` is
    False, because `b` is only expanded below `a`.

    A wildcard expands one level, so it answers True only for a top-level
    name; a dotted path still has to be requested explicitly.
    """
    expand_values = query_param_values(request, EXPAND_PARAM)

    if "." not in field and _contains_wildcard(expand_values):
        return True

    return field in _expanded_paths(expand_values)


def is_included(request, field: str) -> bool:
    """Examines request object to return boolean of whether
    passed field has been excluded, either because `fields` is
    set, and it is not among them, or because `omit` is set and
    it is among them.

    A wildcard in `fields` means "every field at this level", so it includes
    the field - matching what the serializer does. Wildcards are not applied
    to `omit`, which the serializer also matches by exact name only.
    """
    sparse_fields = _leaf_names(query_param_values(request, FIELDS_PARAM))
    omit_fields = _leaf_names(query_param_values(request, OMIT_PARAM))

    if (
        len(sparse_fields) > 0
        and not _contains_wildcard(sparse_fields)
        and field not in sparse_fields
    ):
        return False

    if len(omit_fields) > 0 and field in omit_fields:
        return False

    return True


def split_levels(fields):
    """
    Convert dot-notation such as ['a', 'a.b', 'a.d', 'c'] into
    current-level fields ['a', 'c'] and next-level fields
    {'a': ['b', 'd']}.
    """
    first_level_fields = []
    next_level_fields = {}

    if not fields:
        return first_level_fields, next_level_fields

    assert isinstance(
        fields, Iterable
    ), "`fields` must be iterable (e.g. list, tuple, or generator)"

    if isinstance(fields, str):
        fields = [a.strip() for a in fields.split(",") if a.strip()]
    for e in fields:
        if "." in e:
            first_level, next_level = e.split(".", 1)
            first_level_fields.append(first_level)
            next_level_fields.setdefault(first_level, []).append(next_level)
        else:
            first_level_fields.append(e)

    first_level_fields = list(set(first_level_fields))
    return first_level_fields, next_level_fields


def expandable_fields_attribute_name() -> str:
    """
    The attribute that holds a serializer's expandable-fields mapping.

    Defaults to ``"expandable_fields"``; override it with
    ``MIND_FLEX_FIELDS["EXPANDABLE_FIELDS_ATTRIBUTE"]``. Like the package's
    other options, it is read once at import time.
    """
    return EXPANDABLE_FIELDS_ATTRIBUTE


def _expandable_fields_holders(serializer_object):
    """
    The objects that may declare the mapping, in precedence order.

    ``_meta`` comes first so that classes keeping their options there are
    supported, and ``Meta`` is still consulted when ``_meta`` does not declare
    the attribute - the two are not mutually exclusive.
    """
    for attribute in ("_meta", "Meta"):
        holder = getattr(serializer_object, attribute, None)
        if holder is not None:
            yield holder


def get_expandable_fields(serializer_object, default=_UNSET):
    """
    Return the expandable-fields mapping declared on `serializer_object`.

    Looks at ``_meta`` and then ``Meta``, under the name
    `expandable_fields_attribute_name` returns. Accepts either a serializer
    class or an instance.

    The lookup tests for *presence*, not truthiness, so an explicitly empty
    mapping is returned as-is - that is how a subclass turns expansion off.
    When no holder declares the attribute, `default` is returned, or an empty
    dict if no `default` was given.
    """
    attribute = expandable_fields_attribute_name()

    for holder in _expandable_fields_holders(serializer_object):
        fields = getattr(holder, attribute, _UNSET)
        if fields is not _UNSET:
            return fields

    return {} if default is _UNSET else default
