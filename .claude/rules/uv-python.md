# UV Python Package Manager

Use [UV](https://docs.astral.sh/uv/) for all Python package management in this project.

## Why UV

- **Fast**: 10-100x faster than pip
- **Unified**: Replaces pip, pip-tools, pipx, poetry, pyenv, twine, virtualenv
- **Lock file**: `uv.lock` ensures reproducible builds
- **Project-based**: Uses `pyproject.toml`

## Commands

### Dependency Management

| Task | UV Command | Legacy Equivalent |
|------|-----------|-------------------|
| Install all deps | `uv sync` | `pip install -r requirements.txt` |
| Add dependency | `uv add <package>` | `pip install <package>` |
| Add dev dependency | `uv add --dev <package>` | `pip install --dev <package>` |
| Remove dependency | `uv remove <package>` | `pip uninstall <package>` |
| Update lock file | `uv lock` | `pip-compile` |

### Running Code

| Task | UV Command | Legacy Equivalent |
|------|-----------|-------------------|
| Run Python | `uv run python <script>` | `python <script>` |
| Run module | `uv run python -m <module>` | `python -m <module>` |
| Run CLI | `uv run <command>` | `<command>` |

### Environment

| Task | UV Command |
|------|-----------|
| Create venv | `uv venv` (done automatically by sync) |
| Activate venv | `source .venv/bin/activate` |
| Show env info | `uv pip list` |

## Project Context

- **Lock file**: `uv.lock` exists and should be kept up to date
- **Python**: Requires >=3.12 (specified in `pyproject.toml`)
- **Dev dependencies**: In `[dependency-groups.dev]` (pytest, ruff, alembic)

## Rules

1. **Always use `uv run`** instead of activating the venv or using bare `python` commands
2. **Sync after changes** to `pyproject.toml`: `uv sync`
3. **Commit `uv.lock`** when dependencies change
4. **Never use pip directly** for installation in this project

## Examples

```bash
# Run the CLI (correct)
uv run broll --help

# Run a module (correct)
uv run python -m alembic --help

# Add a dependency (correct)
uv add requests

# Run tests (correct)
uv run pytest

# DON'T do this (wrong)
.venv/bin/python -m broll --help
pip install requests
```
