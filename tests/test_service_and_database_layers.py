from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import load_example


service_example = load_example("service_methods_example", "03-service-methods/service_example.py")
database_example = load_example("database_models_example", "04-database-models-repositories/database_example.py")


def run(coro):
    return asyncio.run(coro)


def test_task_service_enforces_permissions_and_state_transitions() -> None:
    async def scenario() -> None:
        repo = service_example.InMemoryTaskRepository()
        service = service_example.TaskService(repo)
        owner = uuid4()
        assignee = uuid4()
        outsider = uuid4()
        project_id = uuid4()

        task = await service.create_task(
            service_example.TaskCreate(title="Write tests", project_id=project_id),
            current_user_id=owner,
        )

        with pytest.raises(service_example.PermissionDeniedError):
            await service.get_task(task.id, current_user_id=outsider)

        assigned = await service.assign_task(task.id, assignee, current_user_id=owner)
        assert assigned.assignee_id == assignee
        assert (await service.get_task(task.id, current_user_id=assignee)).id == task.id

        started = await service.start_task(task.id, current_user_id=owner)
        assert started.status == service_example.TaskStatus.IN_PROGRESS

        with pytest.raises(service_example.InvalidTaskTransitionError):
            await service.start_task(task.id, current_user_id=owner)

        completed = await service.complete_task(task.id, current_user_id=owner)
        assert completed.status == service_example.TaskStatus.DONE

        with pytest.raises(service_example.TaskAlreadyCompletedError):
            await service.complete_task(task.id, current_user_id=owner)

        archived = await service.archive_task(task.id, current_user_id=owner)
        assert archived.status == service_example.TaskStatus.ARCHIVED

        with pytest.raises(service_example.TaskArchivedError):
            await service.update_task(
                task.id,
                service_example.TaskUpdate(title="Nope"),
                current_user_id=owner,
            )

    run(scenario())


def test_task_service_api_maps_domain_errors_to_http_responses() -> None:
    service_example._task_repository = service_example.InMemoryTaskRepository()
    client = TestClient(service_example.app)

    created = client.post(
        "/v1/tasks/",
        json={"title": "API task", "project_id": str(uuid4())},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    assert client.post(f"/v1/tasks/{task_id}/start").json()["status"] == "in_progress"
    conflict = client.post(f"/v1/tasks/{task_id}/start")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"

    missing = client.get(f"/v1/tasks/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["message"] == "Task not found"


def test_database_repository_crud_filters_pagination_and_delete() -> None:
    async def scenario() -> None:
        repo = database_example.InMemoryTaskRepository()
        owner = uuid4()
        project_id = uuid4()
        other_project_id = uuid4()
        assignee = uuid4()

        first = await repo.create(
            database_example.TaskCreate(title="First", project_id=project_id, assignee_id=assignee),
            created_by=owner,
        )
        second = await repo.create(
            database_example.TaskCreate(title="Second", project_id=project_id),
            created_by=owner,
        )
        await repo.create(
            database_example.TaskCreate(title="Third", project_id=other_project_id),
            created_by=owner,
        )

        updated = await repo.update(first.id, database_example.TaskUpdate(title="Updated"))
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.assignee_id == assignee

        await repo.set_status(second.id, database_example.TaskStatus.DONE)
        project_tasks = await repo.list(database_example.TaskListFilters(project_id=project_id))
        done_tasks = await repo.list(database_example.TaskListFilters(status=database_example.TaskStatus.DONE))
        page = await repo.list(database_example.TaskListFilters(limit=1, offset=1))

        assert {task.id for task in project_tasks} == {first.id, second.id}
        assert [task.id for task in done_tasks] == [second.id]
        assert len(page) == 1
        assert await repo.delete(first.id) is True
        assert await repo.get_by_id(first.id) is None
        assert await repo.delete(uuid4()) is False

    run(scenario())


def test_database_api_crud_and_error_envelopes() -> None:
    database_example._repository = database_example.InMemoryTaskRepository()
    client = TestClient(database_example.app)

    created = client.post(
        "/v1/tasks/",
        json={"title": "Repository API", "project_id": str(uuid4())},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    listed = client.get("/v1/tasks/")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = client.patch(f"/v1/tasks/{task_id}", json={"description": "Updated"})
    assert patched.status_code == 200
    assert patched.json()["description"] == "Updated"

    assert client.delete(f"/v1/tasks/{task_id}").status_code == 204
    missing = client.get(f"/v1/tasks/{task_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
