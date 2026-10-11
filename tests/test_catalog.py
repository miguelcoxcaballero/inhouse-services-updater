"""Release safety policy: A default, explicit exact promotion, immutable artifacts."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('catalog',Path(__file__).parents[1]/'tools/catalog.py')
catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog)
class CatalogPolicy(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)
  self.manifest=dict(version='1.0.1',versionCode=2,apkUrl='https://github.com/owner/app/releases/download/v1.0.1/app.apk',apkSha256='a'*64,apkSizeBytes=40)
 def read(self,channel):return json.loads((self.root/'updates'/(channel+'.json')).read_text())
 def test_default_is_a_and_b_is_empty(self):
  catalog.write_release(self.root,self.manifest,'Popup mejorado.')
  self.assertEqual(self.read('A')['latest']['version'],'1.0.1');self.assertIsNone(self.read('B')['latest'])
 def test_b_requires_explicit_request_and_exact_a_artifact(self):
  with self.assertRaises(ValueError):catalog.write_release(self.root,self.manifest,'Popup mejorado.',channel='B')
  with self.assertRaises(ValueError):catalog.write_release(self.root,self.manifest,'Popup mejorado.',channel='B',user_requested_b=True)
  catalog.write_release(self.root,self.manifest,'Popup mejorado.')
  altered={**self.manifest,'apkSha256':'b'*64}
  with self.assertRaises(ValueError):catalog.write_release(self.root,altered,'Popup mejorado.',channel='B',user_requested_b=True)
  catalog.write_release(self.root,self.manifest,'Popup mejorado.',channel='B',user_requested_b=True)
  self.assertEqual(self.read('A')['latest'],self.read('B')['latest'])
 def test_cannot_overwrite_a_version_or_publish_long_notes(self):
  catalog.write_release(self.root,self.manifest,'Popup mejorado.')
  with self.assertRaises(ValueError):catalog.write_release(self.root,{**self.manifest,'apkSha256':'b'*64},'Popup mejorado.')
  with self.assertRaises(ValueError):catalog.write_release(self.root,self.manifest,'x'*121)
  with self.assertRaises(ValueError):catalog.write_release(self.root,self.manifest,'')
 def test_history_keeps_each_immutable_release(self):
  catalog.write_release(self.root,self.manifest,'Popup mejorado.')
  catalog.write_release(self.root,{**self.manifest,'version':'1.0.2','versionCode':3},'Descarga corregida.')
  self.assertEqual([r['versionCode'] for r in self.read('A')['releases']],[3,2])
  with self.assertRaises(ValueError):catalog.write_release(self.root,{**self.manifest,'version':'1.0.0','versionCode':1},'Versión anterior.')
if __name__=='__main__':unittest.main()
