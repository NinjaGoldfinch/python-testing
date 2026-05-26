# Python Testing Repo

A personal workspace for learning and experimenting with Python backend patterns. Same idea as having a dedicated scratch space — except everything here is organised, runnable, and easy to come back to later instead of getting lost across random files.

The current focus is API design and backend architecture, working through HTTP routing, validation, business logic, persistence, testing, and operational concerns in a logical progression.

---

## Getting Started

```bash
python3 -m pip install -e .[dev]
make run
```

To learn by topic, start in [`rest_api_examples/README.md`](./rest_api_examples/README.md) and work through the numbered folders in order.

---

## Repo Layout

```
rest_api_examples/         The main example set
  main.py                  Interactive launcher for the examples

pyproject.toml             Dependencies and tool config
Makefile                   run, verify, and check targets
CONTRIBUTING.md            How to add or adjust examples
CHANGELOG.md               Repo-level change history
LICENSE                    MIT
```

---

## What's Covered

The `rest_api_examples` folder is a step-by-step backend reference. Each topic has its own folder, its own `README.md`, and a runnable example script.

| # | Topic | What it covers |
|---|-------|----------------|
| 01 | [FastAPI app + routers](./rest_api_examples/01-fastapi-app-routers/) | App setup, routers, middleware, CRUD routes, health checks |
| 02 | [Pydantic schemas](./rest_api_examples/02-pydantic-schemas/) | Request/response models, validation, serialization, nested schemas |
| 03 | [Service methods](./rest_api_examples/03-service-methods/) | Framework-independent business rules and service-layer structure |
| 04 | [Database models + repositories](./rest_api_examples/04-database-models-repositories/) | In-memory repos, ORM-for-dev notes, raw-SQL-for-production notes |
| 05 | [Dependency injection](./rest_api_examples/05-dependency-injection/) | Settings, repository wiring, service wiring, auth dependencies |
| 06 | [Error handling](./rest_api_examples/06-error-handling/) | Structured errors, validation errors, route misses, exception mapping |
| 07 | [Auth + permissions](./rest_api_examples/07-auth-permissions/) | Bearer auth, principals, authorization checks |
| 08 | [Tests](./rest_api_examples/08-tests/) | Service tests, API tests, dependency overrides |
| 09 | [Observability + deployment](./rest_api_examples/09-observability-deployment/) | Logging, metrics, readiness checks, deployment notes |

---

## Running Things

From the repo root:

```bash
make run        # Interactive launcher
make verify     # Full scripted check across all examples
make check
```

Or run individual scripts directly:

```bash
python3 "rest_api_examples/02-pydantic-schemas/pydantic_example.py"
python3 "rest_api_examples/03-service-methods/service_example.py"
python3 "rest_api_examples/04-database-models-repositories/database_example.py"
```

---

## Design Decisions

A few principles that shape how the examples are written:

- **Route handlers stay thin.** They receive a request and hand off to a service — that's it.
- **Pydantic owns the contract.** All request and response shapes go through Pydantic models.
- **Business logic lives in services.** Rules and orchestration belong there, not in the handler.
- **Repositories isolate persistence.** The service layer shouldn't care whether data comes from memory, an ORM, or raw SQL.
- **Database approach is intentionally split** — ORM for development and testing, raw SQL for production. The examples note where this tradeoff applies.

Most examples use in-memory stores so everything stays runnable without any extra setup. Where the learning version takes a deliberate shortcut, there's a note explaining what a production version would do differently.

---

## Why This Exists

Mostly as a reference shelf. When you want to test an idea quickly, compare two approaches, or pull a known-good pattern into a real project, it's useful to have examples that are already runnable and clearly organised rather than rebuilding from scratch each time.
