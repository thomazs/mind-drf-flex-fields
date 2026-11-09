# Upstream issue triage and fix plan

A review of the open issues on [rsinger86/drf-flex-fields](https://github.com/rsinger86/drf-flex-fields/issues)
(25 open issues, fetched 2026-11-05), filtered down to what is worth doing in this fork.

**Inclusion criteria** — an item is planned only if it is all three of:

- **relevant** to this fork's purpose (keeping the library working on current Django/DRF);
- **not a breaking change** — no public name, signature or documented contract changes;
- **not a change to the main behaviour** — expansion, sparse fields and `omit` keep
  working exactly as they do today.

Everything else is listed under [Out of scope](#out-of-scope) with the reason.

**Current state:** every item below is implemented, each with tests that were verified to
fail against the old code. Items 4 and 5 were held back at first because they change
answers that existing code may rely on; that decision has since been taken - both are
fixed, and both are called out as behaviour changes in the
[changelog](CHANGELOG.md) and the README rather than buried as bug fixes.

**Every item below was reproduced against this fork**, not taken on faith from the issue
text. Several upstream reports no longer reproduce, and one problem turned out to be
worse than the issues describe.

---

## Summary

| Item | Upstream | Status here | Priority |
| ---- | -------- | ----------- | -------- |
| [1. Circular import when the backend is in `DEFAULT_FILTER_BACKENDS`](#1-circular-import-when-a-backend-is-in-default_filter_backends) | #46, #56, #59 | ✅ **fixed** | P1 |
| [2. `is_expanded()` ignores repeated query parameters](#2-is_expanded-ignores-repeated-query-parameters) | #137 | ✅ **fixed** | P1 |
| [3. Plain Django `HttpRequest` in serializer context](#3-plain-django-httprequest-in-the-serializer-context) | #128 | ✅ **fixed** | P2 |
| [4. `is_expanded()` and nested paths](#4-is_expanded-and-nested-paths) | #48 | ✅ **fixed** | P2 |
| [5. Explicit `expand=[]` is ignored](#5-explicit-expand-is-ignored) | #108 | ✅ **fixed** | P3 |
| [6. Lazy serializer reference from a callable](#6-lazy-serializer-reference-from-a-callable) | #138 | ✅ **fixed** | P3 |

Already resolved in this fork, no action needed:

| Upstream | What it was | Where it was handled |
| -------- | ----------- | -------------------- |
| #145 | `ImportError: cannot import name 'coreapi'` on DRF ≥ 3.17 | CoreAPI removed; `tests/test_schema.py` |
| #130 | "support Django 4.2 and DRF 3.14?" | Tested on Django 4.2–6.1 and DRF 3.15–3.18 |
| #98 | Wanted a docs-only filter backend, separate from the query optimizer | `FlexFieldsDocsFilterBackend` |
| #142 | `RecursionError` from `fields=["author"], expand=["author"]` | Does not reproduce (see below) |
| #54 | Wanted expandable `SerializerMethodField` | Already supported (see below) |
| #143 | `expand`/`omit` absent from detail routes in the OpenAPI schema | Does not reproduce (see below) |

---

## 1. Circular import when a backend is in `DEFAULT_FILTER_BACKENDS`

**Upstream:** #46, #56, #59 — all three are the same root cause.
**Status: reproduces in this fork today.** This is the most important item here.

### What happens

Configuring either backend the way the README tells people to:

```python
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": (
        "mind_flex_fields.filter_backends.FlexFieldsFilterBackend",
    ),
}
```

makes Django fail to start as soon as anything imports DRF before it imports
`mind_flex_fields`:

```
ImportError: Could not import
'mind_flex_fields.filter_backends.FlexFieldsFilterBackend' for API setting
'DEFAULT_FILTER_BACKENDS'. AttributeError: partially initialized module
'rest_framework.viewsets' has no attribute 'ModelViewSet'
```

### Why

DRF resolves `DEFAULT_FILTER_BACKENDS` from the class body of `GenericAPIView`
(`rest_framework/generics.py`), i.e. while `rest_framework.viewsets` is still
initialising. Resolving the dotted string imports `mind_flex_fields.filter_backends`,
which imports the package, whose `__init__` eagerly does:

```python
from .views import FlexFieldsMixin, FlexFieldsModelViewSet
```

and `views.py` subclasses `viewsets.ModelViewSet` at module scope — a class that does not
exist yet at that point in DRF's own import.

```
rest_framework.viewsets  (line 26: from rest_framework import generics)
└─ rest_framework.generics  (line 43, class body: DEFAULT_FILTER_BACKENDS)
   └─ mind_flex_fields.filter_backends
      └─ mind_flex_fields/__init__
         └─ mind_flex_fields.views
            └─ class …(viewsets.ModelViewSet)   ✗ not defined yet
```

An earlier fix in this fork removed one leg of this (a module-scope
`from rest_framework.viewsets import GenericViewSet` in `filter_backends.py`, now behind
`TYPE_CHECKING`). This remaining leg goes through the package `__init__` instead and is
still live.

### Reproduction

```bash
python - <<'EOF'
import django
from django.conf import settings
settings.configure(
    INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "rest_framework"],
    DATABASES={}, USE_TZ=True,
    REST_FRAMEWORK={"DEFAULT_FILTER_BACKENDS":
                    ("mind_flex_fields.filter_backends.FlexFieldsFilterBackend",)},
)
django.setup()
from rest_framework import viewsets   # the first DRF import -> boom
print("OK")
EOF
```

Measured outcomes, for both backends:

| First DRF module imported | Result |
| ------------------------- | ------ |
| `rest_framework.viewsets` | **fails** |
| `rest_framework.generics` | **fails** |
| `rest_framework.serializers`, then `viewsets` | **fails** |
| `mind_flex_fields` imported before DRF | works |

So it works only when our package happens to be imported first — which is why listing the
package in `INSTALLED_APPS` masks it, and why the existing regression test
(`tests/test_filter_backend_import.py`) passes: its subprocess reaches our module first,
through `api_settings.DEFAULT_FILTER_BACKENDS`. The test needs to cover the other order.

### Fix

Make the package `__init__` lazy with a module-level `__getattr__` (PEP 562), so importing
`mind_flex_fields` no longer pulls in `.views` and `.serializers`:

```python
# mind_flex_fields/__init__.py
_LAZY = {
    "FlexFieldsModelSerializer": ".serializers",
    "FlexFieldsSerializerMixin": ".serializers",
    "FlexFieldsMixin": ".views",
    "FlexFieldsModelViewSet": ".views",
}

def __getattr__(name):
    if name in _LAZY:
        module = importlib.import_module(_LAZY[name], __name__)
        value = getattr(module, name)
        globals()[name] = value          # resolved once
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

Upstream dismissed this in #56 as "the easy fix … but that changes the API". With PEP 562
it does not: `from mind_flex_fields import FlexFieldsModelSerializer` keeps working, the
settings constants stay eager, and `__all__` is unchanged. `utils` can stay eager — it
imports nothing from DRF.

**Verified:** this fix was prototyped against the reproduction matrix above. All eight
scenarios (both backends × four import orders) start cleanly with it applied, the full
test suite still passes (146 tests), and `from mind_flex_fields import
FlexFieldsModelSerializer, FlexFieldsModelViewSet, …` keeps working unchanged. The
prototype was reverted; this document is the plan, not the change.

**Risk:** low. The only visible difference is that a typo in an imported name raises
`AttributeError` from `__getattr__` rather than `ImportError` at package import; both are
import-time failures with the same message content.

**Tests:** extend `tests/test_filter_backend_import.py` with the import orders from the
table above (subprocess each, since the failure happens during `django.setup()`), and
assert — in a clean subprocess, before anything else touches DRF — that `import
mind_flex_fields` alone does not put `rest_framework.viewsets` in `sys.modules`.

---

## 2. `is_expanded()` ignores repeated query parameters

**Upstream:** #137. **Status: reproduces.**

`?expand=author&expand=publisher` is a form the *serializer* already supports — it reads
query parameters with `getlist()`. `is_expanded()` uses `.get()`, which returns only the
last value, so it disagrees with the serializer:

```python
request = Request(APIRequestFactory().get("/books/?expand=author&expand=other"))
is_expanded(request, "author")   # False  <- wrong, the serializer expands it
is_expanded(request, "other")    # True
```

This matters because `is_expanded()` exists to decide `select_related`/`prefetch_related`
in `get_queryset()`; a wrong answer means a wrong query, silently.

### Fix

Read the parameter the same way the serializer does — `getlist(param)`, falling back to
`getlist(f"{param}[]")`, then split each value on commas. Best done as one small helper
shared by `is_expanded` and `is_included` so the two cannot drift again.

**Risk:** very low; it only changes answers in a configuration where they are currently
wrong, and it brings the helper in line with the serializer.

**Tests:** repeated parameters, the `expand[]` form, and the comma form, asserting the
helper agrees with what the serializer actually produced.

> Note: this is the same class of defect as two bugs already fixed in this fork
> (`is_expanded` crashing when wildcards are disabled, `is_included` ignoring wildcards).
> The utilities were written separately from the serializer and keep drifting from it. A
> test that asserts "helper answer == serializer output" for a matrix of query strings
> would be worth more than any single fix here.

---

## 3. Plain Django `HttpRequest` in the serializer context

**Upstream:** #128. **Status: reproduces.**

```python
# a plain django.http.HttpRequest, e.g. from a management command or a non-DRF view
BookSerializer(book, context={"request": request}).data
# AttributeError: 'WSGIRequest' object has no attribute 'query_params'
```

The library reads `request.query_params`, which only DRF's request wrapper provides.

### Fix

Read the query parameters defensively in `_get_query_param_value`:

```python
request = self.context["request"]
params = getattr(request, "query_params", None)
if params is None:
    params = getattr(request, "GET", None)   # plain django HttpRequest
if params is None:
    return []
```

`QueryDict` supports `getlist`, so nothing else changes. Prefer this over wrapping the
request in `rest_framework.request.Request`, which would hand the user back a different
object than the one they put in the context.

**Risk:** none for existing users — it is a fallback on a path that raises today.

**Tests:** a plain `RequestFactory()` request in the context, with and without query
parameters; and that a DRF request still behaves identically.

---

## 4. `is_expanded()` and nested paths

**Upstream:** #48. **Status: ✅ fixed.**

`is_expanded()` flattens every dotted path, so it cannot tell a nested field from a
top-level one:

```python
request = Request(APIRequestFactory().get("/books/?expand=a.b"))
is_expanded(request, "b")     # True   <- should be False: only a.b is expanded
is_expanded(request, "a.b")   # False  <- should be True
```

The issue also points out that `~all` makes it answer `True` for every key, although a
wildcard only expands one level.

### Fix

Build the set of expanded prefixes instead of flattening (the issue includes a working
implementation): for `a.b.c`, record `a`, `a.b` and `a.b.c`; apply the wildcard only when
the queried key has no dot.

`_expanded_paths()` in `mind_flex_fields/utils.py` builds the path set; `is_expanded()`
checks the wildcard only when the queried key has no dot.

**Why it was held back:** it changes the answers a public helper gives for inputs that
exist in the wild. Anyone who wrote `is_expanded(request, "b")` while actually requesting
`a.b` was relying on the wrong answer. No signature or name moves, so it is not a
breaking API change, but it is a visible behaviour change — hence the explicit changelog
entry and the README note, both of which spell out the old behaviour.

**Tests:** `IsExpandedNestedPathTests` in `tests/test_utils.py` — the parametrised table
from the issue (20 cases), the wildcard's one-level scope, a wildcard combined with an
explicit nested path, and an agreement check against what the serializer actually
expanded. `TestUtils.test_dot_notation_expands_the_path_not_the_bare_name` replaces the
upstream test that asserted the old, wrong answer.

---

## 5. Explicit `expand=[]` is ignored

**Upstream:** #108. **Status: ✅ fixed.**

```python
request = Request(APIRequestFactory().get("/books/?expand=author"))
BookSerializer(book, expand=[], context={"request": request}).data
# -> author IS expanded; the empty list was treated as "not given"
```

`__init__` tests the argument for truthiness:

```python
"expand": (
    self._get_permitted_expands_from_query_param(EXPAND_PARAM) if not expand else []
),
```

so `expand=[]` — a caller explicitly saying "expand nothing" — is indistinguishable from
omitting the argument, and the query parameter wins.

### Fix

Default the three keyword arguments to a module-level sentinel and test for presence, the
same way `get_expandable_fields()` already distinguishes "declared empty" from "not
declared" in this fork.

`__init__` pops the three arguments with a `None` default and tests `is None`, so the
empty list is preserved as the caller's decision. Non-empty values already behaved this
way; only the empty case changes.

**Why it was held back:** the same reasoning as item 4. Code that passes an empty list
and relies on query parameters still being honoured changes behaviour.

**Tests:** `tests/test_explicit_flex_arguments.py` (16 tests) — each of the three
arguments empty, explicit and absent, against a request that sets the matching query
parameter; the three together; the wildcard case; no request in context; a non-list
iterable; and the recorded `_flex_options_base` / `_flex_options_rep_only`, where the
distinction actually lives.

---

## 6. Lazy serializer reference from a callable

**Upstream:** #138. **Status: additive gap, does not reproduce as a bug.**

`expandable_fields` accepts a serializer class or a dotted string. Projects that resolve
serializers through their own factory (the issue mentions `django-oscar-api`'s
`get_api_class`) have no way in.

### Fix

In `_make_expanded_field_serializer`, after the existing string handling, accept a
callable that is not a serializer class and call it to obtain one:

```python
if isinstance(serializer_class, str):
    serializer_class = self._get_serializer_class_from_lazy_string(serializer_class)
elif callable(serializer_class) and not (
    isinstance(serializer_class, type)
    and issubclass(serializer_class, serializers.Field)
):
    serializer_class = serializer_class()
```

The `issubclass(..., Field)` guard matters: `SerializerMethodField` is itself a callable
class and is a supported value today (see #54 below) — it must not be called here.

**Risk:** low, but the guard is the whole fix; get it wrong and expandable
`SerializerMethodField` breaks. Covered by the existing test-app serializer, which uses
one.

**Tests:** a factory function returning a serializer class; and that
`SerializerMethodField` still works unchanged.

---

## Out of scope

Kept out deliberately, with the reason.

### Would change write behaviour

- **#93 — omitted fields can still be written.** `omit` is applied in
  `to_representation`, so omitted fields stay writable on `PUT`/`PATCH`. Making `omit`
  remove fields from validation changes what requests are accepted. That is a contract
  change, and some projects rely on omitting a field from the response while still
  accepting it as input.

### Would change queries or the main behaviour

- **#136 — should "deferred" use `.defer()`?** Pushing deferral into the queryset changes
  the SQL for everyone. The existing `FlexFieldsFilterBackend` is already the opt-in place
  for query optimisation.
- **#131 — applying `distinct` to `fields`.** A query-shape change driven by a query
  parameter; belongs in the caller's `get_queryset()`.

### New features, not fixes

- **#141 — automatic/magic expansion from model relationships.** A new way to declare
  expandable fields (`__all__`-style). Large surface, and it makes every relation
  expandable by default, which has security and query-cost implications.
- **#140 — per-view/per-action default expansion and omission.** Additive and reasonable,
  but it is a feature with its own API to design, not a fix.
- **#97 — terser notation for deferred fields.** Same: a new declaration style.

### Not reproducible / already supported

- **#142 — `RecursionError` from `fields=["author"], expand=["author"]`.** Does not
  reproduce here; `BookSerializer([b], many=True, fields=["author"], expand=["author"])`
  returns `[{'author': {...}}]`. Likely fixed by one of the 1.0.x releases. Worth adding
  the case as a test so it cannot come back.
- **#54 — expandable `SerializerMethodField`.** Already works:
  `expandable_fields = {"blurb": serializers.SerializerMethodField}` expands as expected,
  and the test app exercises it.
- **#143 — `expand`/`omit` missing from detail routes in the OpenAPI schema.** Does not
  reproduce on current DRF. With `FlexFieldsDocsFilterBackend` in
  `DEFAULT_FILTER_BACKENDS`, a generated schema carries all three parameters on both
  routes:

  ```
  /things/        -> ['fields', 'omit', 'expand']
  /things/{id}/   -> ['id', 'fields', 'omit', 'expand']
  ```

  DRF's `AutoSchema.allows_filters` lists `retrieve` among the actions that get filter
  parameters, so detail routes are covered. The report predates this, or concerns
  drf-spectacular, which applies its own rules. Worth adding the assertion above to
  `tests/test_schema.py` so a regression would be caught; nothing to fix.
  (Checking this required importing `mind_flex_fields` before DRF, to dodge item 1.)

### Support questions, no actionable defect

- **#12** (dot-notation), **#18** (reverse relationships), **#20**
  (`django-rest-framework-recursive`), **#29** (expand not working as expected),
  **#31** (passing context to child serializers). Usage questions, several of them about
  behaviour that works when `expandable_fields` is declared as documented. Nothing to
  change in the library; #31's recursion complaint overlaps #142 and is covered by adding
  that test.

### Not a code change

- **#145** also announces another maintained fork,
  [drf-flex-fields2](https://github.com/openbook-education/drf-flex-fields2). Worth
  watching: it solves the same two problems this fork started from (CoreAPI removal and a
  cyclic import with `FlexFieldsFilterBackend`) and may be a place to compare fixes with —
  in particular for item 1.

---

## Suggested order

1. ~~**Item 1**~~ — done. The regression test that let it hide now covers every import
   order.
2. ~~**Items 2 and 3**~~ — done.
3. ~~**Item 6**~~ — done.
4. **Items 4 and 5** — remaining. Agree on the behaviour change, then implement together,
   with a changelog entry and a minor version bump.

What is left needs a product decision, not more investigation: in both cases today's
answer is wrong, and correcting it changes what existing callers see.
