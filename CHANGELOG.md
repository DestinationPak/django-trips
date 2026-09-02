# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This file starts with `1.2.0` - the 24 releases before that (`0.2`
through `1.1.2`) predate this changelog and aren't reconstructed here to
avoid misrepresenting history from commit titles alone. See the
[tags](https://github.com/DestinationPak/django-trips/tags) and
[releases](https://github.com/DestinationPak/django-trips/releases) pages
for that history.

## [Unreleased]

### Changed
- Raised the `djangorestframework` ceiling from `<3.17` to `<3.18`, so
  consumers can pick up 3.17.2's fix for GHSA-2m8g-3cmr-wg3w (a bypass
  of Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` when parsing oversized
  JSON/urlencoded bodies through DRF's `request.data`) and
  GHSA-g47c-3xmw-q6m2 (`AdminRenderer` disclosing GET-protected data on
  an invalid write request).

## [1.2.2] - 2026-08-29

### Changed
- Migrated packaging from `setup.py`/`setup.cfg`/`MANIFEST.in` to a single
  `pyproject.toml` (PEP 621), and moved the importable app to `src/
  django_trips/` (the throwaway dev project shell is now `devsite/`,
  renamed from `django-trips/` to stop the two from being confused with
  each other or with the published package).
- `__version__` is now derived from the git tag at build time via
  `setuptools-scm`, instead of being a hand-maintained string in
  `__init__.py` that the release workflow patched with `sed`. The release
  workflow now fails outright if the tag doesn't match the version
  setuptools-scm computes, rather than silently patching around a mismatch.
- Runtime and dev dependencies are declared once, in `pyproject.toml`
  (`[project.dependencies]` / `[project.optional-dependencies] dev`/`docs`)
  - `requirements.txt`/`requirements-dev.txt` are gone, and CI/Docker both
    install via `pip install -e ".[dev]"` instead.
- `.dockerignore` was leftover Node/JS cookiecutter boilerplate
  (`node_modules`, `.eslintrc.json`, `.npmignore`, `commitlint.config.js`)
  that also excluded `README.md`/`LICENSE` from the build context - broken
  now that `pyproject.toml` needs both present to build package metadata.
  Replaced with a Python-appropriate ignore list.
- Removed `default_app_config` from `django_trips/__init__.py` - dead
  code since Django 3.2 (this package requires Django>=4.2), superseded
  by `apps.py`'s own `AppConfig` auto-discovery.

### Fixed
- **The `Unit Tests` CI workflow's "run tests" step was running
  `python -m run_lint.py` (a copy-paste of the `Quality` workflow's lint
  command) instead of `pytest` - this package's test suite has never
  actually run on a pull request.** `django_hotels` and `django_rentals`
  both had this exact bug already fixed; it was still live here.
- The `Quality` workflow's own pylint step (`python -m run_lint.py`) was
  invalid syntax - `-m` takes a module name, not a filename, so it raised
  `ModuleNotFoundError` on every run and pylint never actually executed.
- `run_lint.py` was passing all of its pylint flags as one joined string
  instead of separate list items, so `--load-plugins pylint_django` and
  `--django-settings-module` were silently never applied - Django-specific
  lint checks have never actually been active.
- `.pylintrc` set `suggestion-mode`, an option pylint 4.x removed; every
  lint run errored on an unrecognized option.
- `setup.py` and `setup.cfg` had drifted to disagree with each other -
  `setup.py` (which actually took effect, since it called `setup()` with
  explicit kwargs rather than deferring to `setup.cfg`) pointed
  `url` at `github.com/DestinationPak/django-trips`, while `setup.cfg`'s
  unused `url` still pointed at `github.com/awaisdar001/django-trips`, a
  stale pre-org-transfer URL. `pyproject.toml` now has one `url`, matching
  the actual git remote and README.
- `[tool.setuptools.packages.find]`'s `exclude` alone doesn't stop
  PEP 621's default `include-package-data = true` (combined with
  setuptools-scm's git-file-finder) from sweeping every git-tracked file
  under a found package's directory into the wheel as package data -
  `django_trips.api.tests`/`django_trips.management.tests` (this
  package's own internal test suites, not documented as consumer-facing)
  were leaking into the built wheel despite being listed under `exclude`.
  `include-package-data` is now explicitly disabled; `django_trips.tests`
  (the factories module, which *is* documented as consumer-facing and
  mirrored by `django_hotels`/`django_rentals`) still ships as intended.
- Removed the `Makefile`'s `publish.test`/`publish.prod` targets - a
  second, local release path that both duplicated `release.yaml`'s CI
  pipeline via a deprecated `setup.py sdist bdist_wheel` invocation and
  bypassed its version-gate and PyPI Trusted Publishing (OIDC) entirely in
  favor of a locally-stored token. It also predated the `src/` layout
  migration and would have deleted the real package (`rm -rf
  src/django_trips`) if run today.

### Added
- This `CHANGELOG.md` itself - none existed before, despite 24+ prior
  PyPI releases.
- `.github/dependabot.yml` (pip + github-actions ecosystems, weekly) -
  `django_hotels`/`django_rentals` both already had this, trips didn't.
- `pyproject.toml`'s `docs` extra (`sphinx`, `myst-parser`, `furo`) and a
  `docs/` Sphinx scaffold, publishable to Read the Docs.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant), and
  `SECURITY.md` (vulnerability disclosure process).
- A `Development Status :: 4 - Beta` classifier - previously absent
  entirely, despite being one of the most visible fields on a package's
  PyPI page.

## [1.2.1]

### Fixed
- `setup.py` now actually packages `api/`, `migrations/`, and
  `management/` - its `find_packages()` call was missing them, so
  installs from `1.2.0` and earlier shipped an incomplete package.

## [1.2.0]

### Added
- `Location` split into `AbstractLocation` + `Location(AbstractLocation)`,
  and made swappable via `swapper` - the same mechanism `django_hotels`
  and `django_rentals` mirror one vertical over each.
- `DATABASES` is now configurable via a `DATABASE_ENGINE` env var
  (defaulting to SQLite), matching the pattern well-known reusable Django
  apps use.

### Fixed
- The test suite now actually uses SQLite instead of requiring a running
  MySQL server - nothing in this package's models/migrations is
  MySQL-specific.
- `docker-compose.yml`'s `web` service no longer hardcodes
  `DATABASE_ENGINE=mysql`, which had been silently overriding the
  SQLite-by-default configurability above.
