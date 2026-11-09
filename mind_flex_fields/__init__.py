"""
mind-drf-flex-fields
~~~~~~~~~~~~~~~~~~~~

Flexible, dynamic fields and nested resources for Django REST Framework
serializers.

Fork of `drf-flex-fields` (https://github.com/rsinger86/drf-flex-fields) by
Robert Singer, updated to run on current versions of Django REST Framework
(the CoreAPI schema code has been removed).
"""

from importlib import import_module

from django.conf import settings

__version__ = "1.0"

#: Settings are read from ``MIND_FLEX_FIELDS`` and fall back to
#: ``REST_FLEX_FIELDS`` so that projects migrating from ``drf-flex-fields``
#: keep working without touching their settings module.
FLEX_FIELDS_OPTIONS = getattr(
    settings, "MIND_FLEX_FIELDS", getattr(settings, "REST_FLEX_FIELDS", {})
)

if not isinstance(FLEX_FIELDS_OPTIONS, dict):
    raise ValueError("'MIND_FLEX_FIELDS' should be a dict")

EXPAND_PARAM = FLEX_FIELDS_OPTIONS.get("EXPAND_PARAM", "expand")
FIELDS_PARAM = FLEX_FIELDS_OPTIONS.get("FIELDS_PARAM", "fields")
OMIT_PARAM = FLEX_FIELDS_OPTIONS.get("OMIT_PARAM", "omit")
MAXIMUM_EXPANSION_DEPTH = FLEX_FIELDS_OPTIONS.get("MAXIMUM_EXPANSION_DEPTH", None)
RECURSIVE_EXPANSION_PERMITTED = FLEX_FIELDS_OPTIONS.get(
    "RECURSIVE_EXPANSION_PERMITTED", True
)

#: The attribute that holds a serializer's expandable-fields mapping. Kept
#: configurable for projects that declare their serializer options under a
#: different name. `MIND_EXPANDABLE_FIELDS_ATT` is accepted as a top-level
#: setting too, for compatibility with the first iteration of this option.
EXPANDABLE_FIELDS_ATTRIBUTE = FLEX_FIELDS_OPTIONS.get(
    "EXPANDABLE_FIELDS_ATTRIBUTE",
    getattr(settings, "MIND_EXPANDABLE_FIELDS_ATT", "expandable_fields"),
)

WILDCARD_ALL = "~all"
WILDCARD_ASTERISK = "*"

if "WILDCARD_EXPAND_VALUES" in FLEX_FIELDS_OPTIONS:
    WILDCARD_VALUES = FLEX_FIELDS_OPTIONS["WILDCARD_EXPAND_VALUES"]
elif "WILDCARD_VALUES" in FLEX_FIELDS_OPTIONS:
    WILDCARD_VALUES = FLEX_FIELDS_OPTIONS["WILDCARD_VALUES"]
else:
    WILDCARD_VALUES = [WILDCARD_ALL, WILDCARD_ASTERISK]

assert isinstance(EXPAND_PARAM, str), "'EXPAND_PARAM' should be a string"
assert isinstance(FIELDS_PARAM, str), "'FIELDS_PARAM' should be a string"
assert isinstance(OMIT_PARAM, str), "'OMIT_PARAM' should be a string"
assert isinstance(
    EXPANDABLE_FIELDS_ATTRIBUTE, str
), "'EXPANDABLE_FIELDS_ATTRIBUTE' should be a string"
assert (
    EXPANDABLE_FIELDS_ATTRIBUTE.isidentifier()
), "'EXPANDABLE_FIELDS_ATTRIBUTE' should be a valid attribute name"

if type(WILDCARD_VALUES) not in (list, type(None)):
    raise ValueError("'WILDCARD_EXPAND_VALUES' should be a list of strings or None")
if type(MAXIMUM_EXPANSION_DEPTH) not in (int, type(None)):
    raise ValueError("'MAXIMUM_EXPANSION_DEPTH' should be a int or None")
if type(RECURSIVE_EXPANSION_PERMITTED) is not bool:
    raise ValueError("'RECURSIVE_EXPANSION_PERMITTED' should be a bool")

# `utils` pulls in nothing from DRF, so it is safe to import eagerly.
from .utils import (  # noqa: E402
    expandable_fields_attribute_name,
    get_expandable_fields,
    is_expanded,
    is_included,
    query_param_values,
    request_query_params,
    split_levels,
)

#: Imported on first use rather than here. Loading `.serializers` or `.views`
#: eagerly pulls in `rest_framework.serializers` / `rest_framework.viewsets`,
#: and `.views` subclasses `viewsets.ModelViewSet` at module scope. That breaks
#: whenever this package is imported from inside DRF's own initialisation -
#: which is exactly what happens when a filter backend is named in
#: `REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]`: DRF resolves that setting from
#: the class body of `GenericAPIView`, while `rest_framework.viewsets` is still
#: half-initialised, so `ModelViewSet` does not exist yet.
#:
#: Deferring the import keeps every public name importable exactly as before.
_LAZY_ATTRIBUTES = {
    "FlexFieldsModelSerializer": ".serializers",
    "FlexFieldsSerializerMixin": ".serializers",
    "FlexFieldsMixin": ".views",
    "FlexFieldsModelViewSet": ".views",
}


def __getattr__(name):  # PEP 562
    module_name = _LAZY_ATTRIBUTES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value  # resolved once; later lookups skip __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRIBUTES))


__all__ = [
    "EXPAND_PARAM",
    "EXPANDABLE_FIELDS_ATTRIBUTE",
    "FIELDS_PARAM",
    "OMIT_PARAM",
    "MAXIMUM_EXPANSION_DEPTH",
    "RECURSIVE_EXPANSION_PERMITTED",
    "WILDCARD_ALL",
    "WILDCARD_ASTERISK",
    "WILDCARD_VALUES",
    "FlexFieldsMixin",
    "FlexFieldsModelSerializer",
    "FlexFieldsModelViewSet",
    "FlexFieldsSerializerMixin",
    "expandable_fields_attribute_name",
    "get_expandable_fields",
    "is_expanded",
    "query_param_values",
    "request_query_params",
    "is_included",
    "split_levels",
    "__version__",
]
