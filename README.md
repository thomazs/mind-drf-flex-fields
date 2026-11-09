# Mind DRF FlexFields

Flexible, dynamic fields and nested models for Django REST Framework serializers.

> **This is a fork of [drf-flex-fields](https://github.com/rsinger86/drf-flex-fields) version 1.0.2**, by [Robert Singer (@rsinger86)](https://github.com/rsinger86).
>
> It carries the following changes over that release:
>
> - **adjusted to run on the most recent Django REST Framework** - all CoreAPI references
>   were removed, since CoreAPI no longer exists in DRF (see [Why this fork?](#why-this-fork));
> - **small bug fixes** - including one that made the filter backends unusable via
>   `DEFAULT_FILTER_BACKENDS`; see the [changelog](#changelog) for the full list;
> - **refactored for Django 6.1 compatibility** - no deprecation warnings on current Django.
>
> All credit for the original design and implementation goes to the upstream project and
> its contributors. This fork preserves the original MIT license.

## Why this fork?

Upstream `drf-flex-fields` (1.0.2) imports CoreAPI from DRF's compatibility module:

```python
from rest_framework.compat import coreapi, coreschema
```

**DRF 3.17.0 removed CoreAPI entirely**, so on DRF >= 3.17 that import raises:

```
ImportError: cannot import name 'coreapi' from 'rest_framework.compat'
```

which makes `rest_flex_fields.filter_backends` (and therefore `FlexFieldsFilterBackend` /
`FlexFieldsDocsFilterBackend`) unusable on modern DRF.

This fork removes every CoreAPI reference while keeping the rest of the library fully
functional. Schema/documentation support now relies exclusively on the OpenAPI path
(`get_schema_operation_parameters`), which is what DRF's built-in generator and
third-party generators such as [drf-spectacular](https://github.com/tfranzel/drf-spectacular)
use today.

### Tested against

The full test suite passes on every supported combination below:

| Django | DRF 3.15 | DRF 3.16 | DRF 3.17 | DRF 3.18 |
| ------ | :------: | :------: | :------: | :------: |
| 4.2    |    ✅    |    ✅    |    ✅    |   n/a    |
| 5.1    |    ✅    |    ✅    |    ✅    |   n/a    |
| 5.2    |    ✅    |    ✅    |    ✅    |    ✅    |
| 6.0    |    -     |    -     |    ✅    |    ✅    |
| 6.1    |    -     |    -     |    -     |    ✅    |

`n/a` = DRF 3.18 requires `Django >= 5.2`, so those combinations cannot be installed.
`-` = not part of the verified matrix (older DRF releases predate that Django version).

Latest versions verified: **Django 6.1.3** with **DRF 3.18.3**.

Python 3.9 through 3.13 are verified, and the suite also passes on a 3.14 pre-release
build. Note that Python 3.9 can only be paired with DRF <= 3.16, since DRF 3.18 requires
Python >= 3.10.

# Overview

FlexFields for [Django REST Framework](https://django-rest-framework.org) provides a common
baseline of functionality for dynamically setting fields and nested models within DRF
serializers, with minimal magic and entanglement with DRF's foundational classes.

Key benefits:

- Easily set up fields that can be expanded to their fully serialized counterparts via query parameters (`users/?expand=organization,friends`)
- Select a subset of fields by either:
  - specifying which ones should be included (`users/?fields=id,first_name`)
  - specifying which ones should be excluded (`users/?omit=id,first_name`)
- Use dot notation to dynamically modify fields at arbitrary depths (`users/?expand=organization.owner.roles`)
- Flexible API - options can also be passed directly to a serializer: `UserSerializer(obj, expand=['organization'])`

# Quick Start

```python
from mind_flex_fields import FlexFieldsModelSerializer

class StateSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = State
        fields = ('id', 'name')

class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'population', 'states')
        expandable_fields = {
          'states': (StateSerializer, {'many': True})
        }

class PersonSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Person
        fields = ('id', 'name', 'country', 'occupation')
        expandable_fields = {'country': CountrySerializer}
```

```
GET /people/142/
```

```json
{
  "id": 142,
  "name": "Jim Halpert",
  "country": 1
}
```

```
GET /people/142/?expand=country.states
```

```json
{
  "id": 142,
  "name": "Jim Halpert",
  "country": {
    "id": 1,
    "name": "United States",
    "states": [
      { "id": 23, "name": "Ohio" },
      { "id": 2, "name": "Pennsylvania" }
    ]
  }
}
```

# Table of Contents

- [Why this fork?](#why-this-fork)
- [Overview](#overview)
- [Quick Start](#quick-start)
- [Setup](#setup)
- [Migrating from drf-flex-fields](#migrating-from-drf-flex-fields)
  - [The migration CLI](#the-migration-cli)
  - [Zero-downtime migration (optional shim)](#zero-downtime-migration-optional-shim)
    - [Why a CLI and not a management command](#why-a-cli-and-not-a-management-command)
- [Usage](#usage)
  - [Dynamic Field Expansion](#dynamic-field-expansion)
  - [Deferred Fields](#deferred-fields)
  - [Deep, Nested Expansion](#deep-nested-expansion)
  - [Field Expansion on "List" Views](#field-expansion-on-list-views)
  - [Expanding a "Many" Relationship](#expanding-a-many-relationship)
  - [Dynamically Setting Fields (Sparse Fields)](#dynamically-setting-fields-sparse-fields)
  - [Reference serializer as a string (lazy evaluation)](#reference-serializer-as-a-string-lazy-evaluation)
    - [Reference serializer from a callable](#reference-serializer-from-a-callable)
  - [Increased re-usability of serializers](#increased-re-usability-of-serializers)
- [Serializer Options](#serializer-options)
- [Advanced](#advanced)
  - [Customization](#customization)
    - [Renaming the `expandable_fields` attribute](#renaming-the-expandable_fields-attribute)
  - [Serializer Introspection](#serializer-introspection)
  - [Use of Wildcard to Match All Fields](#use-of-wildcard-to-match-all-fields)
  - [Combining Sparse Fields and Field Expansion](#combining-sparse-fields-and-field-expansion)
  - [Utility Functions](#utility-functions)
  - [Query optimization (experimental)](#query-optimization-experimental)
  - [OpenAPI / schema generation](#openapi--schema-generation)
- [Changelog](#changelog)
- [Testing](#testing)
  - [Quick start](#quick-start-1)
  - [The full matrix](#the-full-matrix)
  - [What the suite covers](#what-the-suite-covers)
  - [Troubleshooting](#troubleshooting)
- [Credits](#credits)
- [License](#license)

# Setup

Install:

```
pip install mind-drf-flex-fields
```

If you generate OpenAPI schemas with DRF's built-in generator, install the extra:

```
pip install "mind-drf-flex-fields[openapi]"
```

Then have your serializers subclass `FlexFieldsModelSerializer`:

```python
from mind_flex_fields import FlexFieldsModelSerializer

class StateSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = State
        fields = ('id', 'name')

class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'population', 'states')
        expandable_fields = {
          'states': (StateSerializer, {'many': True})
        }
```

Alternatively, you can add the `FlexFieldsSerializerMixin` mixin to a model serializer.

There is nothing to add to `INSTALLED_APPS`.

# Migrating from drf-flex-fields

The public API is unchanged - only the import path differs.

If you want the dependency swap and the code change to land separately - or if some
dependency outside your control imports `rest_flex_fields` - install the optional
[compatibility shim](#zero-downtime-migration-optional-shim) and nothing breaks in
between.

1. Replace the dependency:

   ```diff
   - drf-flex-fields
   + mind-drf-flex-fields
   ```

2. Update imports (`rest_flex_fields` -> `mind_flex_fields`) with the bundled CLI:

   ```bash
   mind-flex-fields-migrate --dry-run --diff   # preview
   mind-flex-fields-migrate                    # apply
   ```

   It walks the project, rewrites `import` statements **and** dotted strings such as
   `"rest_flex_fields.filter_backends.FlexFieldsFilterBackend"`, and prompts before
   touching anything. See [The migration CLI](#the-migration-cli) for all options.

   ```diff
   - from rest_flex_fields import FlexFieldsModelSerializer, is_expanded
   + from mind_flex_fields import FlexFieldsModelSerializer, is_expanded
   ```

3. Settings: the `REST_FLEX_FIELDS` dict keeps working as a fallback, so you don't have to
   touch it. The preferred key is now `MIND_FLEX_FIELDS`, which takes precedence when both
   are defined. Pass `--rename-settings` if you want it renamed anyway.

4. `FlexFieldsDocsFilterBackend.get_schema_fields()` (CoreAPI) **no longer exists**. If you
   called it directly, use `get_schema_operation_parameters()` instead. If you only listed
   the backend in `DEFAULT_FILTER_BACKENDS`, no change is needed.

## The migration CLI

`mind-flex-fields-migrate` rewrites references to the upstream package in place. It is
idempotent, so running it twice is harmless, and it never rewrites the installed library
itself.

```bash
mind-flex-fields-migrate [options]

# equivalent, if the console script is not on your PATH
python -m mind_flex_fields_migrate [options]
```

## Zero-downtime migration (optional shim)

Swapping the dependency breaks a project until its references are rewritten, because
Django resolves dotted strings such as
`REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"] = ("rest_flex_fields.filter_backends...",)`
at startup. Nothing inside `mind_flex_fields` can intercept an `import
rest_flex_fields` - the only way to keep that name working is to provide it.

That is what `mind-drf-flex-fields-compat` (in [`compat/`](compat/)) does. With it
installed, an **untouched** project keeps booting after the swap:

```bash
pip uninstall drf-flex-fields
pip install mind-drf-flex-fields mind-drf-flex-fields-compat
# every rest_flex_fields reference still resolves; nothing rewritten yet
```

Then migrate and drop the shim, at your own pace:

```bash
mind-flex-fields-migrate
pip uninstall mind-drf-flex-fields-compat
```

The shim delegates every attribute to `mind_flex_fields`, so the objects are the same
ones - `isinstance` and `issubclass` keep working - and it raises a `DeprecationWarning`
on import so it cannot be forgotten.

**Never install it alongside the real `drf-flex-fields`**: both provide a top-level
`rest_flex_fields` package and would overwrite each other's files. It is a separate
distribution precisely so that installing the library never hijacks that name.

You do not need the shim if you change the dependency and run the CLI in the same commit;
the CLI works on a project that cannot boot, so there is no window where the code is
broken.

### Why a CLI and not a management command

Because a management command would not work when you need it. A management command needs
Django to boot, and half-way through the migration it cannot: if your settings still name
`rest_flex_fields.filter_backends`, that module fails to import on current DRF, so
`manage.py` dies during `django.setup()` before any command can run. Keeping the old
package installed alongside does not help either - it is the old module itself that cannot
be imported.

So this tool runs outside Django entirely. It needs no `DJANGO_SETTINGS_MODULE`, no
`INSTALLED_APPS` entry, and works on a project that is completely broken.

| Option                   | Description                                                                                                                                  |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `--path PATH`            | Directory to walk. Defaults to the current working directory.                                                                                 |
| `--dry-run`              | Report what would change and write nothing.                                                                                                   |
| `--diff`                 | Print a unified diff of every change.                                                                                                         |
| `--extension EXT`        | Extension to rewrite; repeat to pass several. Defaults to `.py`.                                                                               |
| `--exclude DIR`          | Extra directory name to skip; repeat to pass several.                                                                                          |
| `--include-requirements` | Also rename the distribution (`drf-flex-fields` -> `mind-drf-flex-fields`) in `requirements*.txt`/`.in`, `pyproject.toml`, `setup.py`, `setup.cfg` and `Pipfile`. |
| `--rename-settings`      | Also rename the `REST_FLEX_FIELDS` setting to `MIND_FLEX_FIELDS`.                                                                              |
| `--noinput`              | Skip the confirmation prompt.                                                                                                                  |

Notes:

- Version control directories and build/virtualenv noise (`.git`, `__pycache__`, `.venv`,
  `node_modules`, `dist`, `build`, `.tox`, ...) are skipped automatically.
- Only whole-word matches are replaced, so an unrelated package such as
  `rest_flex_fields_extra` is left intact.
- With `--include-requirements`, a pin like `drf-flex-fields==1.0.2` becomes
  `mind-drf-flex-fields==1.0.2` - a version that does not exist, since this fork starts at
  1.0. The command prints a warning listing any such line so you can fix the specifier.
- Commit your work before applying: files are rewritten in place, with no backups.

# Usage

## Dynamic Field Expansion

To define expandable fields, add an `expandable_fields` dictionary to your serializer's `Meta` class. Key the dictionary with the name of the field that you want to dynamically expand, and set its value to either the expanded serializer or a tuple where the first element is the serializer and the second is a dictionary of options that will be used to instantiate the serializer.

```python
class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ['name', 'population']


class PersonSerializer(FlexFieldsModelSerializer):
    country = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Person
        fields = ['id', 'name', 'country', 'occupation']

        expandable_fields = {
            'country': CountrySerializer
        }
```

If the default serialized response is the following:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": 12,
  "occupation": "Programmer"
}
```

When you do a `GET /person/13322?expand=country`, the response will change to:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "name": "United States",
    "population": 330000000
  },
  "occupation": "Programmer"
}
```

## Deferred Fields

Alternatively, you could treat `country` as a "deferred" field by not defining it among the default fields. To make a field deferred, only define it within the serializer's `expandable_fields`.

## Deep, Nested Expansion

Let's say you add `StateSerializer` as a serializer nested inside the country serializer above:

```python
class StateSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = State
        fields = ['name', 'population']


class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ['name', 'population']

        expandable_fields = {
            'states': (StateSerializer, {'many': True})
        }

class PersonSerializer(FlexFieldsModelSerializer):
    country = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Person
        fields = ['id', 'name', 'country', 'occupation']

        expandable_fields = {
            'country': CountrySerializer
        }
```

Your default serialized response might be the following for `person` and `country`, respectively:

```json
{
  "id" : 13322,
  "name" : "John Doe",
  "country" : 12,
  "occupation" : "Programmer"
}
```

```json
{
  "id" : 12,
  "name" : "United States",
  "states" : "http://www.api.com/countries/12/states"
}
```

But if you do a `GET /person/13322?expand=country.states`, it would be:

```json
{
  "id": 13322,
  "name": "John Doe",
  "occupation": "Programmer",
  "country": {
    "id": 12,
    "name": "United States",
    "states": [
      {
        "name": "Ohio",
        "population": 11000000
      }
    ]
  }
}
```

Please be kind to your database, as this could incur many additional queries. Though, you can mitigate this impact through judicious use of `prefetch_related` and `select_related` when defining the queryset for your viewset.

## Field Expansion on "List" Views

If you request many objects, expanding fields could lead to many additional database queries. Subclass `FlexFieldsModelViewSet` if you want to prevent expanding fields by default when calling a ViewSet's `list` method. Place those fields that you would like to expand in a `permit_list_expands` property on the ViewSet:

```python
from mind_flex_fields import FlexFieldsModelViewSet, is_expanded

class PersonViewSet(FlexFieldsModelViewSet):
    permit_list_expands = ['employer']
    serializer_class = PersonSerializer

    def get_queryset(self):
        queryset = models.Person.objects.all()
        if is_expanded(self.request, 'employer'):
            queryset = queryset.select_related('employer')
        return queryset
```

Notice how this example is using the `is_expanded` utility method as well as `select_related` and `prefetch_related` to efficiently query the database if the field is expanded.

## Expanding a "Many" Relationship

Set `many` to `True` in the serializer options to make sure "to many" fields are expanded correctly.

```python
class StateSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = State
        fields = ['name', 'population']


class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ['name', 'population']

        expandable_fields = {
            'states': (StateSerializer, {'many': True})
        }
```

A request to `GET /countries?expand=states` will return:

```python
{
    "id" : 12,
    "name" : "United States",
    "states" : [
      {
        "name" : "Alabama",
        "population": 11000000
      },
      # ... more states ... #
      {
        "name" : "Ohio",
        "population": 11000000
      }
    ]
}
```

## Dynamically Setting Fields (Sparse Fields)

You can use either the `fields` or `omit` keywords to declare only the fields you want to include or to specify fields that should be excluded.

Consider this as a default serialized response:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "name": "United States",
    "population": 330000000
  },
  "occupation": "Programmer",
  "hobbies": ["rock climbing", "sipping coffee"]
}
```

To whittle down the fields via URL parameters, simply add `?fields=id,name,country` to your requests to get back:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "name": "United States",
    "population": 330000000
  }
}
```

Or, for more specificity, you can use dot-notation, `?fields=id,name,country.name`:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "name": "United States"
  }
}
```

Or, if you want to leave out the nested country object, do `?omit=country`:

```json
{
  "id": 13322,
  "name": "John Doe",
  "occupation": "Programmer",
  "hobbies": ["rock climbing", "sipping coffee"]
}
```

## Reference serializer as a string (lazy evaluation)

To avoid circular import problems, it's possible to lazily evaluate a string reference to your serializer class using this syntax:

```python
expandable_fields = {
    'record_set': ('<module_path_to_serializer_class>.RelatedSerializer', {'many': True})
}
```

Fully-qualified import paths to any location are supported, as well as the legacy
`<app_name>.serializers` convention.

### Reference serializer from a callable

You can also pass a callable that returns the serializer class, which helps when your
project resolves serializers through its own loader:

```python
def expanded_serializer():
    return get_api_class("serializers", "RelatedSerializer")


expandable_fields = {"record_set": (expanded_serializer, {"many": True})}
```

Field classes are left alone, so `expandable_fields = {"x": SerializerMethodField}` keeps
working as before.

## Increased re-usability of serializers

The `omit` and `fields` options can be passed directly to serializers. Rather than defining a separate, slimmer version of a regular serializer, you can re-use the same serializer and declare which fields you want.

```python
from mind_flex_fields import FlexFieldsModelSerializer

class CountrySerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'population', 'capital', 'square_miles']

class PersonSerializer(FlexFieldsModelSerializer):
    country = CountrySerializer(fields=['id', 'name'])

    class Meta:
        model = Person
        fields = ['id', 'name', 'country']


serializer = PersonSerializer(person)
print(serializer.data)

>>>{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "id": 1,
    "name": "United States"
  }
}
```

# Serializer Options

Dynamic field options can be passed in the following ways:

- from the request's query parameters; separate multiple values with a comma
- as keyword arguments directly to the serializer class when it is constructed
- from a dictionary placed as the second element in a tuple when defining `expandable_fields`

Approach #1

```
GET /people?expand=friends.hobbies,employer&omit=age
```

Approach #2

```python
serializer = PersonSerializer(
  person,
  expand=["friends.hobbies", "employer"],
  omit="friends.age"
)
```

Approach #3

```python
class PersonSerializer(FlexFieldsModelSerializer):
  # Your field definitions

  class Meta:
    model = Person
    fields = ["age", "hobbies", "name"]
    expandable_fields = {
      'friends': (
        'serializer.FriendSerializer',
        {'many': True, "expand": ["hobbies"], "omit": ["age"]}
      )
    }
```

| Option |                                 Description                                  |
| ------ | :--------------------------------------------------------------------------: |
| expand | Fields to expand; must be configured in the serializer's `expandable_fields` |
| fields |         Fields that should be included; all others will be excluded          |
| omit   |         Fields that should be excluded; all others will be included          |

### Which one wins

A keyword argument passed to the serializer takes precedence over the query parameters,
**including when it is empty**. The three arguments default to `None`, and only `None`
means "the caller said nothing"; an empty list is a decision and is honoured as one:

```python
# GET /pets/?expand=owner

PetSerializer(pet, context={"request": request})            # owner IS expanded
PetSerializer(pet, context={"request": request}, expand=[]) # owner is NOT expanded
```

The same holds for `fields=[]` ("I am not restricting anything", so every field stays)
and `omit=[]` ("I am omitting nothing"). This differs from `drf-flex-fields` 1.0.2,
which tested the arguments for truthiness and so could not tell an empty list from an
argument that was never passed - the query parameter won in both cases
([upstream #108](https://github.com/rsinger86/drf-flex-fields/issues/108)).

Only the root serializer reads query parameters; nested serializers take their options
from their parent.

# Advanced

## Customization

Parameter names and wildcard values can be configured within a Django setting named
`MIND_FLEX_FIELDS`. For backwards compatibility with `drf-flex-fields`, the
`REST_FLEX_FIELDS` setting is still read when `MIND_FLEX_FIELDS` is not defined.

| Option                        | Description                                                                                                                                                                                                                                                                                                                                                                                                               | Default         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| EXPAND_PARAM                  | The name of the parameter with the fields to be expanded                                                                                                                                                                                                                                                                                                                                                                  | `"expand"`      |
| MAXIMUM_EXPANSION_DEPTH       | The max allowed expansion depth. By default it's unlimited. Expanding `state.towns` would equal a depth of 2                                                                                                                                                                                                                                                                                                               | `None`          |
| FIELDS_PARAM                  | The name of the parameter with the fields to be included (others will be omitted)                                                                                                                                                                                                                                                                                                                                         | `"fields"`      |
| OMIT_PARAM                    | The name of the parameter with the fields to be omitted                                                                                                                                                                                                                                                                                                                                                                   | `"omit"`        |
| RECURSIVE_EXPANSION_PERMITTED | If `False`, an exception is raised when a recursive pattern is found                                                                                                                                                                                                                                                                                                                                                       | `True`          |
| EXPANDABLE_FIELDS_ATTRIBUTE   | The attribute that holds a serializer's expandable-fields mapping. Useful when your serializers declare their options under a different name. It is looked up on `_meta` first and then on `Meta`, so either works.                                                                                                                                                                                                                                      | `"expandable_fields"` |
| WILDCARD_VALUES               | List of values that stand in for all field names. Can be used with the `fields` and `expand` parameters. When used with `expand`, a wildcard value will trigger the expansion of all `expandable_fields` at a given level. When used with `fields`, all fields are included at a given level. For example, you could pass `fields=name,state.*` for a city resource with a nested state. To disable wildcards, set to `None`. | `["~all", "*"]` |

For example, if you want your API to work a bit more like [JSON API](https://jsonapi.org/format/#fetching-includes), you could do:

```python
MIND_FLEX_FIELDS = {"EXPAND_PARAM": "include"}
```

### Defining Expansion and Recursive Limits on Serializer Classes

A `maximum_expansion_depth` integer property can be set on a serializer class.

A `recursive_expansion_permitted` boolean property can be set on a serializer class.

Both settings raise `serializers.ValidationError` when conditions are met, but exceptions can be customized by overriding the `recursive_expansion_not_permitted` and `expansion_depth_exceeded` methods.

### Renaming the `expandable_fields` attribute

If your serializers keep their options under another name - or on `_meta` rather than
`Meta` - point the library at it:

```python
MIND_FLEX_FIELDS = {"EXPANDABLE_FIELDS_ATTRIBUTE": "expand_map"}
```

```python
class PersonSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = Person
        fields = ["id", "name"]
        expand_map = {"country": CountrySerializer}
```

`mind_flex_fields.get_expandable_fields(serializer_or_class)` resolves the mapping for
you, checking `_meta` and then `Meta`. An explicitly empty mapping is respected, which is
how a subclass turns expansion off:

```python
class NoExpansion(PersonSerializer):
    class Meta(PersonSerializer.Meta):
        expand_map = {}   # expansion disabled; not treated as "unset"
```

## Serializer Introspection

When using an instance of `FlexFieldsModelSerializer`, you can examine the property `expanded_fields` to discover which fields, if any, have been dynamically expanded.

## Use of Wildcard to Match All Fields

You can pass `expand=*` ([or another value of your choosing](#customization)) to automatically expand all fields that are available for expansion at a given level. To refer to nested resources, you can use dot-notation. For example, requesting `expand=menu.sections` for a restaurant resource would expand its nested `menu` resource, as well as that menu's nested `sections` resource.

Or, when requesting sparse fields, you can pass `fields=*` to include only the specified fields at a given level. To refer to nested resources, you can use dot-notation. For example, if you have an `order` resource, you could request all of its fields as well as only two fields on its nested `restaurant` resource with the following: `fields=*,restaurant.name,restaurant.address&expand=restaurant`.

## Combining Sparse Fields and Field Expansion

You may be wondering how things work if you use both the `expand` and `fields` option, and there is overlap. For example, your serialized person model may look like the following by default:

```json
{
  "id": 13322,
  "name": "John Doe",
  "country": {
    "name": "United States"
  }
}
```

However, you make the following request `HTTP GET /person/13322?fields=id,name&expand=country`. You will get the following back:

```json
{
  "id": 13322,
  "name": "John Doe"
}
```

The `fields` parameter takes precedence over `expand`. That is, if a field is not among the set that is explicitly allowed, it cannot be expanded. If such a conflict occurs, you will not pay for the extra database queries - the expanded field will be silently abandoned.

## Utility Functions

### mind_flex_fields.is_expanded(request, field: str)

Checks whether a field has been expanded via the request's query parameters.

**Parameters**

- **request**: The request object
- **field**: The expansion path to check

`field` is matched as a *path*, not as a bare name. For `?expand=owner.employer`:

```python
is_expanded(request, "owner")           # True
is_expanded(request, "owner.employer")  # True
is_expanded(request, "employer")        # False - only expanded below `owner`
```

A wildcard expands one level, so `?expand=~all` answers `True` for any top-level name
and `False` for any dotted path. `drf-flex-fields` 1.0.2 flattened every path into its
segments, which made it answer `True` for `employer` and `False` for `owner.employer`
above ([upstream #48](https://github.com/rsinger86/drf-flex-fields/issues/48)).

### mind_flex_fields.is_included(request, field: str)

Checks whether a field has NOT been excluded via either the `omit` parameter or the `fields` parameter.

**Parameters**

- **request**: The request object
- **field**: The name of the field to check

## Query optimization (experimental)

An experimental filter backend is available to help you automatically reduce the number of SQL queries and their transfer size. _This feature has not been tested thoroughly and any help testing and reporting bugs is greatly appreciated._ You can add `FlexFieldsFilterBackend` to `DEFAULT_FILTER_BACKENDS` in the settings:

```python
# settings.py

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': (
        'mind_flex_fields.filter_backends.FlexFieldsFilterBackend',
        # ...
    ),
    # ...
}
```

It will automatically call `select_related` and `prefetch_related` on the current QuerySet by determining which fields are needed from many-to-many and foreign key-related models. For sparse fields requests (`?omit=fieldX,fieldY` or `?fields=fieldX,fieldY`), the backend will automatically call `only(*field_names)` using only the fields needed for serialization.

**WARNING:** The optimization currently works only for one nesting level.

> **Difference from upstream:** when the computed list of relations is empty, this fork
> skips the `select_related()` / `prefetch_related()` / `only()` call entirely. Upstream
> called `select_related()` with no arguments in that situation, which makes Django follow
> *every* non-null foreign key and add joins that were never requested (and which Django
> 6.1 deprecates). If you relied on that implicit behaviour, list the relations explicitly
> in your viewset's `get_queryset()`.

## OpenAPI / schema generation

If you only want the `fields`, `omit` and `expand` query parameters documented - without the
query optimization - use `FlexFieldsDocsFilterBackend`, which leaves the queryset untouched:

```python
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': (
        'mind_flex_fields.filter_backends.FlexFieldsDocsFilterBackend',
    ),
}
```

Both backends implement `get_schema_operation_parameters()`, so the parameters show up in
OpenAPI schemas generated by DRF's built-in generator and by drf-spectacular.

> **Breaking change versus upstream:** `get_schema_fields()` (the CoreAPI hook) has been
> removed. CoreAPI schema generation was deprecated in DRF 3.10 and removed in DRF 3.17, so
> there is no supported DRF release where that method could still be used.

# Changelog

## 1.0.2 (November 2026)

Fixes the query optimizer's handling of a **forward `OneToOneField`**: Django flags it
`one_to_one`, not `many_to_one`, so it was left out of `only()` and sent to
`prefetch_related()` - an extra query, and a field deferred behind the view's back. A
view that select-related that field on its own queryset then failed with
`FieldError: ... cannot be both deferred and traversed using select_related`.
Classification now goes through the public helper `is_forward_single_relation()`.
**This changes the generated SQL** for those serializers: one query fewer per request.

## 1.0.1 (November 2026)

No changes to the installed package - identical to 1.0. Fixes the Python 3.9 CI job
(`ubuntu-latest` is now Ubuntu 26.04, which `setup-python` cannot provide 3.9 for;
tox-uv downloads it instead) and points the packaging metadata at the real repository.

## 1.0 (November 2026) - first release of this fork

Forked from `drf-flex-fields` 1.0.2.

- **Removed all CoreAPI references.** `from rest_framework.compat import coreapi, coreschema`
  and `FlexFieldsDocsFilterBackend.get_schema_fields()` are gone, which makes the package
  importable on DRF >= 3.17, where CoreAPI no longer exists. Schema documentation is
  provided through `get_schema_operation_parameters()` (OpenAPI).
- **`is_expanded()` now matches expansion paths instead of bare field names**, so
  `?expand=a.b` reports `a` and `a.b` as expanded and `b` as not (upstream #48).
- **An explicit `expand` / `fields` / `omit` argument always wins over the query string,
  including when it is empty**: the arguments default to `None`, and only `None` lets
  the query parameters through (upstream #108).
- Renamed the import package from `rest_flex_fields` to `mind_flex_fields`.
- Settings are read from `MIND_FLEX_FIELDS`, falling back to `REST_FLEX_FIELDS`.
- Guarded `WILDCARD_VALUES = None` in the schema parameter code (previously raised
  `TypeError` on import when wildcards were disabled).
- Added an `isinstance(cls, type)` guard when walking nested `expandable_fields`, so
  lazy string references and non-class values no longer break schema generation.
- Modernized packaging: `pyproject.toml` (PEP 621), `python_requires >= 3.9`,
  `Django >= 4.2`, `djangorestframework >= 3.15`.
- Test suite fixed for current Django: `django.conf.urls.url` -> `django.urls.re_path`,
  dropped the removed `USE_L10N` setting. Added `tests/test_schema.py`.
- Verified against Django 4.2 / 5.1 / 5.2 and DRF 3.15 / 3.16 / 3.17 / 3.18.

<details>
<summary><strong>Upstream changelog (drf-flex-fields)</strong></summary>

## 1.0.2 (March 2023)

- Adds control over whether recursive expansions are allowed and allows setting the max expansion depth. Thanks @andruten!

## 1.0.1 (March 2023)

- Various bug fixes. Thanks @michaelschem, @andruten, and @erielias!

## 1.0.0 (August 2022)

- Improvements to the filter backends for generic foreign key handling and docs generation. Thanks @KrYpTeD974 and @michaelschem!

## 0.9.9 (July 2022)

- Fixes bug in `FlexFieldsFilterBackend`. Thanks @michaelschem!
- Adds `FlexFieldsDocsFilterBackend` for schema population. Thanks @Rjevski!

## 0.9.8 (April 2022)

- Set expandable fields as the default example for expand query parameters in CoreAPI fields. Thanks @JasperSui!

## 0.9.7 (January 2022)

- Includes m2m in prefetch_related clause even if they're not expanded. Thanks @pablolmedorado and @ADR-007!

## 0.9.6 (November 2021)

- Make it possible to use wildcard values with sparse fields requests.

## 0.9.5 (October 2021)

- Adds OpenAPI support. Thanks @soroush-tabesh!
- Updates tests for Django 3.2 and fixes deprecation warning. Thanks @giovannicimolin!

## 0.9.3 (August 2021)

- Fixes bug where custom parameter names were not passed when constructing nested serializers. Thanks @Kandeel4411!

## 0.9.2 (June 2021)

- Ensures `context` dict is passed down to expanded serializers. Thanks @nikeshyad!

## 0.9.1 (June 2021)

- No longer auto removes `source` argument if it's equal to the field name.

## 0.9.0 (April 2021)

- Allows fully qualified import strings for lazy serializer classes.

## 0.8.9 (February 2021)

- Adds OpenAPI support to experimental filter backend. Thanks @LukasBerka!

## 0.8.8 (September 2020)

- Django 3.1.1 fix. Thanks @NiyazNz!
- Docs typo fix. Thanks @zakjholt!

## 0.8.6 (September 2020)

- Adds `is_included` utility function.

## 0.8.5 (May 2020)

- Adds options to customize parameter names and wildcard values.

## 0.8.1 (May 2020)

- Fixes issue related to the experimental filter backend. Thanks @jsatt!

## 0.8.0 (April 2020)

- Adds support for `expand`, `omit` and `fields` query parameters for non-GET requests.
  - Thanks @kotepillar for raising the issue and @Crocmagnon for the idea of delaying field modification to `to_representation()`.

## 0.7.5 (February 2020)

- Simplifies declaration of `expandable_fields`.

## 0.7.0 (February 2020)

- Adds support for different ways of passing arrays in query strings. Thanks @sentyaev!
- Fixes attribute error when map is supplied to split levels utility function. Thanks @hemache!

## 0.6.1 (September 2019)

- Adds experimental support for automatic SQL query optimization via a `FlexFieldsFilterBackend`. Thanks @ADR-007!
- Adds CircleCI config file. Thanks @mikeIFTS!
- Moves declaration of `expandable_fields` to `Meta` class on serializer for consistency with DRF.
- Python 2 is no longer supported.

## 0.5.0 (April 2019)

- Added support for `omit` keyword for field exclusion.

## 0.3.4 (May 2018)

- Handle case where `request` is `None` when accessing request object from serializer. Thanks @jsatt!

## 0.3.3 (April 2018)

- Exposes `FlexFieldsSerializerMixin` in addition to `FlexFieldsModelSerializer`. Thanks @jsatt!

</details>

# Testing

The suite runs on **pytest** (with
[pytest-django](https://pytest-django.readthedocs.io/)); the tests themselves live in a
small DRF project under [`tests/`](tests/). Configuration is in `pyproject.toml`, so no
arguments are needed.

## Quick start

```bash
pip install -r requirements-dev.txt
pytest
```

That runs every test against whatever Django and DRF you happen to have installed. It
works from any directory - `pytest`, `pytest tests/test_views.py`, or
`pytest /path/to/mind-drf-flex-fields`.

Useful variations:

```bash
pytest -x                                   # stop at the first failure
pytest -k expand                            # only tests whose name matches
pytest tests/test_serializer.py             # one file
pytest tests/test_views.py::PetViewTests    # one class
pytest -q                                   # quiet
pytest -W error::DeprecationWarning         # turn deprecations into failures
```

There is no `manage.py`: this is a library, not a Django project. pytest-django is
pointed at the test settings through `DJANGO_SETTINGS_MODULE` in `pyproject.toml`.

## The full matrix

A single `pytest` run only covers one Django/DRF combination. To run all the supported
ones, use [tox](tox.ini) - which is also what CI invokes, so the matrix is declared in
exactly one place:

```bash
pip install tox tox-uv      # tox-uv is optional, but much faster
tox                         # every environment
tox -p auto                 # ...in parallel (about half a minute)
tox -l                      # list the environments
tox -e py312-dj61-drf318    # one combination
tox -e py312-dj61-drf318 -- -x -k expand    # arguments after -- go to pytest
```

Three environments are not version combinations:

| Environment | What it does |
| ----------- | ------------ |
| `checks`    | Asserts no CoreAPI reference ever comes back |
| `wheel`     | Installs the built distribution and smoke-tests it **from outside the source tree**, so the import resolves to the installed package - this is what catches packaging mistakes, such as a module missing from the wheel or an undeclared console script |
| `shim`      | Installs the library *and* the [compat shim](#zero-downtime-migration-optional-shim) and drives the legacy `rest_flex_fields` path, the way a migrating project would |

The matrix environments run from the project root, so they import `mind_flex_fields`
from the source tree (the current directory wins on `sys.path`). That is what you want
while developing; `wheel` and `shim` are the ones that exercise the real artifacts.

## What the suite covers

Beyond the behaviour inherited from upstream (expansion, sparse fields, `omit`, wildcards,
depth limits, the query-optimizing backend), there are regression tests for each problem
this fork fixes:

| File | Covers |
| ---- | ------ |
| [`test_schema.py`](tests/test_schema.py) | OpenAPI parameter generation, and that no CoreAPI hook remains |
| [`test_filter_backend_import.py`](tests/test_filter_backend_import.py) | The backends can be listed in `DEFAULT_FILTER_BACKENDS` without a circular import |
| [`test_settings_compat.py`](tests/test_settings_compat.py) | `MIND_FLEX_FIELDS` / `REST_FLEX_FIELDS` resolution order |
| [`test_migration_cli.py`](tests/test_migration_cli.py) | The migration engine and CLI, including that it needs no Django |
| [`test_compat_shim.py`](tests/test_compat_shim.py) | The shim's resolution, object identity and deprecation warning |

Some of these spawn subprocesses, because the behaviour they check happens during
`django.setup()` or without Django configured at all.

## Troubleshooting

**`tox` fails immediately for one Python version.** Its interpreter is probably an
incomplete build - a pyenv install without `_sqlite3`, for instance - so it dies before
the first test. With `tox-uv`, have uv fetch its own interpreters instead:

```bash
UV_PYTHON_PREFERENCE=only-managed tox
```

**The shim tests are skipped.** They need `compat/`, which only exists in a source
checkout (it is pruned from the sdist, being a separate distribution).

# Credits

This package is a fork of [drf-flex-fields](https://github.com/rsinger86/drf-flex-fields),
created and maintained by [Robert Singer (@rsinger86)](https://github.com/rsinger86) and its
[contributors](https://github.com/rsinger86/drf-flex-fields/graphs/contributors). The vast
majority of the code and documentation here is their work.

This fork exists only to keep the library working with current Django REST Framework
releases. If upstream resumes maintenance and restores DRF compatibility, prefer the
original package.

# License

MIT - see [LICENSE](LICENSE). The original copyright of `drf-flex-fields` is preserved.
