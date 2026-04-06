# Conventional Commits Rule

Always use [Conventional Commits](https://www.conventionalcommits.org/) format for commit messages.

## Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Types

| Type | Use When |
|------|----------|
| `feat` | Adding a new feature or functionality |
| `fix` | Fixing a bug or issue |
| `docs` | Documentation only changes |
| `style` | Code style changes (formatting, semicolons, etc) that don't affect logic |
| `refactor` | Code changes that neither fix a bug nor add a feature |
| `perf` | Performance improvements |
| `test` | Adding or correcting tests |
| `chore` | Build process, dependencies, or auxiliary tool changes |
| `ci` | CI/CD configuration changes |
| `build` | Build system or external dependency changes |

## Scopes

Use appropriate scopes for this codebase:

| Scope | Description |
|-------|-------------|
| `cli` | CLI commands and interface (`src/broll/cli.py`) |
| `web` | Web UI, templates, static files (`src/broll/web/`) |
| `db` | Database layer, migrations (`src/broll/db.py`, `alembic/`) |
| `api` | API endpoints (`src/broll/web/app.py`) |
| `scanner` | File scanning logic (`src/broll/scanner.py`) |
| `search` | Search functionality (`src/broll/search.py`) |
| `analyzer` | Video analysis/LLM integration (`src/broll/analyzer.py`) |
| `embeddings` | Vector embeddings (`src/broll/embeddings.py`) |
| `config` | Configuration and settings (`src/broll/config.py`) |
| `deps` | Dependencies (`pyproject.toml`) |

## Examples

```
feat(web): add playlist management UI with drag-and-drop reordering

fix(db): resolve migration conflict on playlist_items table

refactor(cli): extract migration helpers into separate functions

docs: update README with Tailscale setup instructions

chore(deps): bump sqlite-vec to 0.2.1

feat(api): add batch add-to-playlist endpoint

test(db): add tests for playlist CRUD operations
```

## Rules

1. **Always use lowercase** for type and scope
2. **No period at the end** of the description
3. **Use imperative mood** ("add" not "added", "fix" not "fixed")
4. **Keep description under 72 characters** for the first line
5. **Use body** for additional context when needed
6. **Reference issues** in footer when applicable: `Closes #123`

## Breaking Changes

For breaking changes, add `!` after type/scope or include `BREAKING CHANGE:` in footer:

```
feat(api)!: remove deprecated /v1/search endpoint

refactor(db)!: change playlist_items schema structure

feat(cli): change default port for web command

BREAKING CHANGE: port changed from 5000 to 8080
```
