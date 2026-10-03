# GOAL — the crier comms interface (agent chat, web)

**Status:** ACTIVE · opened 2026-10-03 · owner: Bane · maintained by: Hermes
**One line:** build the **entire** comms system — the primary interface for humans to talk to agents —
register users with the right access, then tag agents, groups of agents and sessions, so people and
projects can send messages and get the data they need. **Built to grow**, on a **dual backend**
(PostgreSQL + JSONL, kept in sync).

This file is the canonical goal. Subgoals are added as Bane gives detail. Every subgoal carries its own
status and the evidence or decision it waits on.

---

## Non-negotiables (carry across every subgoal)

1. **Sessions, permissions, threading are the spine** — every UI option must show all three. (Bane, explicit.)
2. **Extend, never replace.** The existing text/message paths must not regress. The UI is a *client* of the
   same REST/WS — no parallel truth, no second delivery path.
3. **Address by capability, not only by identity.** `@cap:solver` already exists server-side
   (`POST /capabilities/{capability}/inbox`, round-robin over live holders). The UI must expose it.
4. **Evidence-first.** A design claim is proved by a mock or a live call, not by prose.
5. **Brand.** charcoal `#0b0d12`, mint `#4cc38a`, lavender/amber accents, robots as mascots.
6. **Build the whole system, designed to grow.** Not a slice — the full comms interface, so more
   projects, more teams and more agents slot in without a redesign. (Bane, 2026-10-03.)
7. **Dual backend, kept in sync: PostgreSQL + JSONL files.** PostgreSQL is the queryable store; JSONL is
   the **transport/interchange** form (bundle a session, ship it, re-import). Postgres alone is "big and
   heavy" — JSONL must be a first-class peer, not an export. (Bane, 2026-10-03.)
8. **Trust is a chain, never a shared secret.** Cross-instance federation and cross-instance signatures
   must resolve through an explicit trust ANCHOR the holder already has. Today's single `CR_FED_TOKEN` is
   the thing being replaced, not the model. (Bane, 2026-10-03.)
9. **Summaries and merges are an INDEX, never the record.** A summary, a roll-up of summaries, or a
   compiled/merged message is always generated and marked as such, always cites what it was made from,
   and never replaces the messages underneath. The trace is the record. (Bane, 2026-10-03.)

---

## Subgoals

