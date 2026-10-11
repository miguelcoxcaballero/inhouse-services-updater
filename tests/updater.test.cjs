const {test}=require('node:test');const assert=require('node:assert/strict');const {JSDOM}=require('jsdom');
const U=require('../web/updater.js');
const repo='miguelcoxcaballero/youtube-calma';
const release=(version='0.1.6',code=16,note='Canales A/B y recordatorio.')=>({version,versionCode:code,apkUrl:`https://github.com/${repo}/releases/download/v${version}/app.apk`,apkSha256:'a'.repeat(64),apkSizeBytes:2000,changelog:note});
const cat=(channel='A',rows=[release()])=>({schemaVersion:1,channel,latest:rows[0]||null,releases:rows});
function fixture(extra={}) {
 const dom=new JSDOM('<!doctype html><button id="before">Settings</button>',{url:'https://appassets.androidplatform.net/updates/'});let clock=100000,requests=[],installs=[];
 const catalogs={A:cat(),B:cat('B',[])};
 const fetch=async url=>{requests.push(url);const channel=url.includes('B.json')?'B':'A';return {ok:true,json:async()=>url.includes('api.github.com')?{content:Buffer.from(JSON.stringify(catalogs[channel])).toString('base64')}:catalogs[channel]};};
 const config={window:dom.window,appId:'youtube',appName:'Inhouse YouTube',repository:repo,installedVersion:'0.1.5',installedVersionCode:15,now:()=>clock,fetch,install:r=>installs.push(r),...extra};
 const app=U.create(config);return {dom,app,config,catalogs,requests,installs,setTime:t=>clock=t,button:text=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent===text)};
}
test('catalog validation binds channel, hash, history and repository',()=>{
 assert.equal(U.validateCatalog(cat(),'A',{repository:repo}).latest.version,'0.1.6');
 for(const mutate of [v=>v.channel='B',v=>v.latest={...v.latest,apkUrl:'https://evil.example/app.apk'},v=>v.latest={...v.latest,apkSha256:'x'},v=>v.latest={...v.latest,changelog:'x'.repeat(121)},v=>v.releases.push(v.latest)]){
  const v=cat();mutate(v);assert.throws(()=>U.validateCatalog(v,'A',{repository:repo}));
 }
 assert.equal(U.newer(release('0.1.4',99),'0.1.5',15),false);assert.equal(U.newer(release('0.1.6',14),'0.1.5',15),false);
});
test('popup is optional, shows compact skipped versions and installs exact verified URL/hash',async()=>{
 const f=fixture();f.catalogs.A=cat('A',[release('0.1.10',20),release('0.1.9',19),release('0.1.8',18),release('0.1.7',17),release('0.1.6',16)]);
 assert.equal(await f.app.check({manual:true}),true);
 const text=f.dom.window.document.body.textContent;assert.match(text,/0.1.5 → 0.1.10 A/);assert.match(text,/Versiones intermedias/);assert.match(text,/\(\+1\)/);assert.equal(f.dom.window.document.querySelectorAll('.isu-changes li').length,3);
 f.button('Actualizar').click();assert.equal(f.installs[0].apkSha256,'a'.repeat(64));assert.equal(f.button('Recordármelo más tarde').disabled,true);
 f.app.result({status:'permission_required'});assert.equal(f.button('Continuar').disabled,false);f.app.result({status:'error',message:'Retry'});assert.equal(f.button('Reintentar').disabled,false);
 f.dom.window.close();
});
test('14-day deferral survives restart, suppresses later releases, and manual checks bypass it',async()=>{
 const f=fixture();await f.app.check();f.button('Recordármelo más tarde').click();assert.equal(f.dom.window.document.querySelector('[role=dialog]'),null);
 const restarted=U.create(f.config);f.catalogs.A=cat('A',[release('0.1.7',17)]);const calls=f.requests.length;
 assert.equal(await restarted.check(),false);assert.equal(f.requests.length,calls);
 assert.equal(await restarted.check({manual:true}),true);restarted.close();
 f.setTime(100000+U.TWO_WEEKS-1);assert.equal(await restarted.check(),false);
 f.setTime(100000+U.TWO_WEEKS+1);assert.equal(await restarted.check(),true);assert.ok(f.dom.window.document.querySelector('[role=dialog]'));
 f.dom.window.close();
});
test('same long-lived updater reminds after two weeks',async()=>{
 const f=fixture();await f.app.check();f.button('Recordármelo más tarde').click();f.setTime(100000+U.TWO_WEEKS+1);await f.app.check();assert.ok(f.button('Actualizar'));f.dom.window.close();
});
test('settings exposes A/B, empty B stays empty and never falls back to A or latest',async()=>{
 const f=fixture();f.app.settings();f.button('Versión B').click();await new Promise(r=>setTimeout(r,20));
 assert.equal(f.app.getState().channel,'B');assert.match(f.dom.window.document.body.textContent,/Aún no hay versiones B/);assert.ok(f.requests.every(x=>x.includes('B.json')));assert.ok(f.requests.every(x=>!x.includes('/releases/latest')));
 const restored=U.create(f.config);assert.equal(restored.getState().channel,'B');f.dom.window.close();
});
test('channel switch cannot display the old in-flight A result',async()=>{
 let resolveA;const f=fixture({fetch:async url=>({ok:true,json:async()=>url.includes('A.json')?await new Promise(r=>resolveA=r):url.includes('api.github.com')?{content:Buffer.from(JSON.stringify(cat('B',[]))).toString('base64')}:cat('B',[])})});
 const pending=f.app.check();await new Promise(r=>setTimeout(r,0));f.app.settings();f.button('Versión B').click();resolveA(cat());await pending;await new Promise(r=>setTimeout(r,10));assert.equal(f.button('Actualizar'),undefined);f.dom.window.close();
});
test('quiet host emits catalog; prechecked popup respects persistent snooze/channel',async()=>{
 const offers=[];const f=fixture({onOffer:v=>offers.push(v)});await f.app.check();assert.equal(offers.length,1);assert.equal(f.dom.window.document.querySelector('[role=dialog]'),null);
 assert.equal(f.app.offerPending(offers[0]),true);f.button('Recordármelo más tarde').click();assert.equal(f.app.offerPending(offers[0]),false);f.dom.window.close();
});
test('changelog content is text, not HTML',async()=>{const f=fixture();f.catalogs.A=cat('A',[release('0.1.6',16,'<img src=x onerror=alert(1)>')]);await f.app.check();assert.equal(f.dom.window.document.querySelector('img'),null);f.dom.window.close();});
