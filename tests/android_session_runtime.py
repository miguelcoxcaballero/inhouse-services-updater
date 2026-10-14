#!/usr/bin/env python3
"""Compile the production session installer into a disposable signed Android host.
Drive real Android consent and require PackageManager to advance version 1 -> 2.
No production signing keys, accounts, network downloads, or mock installer used.
"""
import os, re, subprocess, time, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/session-runtime';OUT.mkdir(parents=True,exist_ok=True)
SDK=Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
TOOLS=SDK/'build-tools/36.0.0';ANDROID=SDK/'platforms/android-36/android.jar'
PACKAGE='com.inhouse.installtest'
def run(*args,**kwargs):
 return subprocess.run(list(map(str,args)),check=True,**kwargs)
def output(*args):return run(*args,capture_output=True,text=True).stdout
src=OUT/'src';src.mkdir(exist_ok=True)
(src/'MainActivity.java').write_text('''package com.inhouse.installtest;
import android.app.Activity; import android.os.Bundle; import android.content.Intent; import android.net.Uri;
import android.widget.Button; import java.io.*;
public class MainActivity extends Activity {
 public void onCreate(Bundle saved) { super.onCreate(saved); Button b=new Button(this); b.setText("Install test update");setContentView(b);
 b.setOnClickListener(v->{try{
  try(InputStream in=getAssets().open("update.apk");OutputStream out=new FileOutputStream(new File(getFilesDir(),"update.apk"))){byte[] buf=new byte[65536];int n;while((n=in.read(buf))!=-1)out.write(buf,0,n);}
  startActivity(new Intent(this,com.inhouse.services.updater.InstallActivity.class)
   .setData(Uri.parse("content://"+getPackageName()+".update-provider/base.apk"))
   .putExtra("installId","runtime-consent").putExtra("versionCode",2L).putExtra("versionName","2"));
 }catch(Exception e){throw new RuntimeException(e);}}); }
}''')
(src/'Provider.java').write_text('''package com.inhouse.installtest;
import android.content.*;import android.database.Cursor;import android.net.Uri;import android.os.ParcelFileDescriptor;import java.io.*;
public class Provider extends ContentProvider {
 public boolean onCreate(){return true;}
 public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException{
  if(!"r".equals(mode)||!"/base.apk".equals(uri.getPath()))throw new FileNotFoundException();
  return ParcelFileDescriptor.open(new File(getContext().getFilesDir(),"update.apk"),ParcelFileDescriptor.MODE_READ_ONLY);}
 public String getType(Uri u){return "application/vnd.android.package-archive";}
 public Cursor query(Uri u,String[] p,String s,String[] a,String o){return null;}
 public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
 public int delete(Uri u,String s,String[] a){throw new UnsupportedOperationException();}
 public int update(Uri u,ContentValues v,String s,String[] a){throw new UnsupportedOperationException();}
}''')
classes=OUT/'classes';classes.mkdir(exist_ok=True)
sources=list(src.glob('*.java'))+[ROOT/'android'/name for name in ('InstallActivity.java','InstallReceiver.java','InstallState.java','InstallResultPolicy.java')]
run('javac','--release','8','-cp',ANDROID,'-d',classes,*sources)
dex=OUT/'dex';dex.mkdir(exist_ok=True)
run(TOOLS/'d8','--min-api','23','--lib',ANDROID,'--output',dex,*classes.rglob('*.class'))
key=OUT/'test.jks'
if not key.exists():run('keytool','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','test','-keyalg','RSA','-dname','CN=Disposable Installer Test','-validity','2')
def build(version,asset=None):
 folder=OUT/str(version);folder.mkdir(exist_ok=True)
 manifest=folder/'AndroidManifest.xml'
 manifest.write_text(f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{PACKAGE}" android:versionCode="{version}" android:versionName="{version}">
 <uses-sdk android:minSdkVersion="23" android:targetSdkVersion="36"/>
 <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>
 <application android:label="Installer Runtime Test" android:theme="@android:style/Theme.Material.Light.NoActionBar">
 <activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity>
 <activity android:name="com.inhouse.services.updater.InstallActivity" android:exported="false"/>
 <receiver android:name="com.inhouse.services.updater.InstallReceiver" android:exported="false"/>
 <provider android:name=".Provider" android:authorities="{PACKAGE}.update-provider" android:exported="false" android:grantUriPermissions="true"/>
 </application></manifest>''')
 unsigned=folder/'unsigned.apk';apk=folder/'signed.apk'
 run(TOOLS/'aapt2','link','--manifest',manifest,'-I',ANDROID,'-o',unsigned)
 with zipfile.ZipFile(unsigned,'a') as archive:
  archive.write(dex/'classes.dex','classes.dex')
  if asset:archive.write(asset,'assets/update.apk')
 run(TOOLS/'zipalign','-f','4',unsigned,apk)
 run(TOOLS/'apksigner','sign','--ks',key,'--ks-key-alias','test','--ks-pass','pass:android','--key-pass','pass:android',apk)
 return apk
new=build(2);old=build(1,new)
run('adb','install','-r',old)
run('adb','shell','appops','set',PACKAGE,'REQUEST_INSTALL_PACKAGES','allow')
run('adb','logcat','-c')
run('adb','shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
def tap(label,seconds=35):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  run('adb','shell','uiautomator','dump','/sdcard/session-ui.xml',stdout=subprocess.DEVNULL)
  xml=output('adb','shell','cat','/sdcard/session-ui.xml');(OUT/'screen.xml').write_text(xml)
  for node in ET.fromstring(xml).iter('node'):
   if node.get('text','').casefold()==label.casefold():
    x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
    run('adb','shell','input','tap',(x1+x2)//2,(y1+y2)//2);return
  time.sleep(1)
 raise AssertionError('Android did not show '+label)
try:
 tap('Install test update')
 tap('Install')
 deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  package=output('adb','shell','dumpsys','package',PACKAGE)
  if re.search(r'\bversionCode=2\b',package):
   print('PASS: real Android consent upgraded the production session installer from version 1 to 2.');break
  time.sleep(1)
 else:raise AssertionError('PackageManager did not confirm version 2')
finally:
 (OUT/'logcat.txt').write_text(output('adb','logcat','-d'))
 (OUT/'package.txt').write_text(output('adb','shell','dumpsys','package',PACKAGE))
 with (OUT/'screen.png').open('wb') as file:run('adb','exec-out','screencap','-p',stdout=file)
