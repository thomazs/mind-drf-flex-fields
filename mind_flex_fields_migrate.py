"""
Migrates a project from `drf-flex-fields` to `mind-drf-flex-fields`.

Rewrites `rest_flex_fields` references - import statements and dotted strings
alike - to `mind_flex_fields`, and optionally the distribution name in
requirements files and the `REST_FLEX_FIELDS` setting.

This is a plain CLI rather than a Django management command, on purpose. A
management command needs Django to boot, and half-way through the migration it
cannot: a project whose settings still name `rest_flex_fields.filter_backends`
dies during `django.setup()`, because that module fails to import on current
DRF releases. Installing the old package alongside does not help either - it is
the old module itself that is broken. So this module is a **top-level module,
outside the `mind_flex_fields` package** (whose `__init__` reads Django
settings and imports DRF), and it imports nothing from Django.

    mind-flex-fields-migrate --dry-run --diff
    python -m mind_flex_fields_migrate --help
"""

import argparse
import difflib
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import (
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
)

#: Directories that are never walked into.
DEFAULT_EXCLUDED_DIRS = {
    ".bzr",
    ".direnv",
    ".eggs",
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "venv",
}

#: Files whose dependency declarations are rewritten with
#: ``--include-requirements``.
REQUIREMENT_FILE_NAMES = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "Pipfile",
    "constraints.txt",
}


class Rule(NamedTuple):
    label: str
    pattern: Pattern
    replacement: str


#: The import package was renamed. Matches `rest_flex_fields` as a whole word,
#: which covers `import rest_flex_fields`, `from rest_flex_fields.x import y`
#: and dotted strings such as
#: "rest_flex_fields.filter_backends.FlexFieldsFilterBackend".
IMPORT_RULE = Rule(
    label="imports",
    pattern=re.compile(r"\brest_flex_fields\b"),
    replacement="mind_flex_fields",
)

#: Optional: the settings dict was renamed. `REST_FLEX_FIELDS` keeps working as
#: a fallback, so this is opt-in.
SETTINGS_RULE = Rule(
    label="settings",
    pattern=re.compile(r"\bREST_FLEX_FIELDS\b"),
    replacement="MIND_FLEX_FIELDS",
)

#: Optional: the distribution name on PyPI. The negative lookbehind keeps the
#: rule idempotent - it must not turn `mind-drf-flex-fields` into
#: `mind-mind-drf-flex-fields`.
REQUIREMENT_RULE = Rule(
    label="requirements",
    pattern=re.compile(r"(?<![\w.-])drf-flex-fields\b"),
    replacement="mind-drf-flex-fields",
)

#: Lines that still carry a version specifier after the rename.
STALE_PIN_RE = re.compile(
    r"^.*\bmind-drf-flex-fields\s*(==|~=|>=|<=|>|<|!=).*$", re.MULTILINE
)


class Change(NamedTuple):
    path: Path
    original: str
    updated: str
    hits: List[Tuple[str, int]]

    @property
    def total(self) -> int:
        return sum(count for _, count in self.hits)

    def summary(self) -> str:
        return ", ".join(f"{count} {label}" for label, count in self.hits)

    def diff(self, root: Optional[Path] = None) -> Iterator[str]:
        label = display_path(self.path, root)
        yield from difflib.unified_diff(
            self.original.splitlines(keepends=True),
            self.updated.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
        )

    def stale_pins(self) -> List[str]:
        """Version specifiers that still point at an upstream version."""
        if not any(label == REQUIREMENT_RULE.label for label, _ in self.hits):
            return []
        return [m.group(0).strip() for m in STALE_PIN_RE.finditer(self.updated)]


def display_path(path: Path, root: Optional[Path]) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def own_package_dir() -> Optional[Path]:
    """
    The directory of the installed `mind_flex_fields` package, so that the
    library's own source is never rewritten.

    Uses `find_spec` rather than an import: importing the package would read
    Django settings, which is precisely what this module avoids.
    """
    try:
        spec = importlib.util.find_spec("mind_flex_fields")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin).resolve().parent


def normalize_extensions(extensions: Optional[Iterable[str]]) -> Set[str]:
    if not extensions:
        return {".py"}
    return {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions
    }


def is_requirements_file(path: Path) -> bool:
    if path.name in REQUIREMENT_FILE_NAMES:
        return True
    return path.name.startswith("requirements") and path.suffix in {".txt", ".in"}


def iter_files(
    root: Path,
    extensions: Set[str],
    excluded_dirs: Set[str],
    include_requirements: bool,
) -> Iterator[Path]:
    package_dir = own_package_dir()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in sorted(dirnames)
            if d not in excluded_dirs and not d.endswith(".egg-info")
        ]
        current = Path(dirpath).resolve()

        # Never rewrite the library's own source.
        if package_dir is not None and (
            current == package_dir or package_dir in current.parents
        ):
            dirnames[:] = []
            continue

        for filename in sorted(filenames):
            path = (current / filename).resolve()
            if path.suffix.lower() in extensions:
                yield path
            elif include_requirements and is_requirements_file(path):
                yield path


