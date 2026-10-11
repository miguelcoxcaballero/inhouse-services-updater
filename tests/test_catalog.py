"""Release policy: A includes B, explicit B authorization, immutable artifacts."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('catalog', Path(__file__).parents[1] / 'tools/catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogPolicy(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.note = 'Popup mejorado.'
        self.manifest = self.manifest_for(2)

    def manifest_for(self, code):
        return dict(version=f'1.0.{code - 1}', versionCode=code,
                    apkUrl=f'https://github.com/owner/app/releases/download/v1.0.{code - 1}/app.apk',
                    apkSha256='a' * 64, apkSizeBytes=40)

    def read(self, channel):
        return json.loads((self.root / 'updates' / (channel + '.json')).read_text())

    def store(self, channel, value):
        (self.root / 'updates').mkdir(exist_ok=True)
        (self.root / 'updates' / (channel + '.json')).write_text(json.dumps(value))

    def publish(self, code=2, channel='A', authorized=False):
        return catalog.write_release(self.root, self.manifest_for(code), self.note,
                                     channel=channel, user_requested_b=authorized)

    def snapshot(self):
        return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*.json')}

    def test_default_is_a_and_b_is_empty(self):
        self.publish()
        self.assertEqual(self.read('A')['latest']['version'], '1.0.1')
        self.assertIsNone(self.read('B')['latest'])

    def test_b_requires_explicit_request_even_for_existing_b(self):
        with self.assertRaises(ValueError):
            self.publish(channel='B')
        self.assertFalse((self.root / 'updates').exists())
        self.publish(channel='B', authorized=True)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.publish(channel='B')
        self.assertEqual(self.snapshot(), before)

    def test_direct_b_publication_enters_both_channels(self):
        self.publish(channel='B', authorized=True)
        self.assertEqual(self.read('A')['latest'], self.read('B')['latest'])
        self.assertEqual(self.read('A')['releases'], self.read('B')['releases'])

    def test_newer_b_becomes_latest_a_and_preserves_a_history(self):
        self.publish()
        older_a = self.read('A')['latest']
        self.publish(3, channel='B', authorized=True)
        self.assertEqual(self.read('A')['latest'], self.read('B')['latest'])
        self.assertEqual([r['versionCode'] for r in self.read('A')['releases']], [3, 2])
        self.assertEqual(self.read('A')['releases'][1], older_a)
        self.assertEqual([r['versionCode'] for r in self.read('B')['releases']], [3])

    def test_promoting_older_a_keeps_newer_a_selected(self):
        self.publish()
        older_a = self.read('A')['latest']
        self.publish(3)
        newer_a = self.read('A')['latest']
        self.publish(channel='B', authorized=True)
        self.assertEqual(self.read('A')['latest'], newer_a)
        self.assertEqual(self.read('B')['latest'], older_a)
        self.assertEqual([r['versionCode'] for r in self.read('A')['releases']], [3, 2])

    def test_newer_a_after_b_is_selected_only_in_a(self):
        self.publish(channel='B', authorized=True)
        reviewed = self.read('B')
        self.publish(3)
        self.assertEqual(self.read('A')['latest']['versionCode'], 3)
        self.assertEqual(self.read('B'), reviewed)

    def test_existing_b_retry_repairs_missing_a_and_is_idempotent(self):
        self.publish()
        older_a = self.read('A')
        self.publish(3, channel='B', authorized=True)
        reviewed = self.read('B')['latest']
        self.store('A', older_a)
        self.publish(3, channel='B', authorized=True)
        self.assertEqual(self.read('A')['latest'], reviewed)
        before = self.snapshot()
        self.assertIsNone(self.publish(3, channel='B', authorized=True))
        self.assertEqual(self.snapshot(), before)

    def test_a_retry_reconciles_all_legacy_b_entries_and_selects_maximum(self):
        self.publish()
        older_a = self.read('A')
        self.publish(3, channel='B', authorized=True)
        self.publish(4, channel='B', authorized=True)
        reviewed = self.read('B')
        self.store('A', older_a)
        self.publish()
        self.assertEqual(self.read('A')['latest'], reviewed['latest'])
        self.assertEqual([r['versionCode'] for r in self.read('A')['releases']], [4, 3, 2])
        self.assertEqual(self.read('B'), reviewed)

    def test_b_only_legacy_catalog_without_a_can_be_repaired(self):
        self.publish(channel='B', authorized=True)
        reviewed = self.read('B')
        (self.root / 'updates' / 'A.json').unlink()
        self.publish()
        self.assertEqual(self.read('A')['releases'], reviewed['releases'])
        self.assertEqual(self.read('A')['latest'], reviewed['latest'])

    def test_history_deduplication_sorting_and_stale_latest_repair(self):
        self.publish()
        self.publish(3)
        value = self.read('A')
        newer, older = value['releases']
        value['releases'] = [older, newer, older, newer]
        value['latest'] = older
        self.store('A', value)
        self.publish()
        self.assertEqual(self.read('A')['releases'], [newer, older])
        self.assertEqual(self.read('A')['latest'], newer)
        before = self.snapshot()
        self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_history_keeps_an_orphan_published_latest(self):
        self.publish(channel='B', authorized=True)
        value = self.read('B')
        value['releases'] = []
        self.store('B', value)
        self.publish()
        self.assertEqual(self.read('B')['releases'], [value['latest']])
        self.assertEqual(self.read('A')['latest'], value['latest'])

    def test_conflicting_incoming_artifact_or_note_never_changes_files(self):
        self.publish(channel='B', authorized=True)
        mutations = {'version': '2.0.0', 'apkUrl': 'https://example.com/replaced.apk',
                     'apkSha256': 'b' * 64, 'apkSizeBytes': 41}
        for channel in ('A', 'B'):
            for key, value in mutations.items():
                with self.subTest(channel=channel, key=key):
                    before = self.snapshot()
                    with self.assertRaises(ValueError):
                        catalog.write_release(self.root, {**self.manifest, key: value}, self.note,
                                              channel=channel, user_requested_b=True)
                    self.assertEqual(self.snapshot(), before)
            before = self.snapshot()
            with self.assertRaises(ValueError):
                catalog.write_release(self.root, self.manifest, 'Changed published note.',
                                      channel=channel, user_requested_b=True)
            self.assertEqual(self.snapshot(), before)

    def test_cross_catalog_conflict_rejects_unrelated_publication_without_writes(self):
        self.publish(channel='B', authorized=True)
        value = self.read('B')
        value['latest']['apkSha256'] = 'b' * 64
        value['releases'][0]['apkSha256'] = 'b' * 64
        self.store('B', value)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.publish(3)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_second_catalog_does_not_create_first_catalog(self):
        self.store('B', dict(schemaVersion=1, channel='B', latest=None, releases=[{'versionCode': 2}]))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.publish(3)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'updates' / 'A.json').exists())

    def test_conflicting_duplicate_or_latest_is_not_silently_dropped(self):
        self.publish()
        original = self.read('A')
        for location in ('duplicate', 'latest'):
            with self.subTest(location=location):
                value = copy.deepcopy(original)
                altered = {**value['latest'], 'apkSizeBytes': 100}
                if location == 'duplicate':
                    value['releases'].append(altered)
                else:
                    value['latest'] = altered
                self.store('A', value)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.publish(3)
                self.assertEqual(self.snapshot(), before)

    def test_cannot_publish_new_older_global_version(self):
        self.publish(3, channel='B', authorized=True)
        for channel in ('A', 'B'):
            before = self.snapshot()
            with self.assertRaises(ValueError):
                self.publish(2, channel=channel, authorized=True)
            self.assertEqual(self.snapshot(), before)

    def test_invalid_input_does_not_create_catalogs(self):
        for note in ('', 'x' * 121):
            with self.assertRaises(ValueError):
                catalog.write_release(self.root, self.manifest, note)
        for code in (0, -1, True, '2'):
            with self.assertRaises(ValueError):
                catalog.write_release(self.root, {**self.manifest, 'versionCode': code}, self.note)
        with self.assertRaises(ValueError):
            catalog.write_release(self.root, self.manifest, self.note, channel='C')
        self.assertFalse((self.root / 'updates').exists())


if __name__ == '__main__':
    unittest.main()
