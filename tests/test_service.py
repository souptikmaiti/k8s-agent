import asyncio
from pathlib import Path
import ssl
from unittest.mock import AsyncMock, patch

from a2a.server.tasks import DatabaseTaskStore
import certifi
from google.adk.sessions import DatabaseSessionService
from starlette.testclient import TestClient

from k8s_agent import config
from k8s_agent.agent import build_agent
from k8s_agent.config import Settings
from k8s_agent.server import build_app


def test_a2a_runner_uses_postgresql_session_service():
    with patch("k8s_agent.server.to_a2a") as to_a2a:
        build_app(Settings())

    task_store = to_a2a.call_args.kwargs["task_store"]
    runner = to_a2a.call_args.kwargs["runner"]
    assert isinstance(runner.session_service, DatabaseSessionService)
    assert runner.session_service.db_engine is task_store.engine

    async def close():
        await runner.close()
        await task_store.engine.dispose()

    asyncio.run(close())


def test_card_advertises_deployment_pod_and_service_skills():
    settings = Settings()

    with (
        patch.object(DatabaseTaskStore, "initialize", new_callable=AsyncMock),
        patch.object(DatabaseSessionService, "prepare_tables", new_callable=AsyncMock),
        TestClient(build_app(settings)) as client,
    ):
        response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert [skill["id"] for skill in card["skills"]] == [
        "k8s_deployment_inspection",
        "k8s_pod_inspection",
        "k8s_service_inspection",
    ]
    assert card["supportedInterfaces"][0]["url"] == settings.public_base_url
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"


def test_agent_uses_http_mcp_with_only_inspection_tools():
    settings = Settings(k8s_mcp_token="test-token")
    agent = build_agent(settings)

    assert len(agent.tools) == 1
    toolset = agent.tools[0]
    assert toolset._connection_params.url == "http://127.0.0.1:8083/mcp"
    assert toolset._connection_params.headers == {
        "Authorization": "Bearer test-token"
    }
    assert {"resources_get", "pods_get", "events_list"} <= set(toolset.tool_filter)
    assert not {"pods_exec", "pods_delete", "resources_delete"} & set(
        toolset.tool_filter
    )
    assert agent.generate_content_config.temperature == 1.0
    assert "test-token" not in repr(settings)


def test_https_mcp_client_trusts_configured_ca():
    settings = Settings(
        k8s_mcp_url="https://mcp.example.test/mcp",
        k8s_mcp_ca_file=certifi.where(),
    )
    settings.validate()
    toolset = build_agent(settings).tools[0]

    with patch("k8s_agent.agent.httpx.AsyncClient") as client:
        toolset._connection_params.httpx_client_factory(timeout=None)

    context = client.call_args.kwargs["verify"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.get_ca_certs()


def test_settings_load_local_env(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(
        "K8S_MCP_URL=http://kubernetes-mcp-server:8080/mcp\n"
        "K8S_MCP_TOKEN=test-token\n"
        "K8S_AGENT_MODEL=gemini-3.6-flash\n"
        "K8S_AGENT_TEMPERATURE=0.5\n"
    )
    monkeypatch.chdir(tmp_path)
    for name in (
        "K8S_MCP_URL",
        "K8S_MCP_TOKEN",
        "K8S_AGENT_MODEL",
        "K8S_AGENT_TEMPERATURE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.k8s_mcp_url == "http://kubernetes-mcp-server:8080/mcp"
    assert settings.k8s_mcp_token == "test-token"
    assert settings.model == "gemini-3.6-flash"
    assert settings.temperature == 0.5


def test_settings_load_project_env_when_launched_from_parent(tmp_path: Path, monkeypatch):
    project = tmp_path / "k8s-agent"
    (project / "src" / "k8s_agent").mkdir(parents=True)
    (project / ".env").write_text("K8S_MCP_URL=http://localhost:9999/mcp\n")
    monkeypatch.setattr(config, "__file__", str(project / "src" / "k8s_agent" / "config.py"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("K8S_MCP_URL", raising=False)

    assert config.Settings.from_env().k8s_mcp_url == "http://localhost:9999/mcp"


def test_mcp_url_must_be_http():
    try:
        Settings(k8s_mcp_url="stdio://mcp").validate()
    except ValueError as error:
        assert "K8S_MCP_URL" in str(error)
    else:
        raise AssertionError("non-HTTP MCP URL should fail")
