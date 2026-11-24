# Development

## Code Checks

**Before each commit (pre-commit hook).** Git runs these checks when you do `git commit`. If a check fails, Git stops the commit. Some checks correct the files. Then, add the corrected files with `git add` and do the commit again.

| Check | What it does |
|-------|--------------|
| `ruff check --fix` | Finds code errors. Corrects the errors that it can. |
| `ruff format` | Formats the Python code. |
| `sqlfluff fix` | Formats the SQL files: upper-case keywords, lower-case types and names, aligned column types, a maximum of 88 characters on a line. It stops the commit for a problem that it cannot correct. |
| `check-yaml`, `check-toml` | Finds syntax errors in YAML and TOML files, for example `config/leagues.yaml`. |
| `end-of-file-fixer`, `trailing-whitespace` | Removes spaces at line ends. Adds a newline at the end of each file. |
| `check-merge-conflict` | Finds merge-conflict markers, for example `<<<<<<<`. |
| `check-added-large-files` | Stops a commit that adds a large file. |

The hooks do not change the files in `tests/fixtures/`. These files are copies of real pages, and the tests need them without changes.

To run all checks on all files:

```bash
uv run pre-commit run --all-files
```

**On GitHub (CI).** GitHub Actions runs two jobs on each pull request and on each push to `main`:

| Job | Steps | Time |
|-----|-------|------|
| `lint` | `ruff format --check`, `ruff check`, `basedpyright`, `sqlfluff lint` | Approximately 15 seconds |
| `test` | Install Chromium, apply the migrations, then `pytest` | Approximately 1 minute |

The two jobs run at the same time. The `lint` job does not install a browser, thus it gives a result quickly.

The `test` job has a PostgreSQL 18 *service container* with the name `postgres`. GitHub starts it before the steps and waits until its health check passes. The job runs in a container, thus it connects to `postgres:5432` on the job network. The step `Apply migrations` runs the real migration command on an empty database. Then the database tests run.

To check the workflow file before you push it, use [actionlint](https://github.com/rhysd/actionlint). It finds unknown keys and wrong step structure. It does not find a wrong value, for example a wrong port.

The type checker (`basedpyright`) runs only in CI, not in the pre-commit hook. It checks the full project, not only the changed files, and it takes approximately 9 seconds on a laptop. A slow hook makes people skip it. Your editor shows the same type errors while you write the code (see the version rules below).

To run the type checker in your terminal:

```bash
uv run basedpyright
```

The `test` job runs in the `mcr.microsoft.com/playwright/python` Docker image. This image contains the system packages that Chromium needs. Before, CI installed these packages with `apt-get`. On a slow day, the Ubuntu package server made this step take 9 minutes.

**Version rules:**

- The pre-commit hook, CI and your terminal use the same Ruff version: the version in `uv.lock`. The hook runs `uv run ruff`. It does not install a different Ruff.
- The tag of the Docker image must agree with the Playwright version in `uv.lock`, for example `v1.65.1-noble` for Playwright 1.65.1. When you upgrade Playwright, change the tag in `.github/workflows/ci.yml` in the same pull request.
- CI and your terminal use the basedpyright version in `uv.lock`. The `[tool.pyright]` section of `pyproject.toml` sets `typeCheckingMode = "standard"`. An editor that uses basedpyright, Pyright or Pylance reads this section. The project setting replaces the setting of the editor. Thus, the editor shows the same errors as CI.
- The PostgreSQL image in `docker-compose.yaml` and the service image in `.github/workflows/ci.yml` must have the same major version (now `postgres:18`). If not, a test can pass in CI and fail on your computer.
- The sqlfluff settings are in the `[tool.sqlfluff...]` sections of `pyproject.toml`. The hook, CI and your terminal use the sqlfluff version in `uv.lock`.
