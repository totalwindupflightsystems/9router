#!/usr/bin/env python3
"""Regression tests for fleet-cooldown-policy.py.

Two regression families:
  1) Namespace preservation (2026-08-27): write_fleet_pins() regenerated
     fleet.toml from the projects API only — [[namespaces]] blocks were
     NEVER emitted, so the coding-hermes default_prompt block and any
     namespace-level config were silently clobbered on every --apply run.
  2) Dynamic-model emission (2026-08-28, Bane): the regen baked
     `model = "deepseek-v4-flash"` / `provider = "deepseek-foreman"` into
     every project lacking an explicit pin — re-pinning the whole fleet to
     one hardcoded lane and SHADOWING the task-router's dynamic resolution
     at spawn. fleet.toml only carries a pin when the operator set one.

Run: ~/.hermes/venvs/board/bin/python3 test_fleet_cooldown_policy.py
"""
import importlib.util
import os
import sys
import tempfile
import tomllib
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fleet-cooldown-policy.py")

spec = importlib.util.spec_from_file_location("fleet_cooldown_policy", SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

# The script self-re-execs into the board venv when duckdb is missing.
# Under the board venv python (per the run line above) it imports cleanly.


def sample_namespaces():
    return [
        {
            "id": "coding-hermes",
            "weight": 100,
            "reserved": 70,
            "hard_cap": 100,
            "max_concurrent": 0,
            "enabled": True,
            "description": "Foreman fleet",
            "default_prompt": "You are the foreman.\nLoad skills at start.\nMulti-line\nbody.",
            "model_chain": "",
        },
        {
            "id": "duckbrain-sync",
            "weight": 5,
            "reserved": 1,
            "hard_cap": 100,
            "max_concurrent": 2,
            "enabled": True,
            "description": "DuckBrain namespace sync jobs (Bane 2026-08-27)",
            "default_prompt": "You are a DuckBrain sync tick.\nProtocol:\n1. test-write\n2. scan\n3. verify.",
            "model_chain": '["deepseek-v4-flash@deepseek"]',
        },
    ]


def sample_projects():
    return [
        {
            "name": "helix",
            "repo_url": "https://example.com/helix",
            "workdir": "/home/kara/helix",
            "weight": 10,
            "priority": 5,
            "cooldown_s": 7200,
            "model": "deepseek-v4-flash",
            "provider": "deepseek-foreman",
            "namespace_id": "coding-hermes",
            "enabled": True,
        },
        {
            "name": "blog-sync",
            "repo_url": "local:/home/kara/.hermes/sync-workdirs/blog-sync",
            "workdir": "/home/kara/.hermes/sync-workdirs/blog-sync",
            "weight": 1,
            "priority": 5,
            "cooldown_s": 21600,
            "model": "deepseek-v4-flash",
            "provider": "deepseek-foreman",
            "namespace_id": "duckbrain-sync",
            "deliver": "telegram:-1003310984808:87792",
            "enabled": True,
        },
    ]


class _TomlWriter:
    """Redirect write_fleet_pins' fleet.toml write to a temp file."""

    def __init__(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False,
                                          encoding="utf-8")
        self.tmp_path = tmp.name
        tmp.close()

    def render(self, projects, namespaces):
        import builtins

        real_path = os.path.expanduser("~/.hermes/fleet.toml")
        original_open = builtins.open

        def spy_open(path, mode="r", *a, **k):
            if os.path.expanduser(path) == real_path and "w" in mode:
                return original_open(self.tmp_path, mode, *a, **k)
            return original_open(path, mode, *a, **k)

        builtins.open = spy_open
        try:
            policy.write_fleet_pins(projects, namespaces=namespaces)
        finally:
            builtins.open = original_open
        with open(self.tmp_path, encoding="utf-8") as f:
            return f.read()


class NamespacePreservationTest(unittest.TestCase):
    def test_emits_namespace_blocks(self):
        """REGRESSION (2026-08-27): regen must emit [[namespaces]] blocks.

        Before the fix, write_fleet_pins produced zero namespaces — this
        clobbered the coding-hermes default_prompt and duckbrain-sync
        config. A namespace list passed in must appear verbatim in the
        generated TOML.
        """
        ns = sample_namespaces()
        text = _TomlWriter().render(sample_projects(), ns)
        data = tomllib.loads(text)
        got = {n["id"] for n in data.get("namespaces", [])}
        self.assertEqual(got, {"coding-hermes", "duckbrain-sync"},
                         "namespaces missing from regenerated fleet.toml")

    def test_namespace_fields_roundtrip(self):
        """Every namespace-level field survives the regen (prompt, chain, cap)."""
        ns = sample_namespaces()
        text = _TomlWriter().render(sample_projects(), ns)
        data = tomllib.loads(text)
        by_id = {n["id"]: n for n in data["namespaces"]}

        ch = by_id["coding-hermes"]
        self.assertEqual(ch["weight"], 100)
        self.assertEqual(ch["reserved"], 70)
        self.assertEqual(ch["hard_cap"], 100)
        self.assertEqual(ch["max_concurrent"], 0)
        self.assertEqual(ch["enabled"], True)
        self.assertIn("Load skills at start", ch["default_prompt"])

        ds = by_id["duckbrain-sync"]
        self.assertEqual(ds["max_concurrent"], 2, "max_concurrent must survive")
        self.assertEqual(ds["model_chain"], ["deepseek-v4-flash@deepseek"],
                         "model_chain must survive as a TOML array")
        self.assertIn("test-write", ds["default_prompt"])
        self.assertIn("Bane 2026-08-27", ds["description"])

    def test_default_prompt_multiline_roundtrip(self):
        """Multi-line prompts with quotes survive triple-single-quoted emission."""
        long_prompt = ("You are a DuckBrain sync tick.\n"
                       "Protocol step 1: test-write the rotating key.\n"
                       'Domains: "person" | "event" | "config".\n'
                       "Step 4: write /sync/last-run LAST.\n")
        ns = [{
            "id": "prompt-ns", "weight": 10, "reserved": 1, "hard_cap": 100,
            "max_concurrent": 1, "enabled": True, "description": "",
            "default_prompt": long_prompt, "model_chain": "",
        }]
        text = _TomlWriter().render(sample_projects(), ns)
        data = tomllib.loads(text)
        self.assertEqual(data["namespaces"][0]["default_prompt"], long_prompt)

    def test_regenerated_fleet_toml_parses_with_projects(self):
        """The full regen output (namespaces + projects) is valid TOML and
        projects keep their namespace_id wiring."""
        ns = sample_namespaces()
        text = _TomlWriter().render(sample_projects(), ns)
        data = tomllib.loads(text)
        self.assertEqual(len(data["projects"]), 2)
        by_name = {p["name"]: p for p in data["projects"]}
        self.assertEqual(by_name["blog-sync"]["namespace_id"], "duckbrain-sync")
        self.assertEqual(by_name["blog-sync"]["cooldown_s"], 21600)
        self.assertEqual(by_name["helix"]["namespace_id"], "coding-hermes")


class DynamicModelEmissionTest(unittest.TestCase):
    """REGRESSION (2026-08-28, Bane): the regen must NEVER bake a model
    default. write_fleet_pins used to emit `model = "deepseek-v4-flash"` /
    `provider = "deepseek-foreman"` for every project lacking an explicit
    pin — re-pinning the whole fleet to one hardcoded lane and SHADOWING
    the task-router's dynamic resolution at spawn. The task-router decides;
    fleet.toml only carries an explicit pin when the operator set one."""

    def test_unset_model_stays_unset(self):
        """A project with NO model/provider must get NO model/provider lines
        — the router resolves at spawn; a hardcoded default is the bug."""
        project = {
            "name": "blog-sync", "repo_url": "local:/x",
            "workdir": "/x", "weight": 1, "priority": 5,
            "cooldown_s": 21600, "namespace_id": "duckbrain-sync",
            "enabled": True,
        }
        text = _TomlWriter().render([project], None)
        data = tomllib.loads(text)
        p = data["projects"][0]
        self.assertNotIn("model", p, "regen baked a model default — dynamic "
                                     "resolution is shadowed (Bane 2026-08-28)")
        self.assertNotIn("provider", p,
                         "regen baked a provider default — dynamic "
                         "resolution is shadowed (Bane 2026-08-28)")

    def test_explicit_pin_is_preserved(self):
        """An EXPLICIT operator pin still round-trips (overrides are legal;
        defaults are not)."""
        project = {
            "name": "helix", "repo_url": "https://example.com/helix",
            "workdir": "/home/kara/helix", "weight": 10, "priority": 5,
            "cooldown_s": 7200, "model": "glm-5.3-flash",
            "provider": "zai-glm", "namespace_id": "coding-hermes",
            "enabled": True,
        }
        text = _TomlWriter().render([project], None)
        data = tomllib.loads(text)
        p = data["projects"][0]
        self.assertEqual(p["model"], "glm-5.3-flash")
        self.assertEqual(p["provider"], "zai-glm")


class AdaptiveCooldownArmingTest(unittest.TestCase):
    """SCHED-GAP-1 (Bane 2026-09-04, shipped 2026-09-09): the speed-control
    money lever. Foreman-lane projects must be ARMED in every regen —
    adaptive_cooldown=true with an EXPLICIT 8x ceiling (the scheduler
    defaults an absent ceiling to 604800s = 7 days, which is NOT 8x).
    Other lanes stay off: arming sync/qa/pm now would only mask upstream
    outages as slow ticks until the upstream-quiet signal ships."""

    def test_foreman_lane_armed_with_explicit_ceiling(self):
        project = {
            "name": "helix", "repo_url": "https://example.com/helix",
            "workdir": "/home/kara/helix", "weight": 10, "priority": 5,
            "cooldown_s": 7200, "namespace_id": "coding-hermes",
            "enabled": True,
        }
        p = tomllib.loads(_TomlWriter().render([project], None))["projects"][0]
        self.assertTrue(p.get("adaptive_cooldown"),
                        "foreman-lane project left unarmed — adaptive_cooldown pin absent")
        self.assertEqual(p.get("cooldown_ceiling_s"), 57600,
                         "ceiling must be explicit 8x cooldown (7200*8); "
                         "an absent key defaults to 604800 in the loader")

    def test_non_foreman_lane_stays_disarmed(self):
        for ns in ("duckbrain-sync", "qa", "pm", None):
            project = {
                "name": "blog-sync", "repo_url": "local:/x",
                "workdir": "/x", "weight": 1, "priority": 5,
                "cooldown_s": 21600, "enabled": True,
            }
            if ns:
                project["namespace_id"] = ns
            p = tomllib.loads(_TomlWriter().render([project], None))["projects"][0]
            self.assertFalse(p.get("adaptive_cooldown", False),
                             f"lane {ns!r} must stay disarmed until "
                             f"upstream-quiet signal ships")
            self.assertNotIn("cooldown_ceiling_s", p)


class DisabledLaneEmissionTest(unittest.TestCase):
    """SCHED-GAP-1662: fleet.toml is enabled-only. The regen filtered to
    enabled projects, so the 166 paused lanes had no durable entry and
    restarts re-derived state the file never described. The regen must emit
    EVERY project with `enabled = false` for the paused set."""

    def test_regen_emits_disabled_lane_with_enabled_false(self):
        projects = sample_projects()
        projects.append({
            "name": "paused-lane", "repo_url": "local:/x",
            "workdir": "/x", "weight": 1, "priority": 5,
            "cooldown_s": 43200, "enabled": False,
        })
        data = tomllib.loads(_TomlWriter().render(projects, None))
        names = {p["name"]: p for p in data["projects"]}
        self.assertIn("paused-lane", names,
                      "disabled lane missing from regen — no durable entry")
        self.assertFalse(names["paused-lane"]["enabled"])
        self.assertTrue(names["helix"]["enabled"])

    def test_regen_count_equals_input_count_mixed(self):
        projects = sample_projects() + [
            {"name": f"paused-{i}", "repo_url": "local:/x", "workdir": "/x",
             "weight": 1, "priority": 5, "cooldown_s": 43200,
             "enabled": False}
            for i in range(3)
        ]
        text = _TomlWriter().render(projects, None)
        data = tomllib.loads(text)
        self.assertEqual(len(data["projects"]), len(projects),
                         "regen dropped lanes — enabled-only filter survived")


class EmptyPinMapGuardTest(unittest.TestCase):
    """SCHED-GAP-1662 / SCHED-GAP-123 family: an empty pin map made --apply
    emit rule PUTs that drifted live cooldowns fleet-wide (twice live,
    2026-09-16). --apply with an empty pin map and >10 projects must refuse
    with exit 2 BEFORE any PUT or regen."""

    def _run_main(self, projects, argv):
        import builtins
        real_argv = sys.argv
        real_get = policy.api_get_all_projects
        real_put = policy.api_put
        real_read = policy.read_fleet_pins
        real_vdh = policy.verify_deploy_hash
        real_open = builtins.open
        sys.argv = argv
        policy.api_get_all_projects = lambda: projects
        policy.read_fleet_pins = lambda: {}
        # The deploy-integrity guard compares the live script hash against the
        # canonical sidecar; tests must not depend on it.
        policy.verify_deploy_hash = lambda: (True, policy.STATUS_OK, 'test')
        puts = []
        policy.api_put = lambda path, body: puts.append((path, body))
        # Redirect any fleet.toml READ to an empty temp file (empty map).
        tmp = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        tmp.write("")
        tmp.close()
        real_path = os.path.expanduser("~/.hermes/fleet.toml")

        def spy_open(path, mode="r", *a, **k):
            if os.path.expanduser(path) == real_path and "r" in mode:
                return real_open(tmp.name, mode, *a, **k)
            return real_open(path, mode, *a, **k)
        builtins.open = spy_open
        try:
            policy.main()
        finally:
            sys.argv = real_argv
            policy.api_get_all_projects = real_get
            policy.read_fleet_pins = real_read
            policy.verify_deploy_hash = real_vdh
            policy.api_put = real_put
            builtins.open = real_open
            os.unlink(tmp.name)

    def test_apply_refuses_on_empty_map_with_many_projects(self):
        projects = [{"name": f"p{i}", "workdir": "/x", "cooldown_s": 7200,
                     "enabled": True} for i in range(20)]
        with self.assertRaises(SystemExit) as ctx:
            self._run_main(projects,
                           ["fleet-cooldown-policy.py", "--apply"])
        self.assertEqual(ctx.exception.code, 2,
                         "empty pin map --apply must exit 2 (refusal)")

    def test_small_fleet_does_not_refuse(self):
        # <=10 projects: the size guard does not fire; main runs past it.
        projects = [{"name": f"p{i}", "workdir": "/x", "cooldown_s": 7200,
                     "enabled": True} for i in range(3)]
        try:
            self._run_main(projects,
                           ["fleet-cooldown-policy.py", "--apply", "--dry-run"])
        except SystemExit as e:
            self.assertNotEqual(e.code, 2,
                                "small fleet must not hit the size guard")


class ParityCheckTest(unittest.TestCase):
    """SCHED-GAP-1662 parity tripwire: db project count must equal the
    [[projects]] block count in fleet.toml."""

    def test_count_blocks_parses_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[[projects]]\nname = "a"\n\n[[projects]]\nname = "b"\n')
            path = f.name
        self.assertEqual(policy.count_fleet_toml_project_blocks(path), 2)

    def test_parity_ok_on_match(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[[projects]]\nname = \"a\"\n")
            path = f.name
        projects = [{"name": "a"}, {"name": "b"}][:1]
        ok, msg = policy.check_db_file_parity(projects, path=path)
        self.assertTrue(ok)
        self.assertIn("PARITY OK", msg)
        self.assertIn("db lanes=1", msg)

    def test_parity_fails_on_mismatch(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[[projects]]\nname = \"a\"\n")
            path = f.name
        projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        ok, msg = policy.check_db_file_parity(projects, path=path)
        self.assertFalse(ok)
        self.assertIn("PARITY MISMATCH", msg)
        self.assertIn("db lanes=3 file blocks=1", msg)

    def test_missing_file_counts_zero_and_mismatches(self):
        ok, msg = policy.check_db_file_parity(
            [{"name": "a"}], path="/nonexistent/fleet.toml")
        self.assertFalse(ok)
        self.assertIn("file blocks=0", msg)


class LoaderPathTest(unittest.TestCase):
    """SCHED-GAP-1662: single loader path — every fleet.toml touch goes
    through fleet_toml_path()."""

    def test_helper_returns_hermes_fleet_toml(self):
        self.assertEqual(policy.fleet_toml_path(),
                         os.path.expanduser("~/.hermes/fleet.toml"))

    def test_default_reads_use_helper(self):
        # read_fleet_pins/count_fleet_toml_project_blocks default to the
        # helper's path (pass None explicitly to exercise the default arm).
        self.assertEqual(policy.read_fleet_pins(path=None) ==
                         policy.read_fleet_pins(policy.fleet_toml_path()), True)

    def test_no_hardcoded_fleet_toml_paths_remain(self):
        import re
        with open(SCRIPT, encoding="utf-8") as f:
            src = f.read()
        # Allow the helper definition line + comments/docstrings.
        lines = [l for l in src.splitlines()
                 if re.search(r"fleet\.toml", l)
                 and "expanduser" not in l
                 and not l.lstrip().startswith("#")
                 and "fleet_toml_path" not in l]
        # Strip docstring content: crude but effective — check for any
        # remaining expanduser-free code lines referencing a path literal.
        offenders = [l for l in lines
                     if re.search(r"['\"](/|~/|os\.path\.join\([^)]*fleet)", l)]
        self.assertEqual(offenders, [],
                         f"hardcoded fleet.toml paths remain: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
