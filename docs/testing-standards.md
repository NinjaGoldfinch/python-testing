# Testing Standards

This repo uses tests as executable documentation. A good test should explain the contract of an example as clearly as the README explains the concept.

## Test Layers

- Unit tests cover framework-independent logic: services, repositories, validators, permission helpers, and formatter functions.
- API tests cover FastAPI routes through `TestClient`: status codes, response bodies, validation failures, error envelopes, and dependency overrides.
- Launcher tests cover the interactive helper functions without starting real servers.
- Smoke tests may still live in example scripts, but every durable behavior should also have a pytest test under `tests/`.

## Naming And Layout

- Put tests in top-level `tests/`.
- Name files `test_<topic>.py`.
- Name tests `test_<behavior>_<expected_result>()`.
- Prefer one meaningful behavior per test. A single end-to-end CRUD flow is fine when the behavior is the flow itself.
- Use helper functions only when they remove repetition without hiding important setup.

## Isolation

- Reset module-level in-memory stores before tests that use them.
- Use FastAPI `dependency_overrides` for alternate settings, repositories, and services.
- Clear `app.dependency_overrides` in a `finally` block.
- Do not rely on test order. Each test must be able to run alone.
- Do not start real uvicorn servers in pytest unless the test specifically owns process startup and shutdown.

## Assertions

- Assert public contracts: status code, response shape, domain exception, persisted state, and important headers.
- Avoid asserting incidental values such as generated UUIDs, exact timestamps, log ordering, or object reprs unless those are the contract.
- For errors, assert the stable machine-readable code and the important message fragment.
- For validation, assert that invalid input fails and that the response includes field-level details where the API promises them.

## Async Code

- Keep pytest tests synchronous when possible by wrapping direct service or repository calls with `asyncio.run()`.
- Use `TestClient` for FastAPI route tests unless the behavior specifically requires async HTTP clients.
- Avoid sharing event loops or async state between tests.

## Fixtures And Data

- Prefer local test data built inside the test over broad global fixtures.
- Use fixed UUIDs only when identity matters for the assertion.
- Use random UUIDs when uniqueness is the only requirement.
- Keep payloads minimal, but valid enough to exercise the behavior being tested.

## Documentation Examples

- If a README shows a recommended pattern, add or update a test that proves the pattern works.
- If an example script contains `_run_tests()`, mirror the important checks in pytest so CI can report failures normally.
- When fixing a bug, write the regression test first or in the same change.

## Running Tests

```bash
python3 -m pip install -e .[dev]
make test
```

Use `make verify` for the script self-tests and `make check` for syntax checks. Use `make ci` before larger changes.
