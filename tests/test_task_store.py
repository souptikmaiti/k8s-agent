import asyncio
import os
from uuid import uuid4

from a2a.server.context import ServerCallContext
from a2a.types import Artifact, Part, Task, TaskState, TaskStatus
from google.adk.sessions import DatabaseSessionService
import pytest
from starlette.testclient import TestClient

from k8s_agent.config import Settings
from k8s_agent.server import build_app
from k8s_agent.task_store import create_task_store


def test_task_store_uses_postgresql_without_connecting():
    database_url = "postgresql+asyncpg://postgres:secret@127.0.0.1:5432/k8s_agent_tasks"
    settings = Settings(a2a_task_database_url=database_url)
    settings.validate()

    task_store, _ = create_task_store(settings.a2a_task_database_url)

    assert task_store.engine.url.drivername == "postgresql+asyncpg"
    assert task_store.engine.url.database == "k8s_agent_tasks"
    assert "secret" not in repr(settings)
    asyncio.run(task_store.engine.dispose())


def test_task_store_rejects_other_database_drivers():
    with pytest.raises(ValueError, match=r"postgresql\+asyncpg"):
        Settings(a2a_task_database_url="mysql+asyncmy://user@host/tasks").validate()

    with pytest.raises(ValueError, match=r"postgresql\+asyncpg"):
        create_task_store("mysql+asyncmy://user@host/tasks")


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires an explicitly enabled PostgreSQL integration test",
)
def test_task_survives_store_recreation():
    database_url = Settings.from_env().a2a_task_database_url
    context = ServerCallContext()
    task = Task(
        id=str(uuid4()),
        context_id=str(uuid4()),
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[Artifact(artifact_id="answer", parts=[Part(text="Deployment ready")])],
    )

    async def check():
        first_store, first_lifespan = create_task_store(database_url)
        async with first_lifespan(None):
            await first_store.save(task, context)

        second_store, second_lifespan = create_task_store(database_url)
        async with second_lifespan(None):
            try:
                return await second_store.get(task.id, context)
            finally:
                await second_store.delete(task.id, context)

    restored = asyncio.run(check())
    assert restored is not None
    assert restored.status.state == TaskState.TASK_STATE_COMPLETED
    assert restored.artifacts[0].parts[0].text == "Deployment ready"


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires an explicitly enabled PostgreSQL integration test",
)
def test_adk_session_survives_store_recreation():
    database_url = Settings.from_env().a2a_task_database_url
    session_id = str(uuid4())
    user_id = f"test-{uuid4()}"

    async def check():
        first_store, first_lifespan = create_task_store(database_url)
        first_sessions = DatabaseSessionService(db_engine=first_store.engine)
        async with first_lifespan(None):
            await first_sessions.prepare_tables()
            await first_sessions.create_session(
                app_name="k8s_agent",
                user_id=user_id,
                session_id=session_id,
                state={"namespace": "apiusage"},
            )

        second_store, second_lifespan = create_task_store(database_url)
        second_sessions = DatabaseSessionService(db_engine=second_store.engine)
        async with second_lifespan(None):
            try:
                return await second_sessions.get_session(
                    app_name="k8s_agent", user_id=user_id, session_id=session_id
                )
            finally:
                await second_sessions.delete_session("k8s_agent", user_id, session_id)

    restored = asyncio.run(check())
    assert restored is not None
    assert restored.state["namespace"] == "apiusage"


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires an explicitly enabled PostgreSQL integration test",
)
def test_a2a_app_starts_with_postgresql():
    with TestClient(build_app(Settings.from_env())) as client:
        response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
