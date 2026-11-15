from pathlib import Path
import importlib.util, runpy, tempfile, types
root=Path(__file__).resolve().parents[2]
for slug,app,package,relative,method in [
 ('inhousenotes','notes','com.local.inhousenotes','android app/html_to_apk_builder.py','patch_oauth_persistence'),
 ('inhouse-read','read','com.inhousesoftware.read','android/html_to_apk_builder.py','patch_webview_bridge')]:
 spec=importlib.util.spec_from_file_location(app,root/slug/relative);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 builder=object.__new__(module.ApkBuilderApp);builder.log=lambda *args:None
 builder.version_name=types.SimpleNamespace(get=lambda:'1.2.3');builder.version_code=types.SimpleNamespace(get=lambda:999)
 with tempfile.TemporaryDirectory() as temporary:
  project=Path(temporary);activity=project/'android/app/src/main/java'/Path(*package.split('.'))/'MainActivity.java';activity.parent.mkdir(parents=True);activity.write_text('placeholder')
  manifest=project/'android/app/src/main/AndroidManifest.xml';manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".MainActivity" /></application></manifest>')
  (project/'android/app/build.gradle').write_text("apply plugin: 'com.android.application'\nandroid { compileOptions { targetCompatibility JavaVersion.VERSION_21 } }\n")
  (project/'android/build.gradle').write_text('buildscript { dependencies {} }')
  getattr(builder,method)(project,package)
  runpy.run_path(str(root/slug/'vendor/inhouse-services-updater/auth/register_android.py'))['register'](project,root/slug,app)
  runpy.run_path(str(root/slug/'vendor/inhouse-services-updater/auth/register_android.py'))['register'](project,root/slug,app)
  assert activity.read_text().count('GoogleSessionBridge.install(')==1
  assert manifest.read_text().count('com.inhouse.services.oauth.GoogleSessionProvider')==1
  assert 'androidx.webkit:webkit:1.12.1' in (project/'android/app/build.gradle').read_text()
  print(app,'actual generated shell + idempotent OAuth registration: PASS')