| # | Subgoal | Status | Waits on / evidence |
|---|---|---|---|
| G1 | **UI directions** — 3–4 visual options + one legible HTML mock, each showing sessions, permissions, threading | IN FLIGHT | 4 image options produced 2026-10-03; HTML mock next |
| G2 | **Session model** — participants (humans + agents), membership, ordered history; durable/searchable transcript vs thin view | OPEN | D1 |
| G3 | **Permissions & access** — user registration + access grants; roles; who may deliver to whom | OPEN | D2, D3 |
| G4 | **Addressing & tagging** — grammar: `@agent`, `@team:x`, `@cap:y`, `@ns/*`, `#session` | DRAFTED | needs D4 |
| G5 | **Threading** — session vs thread vs topic; reply semantics; what a "channel" maps to | OPEN | depends G2 |
| G6 | **Bridge for agent-class tools** (dots, grokbot, others) — one agent identity each via the existing onboarding path; adapter only if it speaks something unusual | OPEN | needs: what do they speak? |
| G7 | **Human identity** — a `user` principal bound to agent(s); login (session/OIDC); audit says which human spoke as which agent | OPEN | D2 |
| G8 | **Multi-team / multi-project scale** — project/team maps to a namespace or session group; more teams, more agents, different permissions | OPEN | depends G3 |
| G9 | **Where it ships** — crier core in the public repo, or a separate front-end product | OPEN | **Bane's call** |
| G10 | **The wire stays honest** — UI dogfoods the public API; every UI action is a documented call; guard visible on content | OPEN | depends G1 |
| G11 | **Dual backend** — PostgreSQL + JSONL, kept in sync; JSONL is the transport form (bundle a session, ship it, re-import) | OPEN | **D6** |
| G12 | **Grows without redesign** — add a team, project, agent or capability with no schema surgery | OPEN | depends G2/G3/G8 |
| G13 | **Agent classes & resource ownership** — personal agents (mine, they know me) vs service/shared agents (scoped; may own systems/code); cross-owner is default-deny | OPEN | **D7** |
| G14 | **Slack surfaces** — channels (project rooms), direct messages, and ad-hoc NAMED agent groups you can message at once | OPEN | **D8** |
| G15 | **Assets** — S3-backed file/asset storage; the wire carries a reference, never the bytes | OPEN | **D9** |
| G16 | **Nested threads + the request→thread flow** — a request BECOMES a thread; threads break down deeper; the top level stays about different features | OPEN | the acceptance test for the whole interface |
| G17 | **Late-join context** — adding an agent asks how much to share (summary / since-N / full) and the answer is RECORDED on the thread | OPEN | **D10** |
| G18 | **Sub-thread spawning + navigability** — address a non-member → a sub-thread; depth collapse, timeline rail, per-thread summaries, search that returns LOCATION | OPEN | **D11** |
| G19 | **Message kinds** — plain message ≠ addressed message ≠ TASK/ACTION; a tag is addressing, never an instruction to execute or a fan-out | OPEN | **D12** |
| G20 | **API upgrade** — the endpoints the interface owes, taken from the spec's own element→endpoint table (sessions/transcript/membership/thread_id; the read surfaces; audit + permission reads; group objects) | OPEN | CR-CHAT-019/020/021/022 |
| G21 | **External namespaces** — federated rooms: another crier's members appear as *participants* (the Slack-Connect shape), with a per-peer policy on what crosses | OPEN | **D13**, **D14** |
| G22 | **Federation auth** — replace the single shared secret with real peer auth: peer identity, mutual auth, per-peer authorization, revocation of one peer | OPEN | **D13** |
| G23 | **Chain of trust / signing trusts** — who vouches for a key; cross-instance signature verification; rotation and revocation, and what revocation means for already-signed records | OPEN | **D16** |
| G24 | **Single front door** — one identity for the human across instances and one key for the agent across instances (no extra panels, no per-instance re-registration) | OPEN | **D15** |
| G25 | **Compile & merge messages** — select messages across threads, merge into one payload with **per-part provenance**, and feed an agent by tagging it | OPEN | CR-CHAT-028, **D17** |
| G26 | **Agent situational awareness** — every delivery names its location (instance → namespace → channel → thread → sub-thread) and the agent can fetch what it may read | OPEN | CR-CHAT-029 |
| G27 | **Agent-driven call-out** — an agent addresses the right agents to execute (as a TASK, never a bare tag) and the human sees their outputs in that thread | OPEN | CR-CHAT-030, **D12** |
| G28 | **Dual output mode** — the full interleaved trace with timings, or the last summary; one toggle, nothing hidden | OPEN | CR-CHAT-031 |
| G29 | **Summary roll-up** — summaries of summaries; generated, citing its constituents, bounded in depth | OPEN | CR-CHAT-032 |
| G30 | **Dagger control interface** — create, run, observe, cancel and resume a DAG from crier | OPEN | CR-CHAT-033, **D18** |
| G31 | **Dagger as a scheduling engine** — DAG nodes that drive agents over crier, and crier events that trigger a DAG | OPEN | CR-CHAT-034 |
| G32 | **Remote or local DAG execution** — one interface, run wherever the work belongs | OPEN | CR-CHAT-035 |

---

## Task mapping — every subgoal is a board row (nothing lives only in this doc)

