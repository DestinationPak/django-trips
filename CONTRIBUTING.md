# Contributing

Thanks for considering a contribution to `django-trips`.

## Development setup

All development happens inside Docker; there is no supported bare-metal workflow.

```bash
make build      # docker compose build
make dev.up     # start the web service
make update_db  # run migrations
make test       # run the test suite
```

See `make help` for the full command list.

Prefer a local (non-Docker) environment? Install the package editable with its dev
extras and point it at the bundled dev settings:

```bash
pip install -e ".[dev]"
DJANGO_SETTINGS_MODULE=settings.test pytest
```

## Making a change

- Write tests as `django.test.TestCase` subclasses.
- Build fixtures via `django_trips/tests/factories.py`, not `Model.objects.create(...)`
  directly, unless the test's whole point is model/manager mechanics - `django_hotels`
  and `django_rentals` both mirror this module's shape, so keep its public names stable.
- Run `pre-commit run --all-files` (isort + pylint) before opening a PR - the same
  checks run in CI and will block merge otherwise.
- Update `CHANGELOG.md`'s `[Unreleased]` section in the same PR as the change, not
  reconstructed later from git log.

## Opening a PR

- Target `master`.
- CI runs the test matrix (`Unit Tests`) and `Quality` (pylint) on every PR - both must
  pass before merge.

## Releasing (maintainers)

Releases are entirely CI-driven; there is no local/manual publish path.

1. Move the changes documented under `CHANGELOG.md`'s `[Unreleased]` section into a new
   dated `## [X.Y.Z] - YYYY-MM-DD` section, and commit that to `master`.
2. Tag that commit with the plain version number (`git tag X.Y.Z`, matching
   [SemVer](https://semver.org/)) and push the tag: `git push origin X.Y.Z`.
3. `.github/workflows/release.yaml` takes it from there: it verifies the tag is newer
   than what's live on PyPI, builds the sdist/wheel (version is derived from the tag
   itself via `setuptools-scm` - nothing to bump by hand), runs `twine check`, publishes
   to PyPI via Trusted Publishing (OIDC, no stored token), and creates a GitHub Release.

Pre-releases (`X.Y.Za1`, `X.Y.Zb1`, `X.Y.Zrc1`) are supported by the same workflow.

Note: this repo's git tags include a legacy `v`-prefixed series (`v0.2.1` through
`v2.8`) predating the current bare-number scheme (`1.0.2` onward, matching what's
actually live on PyPI). Always tag new releases without the `v` prefix, matching the
current scheme.
