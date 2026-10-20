"""Read/Notes shells: the update provider must not share a class with the host's."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('register_android', ROOT / 'tools/register_android.py')
register_android = importlib.util.module_from_spec(spec)
spec.loader.exec_module(register_android)
NS = '{http://schemas.android.com/apk/res/android}'


class RegisterAndroid(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.repository = Path(folder.name) / 'repository'
        shutil.copytree(ROOT / 'android', self.repository / 'vendor/inhouse-services-updater/android')
        self.project = Path(folder.name) / 'project'
        app = self.project / 'android/app'
        java = app / 'src/main/java/com/inhousesoftware/read'
        java.mkdir(parents=True)
        (java / 'MainActivity.java').write_text(
            'public class MainActivity {\n    public class InhouseNativeBridge {\n'
            '        public void installAppUpdate(String url, String expectedSha256Hex) {\n'
            '            download(url);\n        }\n    }\n}\n')
        (self.project / 'android/build.gradle').write_text('buildscript {\n    dependencies {\n    }\n}\n')
        (app / 'build.gradle').write_text("apply plugin: 'com.android.application'\n"
                                          'android { compileOptions { targetCompatibility JavaVersion.VERSION_21 } }\n')
        # Capacitor already registers androidx FileProvider for "<package>.fileprovider".
        (app / 'src/main/AndroidManifest.xml').write_text(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application>'
            '<provider android:name="androidx.core.content.FileProvider" android:authorities="${applicationId}.fileprovider"'
            ' android:exported="false" android:grantUriPermissions="true"/></application></manifest>')
        register_android.register(self.project, self.repository)
        self.app = app

    def test_update_provider_has_its_own_class(self):
        providers = ET.parse(self.app / 'src/main/AndroidManifest.xml').getroot().find('application').findall('provider')
        update = [p for p in providers if p.get(NS + 'authorities') == '${applicationId}.update-provider']
        self.assertEqual(len(update), 1)
        self.assertEqual(update[0].get(NS + 'name'), 'com.inhouse.services.updater.UpdateFileProvider')
        others = {p.get(NS + 'name') for p in providers if p is not update[0]}
        self.assertNotIn(update[0].get(NS + 'name'), others)
        self.assertTrue((self.app / 'src/main/java/com/inhouse/services/updater/UpdateFileProvider.java').is_file())
        self.assertIn('<cache-path name="updates" path="updates/"/>', (self.app / 'src/main/res/xml/inhouse_update_paths.xml').read_text())

    def test_shell_installer_uses_the_shared_installer(self):
        source = (self.app / 'src/main/java/com/inhousesoftware/read/MainActivity.java').read_text()
        self.assertIn('installInhouseUpdate(url, expectedSha256Hex);', source)
        self.assertNotIn('download(url);', source)


if __name__ == '__main__':
    unittest.main()
