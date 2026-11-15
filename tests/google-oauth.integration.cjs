// Run Notes on localhost:4173 and Paellas on localhost:4174; all Google responses are mocked.
const { chromium } = require(require.resolve('playwright', { paths: [process.cwd(), require('node:path').resolve('../inhousenotes')] }));
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(()=>{
  window.__authURLs=[];
  window.PaellasApp={postMessage(raw){const value=JSON.parse(raw);if(value.type==='signIn')window.__authURLs.push(value.url)}};
  window.InhouseOAuthNative={postMessage(raw){const value=JSON.parse(raw);if(value.method==='write')window.__sharedSession=value.session;
   setTimeout(()=>window.InhouseOAuthNative.onmessage({data:JSON.stringify({id:value.id,session:null})}),0)}};
 });
 const scopes=['drive','spreadsheets','forms','script.projects','script.deployments'].map(x=>'https://www.googleapis.com/auth/'+x).join(' ');
 await page.route('https://oauth2.googleapis.com/token',async route=>{
  const fields=new URLSearchParams(route.request().postData());
  assert.equal(fields.get('client_id'),'435784295430-9idsoe7bb2c6l07m7bb56a25qjnhb43g.apps.googleusercontent.com');
  assert.equal(fields.get('redirect_uri'),'com.inhouse.paellas:/oauth2redirect');
  assert.ok(fields.get('code_verifier').length>=43);
  await route.fulfill({contentType:'application/json',body:JSON.stringify({access_token:'native-token',refresh_token:'native-refresh',expires_in:3600,scope:scopes})});
 });
 await page.route('https://www.googleapis.com/**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({user:{displayName:'Test',emailAddress:'test@example.com',permissionId:'test'},files:[]})}));
 await page.goto('http://127.0.0.1:4174/',{waitUntil:'domcontentloaded'});await page.locator('#loginBtn').click();
 await page.waitForFunction(()=>window.__authURLs.length===1);
 const authURL=new URL(await page.evaluate(()=>window.__authURLs[0]));
 assert.equal(authURL.searchParams.get('response_type'),'code');assert.equal(authURL.searchParams.get('code_challenge_method'),'S256');
 await page.evaluate(state=>window.paellasAuth('code=mock-code&state='+state),authURL.searchParams.get('state'));
 await page.waitForFunction(()=>window.__sharedSession?.refresh_token==='native-refresh');
 const shared=await page.evaluate(()=>window.__sharedSession);assert.equal(shared.client_id,authURL.searchParams.get('client_id'));
 console.log('Paellas PKCE callback + shared grant:',JSON.stringify({errors,success:true}));
 const notes=await browser.newPage({userAgent:'Mozilla/5.0 InhouseNotesApp/1.0.29'});const noteErrors=[];notes.on('pageerror',e=>noteErrors.push(e.message));
 await notes.addInitScript(session=>{
  window.__openedAuth=0;window.InhouseNative={openAuthUrl(){window.__openedAuth++}};
  window.InhouseOAuthNative={postMessage(raw){const value=JSON.parse(raw);setTimeout(()=>window.InhouseOAuthNative.onmessage({data:JSON.stringify({id:value.id,session:value.method==='read'?session:null})}),0)}};
 },shared);
 await notes.route('https://www.googleapis.com/**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({user:{displayName:'Test',emailAddress:'test@example.com',permissionId:'test'},files:[]})}));
 await notes.goto('http://127.0.0.1:4173/',{waitUntil:'domcontentloaded'});
 await notes.waitForFunction(()=>JSON.parse(localStorage.getItem('drive-token-v1')||'null')?.token==='native-token');
 assert.equal(await notes.evaluate(()=>window.__openedAuth),0);
 console.log('Fresh Notes install restores Paellas grant:',JSON.stringify({errors:noteErrors,success:true}));
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
