"""
tests_example.py
================
Reference implementation for API and service tests.

Run:
    python3 tests_example.py

This file uses simple assert-based tests so it runs without pytest. The same
test functions can be moved into tests/test_tasks.py and run with pytest.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class TaskRead(BaseModel):
    id: UUID
    title: str
    completed: bool = False


@dataclass
class TaskService:
    tasks: dict[UUID, TaskRead]

    async def create(self, payload: TaskCreate) -> TaskRead:
        task = TaskRead(id=uuid4(), title=payload.title)
        self.tasks[task.id] = task
        return task

    async def get(self, task_id: UUID) -> TaskRead:
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    async def complete(self, task_id: UUID) -> TaskRead:
        task = await self.get(task_id)
        completed = task.model_copy(update={"completed": True})
        self.tasks[task_id] = completed
        return completed


_service = TaskService(tasks={})


async def get_task_service() -> TaskService:
    return _service


app = FastAPI(title="Testing Example API", version="1.0.0")


@app.post("/v1/tasks/", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, service: TaskService = Depends(get_task_service)) -> TaskRead:
    return await service.create(payload)


@app.get("/v1/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, service: TaskService = Depends(get_task_service)) -> TaskRead:
    try:
        return await service.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/v1/tasks/{task_id}/complete", response_model=TaskRead)
async def complete_task(task_id: UUID, service: TaskService = Depends(get_task_service)) -> TaskRead:
    try:
        return await service.complete(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_service_create_and_complete() -> None:
    import asyncio

    service = TaskService(tasks={})
    task = asyncio.run(service.create(TaskCreate(title="Write unit test")))
    assert task.completed is False

    completed = asyncio.run(service.complete(task.id))
    assert completed.completed is True
    assert completed.title == "Write unit test"


def test_api_create_get_complete() -> None:
    isolated_service = TaskService(tasks={})

    async def override_service() -> TaskService:
        return isolated_service

    app.dependency_overrides[get_task_service] = override_service
    try:
        client = TestClient(app)

        created = client.post("/v1/tasks/", json={"title": "Write API test"})
        assert created.status_code == 201
        task_id = created.json()["id"]

        fetched = client.get(f"/v1/tasks/{task_id}")
        assert fetched.status_code == 200
        assert fetched.json()["title"] == "Write API test"

        completed = client.post(f"/v1/tasks/{task_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["completed"] is True
    finally:
        app.dependency_overrides.clear()


def test_api_validation_and_not_found() -> None:
    client = TestClient(app)

    invalid = client.post("/v1/tasks/", json={"title": ""})
    assert invalid.status_code == 422

    missing = client.get(f"/v1/tasks/{uuid4()}")
    assert missing.status_code == 404


def _run_tests() -> None:
    tests = [
        test_service_create_and_complete,
        test_api_create_get_complete,
        test_api_validation_and_not_found,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("All testing example tests passed.")


if __name__ == "__main__":
    _run_tests()
