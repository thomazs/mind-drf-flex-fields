# Changelog

All notable changes to this project are documented here.

This project is a fork of [drf-flex-fields](https://github.com/rsinger86/drf-flex-fields);
the upstream changelog is preserved in the [README](README.md#changelog).

## Unreleased

### Fixed

- **`FlexFieldsFilterBackend` treated a forward `OneToOneField` as a multi-valued
  relation.** Django flags a forward `ForeignKey` as `many_to_one` and a forward
  `OneToOneField` as `one_to_one`, and the query optimizer only tested `many_to_one`.
  A forward one-to-one was therefore left out of `only()` and handed to
  `prefetch_related()` - a query where a JOIN would do, and, worse, a field deferred
  behind the view's back. Any view that select-relates such a field on its own queryset
  (`queryset = Person.objects.select_related("user")`, the documented way to avoid an
  N+1) then died with

      FieldError: Field Person.user cannot be both deferred and traversed
      using select_related at the same time.

  Upstream `drf-flex-fields` has the same defect but hid it: when no concrete
  `many_to_one` field was found it called `select_related()` with **no arguments**,
  which means "follow every non-null foreign key" and silently *discarded* the view's
  explicit `select_related()`. Django does not validate that form against deferred
  fields, so the conflict never surfaced - the join was simply lost. Release 1.0
  stopped making that no-argument call, which turned a silent pessimisation into a
  hard error.

  Classification now goes through the new public helper
  `is_forward_single_relation()`: a relation is a JOIN when it is concrete and either
  `many_to_one` or `one_to_one`. Reverse relations, many-to-many and
  `GenericForeignKey` are unaffected and still go to `prefetch_related()`.

  **This changes the generated SQL** for serializers with a forward one-to-one: the
  column is selected, the relation is joined instead of prefetched, and one query
  disappears per request.

## 1.0.1 - 2026-11-09

**No changes to the installed package.** The library and the compatibility shim are
functionally identical to 1.0; only repository tooling changed, and `.github/` is not
part of either distribution. This version exists so that the first release published
through the automated workflow is a real upload, rather than a re-upload of 1.0 that
PyPI would reject.

### Fixed

- CI: the Python 3.9 job failed in `Set up Python` without running a test.
  `ubuntu-latest` is now Ubuntu 26.04, for which `actions/python-versions` does not
  publish Python 3.9 - it reached end of life in October 2025. `setup-python` is now
  pinned to 3.12 purely to run tox, and `UV_PYTHON_PREFERENCE=only-managed` makes uv
  download the interpreter each tox environment asks for, so the matrix no longer
  depends on what the runner image ships. Python 3.9 remains supported and tested
  (Django 4.2 with DRF 3.15 and 3.16).

### Changed

- Repository URLs point at `github.com/thomazs/mind-drf-flex-fields` in both
  distributions' metadata.

## 1.0 - 2026-11-05

First release of the `mind-drf-flex-fields` fork, based on `drf-flex-fields` 1.0.2.

### Removed

- **All CoreAPI references.** `from rest_framework.compat import coreapi, coreschema` and
  `FlexFieldsDocsFilterBackend.get_schema_fields()` have been removed. CoreAPI schema
  generation was deprecated in DRF 3.10 and removed in DRF 3.17, so upstream's
  `rest_flex_fields.filter_backends` module cannot be imported on DRF >= 3.17.
  Schema documentation is now provided solely via `get_schema_operation_parameters()`
  (OpenAPI), which DRF's built-in generator and drf-spectacular both use.

### Changed

- The attribute holding a serializer's expandable-fields mapping is configurable through
  `MIND_FLEX_FIELDS["EXPANDABLE_FIELDS_ATTRIBUTE"]`, and is looked up on `_meta` before
  `Meta`, for projects that keep their serializer options there. The mapping is resolved
  by the new public helper `get_expandable_fields()`, which tests for presence rather
  than truthiness - so an explicitly empty mapping disables expansion instead of falling
  back to the legacy class attribute.
- **`is_expanded()` matches expansion paths, not bare field names.** Upstream flattened
  every dotted path into its segments, so `?expand=a.b` reported `b` as expanded and
  `a.b` as not expanded. The helper now builds the set of requested paths and their
  ancestors: for `?expand=a.b.c`, `a`, `a.b` and `a.b.c` are expanded and nothing else
  is. A wildcard expands one level, so it answers `True` only for a top-level name; a
  dotted path still has to be requested explicitly. **This changes the answers the
  helper gives**, and code that asked for a bare leaf name while requesting a nested
  path was relying on the old, wrong answer. (upstream #48)
- **An explicitly passed `expand`, `fields` or `omit` always wins over the query
  string, including when it is empty.** The three arguments default to `None`, and only
  `None` means "the caller said nothing" - which is what lets the request's query
  parameters through. Passing `expand=[]` is a decision ("expand nothing") and is now
  honoured; upstream tested the arguments for truthiness, so an empty list was
  indistinguishable from omitting them and the query parameter took over. Non-empty
  values behaved this way already; what changes is the empty case. (upstream #108)
- Import package renamed from `rest_flex_fields` to `mind_flex_fields`.
- Settings are read from `MIND_FLEX_FIELDS`, falling back to `REST_FLEX_FIELDS` so that
  existing projects keep working without changes.
- Packaging modernized: PEP 621 `pyproject.toml` replaces `setup.py`;
  `requires-python >= 3.9`, `Django >= 4.2`, `djangorestframework >= 3.15`.
- Dropped Python 2 era idioms (`super(Cls, self)`, `object` base classes,
  `type(x) == str`).
- `tests/settings.py` now uses an in-memory SQLite database and no longer sets the
  removed `USE_L10N` setting.
- `tests/urls.py` uses `django.urls.re_path` instead of `django.conf.urls.url`,
  which was removed in Django 4.0.

### Fixed

- Naming either filter backend in `REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]` - the
  documented setup - could stop Django from starting, depending on which module imported
  DRF first. The package `__init__` eagerly imported `.views`, which subclasses
  `viewsets.ModelViewSet` at module scope, and DRF resolves that setting from the class
  body of `GenericAPIView`, while `rest_framework.viewsets` is still initialising. The
  serializer and view classes are now imported on first use through a module-level
  `__getattr__` (PEP 562), so every public name is importable exactly as before.
  (upstream #46, #56, #59)
- `is_expanded()` and `is_included()` only saw the last value of a repeated query
  parameter (`?expand=a&expand=b`), a form the serializer has always supported, so the
  helpers disagreed with it. They now read parameters exactly as the serializer does,
  including the `?expand[]=a` form. (upstream #137)
- A plain Django `HttpRequest` in the serializer context raised
  `AttributeError: 'WSGIRequest' object has no attribute 'query_params'`. Query
  parameters are now read from `query_params` or, failing that, `GET`, so serializers
  built by hand - in a management command, a non-DRF view - work too. (upstream #128)

- `is_expanded()` raised `TypeError` when wildcards were disabled with
  `WILDCARD_VALUES: None`, a documented configuration: the wildcard list was assumed to
  be iterable.
- `is_included()` ignored wildcards, so it answered `False` for fields that the
  serializer does include under `?fields=*`. Since the helper is used to decide on
  `select_related`/`only` before serialization, it could lead to the wrong query.

- **The filter backends can finally be used the way the docs describe.**
  `filter_backends.py` imported `GenericViewSet` from `rest_framework.viewsets`
  at module scope, purely for a type annotation. Listing either backend in
  `REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]` makes DRF import it from the class
  body of `GenericAPIView` - that is, while `rest_framework.viewsets` is still
  initialising - so the import failed and Django would not start at all. The
  annotation imports now sit behind `typing.TYPE_CHECKING`. This bug is present
  upstream too, and the upstream test suite never caught it because the tests
  attach the backend to a viewset directly instead of through the setting.
- `FlexFieldsFilterBackend` no longer calls `select_related()` / `prefetch_related()` /
  `only()` with zero arguments. When the computed field list was empty (for example a
  model whose only nested field is a `GenericForeignKey`), upstream called
  `select_related()` with no arguments, which makes Django follow **every** non-null
  foreign key and emit joins nobody asked for. Django 6.1 deprecates that call style, so
  it would also have become an error. **This changes the generated SQL** versus upstream:
  the superfluous join is gone. Query counts are unaffected.
- `WILDCARD_VALUES = None` (wildcards disabled) no longer raises `TypeError` when the
  filter backends module is imported.
- Walking nested `expandable_fields` for schema generation no longer raises `TypeError`
  when a value is not a class (e.g. a lazy string reference).

### Added

- `expandable_fields` accepts a callable that returns the serializer class, for projects
  that resolve serializers through their own loader. Field classes such as
  `SerializerMethodField` are still passed through untouched. (upstream #138)
- `fix-issues.md`, a triage of the upstream issue tracker: what was fixed here, what is
  deliberately out of scope, and what is still open.

- `mind-flex-fields-migrate`, a migration CLI (top-level `mind_flex_fields_migrate`
  module) that walks a project and rewrites `rest_flex_fields` imports - and dotted
  strings such as `"rest_flex_fields.filter_backends.FlexFieldsFilterBackend"` - to
  `mind_flex_fields`. Supports `--dry-run`, `--diff`, `--path`, `--extension`,
  `--exclude`, `--include-requirements` and `--rename-settings`; prompts before writing,
  and is idempotent.

  It is a CLI rather than a management command on purpose: a management command needs
  Django to boot, and a project whose settings still reference
  `rest_flex_fields.filter_backends` cannot boot on current DRF - not even with the old
  package still installed, since that module is the thing that fails to import. The CLI
  imports nothing from Django and needs no `INSTALLED_APPS` entry.
- `tests/test_schema.py`, covering OpenAPI parameter generation and asserting that no
  CoreAPI hooks remain.
- `tests/test_settings_compat.py`, covering the `MIND_FLEX_FIELDS` /
  `REST_FLEX_FIELDS` resolution order.
- `mind-drf-flex-fields-compat`, an optional second distribution (in `compat/`) that
  provides the old `rest_flex_fields` import path as a thin delegating shim. With it
  installed, an untouched project keeps booting right after the dependency swap, so the
  dependency change and the code rewrite no longer have to land together. It also covers
  references in third-party code, which the CLI cannot rewrite. Attributes are resolved
  lazily through a module-level `__getattr__`, which is required: a dotted settings path
  is imported from inside `mind_flex_fields/__init__`, while that package is still
  partially initialised. Shipped separately so that installing the library never hijacks
  the `rest_flex_fields` name.
- `tests/test_migration_cli.py`, covering the migration engine and its CLI.
- `tests/test_compat_shim.py`, covering the shim's resolution, object identity,
  deprecation warning and end-to-end serialization.
- `openapi` extra (`uritemplate`, `inflection`, `PyYAML`) for DRF's schema generator.
- The suite now runs on pytest + pytest-django, configured in `pyproject.toml`.
  Upstream's `manage.py` is gone: it was only a test entry point, and a library does not
  need a Django project scaffold. Dropping it exposed three subprocess-based tests that
  silently relied on being started from the repository root, which `manage.py` guaranteed
  by accident; they now resolve the root from `__file__`, so `pytest` works from any
  directory.
- `tox.ini` defining the supported matrix, plus `checks`, `wheel` and `shim`
  environments. The `wheel` and `shim` environments run from outside the source tree, so
  they test the installed distributions rather than the working copy - the gap that let
  packaging mistakes through before.
- CI for GitHub Actions and GitLab, both delegating to tox so the matrix is declared
  once, and both building and publishing the library and the shim.

### Verified

- Django 4.2, 5.1, 5.2, 6.0 and 6.1 against DRF 3.15 - 3.18, on Python 3.9 - 3.14.
  Newest combination tested: Django 6.1.3 + DRF 3.18.3.
