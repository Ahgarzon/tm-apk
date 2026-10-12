import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('coord', Path(__file__).with_name('coordination.py'))
coord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coord)


class Leases(unittest.TestCase):
    def state(self):
        return {'schema': 1, 'counter': 1, 'domains': {'brain': None}}

    def test_acquire_and_preserve_other_domains(self):
        state = self.state()
        changed, receipt = coord.transition(state, 100, 'acquire')
        self.assertEqual(changed['domains']['brain'], None)
        self.assertEqual(state, self.state())
        self.assertEqual(receipt['expires'], 1900)
        self.assertEqual(receipt['fence'], 2)

    def test_existing_james_cannot_be_stolen(self):
        changed, r = coord.transition(self.state(), 100, 'acquire')
        changed['domains']['release-android']['owner'] = 'jamesvidaltourmaps'
        next_state, result = coord.transition(changed, 101, 'acquire')
        self.assertIsNone(next_state)
        self.assertTrue(result['busy'])

    def test_stale_or_wrong_lease_refused(self):
        changed, r = coord.transition(self.state(), 100, 'acquire')
        for when, lease in [(1901, r['lease']), (101, '0' * 32)]:
            with self.assertRaises(ValueError):
                coord.transition(changed, when, 'check', lease)

    def test_check_renew_release(self):
        state, r = coord.transition(self.state(), 100, 'acquire')
        _, check = coord.transition(state, 101, 'check', r['lease'])
        self.assertEqual(check['fence'], r['fence'])
        state, r = coord.transition(state, 200, 'renew', r['lease'])
        self.assertEqual(r['expires'], 2000)
        state, _ = coord.transition(state, 201, 'release', r['lease'])
        self.assertIsNone(state['domains']['release-android'])

    def test_unknown_state_refused(self):
        state = self.state()
        state['domains']['personal'] = None
        with self.assertRaises(ValueError):
            coord.transition(state, 100, 'acquire')

    def test_cloud_qa_is_independent_and_cannot_steal_other_host_qa(self):
        state, r = coord.transition(self.state(), 100, 'acquire')
        state, qa = coord.transition(state, 101, 'acquire', domain='qa-isolated')
        self.assertEqual(state['domains']['release-android']['lease'], r['lease'])
        self.assertNotEqual(qa['lease'], r['lease'])
        changed, busy = coord.transition(state, 102, 'acquire', domain='qa-isolated')
        self.assertIsNone(changed)
        self.assertTrue(busy['busy'])
        with self.assertRaises(ValueError):
            coord.transition(state, 103, 'acquire', domain='brain')


if __name__ == '__main__':
    unittest.main()
