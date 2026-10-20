"""tools/sync.py writes identical copies into each app; Learn is a native host like Photos."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import sync  # noqa: E402


class SyncTest(unittest.TestCase):
    def synced(self, app):
        destination = Path(tempfile.mkdtemp())
        # YouTube and Instagram read their installed version from CalmaBuild.java.
        builds = {'youtube': 'src/es/calma/youtube/nativeapp/CalmaBuild.java',
                  'instagram': 'native/src/es/calma/instagram/nativeapp/CalmaBuild.java'}
        if app in builds:
            (destination / builds[app]).parent.mkdir(parents=True)
            (destination / builds[app]).write_text('static final String VERSION = "0.0.1";\n')
        try:
            sync.sync(app, destination)
        except subprocess.CalledProcessError:
            self.skipTest('sync.py only copies a committed tree; commit the updater first')
        return destination

    def test_every_locked_copy_matches(self):
        for app in sync.APPS:
            destination = self.synced(app)
            lock = json.loads((destination / 'inhouse-updater.lock.json').read_text())
            self.assertEqual(lock['appId'], app)
            for target, entry in lock['files'].items():
                self.assertEqual((destination / target).read_bytes(), (ROOT / entry['source']).read_bytes(), target)
                self.assertEqual(hashlib.sha256((destination / target).read_bytes()).hexdigest(), entry['sha256'])
            self.assertIn('Learn', (destination / 'UPDATER.md').read_text())

    def test_learn_is_a_native_host(self):
        destination = self.synced('learn')
        assets = destination / 'android/app/src/main/assets/updates'
        java = destination / 'android/app/src/main/java/com/inhouse/services/updater'
        for name in ('index.html', 'updater.js', 'updater.css', 'host.js', 'host.css'):
            self.assertEqual((assets / name).read_bytes(), (ROOT / 'web' / name).read_bytes())
        for source in (ROOT / 'android').iterdir():
            self.assertEqual((java / source.name).read_bytes(), source.read_bytes())
        self.assertEqual(json.loads((assets / 'config.json').read_text()), {
            'appId': 'learn', 'appName': 'Inhouse Learn', 'repository': 'miguelcoxcaballero/inhouselearn'})
        subprocess.run([sys.executable, str(destination / 'vendor/inhouse-services-updater/verify.py'), str(destination)],
                       check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
