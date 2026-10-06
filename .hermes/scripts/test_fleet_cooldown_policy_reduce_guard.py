"""SCHED-GAP-1671: derived REDUCE guard (regression suite, tick 2026-09-29-21-55) — a lane pinned above TARGET_IDLE is
hard-skipped by the REDUCE rule even when the pin is not in ELEVATED_PINS.
Runs fully offline (API + board + ledger + deploy-hash all mocked)."""
import importlib.util, json, sys, unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("fcp", "/home/kara/.hermes/scripts/fleet-cooldown-policy.py")
fcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fcp)

def run_apply(projects, fleet_pins, apply=False, argv_extra=()):
    """Drive main() offline; returns printed lines."""
    argv = ['fleet-cooldown-policy.py', '--dry-run'] + list(argv_extra)
    with mock.patch.object(sys, 'argv', argv), \
         mock.patch.object(fcp, 'verify_deploy_hash', return_value=(True, fcp.STATUS_OK, 'ok')), \
         mock.patch.object(fcp, 'read_fleet_pins', return_value=fleet_pins), \
         mock.patch.object(fcp, 'api_get_all_projects', return_value=projects), \
         mock.patch.object(fcp, 'board_pending', return_value=3), \
         mock.patch.object(fcp, 'open_ledger_gaps', return_value=0), \
         mock.patch.object(fcp, 'api_put') as put, \
         mock.patch('builtins.print') as pr:
        fcp.main()
    return [c.args[0] for c in pr.call_args_list if c.args], put

class DerivedReduceGuardTest(unittest.TestCase):
    def test_weekly_review_lane_not_reduced(self):
        """A 604800-pinned lane with pending work must survive an apply pass."""
        projects = [{'name': 'foo-review', 'enabled': True, 'workdir': '/tmp/x',
                     'cooldown_s': 604800}]
        pins = {'foo-review': 604800}
        lines, put = run_apply(projects, pins, apply=False)
        blob = '\n'.join(lines)
        self.assertNotIn('REDUCE', blob,
                         "REDUCE fired on a pin-above-TARGET_IDLE lane")

    def test_plain_above_idle_with_work_still_reduced(self):
        """Guard must be derived, not a blanket ban: an unpinned 43200 lane
        with real work still goes to the 6h default."""
        projects = [{'name': 'plain-lane', 'enabled': True, 'workdir': '/tmp/x',
                     'cooldown_s': 43200}]
        pins = {'plain-lane': None}  # no pin
        lines, put = run_apply(projects, pins)
        blob = '\n'.join(lines)
        self.assertIn('REDUCE 43200→21600', blob)

if __name__ == '__main__':
    unittest.main(verbosity=2)

class TruncationResidueTest(unittest.TestCase):
    def test_no_pin_live_604800_with_work(self):
        """The actual SCHED-GAP-1671 hole: regen truncation dropped the toml
        pin; live cooldown 604800 + pending work — REDUCE must NOT fire on a
        lane whose LIVE cadence is slower than the default without the
        operator having re-decided."""
        projects = [{'name': 'foo-review', 'enabled': True, 'workdir': '/tmp/x',
                     'cooldown_s': 604800}]
        pins = {}  # pin lost (truncation scenario)
        lines, put = run_apply(projects, pins)
        print('\n'.join(lines))
        blob = '\n'.join(lines)
        self.assertNotIn('REDUCE', blob)

if __name__ == '__main__':
    unittest.main(verbosity=2)