| Subgoal | Board row | Pri | Depends on |
|---|---|---|---|
| G1 UI directions | **CR-CHAT-011** (legible HTML mock) + the 4 image options | P3 | CR-CHAT-001 |
| G2 Session model | **CR-CHAT-002** | P2 | 001 |
| G3 Permissions & access | **CR-CHAT-003** | P1 | 001 |
| G4 Addressing & tagging | **CR-CHAT-004** | P2 | 001 |
| G5 Threading | **CR-CHAT-005** | P2 | 002 |
| G6 Bridge (dots/grokbot) | **CR-CHAT-008** | P3 | 001 + what they speak |
| G7 Human identity | **CR-CHAT-007** | P2 | 003 |
| G8 Multi-team scale | **CR-CHAT-010** | P2 | 003, 006 |
| G9 Where it ships | decision only (D5) — no row until called | — | Bane |
| G10 Wire stays honest | folded into **CR-CHAT-009** | P2 | 002–005 |
| G11 Dual backend | **CR-CHAT-006** | P1 | 001 |
| G12 Grows without redesign | folded into **CR-CHAT-010** | P2 | 003, 006 |
| G13 Agent classes & resource ownership | **CR-CHAT-012** | P1 | 001 |
| G14 Slack surfaces (channels / DMs / groups) | **CR-CHAT-013** | P1 | 001, 004 |
| G15 Assets (S3) | **CR-CHAT-014** | P2 | 001, 006 |
| G16 Nested threads + request→thread flow | **CR-CHAT-015** | P1 | 002, 005 |
| G17 Late-join context | **CR-CHAT-016** | P1 | 002, 005 |
| G18 Sub-thread spawning + navigability | **CR-CHAT-017** | P1 | 005, 015 |
| G19 Message kinds (tag ≠ action) | **CR-CHAT-018** | P1 | 005, 017 |
| G20 API upgrade (sessions/transcript/membership/thread_id · read surfaces · audit+permission reads · groups) | **CR-CHAT-019/020/021/022** | P1/P2 | derived from specs/CHAT-INTERFACE.md §4 |
| G21 External namespaces (federated rooms) | **CR-CHAT-023** | P1 | 002, 003 |
| G22 Federation auth (peer identity, per-peer authorization, revocation) | **CR-CHAT-024** | P1 | 003, 023 |
| G23 Chain of trust / signing trusts | **CR-CHAT-025** | P1 | 024 |
| G24 Single front door (one identity, one key) | **CR-CHAT-026** | P2 | 007, 024 |
| G25 Compile & merge messages | **CR-CHAT-028** | P1 | 002, 005 |
| G26 Agent situational awareness | **CR-CHAT-029** | P1 | 002, 016 |
| G27 Agent-driven call-out (TASK, not a tag) | **CR-CHAT-030** | P1 | 018, 029 |
| G28 Dual output mode (trace vs summary) | **CR-CHAT-031** | P2 | 009, 017 |
| G29 Summary roll-up | **CR-CHAT-032** | P2 | 031 |
| G30 Dagger control interface | **CR-CHAT-033** | P1 | — |
| G31 Dagger scheduling engine | **CR-CHAT-034** | P1 | 033 |
| G32 Remote or local DAG execution | **CR-CHAT-035** | P2 | 033 |
| — signed MESSAGE content (the body-binding gap) | **CR-CHAT-027** | P2 | — |
| — the spec of record | **CR-CHAT-001** | P1 | — |
| — the UI itself | **CR-CHAT-009** (web client MVP) | P2 | 002, 003, 004, 005 |

Filed on the crier board 2026-10-03. **CR-CHAT-001 is the gate** — everything except G9 hangs off it.

---

## Decisions pending (Bane)

