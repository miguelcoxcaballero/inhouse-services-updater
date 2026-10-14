"""Execute the real receiver against Android boundary fixtures, not a source-text check."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_install_result_policy import compiler

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {
'android/content/BroadcastReceiver.java': 'package android.content; public abstract class BroadcastReceiver { public abstract void onReceive(Context c, Intent i); }',
'android/content/Context.java': '''package android.content;
public class Context { public Intent opened; public boolean blocked;
 public void startActivity(Intent i) { if(blocked) throw new SecurityException(); opened=i; } }''',
'android/content/Intent.java': '''package android.content; import java.util.*;
public class Intent { public static final String EXTRA_INTENT="intent"; public static final int FLAG_ACTIVITY_NEW_TASK=0x10000000;
 public Map<String,Object> extras=new HashMap<>(); public int flags;
 public Intent putExtra(String k,Object v){extras.put(k,v);return this;}
 public String getStringExtra(String k){return (String)extras.get(k);}
 public int getIntExtra(String k,int d){return extras.containsKey(k)?(Integer)extras.get(k):d;}
 @SuppressWarnings("unchecked") public <T> T getParcelableExtra(String k){return (T)extras.get(k);}
 public Intent addFlags(int f){flags|=f;return this;}}
''',
'android/content/pm/PackageInstaller.java': '''package android.content.pm; public class PackageInstaller {
 public static final String EXTRA_STATUS="status";
 public static final int STATUS_PENDING_USER_ACTION=-1,STATUS_SUCCESS=0,STATUS_FAILURE=1,STATUS_FAILURE_ABORTED=3; }''',
'com/inhouse/services/updater/InstallState.java': '''package com.inhouse.services.updater; import android.content.Context;
public class InstallState { public static String status="installing",message=""; public static int writes;
 public static boolean isCurrent(Context c,String id){return "current".equals(id);}
 public static void finish(Context c,String id,String s,String m){status=s;message=m;writes++;}}
''',
'Probe.java': '''import android.content.*; import android.content.pm.*; import com.inhouse.services.updater.*;
public class Probe {
 static void check(boolean value){if(!value)throw new AssertionError();}
 public static void main(String[] args){
  Context context=new Context(); InstallReceiver receiver=new InstallReceiver();
  Intent consent=new Intent(); Intent result=new Intent().putExtra("installId","current").putExtra("status",-1).putExtra(Intent.EXTRA_INTENT,consent);
  receiver.onReceive(context,result);check(context.opened==consent);check((consent.flags&Intent.FLAG_ACTIVITY_NEW_TASK)!=0);check(InstallState.writes==0);
  context.blocked=true;receiver.onReceive(context,result);check(InstallState.status.equals("error"));check(InstallState.message.contains("Download APK"));
  context.blocked=false;result.extras.remove(Intent.EXTRA_INTENT);receiver.onReceive(context,result);check(InstallState.status.equals("error"));
  for(int status=0;status<=7;status++){result.putExtra("status",status);receiver.onReceive(context,result);
   check(InstallState.status.equals(status==0?"installed":status==3?"cancelled":"error"));}
  int writes=InstallState.writes;result.putExtra("installId","old").putExtra("status",0);receiver.onReceive(context,result);check(InstallState.writes==writes);
  result.extras.remove("installId");receiver.onReceive(context,result);check(InstallState.writes==writes);
  System.out.println("PASS consent, rejection, cancellation, terminal failures and stale callbacks");
 }}'''
}

class ReceiverTest(unittest.TestCase):
 def test_session_callbacks(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);files=[]
   for name,source in FIXTURES.items():
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source);files.append(str(path))
   subprocess.run(compiler()+['-d',str(root)]+files+[str(ROOT/'android/InstallReceiver.java'),str(ROOT/'android/InstallResultPolicy.java')],check=True,capture_output=True,text=True)
   result=subprocess.run(['java','-cp',str(root),'Probe'],check=True,capture_output=True,text=True)
   self.assertIn('PASS consent',result.stdout)