def build_rules(rename_settings: bool, include_requirements: bool):
    code_rules = [IMPORT_RULE]
    if rename_settings:
        code_rules.append(SETTINGS_RULE)
    requirement_rules = [REQUIREMENT_RULE] if include_requirements else []
    return code_rules, requirement_rules


def plan(
    root: Path,
    extensions: Optional[Iterable[str]] = None,
    excluded_dirs: Optional[Iterable[str]] = None,
    include_requirements: bool = False,
    rename_settings: bool = False,
) -> Tuple[List[Change], List[Tuple[Path, str]]]:
    """
    Compute the rewrites without touching anything.

    Returns ``(changes, skipped)``, where ``skipped`` holds
    ``(path, reason)`` pairs for files that could not be read.
    """
    extensions = normalize_extensions(extensions)
    excluded = DEFAULT_EXCLUDED_DIRS | set(excluded_dirs or ())
    code_rules, requirement_rules = build_rules(rename_settings, include_requirements)

    changes: List[Change] = []
    skipped: List[Tuple[Path, str]] = []

    for path in iter_files(root, extensions, excluded, bool(requirement_rules)):
        rules = list(code_rules if path.suffix.lower() in extensions else [])
        if requirement_rules and is_requirements_file(path):
            rules += requirement_rules

        if not rules:
            continue

        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            skipped.append((path, type(exc).__name__))
            continue

        updated = original
        hits: List[Tuple[str, int]] = []
        for rule in rules:
            updated, count = rule.pattern.subn(rule.replacement, updated)
            if count:
                hits.append((rule.label, count))

        if updated != original:
            changes.append(Change(path, original, updated, hits))

    return changes, skipped


def apply(changes: Sequence[Change]) -> Tuple[int, List[Tuple[Path, str]]]:
    """Write the planned changes. Returns ``(written, errors)``."""
    written = 0
    errors: List[Tuple[Path, str]] = []
    for change in changes:
        try:
            change.path.write_text(change.updated, encoding="utf-8")
        except OSError as exc:
            errors.append((change.path, str(exc)))
            continue
        written += 1
    return written, errors


# -- standalone CLI --------------------------------------------------------


def build_parser(prog: Optional[str] = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Rewrite references to drf-flex-fields (rest_flex_fields) so that "
            "they point at mind-drf-flex-fields (mind_flex_fields). Runs "
            "without loading Django, so it works even when the project cannot "
            "boot yet."
        ),
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Directory to walk. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--extension",
        action="append",
        dest="extensions",
        metavar="EXT",
        help="File extension to rewrite; repeat to pass several. Default: .py",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="excludes",
        default=[],
        metavar="DIR",
        help="Extra directory name to skip; repeat to pass several.",
    )
    parser.add_argument(
        "--include-requirements",
        action="store_true",
        help=(
            "Also rewrite the distribution name in requirements files, "
            "pyproject.toml, setup.py, setup.cfg and Pipfile."
        ),
    )
    parser.add_argument(
        "--rename-settings",
        action="store_true",
        help="Also rename the REST_FLEX_FIELDS setting to MIND_FLEX_FIELDS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff of every change.",
    )
    parser.add_argument(
        "--noinput",
        "--no-input",
        action="store_false",
        dest="interactive",
        help="Do not prompt for confirmation before writing.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    options = build_parser().parse_args(argv)

    root = Path(options.path).expanduser() if options.path else Path.cwd()
    root = root.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    changes, skipped = plan(
        root,
        extensions=options.extensions,
        excluded_dirs=options.excludes,
        include_requirements=options.include_requirements,
        rename_settings=options.rename_settings,
    )

    print(f"Scanning {root}")
    for path, reason in skipped:
        print(f"Skipped {path} ({reason})", file=sys.stderr)

    if not changes:
        print("Nothing to migrate - no references to drf-flex-fields found.")
        return 0

    print()
    for change in changes:
        print(f"  {display_path(change.path, root)} ({change.summary()})")
        if options.diff:
            for line in change.diff(root):
                print(line.rstrip("\n"))

    total = sum(change.total for change in changes)
    print()
    print(f"{total} replacement(s) across {len(changes)} file(s).")

    if options.dry_run:
        print("Dry run - no files were modified.")
        return 0

    if options.interactive:
        print(
            f"\nThis will modify {len(changes)} file(s) in place. "
            "Make sure your work is committed to version control."
        )
        if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Aborted - nothing written.")
            return 1

    written, errors = apply(changes)
    for path, message in errors:
        print(f"Could not write {path}: {message}", file=sys.stderr)
    print(f"Rewrote {written} file(s).")

    pins = [(change.path, pin) for change in changes for pin in change.stale_pins()]
    if pins:
        print(
            "\nCheck these version specifiers - they still carry the upstream "
            "version:"
        )
        for path, pin in pins:
            print(f"  {display_path(path, root)}: {pin}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
