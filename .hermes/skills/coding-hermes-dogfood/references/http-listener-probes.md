# HTTP listener & probe attribution pitfalls

Depth for the dogfood loop's HTTP-probing steps: proving WHICH process answered, and reading server-side crashes from client symptoms.

## Verify the port is YOUR process

**Verify the port you curl is YOUR process before trusting any HTTP result.** Shared dev hosts carry foreign listeners: a 200 on the port you 'chose' may come from an unrelated daemon while your own server's log says 'address already in use'. Check `ss -ltnp` (or fuser) plus the server's own startup log before drawing a conclusion from curl output.

## A runner POSTing to a DEFAULT port grades a foreign server's error body as node output

**A runner that POSTs node work to a DEFAULT port can grade a FOREIGN server's error body as node output — read error-shaped Output as evidence, never as data.** When the runner special-cases only ONE HTTP status (typically 401) after the POST, every other non-200 body that fails JSON-decode falls through as the node's Output with a nil error: the foreign daemon's `404 page not found` mux reply graded ✅ Passed with exit 0, on a shared host where another service owns the default port. Always pass the product's explicit `--server`/`--addr` + token pointing at YOUR instance, grep node Output for `page not found|unauthorized` before believing a pass, and pin the defect by driving BOTH failure legs: no listener at all (the runner must fail honestly with 'connection refused') versus a foreign listener on the default port (the false green). The row's fix direction is the missing status-code check in the runner — require HTTP 200 AND a decodable response envelope — not the port collision itself.

## docker-compose: a foreign listener makes the bind fail SILENTLY

**On docker-compose products, a foreign listener on the published host port makes the bind fail SILENTLY — `docker ps` still shows Up.** Docker's endpoint programming fails ('Bind for 0.0.0.0:<port> failed: port is already allocated') but the container keeps running with `NetworkSettings.Networks = {}` and empty Ports; the only visible symptom is the missing PORTS cell in `docker compose ps`, and the user gets the foreign daemon's 404. Diagnose: `docker inspect <c> --format '{{json .NetworkSettings.Networks}}'` (empty = not on any network), `ps aux | grep 'docker-proxy' | grep 'host-port <port>'` (argv names the container that really owns the port), and `docker network connect` reproduces the bind error verbatim. File it as a P0 product/deploy gap (add a post-up reachability gate that fingerprints the served page), and free the port for your own smoke by stopping the foreign stack — never re-point the project's compose ports to dodge a collision.

## Empty reply = server-side panic until proven otherwise

**An HTTP request that dies with an empty reply is a server-side PANIC until proven otherwise.** curl exit 52 'Empty reply from server' (browser: fetch 'Failed to fetch' with no status code) means the handler crashed and net/http killed the connection — grep the SERVER log for 'http: panic serving' before filing 'transport/network broken'; the stack trace in the log names the exact file:line. The classic shape: a Postgres-only repository field (nil pgxpool) dereferenced on a SQLite backend where the wiring never initializes it — the handler works on one configured backend and kills connections on the default one, which is exactly what unit tests on the other backend cannot see. Related admin/optional routes can each behave differently (one 404s, one 403s, one panics) — drive every route in the family, not just the ones the UI links to.
