# Releasing aieasybatch

The package name `aieasybatch` is free on **PyPI** and **npm**. Two ways to publish — pick one.

## Pre-flight (already validated, but to re-check locally)

```bash
# Python
python -m build                              # -> dist/*.whl + dist/*.tar.gz
python -m venv /tmp/v && /tmp/v/bin/pip install -U twine
/tmp/v/bin/twine check dist/*                # must say PASSED (needs a recent `packaging`)

# JS
cd js && node --test && npm publish --dry-run
```

> Note: `twine check` needs `packaging >= 24.2` (PEP 639 license metadata). A clean venv
> gets that automatically; some system Pythons pin an older one.

---

## Option A — automated, tokenless (recommended)

One-time setup, then every release is just a tag.

1. **PyPI trusted publishing** (no API token ever): on <https://pypi.org> → *Your projects →
   Publishing* (or *Account → Publishing* for a new project), add a **GitHub Actions**
   publisher:
   - Owner: `liam499`  ·  Repo: `easy-batch-prompting`
   - Workflow: `release.yml`  ·  Environment: `release`
2. **npm**: create an *Automation* token at <https://www.npmjs.com/settings/~/tokens> and add
   it as the repo secret **`NPM_TOKEN`** (Settings → Secrets and variables → Actions). *(Or
   configure npm OIDC trusted publishing and delete the `NODE_AUTH_TOKEN` line in
   `release.yml`.)*
3. **Tag and push** — `.github/workflows/release.yml` builds, tests, and publishes both:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

## Option B — publish from your machine right now (30 seconds)

```bash
# PyPI  (token from https://pypi.org/manage/account/token/)
python -m build
python -m twine upload dist/*            # username: __token__   password: pypi-...

# npm   (after `npm login`)
cd js && npm publish --access public
```

---

## After publishing

```bash
pip install aieasybatch        # smoke
npm install aieasybatch
```

Bump `version` in **both** `pyproject.toml` and `js/package.json` (and `__version__` in
`src/aieasybatch/__init__.py`, which the single-file build reads) for the next release, then
`python tools/build_single.py` to refresh `aieasybatch.py`.
