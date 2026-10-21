# 🚀 9Router

**A local AI routing gateway + Next.js dashboard**

9Router exposes one OpenAI-compatible endpoint (`/v1/*`) and routes traffic across 40+ upstream providers with format translation, model-combo fallback, multi-account fallback, OAuth/API-key credential management, token refresh, quota/usage tracking, and optional federation (multi-instance replication).

## 📦 Install

```bash
npm install -g 9router
```

Or clone the repo and install locally:

```bash
git clone https://github.com/totalwindupflightsystems/9router.git
cd 9router
npm install
```

**Requirements**: Node.js **22** or later (see [Architecture](docs/ARCHITECTURE.md) for the full runtime matrix).

## 🏃 Quick Start

```bash
cd 9router
cp .env.example .env
# Configure your providers and API keys in .env
PORT=20128 npm run dev
```

Open [http://localhost:20128](http://localhost:20128) to access the dashboard.

### Self-hosting

When self-hosting, set `DATA_DIR` to control where 9Router stores its SQLite database and runtime files:

```bash
DATA_DIR=/path/to/data PORT=20128 npm run start
```

This applies to all persisted state: the SQLite database, usage logs, and session cookies.

## 🏗️ Federation Mode

9Router supports multi-instance federation for deployment across multiple datacenters or hosts:

- **Standalone**: Default mode, runs independently (no federation required)
- **Edge**: Proxies requests to a central instance, replicates its database
- **Central**: The authoritative instance that edges track and replicate from

See [Federation Spec](docs/federation-spec.md) for deployment topologies and configuration.

## 📊 Dashboard

The dashboard provides:
- **Provider Management**: Configure upstream provider connections
- **Model Catalog**: Browse 800+ supported models
- **Usage Tracking**: Monitor token usage across providers
- **Combo Routing**: Configure model combinations and fallbacks
- **Proxy Pools**: Set up proxy routing for provider nodes

## 🔌 API

All API endpoints follow the OpenAI-compatible format under `/v1/*`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | Chat completions |
| POST | `/v1/completions` | Legacy completions |
| POST | `/v1/embeddings` | Text embeddings |
| POST | `/v1/images/generations` | Image generation |
| GET | `/v1/models` | Model catalog |
| GET | `/v1/models/info` | Detailed model info |

See [API Reference](docs/api-reference.md) for the full endpoint list with request/response shapes.

## 🧪 Testing

```bash
npm install
cd tests && npm install && cd ..
npm test
```

The test suite is in `tests/` — an independent ESM package with its own dependency tree.

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md) — Full system architecture and request lifecycle
- [API Reference](docs/api-reference.md) — All `/v1/*` endpoints with examples
- [Federation Spec](docs/federation-spec.md) — Multi-instance deployment guide
- [Docker Setup](DOCKER.md) — Containerized deployment

## 🤖 Agent Skills

9Router ships a library of 13 agent skills for development, testing, and deployment automation. These are documented in [skills/README.md](skills/README.md).

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## 🤝 Contributing

We welcome contributions. Please see [AGENTS.md](AGENTS.md) for development conventions and the coding standards we follow.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
