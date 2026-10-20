"""FROZEN Android installer: it must stay byte-identical to tag installer-known-good.

The installer below installed an update from inside the app on a real Samsung
phone on 2026-10-20 (Inhouse Notes 1.0.27 -> 1.0.28). Every earlier attempt to
"improve" it broke in-app updates. Read FROZEN_INSTALLER.md. If this test fails,
undo your change to the frozen files; do not edit this test, the tag or the
hashes. Only the user, in their own words, can unfreeze the installer.
"""
import hashlib
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = 'installer-known-good'
FROZEN = (
    'android/PhotosUpdateInstaller.kt',
    'android/UpdateFileProvider.java',
    'tools/register_android.py',
    'FROZEN_INSTALLER.md',
    'tests/test_frozen_installer.py',
    '.github/workflows/frozen-installer.yml',
    '.github/CODEOWNERS',
    '.claude/settings.json',
    '.claude/hooks/protect_frozen_installer.py',
)
WHY = 'The Android installer is frozen; read FROZEN_INSTALLER.md and undo the change.'


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True)


class FrozenInstaller(unittest.TestCase):
    def test_frozen_files_match_the_verified_tag(self):
        if git('rev-parse', '--verify', '--quiet', f'refs/tags/{TAG}^{{commit}}').returncode:
            self.fail(f'Tag {TAG} is missing. Fetch it with "git fetch --tags"; never recreate or move it. {WHY}')
        for path in FROZEN:
            with self.subTest(path=path):
                tagged = git('show', f'{TAG}:{path}')
                self.assertEqual(tagged.returncode, 0, f'{path} is not in {TAG}. {WHY}')
                self.assertTrue((ROOT / path).is_file(), f'{path} was deleted. {WHY}')
                self.assertEqual((ROOT / path).read_bytes(), tagged.stdout, f'{path} differs from {TAG}. {WHY}')

    def test_installer_hands_the_apk_to_android_with_action_view(self):
        source = (ROOT / 'android/PhotosUpdateInstaller.kt').read_text()
        for required in ('Intent(Intent.ACTION_VIEW)', 'setDataAndType(apkUri, APK_MIME_TYPE)',
                         'ClipData.newRawUri("Update APK", apkUri)', 'addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)',
                         '"${activity.packageName}.update-provider"', 'File(activity.cacheDir, "updates")',
                         'canRequestPackageInstalls()', 'verifyApk(apkFile, expectedSha256)'):
            self.assertIn(required, source, WHY)
        code = '\n'.join(line for line in source.splitlines() if not line.strip().startswith('//'))
        for forbidden in ('createSession', 'ACTION_INSTALL_PACKAGE', 'DownloadManager', 'FLAG_ACTIVITY_NEW_TASK'):
            self.assertNotIn(forbidden, code, WHY)

    def test_update_provider_has_its_own_class(self):
        provider = (ROOT / 'android/UpdateFileProvider.java').read_text()
        self.assertIn('public class UpdateFileProvider extends androidx.core.content.FileProvider {}', provider, WHY)
        register = (ROOT / 'tools/register_android.py').read_text()
        self.assertIn("update_provider='com.inhouse.services.updater.UpdateFileProvider'", register, WHY)
        self.assertIn("'${applicationId}.update-provider'", register, WHY)
        self.assertIn('<cache-path name="updates" path="updates/"/>', register, WHY)
        self.assertNotIn("f'{{{ns}}}name':'androidx.core.content.FileProvider'", register, WHY)

    def test_app_builds_reject_a_changed_installer(self):
        source = (ROOT / 'tools/verify.py').read_text()
        for path in ('android/PhotosUpdateInstaller.kt', 'android/UpdateFileProvider.java', 'tools/register_android.py'):
            digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            self.assertTrue(f"'{path}':'{digest}'" in source, f'{path} does not match its frozen SHA-256 in tools/verify.py. {WHY}')


if __name__ == '__main__':
    unittest.main()
