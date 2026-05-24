"""
main.py
=======
Interactive launcher for the Python REST API learning examples.

Run:
    python3 main.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent


MODULES: dict[str, dict[str, Any]] = {
    "1": {
        "name": "FastAPI app + routers",
        "path": ROOT / "01-fastapi-app-routers" / "fastapi_example.py",
        "readme": ROOT / "01-fastapi-app-routers" / "README.md",
        "description": "App creation, routers, middleware, health checks, and CRUD routes.",
        "server": True,
        "port": 8000,
        "tests": [
            {"name": "healthz", "method": "GET", "path": "/healthz", "expect": 200},
            {"name": "readyz", "method": "GET", "path": "/readyz", "expect": 200},
            {"name": "list items", "method": "GET", "path": "/v1/items/", "expect": 200},
            {
                "name": "create item",
                "method": "POST",
                "path": "/v1/items/",
                "body": {"name": "Widget", "price": "9.99", "category": "hardware"},
                "expect": 201,
            },
            {"name": "missing item", "method": "GET", "path": "/v1/items/00000000-0000-0000-0000-000000000000", "expect": 404},
        ],
    },
    "2": {
        "name": "Pydantic schemas",
        "path": ROOT / "02-pydantic-schemas" / "pydantic_example.py",
        "readme": ROOT / "02-pydantic-schemas" / "README.md",
        "description": "Pydantic v2 validation, serialization, nested schemas, and error models.",
        "server": False,
        "tests": [],
    },
    "3": {
        "name": "Service methods / business logic",
        "path": ROOT / "03-service-methods" / "service_example.py",
        "readme": ROOT / "03-service-methods" / "README.md",
        "description": "Framework-independent business logic with repository protocols.",
        "server": True,
        "port": 8001,
        "tests": [
            {"name": "healthz", "method": "GET", "path": "/healthz", "expect": 200},
            {"name": "list tasks", "method": "GET", "path": "/v1/tasks/", "expect": 200},
            {
                "name": "create task",
                "method": "POST",
                "path": "/v1/tasks/",
                "body": {"title": "Demo task", "project_id": "00000000-0000-0000-0000-000000000099"},
                "expect": 201,
            },
            {"name": "route miss", "method": "GET", "path": "/v1/notaroute", "expect": 404},
        ],
    },
    "4": {
        "name": "Database models + repository methods",
        "path": ROOT / "04-database-models-repositories" / "database_example.py",
        "readme": ROOT / "04-database-models-repositories" / "README.md",
        "description": "SQLAlchemy model notes, repository methods, and migration guidance.",
        "server": True,
        "port": 8002,
        "tests": [
            {"name": "healthz", "method": "GET", "path": "/healthz", "expect": 200},
            {"name": "list tasks", "method": "GET", "path": "/v1/tasks/", "expect": 200},
            {
                "name": "create task",
                "method": "POST",
                "path": "/v1/tasks/",
                "body": {"title": "Repository demo", "project_id": "00000000-0000-0000-0000-000000000099"},
                "expect": 201,
            },
        ],
    },
    "5": {
        "name": "Dependency injection",
        "path": ROOT / "05-dependency-injection" / "dependency_injection_example.py",
        "readme": ROOT / "05-dependency-injection" / "README.md",
        "description": "Settings, repositories, services, and auth dependencies.",
        "server": True,
        "port": 8003,
        "tests": [
            {"name": "healthz", "method": "GET", "path": "/healthz", "expect": 200},
            {"name": "unauthorized notes", "method": "GET", "path": "/v1/notes/", "expect": 401},
            {
                "name": "create note",
                "method": "POST",
                "path": "/v1/notes/",
                "headers": {"X-API-Key": "dev-api-key"},
                "body": {"text": "DI smoke test"},
                "expect": 201,
            },
        ],
    },
    "6": {
        "name": "Error handling",
        "path": ROOT / "06-error-handling" / "error_handling_example.py",
        "readme": ROOT / "06-error-handling" / "README.md",
        "description": "Domain, HTTP, validation, route-miss, and unhandled error envelopes.",
        "server": True,
        "port": 8004,
        "tests": [
            {"name": "validation error", "method": "POST", "path": "/v1/widgets/", "body": {"name": ""}, "expect": 422},
            {"name": "create widget", "method": "POST", "path": "/v1/widgets/", "body": {"name": "alpha"}, "expect": 201},
            {"name": "route miss", "method": "GET", "path": "/v1/nope", "expect": 404},
        ],
    },
    "7": {
        "name": "Auth / permissions",
        "path": ROOT / "07-auth-permissions" / "auth_permissions_example.py",
        "readme": ROOT / "07-auth-permissions" / "README.md",
        "description": "Bearer-token auth and resource-level permission checks.",
        "server": True,
        "port": 8005,
        "tests": [
            {"name": "missing auth", "method": "GET", "path": "/v1/documents/", "expect": 401},
            {
                "name": "create document",
                "method": "POST",
                "path": "/v1/documents/",
                "headers": {"Authorization": "Bearer user-token"},
                "body": {"title": "Runbook", "body": "Operational notes"},
                "expect": 201,
            },
        ],
    },
    "8": {
        "name": "Tests",
        "path": ROOT / "08-tests" / "tests_example.py",
        "readme": ROOT / "08-tests" / "README.md",
        "description": "Service and API tests with TestClient and dependency overrides.",
        "server": False,
        "tests": [],
    },
    "9": {
        "name": "Observability + deployment",
        "path": ROOT / "09-observability-deployment" / "observability_deployment_example.py",
        "readme": ROOT / "09-observability-deployment" / "README.md",
        "description": "Structured logs, metrics, health/readiness, and deployment snippets.",
        "server": True,
        "port": 8006,
        "tests": [
            {"name": "healthz", "method": "GET", "path": "/healthz", "expect": 200},
            {"name": "ping", "method": "GET", "path": "/v1/ping", "headers": {"X-Request-ID": "main-smoke"}, "expect": 200},
            {"name": "metrics", "method": "GET", "path": "/metrics", "expect": 200},
        ],
    },
}


BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'-' * 72}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'-' * 72}{RESET}\n")


def ok(text: str) -> None:
    print(f"  {GREEN}OK{RESET}  {text}")


def fail(text: str) -> None:
    print(f"  {RED}FAIL{RESET}  {text}")


def info(text: str) -> None:
    print(f"  {DIM}{text}{RESET}")


def prompt(text: str) -> str:
    try:
        return input(f"\n{BOLD}{text}{RESET} ").strip()
    except EOFError:
        return "0"


def run_script(path: Path) -> int:
    return subprocess.call([sys.executable, str(path)], cwd=str(path.parent))


def start_server(module: dict[str, Any]) -> subprocess.Popen | None:
    path = module["path"]
    port = module["port"]
    app_import = f"{path.stem}:app"

    print(f"\n  Starting http://127.0.0.1:{port}")
    info(f"Swagger UI: http://127.0.0.1:{port}/docs")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            app_import,
            "--port",
            str(port),
            "--reload",
            "--no-server-header",
        ],
        cwd=str(path.parent),
    )
    time.sleep(2)
    if proc.poll() is not None:
        fail("Server failed to start. Check that uvicorn can import the module.")
        return None
    ok(f"Server running with PID {proc.pid}")
    return proc


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=10)
        ok("Server stopped.")
    else:
        info("No server is running.")


def request_json(method: str, url: str, body: dict | None, headers: dict[str, str] | None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    request_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def run_server_tests(module: dict[str, Any]) -> None:
    header(f"Smoke tests - {module['name']}")
    passed = 0
    failed = 0
    base_url = f"http://127.0.0.1:{module['port']}"

    for test in module["tests"]:
        status_code, response = request_json(
            test["method"],
            f"{base_url}{test['path']}",
            test.get("body"),
            test.get("headers"),
        )
        if status_code == test["expect"]:
            ok(f"{test['name']} -> {status_code}")
            passed += 1
        else:
            fail(f"{test['name']} -> expected {test['expect']}, got {status_code}")
            info(json.dumps(response)[:160])
            failed += 1

    print()
    if failed:
        fail(f"{passed} passed, {failed} failed")
    else:
        ok(f"All {passed} smoke tests passed")


def module_menu(key: str) -> None:
    module = MODULES[key]
    server_proc: subprocess.Popen | None = None

    while True:
        header(module["name"])
        print(f"  {module['description']}")
        info(f"Example: {module['path'].relative_to(ROOT)}")
        info(f"README:  {module['readme'].relative_to(ROOT)}")

        if module["server"]:
            print(f"\n  {BOLD}1{RESET}  Start server")
            print(f"  {BOLD}2{RESET}  Run server smoke tests")
            print(f"  {BOLD}3{RESET}  Run script self-tests")
            print(f"  {BOLD}4{RESET}  Stop server")
        else:
            print(f"\n  {BOLD}1{RESET}  Run script demos/self-tests")
        print(f"  {BOLD}0{RESET}  Back")

        if module["server"]:
            running = server_proc is not None and server_proc.poll() is None
            info(f"Server status: {'running' if running else 'stopped'}")

        choice = prompt("Choose an option:")

        if choice == "1":
            if module["server"]:
                if server_proc and server_proc.poll() is None:
                    info("Server is already running.")
                else:
                    server_proc = start_server(module)
            else:
                run_script(module["path"])
                prompt("Press Enter to continue:")
        elif choice == "2" and module["server"]:
            if not (server_proc and server_proc.poll() is None):
                info("Start the server first with option 1.")
            else:
                run_server_tests(module)
                prompt("Press Enter to continue:")
        elif choice == "3" and module["server"]:
            run_script(module["path"])
            prompt("Press Enter to continue:")
        elif choice == "4" and module["server"]:
            stop_server(server_proc)
            server_proc = None
        elif choice == "0":
            stop_server(server_proc)
            break
        else:
            info("Invalid option.")


def main() -> None:
    while True:
        header("Python REST API Learning Examples")
        for key, module in MODULES.items():
            print(f"  {BOLD}{key}{RESET}  {module['name']}")
            info(f"     {module['description']}")
        print(f"\n  {BOLD}0{RESET}  Exit")

        choice = prompt("Choose a module:")
        if choice == "0":
            print("\n  Goodbye.\n")
            return
        if choice in MODULES:
            module_menu(choice)
        else:
            info("Invalid option.")


if __name__ == "__main__":
    main()
