// Minimal repro of the key-access /v1/models test against the MERGED tree.
import { describe, it, expect, vi } from "vitest";

const fx = vi.hoisted(() => ({
  combos: [{ id: "c1", name: "Main", models: ["openai/model-a", "openai/model-b"] }],
  keys: {},
}));

vi.mock("@/lib/localDb", () => ({
  getSettings: async () => ({ requireApiKey: false, comboStrategy: "fallback" }),
  getModelAliases: async () => ({}),
  getComboByName: async (name) => fx.combos.find((c) => c.name === name) || null,
  getProviderNodes: async () => [],
  getCombos: async () => fx.combos,
  getProviderConnections: async () => [],
  getProviderConnectionById: async () => null,
  getCustomModels: async () => [],
}));
vi.mock("@/lib/disabledModelsDb", () => ({ getDisabledModels: async () => ({}) }));
vi.mock("@/lib/db/repos/combosRepo.js", () => ({ getCombos: async () => fx.combos }));
vi.mock("@/lib/db/repos/apiKeysRepo.js", () => ({ getApiKeyByKey: async (k) => fx.keys[k] || null }));

const modelsRoute = await import("../../src/app/api/v1/models/route.js");

describe("repro", () => {
  it("lists static openai models with zero connections", async () => {
    const r = await modelsRoute.GET(new Request("http://localhost/v1/models"));
    const j = await r.json();
    const ids = (j.data || []).map((m) => m.id);
    console.log("total:", ids.length, "| openai/*:", ids.filter((i) => i.startsWith("openai/")).length, "| sample:", ids.slice(0, 8));
    expect(ids.length).toBeGreaterThan(0);
  });
});
