# Dogfooding self-update / signed-distribution flows

When the target's flagship promise is "the binary fetches a signed manifest from a
well-known URL and updates itself", the crypto internals are usually tested and the
END-TO-END reachability is not. Probe in this order; each step has killed a flagship
claim in the wild. Companion: `references/probe-attribution.md` for attributing a
boot/probe failure to the product vs a host-global store.

## 1. Curl the hard-coded default endpoint BEFORE building anything

The spec's release URL is a claim, not a service: `curl -s -D- <default-url>` first.
A parked/registrar-forwarded domain answers `302 -> <registrar>/forsale` while the
client surfaces it as a bare `HTTP 403 Forbidden` every check interval — the flagship
flow is dead on every shipped artifact while its unit tests stay green. Quote both
the redirect target and the client's own error line in the finding.

## 2. Check the consumer wiring, not just the URL

The daemon may construct the updater WITHOUT the override fields the library exposes:
no `ManifestURL` flag/env, no embedded public key. `grep -rn 'go:embed'` verifies the
spec's promised key embed (usually absent); `grep -n 'Updater{' cmd/` shows which
fields are actually set. When no override exists, no URL fix short of a release can
rescue the flow — that is its own row (fix direction: override flag + embedded key
per the spec, then a release), distinct from the dead-URL row.

## 3. Version-stamp the HEAD build before driving version-comparison code

Updater/gate code parses semver and refuses the bare `dev` stamp, so every check
dies on your build, not the logic:

    go build -ldflags "-X main.version=0.1.0 -X main.commit=<stamp>" -o /tmp/bin ./cmd/<bin>

Only a stamped binary exercises the compare/select arms.

## 4. Drive the full ladder as a real consumer against a scratch static server

Serve the manifest with `python3 -m http.server <port>` in a BACKGROUND terminal
session (foreground `&` is refused on unattended surfaces), then drive:

1. check → download → apply → verify the swapped binary is BYTE-IDENTICAL to the
   served artifact (read both files and compare, never trust the apply return path alone)
2. fail-closed arms, each re-signed with the SAME key via the package's own signer:
   tampered sha256 → typed invalid-signature; wrong key → same; no-downgrade
   (same-version manifest, live-served) → `available=false` with no error
3. the live server's own opt-in flag (`--update-interval`) against the scratch
   manifest host, capturing the per-interval log line

A signer that accepts PKCS#8/base64/hex key material (read the key parser) makes
re-signing mutated manifests trivial. Report each arm's verbatim refusal.

## 5. Grade the two-sided verdict honestly

All-green crypto on a dead default URL is TWO findings, not one: the flow WORKS when
a URL and key are supplied (that is a real, citable PASS with numbers), and the flow
is UNREACHABLE as shipped (that is the P1). Filing only the P1 erases the evidence
the foreman needs to know the internals are sound; filing only the green ladder
hides that no user can ever reach it.

## 6. release-tool / packager friction is its own row class

- Tooling that silently SKIPS files not matching a platform-filename switch (a
  `notes.txt` vanishes without warning) and then errors `no release artifacts found`
  has an undocumented filename contract — read the `platformForFilename` source,
  list the accepted names in the row, and file 'contract undocumented + silent skip'.
- Check the RELEASED artifact, not only HEAD: a released binary built before the
  feature landed rejects the new flags outright (`flag provided but not defined`) —
  docs-ahead-of-release, fix direction a release cut, never a doc rewrite. Compare
  `gh api repos/<org>/<repo>/releases/latest -q '.assets[].name'` against what the
  release workflow uploads.
- A manifest published as a per-version release ASSET cannot serve as a stable
  update URL (the path pins the version) — the workflow needs a fixed well-known
  location (gh-pages or a repo raw path) for the updater to poll.

## 7. Perf numbers come free with this ladder

The consumer run IS the timed workload: check/download/apply timings per leg,
plus `hyperfine` on the packager (warm 20 runs) and a boot-to-healthy loop
(Popen + poll /health, 3 runs) for the server. File PERF rows only when a number
would make a user wait.
