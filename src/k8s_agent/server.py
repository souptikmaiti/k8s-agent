"""A2A application and CLI entry point."""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from google.adk.a2a.utils.agent_to_a2a import to_a2a
import uvicorn

from k8s_agent.agent import build_agent
from k8s_agent.config import Settings


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
    return to_a2a(
        build_agent(settings),
        agent_card=build_card(settings),
        port=settings.port,
    )


app = build_app(Settings.from_env())


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run("k8s_agent.server:app", host="0.0.0.0", port=settings.port)
