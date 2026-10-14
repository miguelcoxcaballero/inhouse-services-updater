"""Execute real native install policy and persistence with Android boundary fixtures.

Requires a JDK (or ECJ_JAR with a Java runtime). State tests also use JSON_JAR,
an org.json implementation, because Android's JSONObject is unavailable on JVM.
These tests do not emulate PackageInstaller; APK/device checks remain separate.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def compiler():
    javac = os.environ.get('JAVAC') or shutil.which('javac')
    if javac:
        return [javac, '-encoding', 'UTF-8']
    ecj = os.environ.get('ECJ_JAR')
    if ecj and Path(ecj).is_file():
        return ['java', '-jar', ecj, '-17', '-proc:none', '-encoding', 'UTF-8']
    raise unittest.SkipTest('Install a JDK or set ECJ_JAR to compile native JVM checks')


class InstallResultPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        command = compiler()
        cls.temporary = tempfile.TemporaryDirectory(prefix='inhouse-install-policy-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        fixture = cls.root / 'InstallPolicyProbe.java'
        fixture.write_text('''
import com.inhouse.services.updater.InstallResultPolicy;
public final class InstallPolicyProbe {
    public static void main(String[] args) {
        if ("session".equals(args[0])) {
            System.out.print(InstallResultPolicy.sessionMessage(Integer.parseInt(args[1])));
            return;
        }
        if ("message".equals(args[0])) {
            System.out.print(InstallResultPolicy.failureMessage(Integer.parseInt(args[1])));
            return;
        }
        long expected = Long.parseLong(args[1]), actual = Long.parseLong(args[2]);
        System.out.print("callback".equals(args[0])
            ? InstallResultPolicy.callback(expected, actual, Integer.parseInt(args[3]))
            : InstallResultPolicy.reconcile(expected, actual, args[3], Boolean.parseBoolean(args[4])));
    }
}
''')
        subprocess.run(command + ['-d', str(cls.root),
            str(ROOT / 'android/InstallResultPolicy.java'), str(fixture)], check=True,
            capture_output=True, text=True)

    def result(self, mode, expected, actual, status, different_process=False):
        return subprocess.run(['java', '-cp', str(self.root), 'InstallPolicyProbe',
            mode, str(expected), str(actual), str(status), str(different_process).lower()],
            check=True, capture_output=True, text=True).stdout

    def test_session_errors_are_actionable_and_not_success(self):
        for code, reason in ((2, 'restrictions'), (3, 'cancelled'), (4, 'read'),
                             (5, 'signature'), (6, 'storage'), (7, 'compatible'), (1, 'Download APK')):
            message = subprocess.run(['java', '-cp', str(self.root), 'InstallPolicyProbe',
                'session', str(code)], check=True, capture_output=True, text=True).stdout
            self.assertIn(reason, message)
            self.assertNotIn('Update installed.', message)

    def test_cancelling_android_installer_is_retryable(self):
        self.assertEqual(self.result('callback', 42, 41, 0), 'cancelled')

    def test_android_install_failure_is_retryable(self):
        self.assertEqual(self.result('callback', 42, 41, 1), 'error')

    def test_activity_success_without_installed_version_is_not_success(self):
        self.assertEqual(self.result('callback', 42, 41, -1), 'error')

    def test_actual_installed_version_overrides_missing_or_cancelled_result(self):
        for callback in (0, -1, 1):
            for version in (42, 43):
                with self.subTest(callback=callback, version=version):
                    self.assertEqual(self.result('callback', 42, version, callback), 'installed')

    def test_process_restart_reconciles_actual_installation(self):
        self.assertEqual(self.result('reconcile', 42, 42, 'installing', True), 'installed')
        self.assertEqual(self.result('reconcile', 42, 41, 'installing', True), 'error')

    def test_same_process_install_remains_pending_until_evidence(self):
        self.assertEqual(self.result('reconcile', 42, 41, 'installing'), 'installing')

    def test_terminal_outcome_survives_process_restart(self):
        for status in ('cancelled', 'error'):
            with self.subTest(status=status):
                self.assertEqual(self.result('reconcile', 42, 41, status, True), status)

    def test_previous_success_is_rechecked_after_restore_or_query_failure(self):
        for actual in (0, 41):
            with self.subTest(actual=actual):
                self.assertEqual(self.result('reconcile', 42, actual, 'installed', True), 'error')

    def test_android_failure_messages_explain_the_recoverable_problem(self):
        for code, reason in ((-4, 'storage'), (-7, 'signature'), (-25, 'older version'),
                             (-111, 'restrictions'), (-2, 'read the update package'),
                             (999, 'could not install')):
            with self.subTest(code=code):
                message = subprocess.run(['java', '-cp', str(self.root), 'InstallPolicyProbe',
                    'message', str(code)], check=True, capture_output=True, text=True).stdout
                self.assertIn(reason, message)

    def test_invalid_target_or_failed_version_query_never_reports_installed(self):
        for expected, actual in ((0, 42), (-1, 42), (42, 0)):
            with self.subTest(expected=expected, actual=actual):
                self.assertNotEqual(self.result('callback', expected, actual, -1), 'installed')
                self.assertNotEqual(self.result('reconcile', expected, actual, 'installing', True), 'installed')

    def test_android_long_version_codes_do_not_overflow(self):
        self.assertEqual(self.result('callback', 4_000_000_000, 3_999_999_999, -1), 'error')
        self.assertEqual(self.result('callback', 4_000_000_000, 4_000_000_000, -1), 'installed')


STATE_FIXTURES = {
    'android/content/SharedPreferences.java': '''package android.content;
public interface SharedPreferences {
    String getString(String key, String fallback);
    Editor edit();
    interface Editor { Editor putString(String key, String value); boolean commit(); }
}''',
    'android/content/Context.java': '''package android.content;
public abstract class Context {
    public abstract SharedPreferences getSharedPreferences(String name, int mode);
    public abstract android.content.pm.PackageManager getPackageManager();
    public abstract String getPackageName();
}''',
    'android/content/pm/PackageManager.java': '''package android.content.pm;
public abstract class PackageManager {
    public abstract PackageInfo getPackageInfo(String name, int flags) throws Exception;
}''',
    'android/content/pm/PackageInfo.java': '''package android.content.pm;
public final class PackageInfo {
    public int versionCode; public long longVersionCode;
    public long getLongVersionCode() { return longVersionCode; }
}''',
    'android/os/Build.java': '''package android.os;
public final class Build { public static final class VERSION { public static int SDK_INT = 36; } }
''',
    'InstallStateProbe.java': '''
import android.content.*;
import android.content.pm.*;
import com.inhouse.services.updater.InstallState;
import org.json.JSONObject;

public final class InstallStateProbe {
    static final class Memory implements SharedPreferences {
        String value = "{}"; boolean writable = true; int commits;
        public String getString(String key, String fallback) { return value; }
        public Editor edit() { return new Editor() {
            String next;
            public Editor putString(String key, String value) { next = value; return this; }
            public boolean commit() { commits++; if (!writable) return false; value = next; return true; }
        }; }
    }
    static final class App extends Context {
        final Memory memory = new Memory(); long version = 41; boolean queryFails;
        public SharedPreferences getSharedPreferences(String name, int mode) { return memory; }
        public String getPackageName() { return "com.example.notes"; }
        public PackageManager getPackageManager() { return new PackageManager() {
            public PackageInfo getPackageInfo(String name, int flags) throws Exception {
                if (queryFails) throw new Exception("Package query unavailable");
                PackageInfo info = new PackageInfo(); info.versionCode = (int) version;
                info.longVersionCode = version; return info;
            }
        }; }
    }
    static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    static JSONObject read(App app) { return new JSONObject(InstallState.read(app)); }
    static void restart(App app) { app.memory.value = new JSONObject(app.memory.value).put("process", "old-process").toString(); }
    public static void main(String[] args) {
        App app = new App();
        String scenario = args[0];
        if ("empty".equals(scenario)) {
            check("{}".equals(InstallState.read(app)), "No imaginary prior installation");
            check(InstallState.expectedVersion(app, "none") == 0, "Unknown attempt has no target");
        } else if ("invalid".equals(scenario)) {
            for (String id : new String[] {null, ""}) {
                try { InstallState.begin(app, id, 42, "1.2"); throw new AssertionError("Bad attempt ID accepted"); }
                catch (IllegalArgumentException expected) { }
            }
            try { InstallState.begin(app, "x", 0, "1.2"); throw new AssertionError("Zero target accepted"); }
            catch (IllegalArgumentException expected) { }
            check(app.memory.commits == 0, "Invalid attempt must not persist");
        } else if ("commit-failure".equals(scenario)) {
            app.memory.writable = false;
            try { InstallState.begin(app, "one", 42, "1.2"); throw new AssertionError("Durability failure ignored"); }
            catch (IllegalStateException expected) { }
            check("{}".equals(app.memory.value), "Failed transaction changed storage");
            JSONObject failure = read(app);
            check("error".equals(failure.getString("status")), "Storage failure leaves foreground spinner active");
            check("one".equals(failure.getString("id")), "Storage failure loses attempt ownership");
            app.memory.writable = true; InstallState.begin(app, "retry", 42, "1.2");
            check("retry".equals(read(app).getString("id")), "Durable retry cannot replace transient storage error");
        } else {
            InstallState.begin(app, "one", 42, "1.2");
            check(app.memory.commits > 0, "Attempt must be committed before installer handoff");
            if ("stale".equals(scenario)) {
                InstallState.begin(app, "two", 43, "1.3");
                InstallState.finish(app, "one", "cancelled", "Old result");
                JSONObject state = read(app);
                check("two".equals(state.getString("id")), "Stale callback replaced retry");
                check("installing".equals(state.getString("status")), "Stale callback changed retry status");
                check(InstallState.expectedVersion(app, "one") == 0, "Old attempt still owns target");
                check(!InstallState.isCurrent(app, "one"), "Old attempt still current");
            } else if ("restart-success".equals(scenario)) {
                restart(app); app.version = 42;
                check("installed".equals(read(app).getString("status")), "Self-update process death was not reconciled");
            } else if ("restart-interrupted".equals(scenario)) {
                restart(app);
                check("error".equals(read(app).getString("status")), "Interrupted attempt keeps spinner locked");
            } else if ("cancel".equals(scenario)) {
                InstallState.finish(app, "one", "cancelled", "Cancelled"); restart(app);
                check("cancelled".equals(read(app).getString("status")), "Cancellation does not survive restart");
            } else if ("version-evidence".equals(scenario)) {
                app.version = 43; InstallState.finish(app, "one", "error", "OEM result lost");
                check("installed".equals(read(app).getString("status")), "Actual package evidence ignored");
            } else if ("query-failure".equals(scenario)) {
                app.queryFails = true; restart(app);
                check("error".equals(read(app).getString("status")), "Failed package query claims success");
            } else if ("restored-success".equals(scenario)) {
                app.version = 42; InstallState.finish(app, "one", "installed", "Installed");
                app.version = 41; restart(app);
                check("error".equals(read(app).getString("status")), "Old restored success ignores current package");
            } else if ("legacy-api".equals(scenario)) {
                android.os.Build.VERSION.SDK_INT = 27; app.version = 42;
                check("installed".equals(read(app).getString("status")), "Legacy versionCode unsupported");
            } else if ("long-version".equals(scenario)) {
                InstallState.begin(app, "large", 4000000000L, "2.0"); app.version = 4000000000L;
                check("installed".equals(read(app).getString("status")), "Long versionCode truncated");
            } else if ("bridge".equals(scenario)) {
                check(!read(app).has("process"), "Internal process identifier leaked to bridge");
                check(new JSONObject(app.memory.value).has("process"), "Reading removed persisted process ownership");
                check("installing".equals(read(app).getString("status")), "Repeated read changes active status");
            } else throw new AssertionError("Unknown scenario " + scenario);
        }
        System.out.print("PASS " + scenario);
    }
}
''',
}


class InstallStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        command = compiler()
        json_jar = os.environ.get('JSON_JAR')
        if not json_jar or not Path(json_jar).is_file():
            raise unittest.SkipTest('Set JSON_JAR to an org.json jar for Android persistence boundary checks')
        cls.temporary = tempfile.TemporaryDirectory(prefix='inhouse-install-state-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.classpath = os.pathsep.join([str(cls.root), json_jar])
        files = []
        for name, source in STATE_FIXTURES.items():
            destination = cls.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source)
            files.append(str(destination))
        files += [str(ROOT / 'android' / name) for name in ('InstallState.java', 'InstallResultPolicy.java')]
        subprocess.run(command + ['-classpath', json_jar, '-d', str(cls.root)] + files,
            check=True, capture_output=True, text=True)

    def test_durable_attempts_and_real_package_evidence(self):
        for scenario in ('empty', 'invalid', 'commit-failure', 'stale', 'restart-success',
                         'restart-interrupted', 'cancel', 'version-evidence', 'query-failure',
                         'restored-success', 'legacy-api', 'long-version', 'bridge'):
            with self.subTest(scenario=scenario):
                result = subprocess.run(['java', '-cp', self.classpath, 'InstallStateProbe', scenario],
                    check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout, 'PASS ' + scenario)


if __name__ == '__main__':
    unittest.main()
