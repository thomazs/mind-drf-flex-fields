"""
Compatibility shim: makes the old `rest_flex_fields` import path resolve to
`mind_flex_fields`.

Install this only while migrating. It lets a project that still references
`rest_flex_fields` - in imports, or in dotted strings such as
`REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]` - keep booting after you swap
`drf-flex-fields` for `mind-drf-flex-fields`, so the dependency change and the
code change do not have to happen in the same step.

Everything is delegated to `mind_flex_fields`; the objects handed out are the
same ones, not copies, so `isinstance` and `issubclass` behave as expected.

Once `mind-flex-fields-migrate` has rewritten your references, uninstall this
package.

This package replaces the real `drf-flex-fields` on disk: both provide a
top-level `rest_flex_fields`, so never have the two installed at once.

Note on laziness
----------------
Attributes are resolved through a module-level ``__getattr__`` rather than
eager ``from mind_flex_fields import ...`` lines, and this is load-bearing.
Resolving a dotted settings path imports this package from inside
``mind_flex_fields/__init__`` (DRF reads DEFAULT_FILTER_BACKENDS while
``rest_framework.viewsets`` is still initialising, which that ``__init__``
triggers). At that moment ``mind_flex_fields`` is only partially initialised,
so an eager import of a name such as ``FlexFieldsMixin`` would fail with a
circular-import error. Deferring the lookup to first attribute access avoids
the problem entirely.
"""

import warnings

import mind_flex_fields as _target

#: The public API, re-exported from `mind_flex_fields`.
__all__ = [
    "EXPAND_PARAM",
    "FIELDS_PARAM",
    "FLEX_FIELDS_OPTIONS",
    "MAXIMUM_EXPANSION_DEPTH",
    "OMIT_PARAM",
    "RECURSIVE_EXPANSION_PERMITTED",
    "WILDCARD_ALL",
    "WILDCARD_ASTERISK",
    "WILDCARD_VALUES",
    "FlexFieldsMixin",
    "FlexFieldsModelSerializer",
    "FlexFieldsModelViewSet",
    "FlexFieldsSerializerMixin",
    "is_expanded",
    "is_included",
    "split_levels",
]


def __getattr__(name):
    try:
        return getattr(_target, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


def __dir__():
    return sorted(set(__all__) | set(dir(_target)))


warnings.warn(
    "`rest_flex_fields` is a temporary compatibility shim for "
    "`mind_flex_fields`. Run `mind-flex-fields-migrate` to rewrite your "
    "references, then uninstall mind-drf-flex-fields-compat.",
    DeprecationWarning,
    stacklevel=2,
)
