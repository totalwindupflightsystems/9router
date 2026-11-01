#!/usr/bin/env node
// HYG-9ROUTER-20: prove the one-path GitReins sensitive-path exception is
// limited to the tracked placeholder template. This creates disposable Git
// repositories; it never changes this checkout's index or any real credential.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const gitreins = process.env.GITREINS_BIN || "gitreins";

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    env: { ...process.env, NO_COLOR: "1" },
  });
  if (result.error) throw result.error;
  return {
    status: result.status ?? 1,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    output: `${result.stdout || ""}${result.stderr || ""}`,
  };
}

function secretsSummary(result) {
  const evidence = JSON.parse(result.stdout);
  const secrets = evidence.checks.find((check) => check.id === "secrets");
  assert.ok(secrets, `guard evidence had no secrets check:\n${result.output}`);
  return secrets.summary;
}

function createFixture(name, sensitivePath) {
  const root = mkdtempSync(join(tmpdir(), `9router-gitreins-${name}-`));
  mkdirSync(join(root, ".gitreins"));
  writeFileSync(
    join(root, ".gitreins", "config.yaml"),
    [
      "guards:",
      "  secrets: true",
      "  lint: false",
      "  tests: false",
      "  sensitive_paths:",
      "    allow:",
      '      - ".env.example"',
      "",
    ].join("\n"),
  );
  writeFileSync(join(root, sensitivePath), "SAFE_TEMPLATE_VALUE=placeholder\n");

  for (const [command, args] of [
    ["git", ["init", "-q"]],
    ["git", ["config", "user.name", "policy fixture"]],
    ["git", ["config", "user.email", "policy-fixture@example.invalid"]],
    ["git", ["add", ".gitreins/config.yaml"]],
    ["git", ["commit", "-qm", "fixture config"]],
    // The host's global excludes can ignore .env* in a disposable repository;
    // force-add only this harmless fixture so the guard grades the intended path.
    ["git", ["add", "-f", sensitivePath]],
  ]) {
    const result = run(command, args, root);
    assert.equal(result.status, 0, `${command} ${args.join(" ")} failed:\n${result.output}`);
  }
  const staged = run("git", ["diff", "--cached", "--name-only"], root);
  assert.match(
    staged.output,
    new RegExp(`^${sensitivePath.replace(".", "\\.")}$`, "m"),
    `fixture did not stage ${sensitivePath}:\n${staged.output}`,
  );
  return root;
}

function verifyAllowedTemplate() {
  const root = createFixture("allowed", ".env.example");
  try {
    const result = run(gitreins, ["guard", "--staged-only", "--json"], root);
    assert.equal(result.status, 0, `allowed template was rejected:\n${result.output}`);
    assert.match(
      secretsSummary(result),
      /sensitive-path override applied: \.env\.example/,
      `allowed template had no auditable override witness:\n${result.output}`,
    );
    return "PASS: .env.example accepted with auditable sensitive-path override";
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function verifyUnrelatedSensitivePathStillFails() {
  const root = createFixture("rejected", ".env");
  try {
    const result = run(gitreins, ["guard", "--staged-only", "--json"], root);
    assert.notEqual(result.status, 0, `unrelated .env was unexpectedly accepted:\n${result.output}`);
    assert.match(
      secretsSummary(result),
      /\.env: SENSITIVE PATH \(credential-store path class\)/,
      `unrelated .env did not fail through the sensitive-path gate:\n${result.output}`,
    );
    return "PASS: unrelated .env remains blocked by sensitive-path gate";
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

console.log(verifyAllowedTemplate());
console.log(verifyUnrelatedSensitivePathStillFails());
console.log("GitReins sensitive-path policy probe passed.");
