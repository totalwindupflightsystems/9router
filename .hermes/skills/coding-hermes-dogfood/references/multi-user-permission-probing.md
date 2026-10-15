# Multi-User & Permission-Surface Probing (dogfood)

Single-identity real-use runs cannot see authorization defects: everything the provisioned identity touches is owner-level. Permission/share/invite flows are only exercised honestly with at least two identities. This file holds the probing rules for that class of surface.

## Second identity

- Dev-mode products usually provision exactly one identity (a dev JWT sub). Hand-mint a JWT for a SECOND row that already exists in the users table (same signing secret, different sub) — no schema mutation, no credential minting. Drive the shared-resource workflow across both: A creates + shares, B accesses + writes.
- Attribute every 403 by reading the membership table directly, not by re-reading the response. `SELECT count(*) FROM <members_table>` distinguishes 'gate works, B is just not a member' from 'provisioner never wrote the owner row'.

## Bootstrap/provisioning vs authorization

- A bootstrap/provisioner that creates a workspace/team/tree resource but never inserts the OWNER's membership row makes every owner route 403 on a fresh install. The 403 looks like 'authorization working' in logs; it is provisioning broken. Verify the owner row exists before filing any 'membership gate works' claim, and file the finding against the bootstrap transaction (fix = add the membership insert there), not against the gate.
- A deliberate existence-oracle collapse (member-gate folded into a not-found-shaped 403) is defensible — but when the owner hits it via a provisioning bug, they cannot self-diagnose. File the diagnosability gap as its own P2, quoting the documented oracle rationale, not as 'auth broken'.

## Stored-but-unread permission levels

- A permission level that is stored but never read is decoration. Grep the role/permission constant for enforcement readers before trusting any share feature: `grep -rn '<RoleConstant>'` — one writer (the share handler mapping) and zero readers in gates/middleware means the tier is unenforced.
- A membership-EXISTS check (or bare 'is a member' middleware) is NOT a role check. A viewer shared with a resource can create nodes with 201 while every test passes, because tests share one admin identity. The discriminating probe is exactly this: B-as-viewer attempts a write.
- File as 'role stored, never consulted' with the file:line of the EXISTS check and the role constant; fix direction = return the role from the membership check and gate writes on it.

## Membership/role management surface

- After a share succeeds, check the OTHER half of the lifecycle: is there a documented way to list, change, or remove members? A share endpoint with no list/downgrade/revoke path is a real-use dead end (the user can grant access but never see or undo it). Also verify the documented request-body field names against the handler's request struct — a docs-guessed field name 400s and reads as a broken feature.

## Isolated scratch instance for the flow

- Prefer the repo's own scratch-isolation script when one exists — it encodes the project's real collision list (fixed container names, published ports, shared $HOME stores, per-port run registries). If none exists, replicate four isolations yourself: own DATABASE (unique name on the existing server), own loopback PORT, own HOME, own file root, plus a clean `env -i` process environment.
- Afterward prove zero contamination: live instance /health and pid unchanged, DB list unchanged, shared $HOME stores untouched, scratch port released. Teardown order: kill the serve process (kill its direct PID — the shell wrapper persists), drop the scratch DB (retry after the server is down; 'being accessed by other users' means the server is still alive), then delete temp files.
