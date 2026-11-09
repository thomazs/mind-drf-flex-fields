"""
Compatibility shim for `mind_flex_fields.utils`.

Every attribute is delegated to the real module, so the objects handed out are
the same ones - not copies - and dotted lookups such as
"rest_flex_fields.utils.FlexFieldsFilterBackend" resolve exactly as before.
"""

import mind_flex_fields.utils as _target


def __getattr__(name):
    try:
        return getattr(_target, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


def __dir__():
    return sorted(dir(_target))