| # | Decision | My recommendation |
|---|---|---|
| D1 | Session: first-class object (durable transcript, membership) vs thin view over relay topic + inbox | first-class, **implemented as** inbox fan-out — no new delivery path |
| D2 | Humans: a distinct `user` principal that can *speak as* a bound agent, vs humans-as-agents-with-keys | distinct `user` principal (audit + sane UX) |
| D3 | Delivery ACL: explicit "who may deliver to `@agent`" grants, vs namespace membership = blanket permission | explicit grants — the real new security surface |
| D4 | Addressing extent | all four: identity + group + capability + namespace |
| D5 | Ship location (G9) | needs your call — public core vs separate product |
| D6 | **Dual-backend authority** — which store is the source of truth, and how they reconcile | see recommendation below — **JSONL as the ordered append log, PostgreSQL as the query view** |
| D7 | **Agent class and default reach** — personal (owner-only) vs service (scope-based); is cross-owner reach grant-only? | personal + service as classes; cross-owner **default-deny**; a service agent's scope is an explicit, inspectable object |
| D8 | **Group kinds** — one kind of group, or both a NAMED curated set and a dynamic capability target? | **both** — named groups (`@team:x`) are curated and editable; capability targets (`@cap:y`) stay dynamic and already ship |
| D9 | **Asset permissions** — inherit the message's grant at upload, or check per fetch? | check per fetch against the caller's grant (an asset must not become a permission bypass) |
| D10 | **Default context on join** — what an added agent receives by default | **summary** by default, with `since <message>` and `full` offered; the choice is recorded as a system event |
| D11 | **Addressing a non-member** — spray the thread, or spawn a sub-thread? | **neither, automatically**: a reply STAYS IN THREAD — agents talking to each other are messages at the SAME level, not new levels, and depth is never a function of who replied or how many replied. A sub-thread is created only when **deliberately branched**. *(Revised 2026-10-03: my first answer auto-spawned on a tag; Bane corrected it — depth must be earned.)* |
| D12 | **Is a tag an action?** — does `@agent` mean "execute this", or fan out to others? | **No.** Tagging is ADDRESSING ("this message is for you"). A TASK/ACTION is a separate, explicit message kind, rendered and stored differently |
| D13 | **Federation trust anchor** — shared secret, explicit peer keys, or a CA? | **explicit peer keys with mutual signing**, plus an allowlist of trusted peers. The shared secret (`CR_FED_TOKEN`) stays as the degraded default until an operator turns it off — extend, never replace |
| D14 | **Remote participant model** — is a remote user/agent a local shadow principal? | **yes** — a local principal marked `remote`, so the grant model stays local and uniform and permissions are always checked locally |
| D15 | **Cross-instance identity** — one identity everywhere, or per-instance accounts bridged? | **one identity** (OIDC-shaped) with a local shadow per instance — answers "I don't want to log into more panels" |
| D16 | **Trust depth** — is trust transitive (a trusted peer's vouching for a third key is enough)? | **direct peers only by default**; transitive only through an explicit delegation, with a revocation path. No silent second-hand trust |
| D17 | **A merged / compiled message** — a new message, or a view over the sources? | **a NEW message** whose parts each cite the source id, sources stay resolvable, never an untraceable blob |
| D18 | **The dagger boundary** — does crier embed a runner, or call the existing dagger surface? | **call the existing surface** — crier holds the run id + evidence refs; no second executor, no second truth |

---

## Dual backend — my recommendation (for D6)

The trap is two independent stores with live two-way writes: that needs distributed-transaction
machinery and loses on conflict. The shape that works — and that this fleet already runs — is:

- **JSONL is the ordered append log** (the transport form). One line per record-version, append-only,
  git-friendly, ship-anywhere. This is exactly the board/DuckBrain pattern already in use.
- **PostgreSQL is the query view** built from that log — indexed, searchable, transactional, the thing
  the API serves from.
- **Idempotent keys + keep-LAST** on replay, so re-importing a bundle is safe and repeatable.
- **A reconciler** (the same shape as the fleet's board reconciler) proves the view and the log agree —
  a mismatch is a *finding*, not a silent drift.

That gives "easy transport" (a session is a file bundle) without giving up Postgres's query power, and
it keeps the protocol honest: the JSONL *is* the wire format we already speak.

---

## What already exists (reuse, do not rebuild)

- **Namespaces** — realms with per-realm auth posture (`shared`/`token`), rate, retention → the team/project wall.
- **Capability routing** — `POST /capabilities/{capability}/inbox`, `?capability=` discovery → "tag a group of agents".
- **Muster bridge pattern** — `scripts/onboard-connection.sh <platform>`, OpenAPI as target, one agent identity per platform connection.
- **A2A Agent Card** — external discovery for non-crier agents.
- **Inbox + lease/ack + TTL**, **guard** (prompt-injection classification), **webhooks**, **federation**.
- **Postgres durability already landed** (CR-FEAT-034) — the dual backend extends it, it does not replace it.
- **JSONL precedent fleet-wide**: boards are JSONL append-logs (keep-LAST), DuckBrain's storage of record
  is git-backed JSONL row-images, the scheduler ships config/templates as JSONL via a deploy API.
- There is **no UI today** (`cmd/` = `server` + `crier-mcp`), so G1 is genuinely net-new.

---

## What others are doing (recon, 2026-10-03)

- **Slack is positioning itself as the conversational UI for agents** — agents run in channels, threads and
  DMs; split-view container, app threads, text streaming, suggested prompts, interactive Block Kit.
- **Agent-run consoles**: 288px agent sidebar with oversight toggles, chat thread with phase dividers +
  expandable tool cards + handoffs + human broadcasts, detail pane with Board/Steps/Subtask/Tool-calls tabs.
- **Multi-agent dashboards** (React Flow class): orchestrators + sub-agents with live status.
- **Agentic-UX writing (2026)**: the chat box + streaming cursor is no longer enough — plan visibility,
  progress across multi-step work, intervention points, and an **audit trail of what the agent did and why**.
- **Takeaway:** what others *lack* is exactly what crier has natively — capability addressing, namespaces as
  real tenant walls, durable lease/ack semantics, and the injection guard on content. The UI should make
  those visible rather than imitate Slack.

---

## Change log

- 2026-10-03 — goal opened; G1–G10 drafted; recon of others' work; D1–D5 raised; 4 UI options produced.
- 2026-10-03 — +G11 dual backend (Postgres + JSONL, synced, transport-first) and +G12 grow-without-redesign;
  +D6 and the dual-backend recommendation. "Build the entire system" added as non-negotiable #6.
