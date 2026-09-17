export default {
  id: "opencode",
  priority: 40,
  hasFree: true,
  alias: "oc",
  uiAlias: "oc",
  display: {
    name: "OpenCode Free",
    icon: "terminal",
    color: "#E87040",
    textIcon: "OC",
  },
  category: "free",
  noAuth: true,
  // LIVE PROBE (2026-09-17): the credentialless path only works from OpenCode's
  // own client. GET /zen/v1/models answers 200 (so the provider LOOKS healthy),
  // but POST /zen/v1/responses answers 403 FreeTierError "OpenCode's free tier
  // can only be used from within OpenCode" even when the request carries
  // OpenCodeExecutor's own header set, and /zen/v1/chat/completions answers
  // 401 "Missing API key.". A working model list therefore does NOT make the
  // provider usable from this process.
  requiresVendorClient: true,
  transport: {
    baseUrl: "https://opencode.ai",
    headers: {
      "x-opencode-client": "desktop",
    },
    noAuth: true,
  },
  models: [
    // Muse Spark models are served by /zen/v1/responses; the rest stay on
    // /chat/completions, so the format is declared per-model, not per-provider.
    { id: "muse-spark-1.2-contributor-free", name: "Muse Spark 1.2 Contributor Free", targetFormat: "openai-responses" },
    { id: "muse-spark-1.3-contributor-free", name: "Muse Spark 1.3 Contributor Free", targetFormat: "openai-responses" },
  ],
  modelsFetcher: { url: "https://opencode.ai/zen/v1/models", type: "opencode-free" },
  passthroughModels: true,
};
