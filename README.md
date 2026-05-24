# Python Testing Repo

This repository is a personal Python testing and learning workspace. It is set up as a place to try patterns, document approaches, and keep runnable reference examples together in one repo instead of scattering them across scratch files.

The current focus is API design and backend architecture in Python, with examples that move from HTTP routing through validation, business logic, persistence, testing, and operational concerns.

## How To Use This Repo

Choose the path that fits what you want to do:

- Learn by topic: start in [`rest_api_examples/README.md`](./rest_api_examples/README.md) and move through the numbered folders.
- Run the examples: use `make run` for the launcher or `make verify` to run the scripted checks.

## Quick Start

```bash
python3 -m pip install -e .[dev]
make run
```

## Repo Layout

- [`rest_api_examples/`](./rest_api_examples/) contains the main example set.
- [`rest_api_examples/main.py`](./rest_api_examples/main.py) is the interactive launcher for the examples.
- [`pyproject.toml`](./pyproject.toml) defines the project dependencies and lightweight tool configuration.
- [`Makefile`](./Makefile) provides `run`, `verify`, and `check` commands.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) describes the conventions for adding or adjusting examples.
- [`CHANGELOG.md`](./CHANGELOG.md) tracks the higher-level repo changes.
- [`LICENSE`](./LICENSE) gives the repo a reusable MIT license.
- [`.gitignore`](./.gitignore) ignores local Python, editor, and macOS generated files.

## What This Repo Is For

- Testing Python patterns before using them in a larger project.
- Keeping runnable examples for common backend topics.
- Comparing architecture approaches, especially around API layering.
- Documenting decisions and tradeoffs in a way that is easy to revisit later.

## Main Example Set

The `rest_api_examples` folder is organized as a step-by-step backend reference. Each topic has its own folder, its own `README.md`, and a runnable example script.

| Topic | Folder | What it covers |
|------|--------|----------------|
| FastAPI app + routers | [`01-fastapi-app-routers`](./rest_api_examples/01-fastapi-app-routers/) | App setup, routers, middleware, CRUD routes, health checks |
| Pydantic schemas | [`02-pydantic-schemas`](./rest_api_examples/02-pydantic-schemas/) | Request/response models, validation, serialization, nested schemas |
| Service methods / business logic | [`03-service-methods`](./rest_api_examples/03-service-methods/) | Framework-independent business rules and service-layer structure |
| Database models + repositories | [`04-database-models-repositories`](./rest_api_examples/04-database-models-repositories/) | In-memory repos, ORM-for-dev notes, raw-SQL-for-production notes |
| Dependency injection | [`05-dependency-injection`](./rest_api_examples/05-dependency-injection/) | Settings, repository wiring, service wiring, auth dependencies |
| Error handling | [`06-error-handling`](./rest_api_examples/06-error-handling/) | Structured errors, validation errors, route misses, exception mapping |
| Auth / permissions | [`07-auth-permissions`](./rest_api_examples/07-auth-permissions/) | Bearer auth, principals, authorization checks |
| Tests | [`08-tests`](./rest_api_examples/08-tests/) | Service tests, API tests, dependency overrides |
| Observability + deployment | [`09-observability-deployment`](./rest_api_examples/09-observability-deployment/) | Logging, metrics, readiness checks, deployment notes |

## Topic Links

- [`rest_api_examples/README.md`](./rest_api_examples/README.md): overall guide to the API example set
- [`01-fastapi-app-routers/README.md`](./rest_api_examples/01-fastapi-app-routers/README.md)
- [`02-pydantic-schemas/README.md`](./rest_api_examples/02-pydantic-schemas/README.md)
- [`03-service-methods/README.md`](./rest_api_examples/03-service-methods/README.md)
- [`04-database-models-repositories/README.md`](./rest_api_examples/04-database-models-repositories/README.md)
- [`05-dependency-injection/README.md`](./rest_api_examples/05-dependency-injection/README.md)
- [`06-error-handling/README.md`](./rest_api_examples/06-error-handling/README.md)
- [`07-auth-permissions/README.md`](./rest_api_examples/07-auth-permissions/README.md)
- [`08-tests/README.md`](./rest_api_examples/08-tests/README.md)
- [`09-observability-deployment/README.md`](./rest_api_examples/09-observability-deployment/README.md)

## Running The Examples

From the repo root:

```bash
make run
```

You can also run individual scripts directly, for example:

```bash
python3 "rest_api_examples/02-pydantic-schemas/pydantic_example.py"
python3 "rest_api_examples/03-service-methods/service_example.py"
python3 "rest_api_examples/04-database-models-repositories/database_example.py"
```

For a quick whole-repo verification pass:

```bash
make verify
make check
```

## Architecture Notes

- Route handlers stay thin and pass work into services.
- Pydantic handles request and response contracts.
- Service methods own business rules and orchestration.
- Repository interfaces isolate persistence from the service layer.
- For database work, the repo notes currently prefer ORM-backed development/testing and raw SQL for production deployments.

## Current Tradeoffs

- The examples optimize for readability and teaching value first.
- Most examples use in-memory stores so they stay runnable without extra setup.
- Production notes are included where the learning version intentionally takes shortcuts.

## Why Keep This Repo

This repo is useful as both a sandbox and a reference shelf. When you want to test an idea quickly, compare implementation styles, or lift a known-good pattern into a real project, the examples here are meant to be easy to run and easy to navigate.
