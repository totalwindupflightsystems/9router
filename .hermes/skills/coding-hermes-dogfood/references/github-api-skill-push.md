# Pushing a Skill to the coding-hermes/skills Repo (no local clone)

The fleet skills repo `github.com/coding-hermes/skills` has **no local
checkout** on this machine — `~/.hermes/skills/` is the canonical working
copy, and distribution happens via the GitHub Contents API. Layout: skills
live at repo root (`coding-hermes-dogfood/SKILL.md`) mirroring
`~/.hermes/skills/`, with `software-development/` and `skills/` subdirs for
older/category entries.

## The Working Pattern

```python
# 1. Build the payload
import json, base64, subprocess
with open('/home/kara/.hermes/skills/<name>/SKILL.md', 'rb') as f:
    content = f.read()
payload = {
    "message": "add <name>: <short description>",
    "content": base64.b64encode(content).decode(),
    "branch": "main",
}
# 2. Write payload to a temp file, then use --input (see pitfall below)
with open('/tmp/skill-payload.json', 'w') as f:
    json.dump(payload, f)
r = subprocess.run(['gh', 'api', '-X', 'PUT',
                    '/repos/coding-hermes/skills/contents/<name>/SKILL.md',
                    '--input', '/tmp/skill-payload.json'],
                   capture_output=True, text=True)
```

If the file already exists, fetch its SHA first and add `"sha": <sha>` to the
payload (Contents API requires the current blob SHA to overwrite).

## Pitfall: `-f data='{...}'` double-encodes and silently fails

`gh api ... -f data='{"content":"..."}'` passes the JSON as a *form value*,
which GitHub rejects with:

```
{"message":"Invalid request.\n\n\"content\", \"message\" weren't supplied.","status":"422"}
```

The `-f` flag encodes the value as a string field, so `data` never arrives as
a JSON object. **Fix:** write the payload dict to a temp file and use
`gh api --input <file>` (raw JSON body). Verified working: dogfood skill push,
commit `f9ae791` (2026-08-01).

## Verification

```bash
gh api /repos/coding-hermes/skills/contents/<name>/SKILL.md --jq '.sha, .path'
```
