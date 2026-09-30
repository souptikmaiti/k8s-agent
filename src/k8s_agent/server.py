"""A2A application and CLI entry point."""

from contextlib import asynccontextmanager

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.artifacts import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import InMemoryCredentialService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
import uvicorn

from k8s_agent.agent import build_agent
from k8s_agent.config import Settings
from k8s_agent.task_store import create_task_store


def build_card(settings: Settings) -> AgentCard:
    return AgentCard(
        name="k8s_agent",
        description="Read-only Kubernetes inspection service backed by MCP.",
        supported_interfaces=[
            AgentInterface(
                url=settings.public_base_url.rstrip("/"),
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="k8s_deployment_inspection",
                name="Kubernetes deployment inspection",
                description="Inspect deployment configuration, rollout status, replicas, and related events.",
                tags=["kubernetes", "deployment", "rollout"],
                examples=["Is deployment api healthy in namespace production?"],
            ),
            AgentSkill(
                id="k8s_pod_inspection",
                name="Kubernetes pod inspection",
                description="Inspect pod status, container health, recent logs, and events.",
                tags=["kubernetes", "pod", "diagnostics"],
                examples=["Why is pod api-123 restarting in namespace production?"],
            ),
            AgentSkill(
                id="k8s_service_inspection",
                name="Kubernetes service inspection",
                description="Inspect service type, selectors, ports, and related workload state.",
                tags=["kubernetes", "service", "networking"],
                examples=["Which port does service api expose in namespace production?"],
            ),
        ],
    )


def build_app(settings: Settings):
    settings.validate()
    agent = build_agent(settings)
    task_store, task_lifespan = create_task_store(settings.a2a_task_database_url)
    session_service = DatabaseSessionService(db_engine=task_store.engine)
    runner = Runner(
        app_name=agent.name,
        agent=agent,
        session_service=session_service,
        artifact_service=InMemoryArtifactService(),
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with task_lifespan(app):
            try:
                await session_service.prepare_tables()
                yield
            finally:
                await runner.close()

    return to_a2a(
        agent,
        agent_card=build_card(settings),
        port=settings.port,
        task_store=task_store,
        runner=runner,
        lifespan=lifespan,
    )


app = build_app(Settings.from_env())


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run("k8s_agent.server:app", host="0.0.0.0", port=settings.port)
