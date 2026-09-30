# Kubernetes agent

An independent Google ADK service that exposes Kubernetes inspection skills
through A2A. It connects over Streamable HTTP to a separately running
[Kubernetes MCP Server](https://github.com/containers/kubernetes-mcp-server).
The agent does not hold a kubeconfig or talk directly to the Kubernetes API;
the MCP server owns the cluster connection and permissions.

The A2A card advertises three skills: deployment inspection, pod inspection,
and service inspection. The ADK toolset exposes only the MCP server's named
read tools for resources, pods, logs, events, and namespaces. No pod exec,
create, update, delete, or scale tools are exposed to the agent.

## Kubernetes MCP server

This repository targets `containers/kubernetes-mcp-server`, whose HTTP mode
serves Streamable HTTP at `/mcp`. Configure and run that server separately.
The supplied [mcp-server.example.toml](mcp-server.example.toml) enables only
the tools this agent needs, sets `read_only = true`, and denies Secret objects.
For a local binary with a suitable kubeconfig and context:

```sh
kubernetes-mcp-server --config mcp-server.example.toml
```

The example listens on `127.0.0.1:8083`, so the agent's default MCP URL is
`http://127.0.0.1:8083/mcp`. Check the MCP endpoint and available tools with
MCP Inspector before testing the A2A agent. The server's
[configuration reference](https://github.com/containers/kubernetes-mcp-server/blob/main/docs/configuration.md)
documents HTTP mode, authentication, tool filtering, and denied resources.

Give the MCP server a dedicated Kubernetes identity with `get` and `list`
access only to the intended namespaces and resource types. Its
[Kubernetes setup guide](https://github.com/containers/kubernetes-mcp-server/blob/main/docs/getting-started-kubernetes.md)
shows a read-only ServiceAccount. The agent's tool allowlist and the server's
read-only mode are additional boundaries; Kubernetes RBAC is the final access
control. For an in-cluster MCP deployment, use that server's own chart and
ServiceAccount. The k8s-agent pod needs no Kubernetes API permissions.

## Run locally

Requires Python 3.11+, `uv`, a running Kubernetes MCP Server, and a Google API
key for the configured model. Copy `.env.example` to `.env` and set
`GOOGLE_API_KEY`. Set `K8S_MCP_URL` if your MCP server uses another address.
`K8S_MCP_TOKEN` is optional and is sent as a bearer token only when provided.
For an HTTPS endpoint signed by an internal CA, set `K8S_MCP_CA_FILE` to the
absolute path of its PEM CA certificate. The agent uses it for the MCP
connection while keeping certificate verification enabled.
Keep `.env` out of Git. Existing process environment variables take precedence.

```sh
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY.
uv sync --locked
uv run --locked k8s-agent
```

The service listens on port 8002. From another terminal, discover its A2A
skills and send a request:

```sh
a2a card get http://127.0.0.1:8002
a2a send -a http://127.0.0.1:8002 \
  "Inspect deployment api in namespace production. Report ready replicas and recent warning events."
```

The card endpoint is also available at
`http://127.0.0.1:8002/.well-known/agent-card.json`. It can be read without
model or cluster connectivity. A live request needs both the model key and a
reachable, authorized MCP server.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GOOGLE_API_KEY` | unset | Google model credential |
| `K8S_MCP_URL` | `http://127.0.0.1:8083/mcp` | Kubernetes MCP Streamable HTTP endpoint |
| `K8S_MCP_TOKEN` | unset | Optional MCP HTTP bearer token |
| `K8S_MCP_CA_FILE` | unset | Optional PEM CA certificate file for the MCP HTTPS connection |
| `K8S_AGENT_BASE_URL` | `http://localhost:8002` | A2A URL advertised in the agent card |
| `K8S_AGENT_MODEL` | `gemini-3.6-flash` | ADK model name |
| `K8S_AGENT_TEMPERATURE` | `1.0` | Model sampling temperature (0 to 1) |
| `PORT` | `8002` | A2A listening port |

Google recommends temperature 1.0 for Gemini 3 because lower values can
degrade reasoning. See the
[Gemini 3 guidance](https://ai.google.dev/gemini-api/docs/gemini-3#temperature).

## Container and Helm

The image and chart deploy **only** this A2A agent. Run Kubernetes MCP as a
separate service and point `K8S_MCP_URL` or `k8sMcpUrl` at its `/mcp` endpoint.
Inside a container, `127.0.0.1` refers to that container; use a reachable
service address instead.

```sh
docker build -t k8s-agent:0.1.0 .
```

The chart in `charts/k8s-agent` expects a Secret containing `GOOGLE_API_KEY`.
For an authenticated MCP HTTP endpoint, set `existingK8sMcpSecret` to a Secret
containing `K8S_MCP_TOKEN`. The chart advertises its in-cluster Service URL in
the A2A card.

```sh
helm upgrade --install k8s-agent charts/k8s-agent \
  --set image.repository=YOUR_REGISTRY/k8s-agent \
  --set image.tag=0.1.0 \
  --set k8sMcpUrl=http://kubernetes-mcp-server.YOUR_NAMESPACE.svc.cluster.local:8080/mcp \
  --set existingSecret=YOUR_MODEL_SECRET
```

Use TLS and authentication when the MCP endpoint is exposed beyond a trusted
local network. The initial single replica uses ADK's in-memory A2A task and
session storage; configure shared storage before scaling it.

## Limits

- The tool names target `containers/kubernetes-mcp-server`. Another Kubernetes
  MCP implementation may need a different allowlist.
- `resources_get` and `resources_list` are generic read tools; the MCP server
  and Kubernetes RBAC must deny resource types the agent should not see.
- Logs and cluster objects may contain sensitive data. The configured Gemini
  API receives excerpts selected for model context.
