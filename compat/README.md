# mind-drf-flex-fields-compat

Temporary compatibility shim for
[mind-drf-flex-fields](https://pypi.org/project/mind-drf-flex-fields/), a fork of
`drf-flex-fields`.

Installing it makes the old `rest_flex_fields` import path resolve to
`mind_flex_fields`, so a project can swap the dependency **without** changing any code
yet:

```bash
pip uninstall drf-flex-fields
pip install mind-drf-flex-fields mind-drf-flex-fields-compat
# the project still boots, with every `rest_flex_fields` reference intact
```

Then rewrite the references and drop the shim:

```bash
mind-flex-fields-migrate
pip uninstall mind-drf-flex-fields-compat
```

Everything is re-exported from `mind_flex_fields` - the same objects, not copies - so
`isinstance` and `issubclass` keep working, and dotted settings strings such as
`"rest_flex_fields.filter_backends.FlexFieldsFilterBackend"` resolve as before. Importing
it raises a `DeprecationWarning`.

**Never install this alongside the real `drf-flex-fields`**: both provide a top-level
`rest_flex_fields` package and would overwrite each other's files.

See the [main project README](https://pypi.org/project/mind-drf-flex-fields/) for details.
