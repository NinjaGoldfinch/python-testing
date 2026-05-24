# Python Testing Repo

This repository is a personal Python testing and learning workspace. It is set up as a place to try patterns, document approaches, and keep runnable reference examples together in one repo instead of scattering them across scratch files.

The current focus is API design and backend architecture in Python, with examples that move from HTTP routing through validation, business logic, persistence, testing, and operational concerns.

## Repo Layout

- [`Rest API examples/`](./Rest%20API%20examples/) contains the main example set.
- [`Rest API examples/main.py`](./Rest%20API%20examples/main.py) is the interactive launcher for the examples.
- [`.gitignore`](./.gitignore) ignores local Python, editor, and macOS generated files.

## What This Repo Is For

- Testing Python patterns before using them in a larger project.
- Keeping runnable examples for common backend topics.
- Comparing architecture approaches, especially around API layering.
- Documenting decisions and tradeoffs in a way that is easy to revisit later.

## Main Example Set

The `Rest API examples` folder is organized as a step-by-step backend reference. Each topic has its own folder, its own `README.md`, and a runnable example script.

| Topic | Folder | What it covers |
|------|--------|----------------|
| FastAPI app + routers | [`01-fastapi-app-routers`](./Rest%20API%20examples/01-fastapi-app-routers/) | App setup, routers, middleware, CRUD routes, health checks |
| Pydantic schemas | [`02-pydantic-schemas`](./Rest%20API%20examples/02-pydantic-schemas/) | Request/response models, validation, serialization, nested schemas |
| Service methods / business logic | [`03-service-methods`](./Rest%20API%20examples/03-service-methods/) | Framework-independent business rules and service-layer structure |
| Database models + repositories | [`04-database-models-repositories`](./Rest%20API%20examples/04-database-models-repositories/) | In-memory repos, ORM-for-dev notes, raw-SQL-for-production notes |
| Dependency injection | [`05-dependency-injection`](./Rest%20API%20examples/05-dependency-injection/) | Settings, repository wiring, service wiring, auth dependencies |
| Error handling | [`06-error-handling`](./Rest%20API%20examples/06-error-handling/) | Structured errors, validation errors, route misses, exception mapping |
| Auth / permissions | [`07-auth-permissions`](./Rest%20API%20examples/07-auth-permissions/) | Bearer auth, principals, authorization checks |
| Tests | [`08-tests`](./Rest%20API%20examples/08-tests/) | Service tests, API tests, dependency overrides |
| Observability + deployment | [`09-observability-deployment`](./Rest%20API%20examples/09-observability-deployment/) | Logging, metrics, readiness checks, deployment notes |

## Topic Links

- [`Rest API examples/README.md`](./Rest%20API%20examples/README.md): overall guide to the API example set
- [`01-fastapi-app-routers/README.md`](./Rest%20API%20examples/01-fastapi-app-routers/README.md)
- [`02-pydantic-schemas/README.md`](./Rest%20API%20examples/02-pydantic-schemas/README.md)
- [`03-service-methods/README.md`](./Rest%20API%20examples/03-service-methods/README.md)
- [`04-database-models-repositories/README.md`](./Rest%20API%20examples/04-database-models-repositories/README.md)
- [`05-dependency-injection/README.md`](./Rest%20API%20examples/05-dependency-injection/README.md)
- [`06-error-handling/README.md`](./Rest%20API%20examples/06-error-handling/README.md)
- [`07-auth-permissions/README.md`](./Rest%20API%20examples/07-auth-permissions/README.md)
- [`08-tests/README.md`](./Rest%20API%20examples/08-tests/README.md)
- [`09-observability-deployment/README.md`](./Rest%20API%20examples/09-observability-deployment/README.md)

## Running The Examples

From the repo root:

```bash
cd "Rest API examples"
python3 main.py
```

You can also run individual scripts directly, for example:

```bash
python3 "Rest API examples/02-pydantic-schemas/pydantic_example.py"
python3 "Rest API examples/03-service-methods/service_example.py"
python3 "Rest API examples/04-database-models-repositories/database_example.py"
```

## Architecture Notes

- Route handlers stay thin and pass work into services.
- Pydantic handles request and response contracts.
- Service methods own business rules and orchestration.
- Repository interfaces isolate persistence from the service layer.
- For database work, the repo notes currently prefer ORM-backed development/testing and raw SQL for production deployments.

## Why Keep This Repo

This repo is useful as both a sandbox and a reference shelf. When you want to test an idea quickly, compare implementation styles, or lift a known-good pattern into a real project, the examples here are meant to be easy to run and easy to navigate.
