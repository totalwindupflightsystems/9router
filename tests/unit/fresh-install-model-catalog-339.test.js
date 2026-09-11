import { beforeEach, describe, expect, it, vi } from "vitest";
import { AI_PROVIDERS } from "@/shared/constants/providers";

// DF-9ROUTER-2 / df2-model-catalog-t339 — a fresh install (successful provider
// lookup, zero active connections) must not advertise static models whose
// provider still needs credentials: the chat handler answers those with
// 404 "No active credentials for provider", so listing them is a lie. A
// FAILED lookup (DB unavailable) keeps the legacy all-static fail-open list.

const mocks = vi.hoisted(() => ({
  getProviderConnections: vi.fn(),
  getCombos: vi.fn(),
  getCustomModels: vi.fn(),
  getModelAliases: vi.fn(),
  getDisabledModels: vi.fn(),
}));

vi.mock("@/lib/localDb", () => ({
  getProviderConnections: mocks.getProviderConnections,
  getCombos: mocks.getCombos,
  getCustomModels: mocks.getCustomModels,
  getModelAliases: mocks.getModelAliases,
}));

vi.mock("@/lib/disabledModelsDb", () => ({
  getDisabledModels: mocks.getDisabledModels,
}));

const { buildModelsList, GET } = await import("../../src/app/api/v1/models/route.js");
const { GET: GET_MODEL } = await import("../../src/app/api/v1/models/[...model]/route.js");

// Derived from the registry so the expectations track `noAuth: true` entries
// instead of a hand-maintained list.
const NO_AUTH_ALIASES = new Set(
  Object.values(AI_PROVIDERS)
    .filter((p) => p.noAuth === true)
    .map((p) => p.alias || p.id),
);

const NO_AUTH_LLM_MODEL = "oc/muse-spark-1.2-contributor-free";
const NO_AUTH_TTS_MODEL = "edge-tts/en-US-AriaNeural";
const CREDENTIALED_LLM_MODELS = [
  "cc/claude-sonnet-5",
  "anthropic/claude-sonnet-4-20250514",
  "deepseek/deepseek-v4-flash",
];

const ids = (models) => models.map((m) => m.id);
const nonNoAuthIds = (list) => list.filter((id) => !NO_AUTH_ALIASES.has(id.split("/")[0]));

const params = (model) => ({ params: Promise.resolve({ model }) });

async function llmIds() {
  return ids(await buildModelsList(["llm"]));
}

describe("fresh-install model catalog (DF-9ROUTER-2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getProviderConnections.mockResolvedValue([]);
    mocks.getCombos.mockResolvedValue([]);
    mocks.getCustomModels.mockResolvedValue([]);
    mocks.getModelAliases.mockResolvedValue({});
    mocks.getDisabledModels.mockResolvedValue({});
  });

  it("advertises only credentialless noAuth providers when the lookup succeeds with zero connections", async () => {
    const list = await llmIds();

    expect(list).toContain(NO_AUTH_LLM_MODEL);
    for (const credentialed of CREDENTIALED_LLM_MODELS) {
      expect(list).not.toContain(credentialed);
    }
    // Nothing outside the registry-declared noAuth set may leak through.
    expect(nonNoAuthIds(list)).toEqual([]);
  });

  it("keeps genuinely credentialless TTS providers in zero-connection capability listings", async () => {
    const list = ids(await buildModelsList(["tts"]));

    expect(list).toContain(NO_AUTH_TTS_MODEL);
    expect(nonNoAuthIds(list)).toEqual([]);
  });

  it("honours disabled-model filtering inside the filtered fresh catalog", async () => {
    mocks.getDisabledModels.mockResolvedValue({ oc: ["muse-spark-1.2-contributor-free"] });

    const list = await llmIds();

    expect(list).not.toContain(NO_AUTH_LLM_MODEL);
    expect(list).toContain("oc/muse-spark-1.3-contributor-free");
  });

  it("does not advertise custom models whose provider still needs credentials", async () => {
    mocks.getCustomModels.mockResolvedValue([
      { id: "cc-custom-1", providerAlias: "cc" },
      { id: "oc-custom-1", providerAlias: "oc" },
    ]);

    const list = await llmIds();

    expect(list).not.toContain("cc/cc-custom-1");
    expect(list).toContain("oc/oc-custom-1");
  });

  it("treats a stored but inactive connection as zero active connections", async () => {
    mocks.getProviderConnections.mockResolvedValue([
      { id: "conn-1", provider: "anthropic", isActive: false },
    ]);

    const list = await llmIds();

    expect(list).toContain(NO_AUTH_LLM_MODEL);
    expect(list).not.toContain("anthropic/claude-sonnet-4-20250514");
  });

  it("keeps the all-static fail-open catalog when the provider lookup throws", async () => {
    mocks.getProviderConnections.mockRejectedValue(new Error("db unavailable"));

    const list = await llmIds();

    expect(list).toContain(NO_AUTH_LLM_MODEL);
    for (const credentialed of CREDENTIALED_LLM_MODELS) {
      expect(list).toContain(credentialed);
    }
    expect(list.length).toBeGreaterThan(100);
  });

  it("leaves the non-empty active-connection path unchanged", async () => {
    mocks.getProviderConnections.mockResolvedValue([
      { id: "conn-1", provider: "anthropic", isActive: true },
    ]);

    const list = await llmIds();

    expect(list).toContain("anthropic/claude-sonnet-4-20250514");
    expect(list).not.toContain(NO_AUTH_LLM_MODEL);
    expect(list).not.toContain("deepseek/deepseek-v4-flash");
  });

  it("GET /v1/models hides credential-required static models on a fresh install", async () => {
    const response = await GET(new Request("https://router.test/v1/models"));
    const body = await response.json();
    const list = ids(body.data);

    expect(response.status).toBe(200);
    expect(list).toContain(NO_AUTH_LLM_MODEL);
    expect(list).not.toContain("cc/claude-sonnet-5");
  });

  it("cannot retrieve an unconfigured credential-required model through the exact-model endpoint", async () => {
    const found = await GET_MODEL(
      new Request("https://router.test/v1/models/oc/muse-spark-1.2-contributor-free"),
      params(["oc", "muse-spark-1.2-contributor-free"]),
    );
    expect(found.status).toBe(200);
    expect((await found.json()).id).toBe(NO_AUTH_LLM_MODEL);

    const missing = await GET_MODEL(
      new Request("https://router.test/v1/models/cc/claude-sonnet-5"),
      params(["cc", "claude-sonnet-5"]),
    );
    expect(missing.status).toBe(404);
    expect((await missing.json()).error.code).toBe("model_not_found");
  });
});
