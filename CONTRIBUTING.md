# Contributing to RouteMonitor

## Development Setup

```bash
git clone https://github.com/rohithachanta14/routemonitor.git
cd routemonitor

# Install dev dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Start services
docker compose up -d

# Run migrations
docker compose exec api alembic upgrade head

# Run tests
TESTING=1 pytest tests/unit/ -v
```

## Code Style

- `black` for formatting (line length 100)
- `isort` for import ordering
- `flake8` for linting
- `mypy` for type checking

```bash
black .
isort .
flake8 api/ core/ tasks/
mypy api/ core/ tasks/ --ignore-missing-imports
```

## Branch Naming

- `feature/description` — new features
- `fix/description` — bug fixes
- `phase-N/description` — phase implementation work

## Commit Messages

```
type(scope): short description

Types: feat, fix, docs, test, refactor, perf, chore
Examples:
  feat(detector): add correlated failure detection
  fix(bmp_parser): handle extended-length path attributes
  test(telemetry): add pagination tests for route events
```
