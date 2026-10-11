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
 if (!extra.defaultB) dom.window.localStorage.setItem("inhouse-services-updater:youtube",JSON.stringify({channel:"A",developmentConsent:1,snooze:{}}));
 const app=U.create(config);return {dom,app,config,catalogs,requests,installs,setTime:t=>clock=t,button:text=>[...dom.window.document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||b.textContent)===text)};
}
test('embedded account settings retain channels and checks without a modal or focus trap',async()=>{
 const f=fixture({defaultB:true}),doc=f.dom.window.document,container=doc.createElement('section');doc.body.append(container);
 f.app.settings('',{container});
 assert.equal(doc.querySelector('[role=dialog]'),null);assert.equal(doc.querySelector('[aria-modal]'),null);
 assert.ok(container.querySelector('.isu-inline[role=region]'));assert.ok(f.button('Version B'));
 const last=container.querySelector('.isu-github');last.focus();
 const tab=new f.dom.window.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true});last.dispatchEvent(tab);assert.equal(tab.defaultPrevented,false);
 await f.app.check({manual:true});assert.match(container.textContent,/No releases on version B/);
 f.button('Version A').click();assert.match(container.textContent,/untested development updates/);assert.equal(f.app.getState().channel,'B');
 f.button('I understand').click();const slider=container.querySelector('input');slider.value='100';slider.dispatchEvent(new f.dom.window.Event('change'));
 await new Promise(r=>setTimeout(r,20));assert.equal(f.app.getState().channel,'A');assert.ok(container.querySelector('[data-isu-install]'));assert.equal(doc.querySelector('[role=dialog]'),null);
 f.button('Update').click();assert.equal(f.installs.length,1);f.app.result({status:'ready'});f.app.close();assert.equal(container.children.length,0);
 f.app.settings();assert.ok(doc.querySelector('[role=dialog]'));f.dom.window.close();
});

test('closing an embedded menu prevents a pending manual result from opening a popup',async()=>{
 let respond;const f=fixture({fetch:()=>new Promise(resolve=>respond=resolve)}),container=f.dom.window.document.createElement('section');f.dom.window.document.body.append(container);
 f.app.settings('',{container});const pending=f.app.check({manual:true});f.app.close();respond({ok:true,json:async()=>cat()});
 assert.equal(await pending,false);assert.equal(f.dom.window.document.querySelector('#inhouse-services-update'),null);f.dom.window.close();
});

test('manual checks joining startup checks still report the empty channel',async()=>{
 let unblock;const gate=new Promise(resolve=>unblock=resolve);
 const f=fixture({defaultB:true,fetch:async url=>{await gate;return {ok:true,json:async()=>url.includes('api.github.com')?{content:Buffer.from(JSON.stringify(cat('B',[]))).toString('base64')}:cat('B',[])}}});
 const startup=f.app.check();f.app.settings();const manual=f.app.check({manual:true});unblock();
 assert.equal(await startup,false);assert.equal(await manual,false);assert.match(f.dom.window.document.body.textContent,/No releases on version B/);f.dom.window.close();
});

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
 const doc=f.dom.window.document;assert.equal(doc.querySelector('.isu-versions').textContent,'0.1.5 → 0.1.10');assert.equal(doc.querySelector('.isu-note').textContent,'Canales A/B y recordatorio.');assert.equal(doc.querySelector('.isu-more').hidden,true);
 f.button('Details').click();assert.equal(doc.querySelector('.isu-more').hidden,false);assert.equal(doc.querySelector('.isu-disclosure').getAttribute('aria-expanded'),'true');
 assert.deepEqual([...doc.querySelectorAll('.isu-changes small')].map(v=>v.textContent),['0.1.9','0.1.8','0.1.7']);assert.equal(doc.querySelector('.isu-earlier').textContent,'+1 earlier version');
 assert.match(doc.querySelector('.isu-facts').textContent,/Version A/);
 f.button('Update').click();assert.equal(f.installs[0].apkSha256,'a'.repeat(64));assert.equal(f.button('Later').disabled,true);
 f.app.result({status:'permission_required'});assert.equal(f.button('Continue').disabled,false);f.app.result({status:'error',message:'Checksum mismatch'});assert.equal(f.button('Try again').disabled,false);assert.match(doc.querySelector('[data-isu-status]').textContent,/Checksum mismatch/);
 f.dom.window.close();
});
test('14-day deferral survives restart, suppresses later releases, and manual checks bypass it',async()=>{
 const f=fixture();await f.app.check();f.button('Later').click();assert.equal(f.dom.window.document.querySelector('[role=dialog]'),null);
 const restarted=U.create(f.config);f.catalogs.A=cat('A',[release('0.1.7',17)]);const calls=f.requests.length;
 assert.equal(await restarted.check(),false);assert.equal(f.requests.length,calls);
 assert.equal(await restarted.check({manual:true}),true);restarted.close();
 f.setTime(100000+U.TWO_WEEKS-1);assert.equal(await restarted.check(),false);
 f.setTime(100000+U.TWO_WEEKS+1);assert.equal(await restarted.check(),true);assert.ok(f.dom.window.document.querySelector('[role=dialog]'));
 f.dom.window.close();
});
test('same long-lived updater reminds after two weeks',async()=>{
 const f=fixture();await f.app.check();f.button('Later').click();f.setTime(100000+U.TWO_WEEKS+1);await f.app.check();assert.ok(f.button('Update'));f.dom.window.close();
});
test('settings exposes A/B, empty B stays empty and never falls back to A or latest',async()=>{
 const f=fixture();f.app.settings();f.button('Version B').click();await new Promise(r=>setTimeout(r,20));
 assert.equal(f.app.getState().channel,'B');assert.match(f.dom.window.document.body.textContent,/No releases on version B/);assert.ok(f.requests.every(x=>x.includes('B.json')));assert.ok(f.requests.every(x=>!x.includes('/releases/latest')));
 const restored=U.create(f.config);assert.equal(restored.getState().channel,'B');f.dom.window.close();
});
test('channel switch cannot display the old in-flight A result',async()=>{
 let resolveA;const f=fixture({fetch:async url=>({ok:true,json:async()=>url.includes('A.json')?await new Promise(r=>resolveA=r):url.includes('api.github.com')?{content:Buffer.from(JSON.stringify(cat('B',[]))).toString('base64')}:cat('B',[])})});
 const pending=f.app.check();await new Promise(r=>setTimeout(r,0));f.app.settings();f.button('Version B').click();resolveA(cat());await pending;await new Promise(r=>setTimeout(r,10));assert.equal(f.button('Update'),undefined);f.dom.window.close();
});
test('quiet host emits catalog; prechecked popup respects persistent snooze/channel',async()=>{
 const offers=[];const f=fixture({onOffer:v=>offers.push(v)});await f.app.check();assert.equal(offers.length,1);assert.equal(f.dom.window.document.querySelector('[role=dialog]'),null);
 assert.equal(f.app.offerPending(offers[0]),true);f.button('Later').click();assert.equal(f.app.offerPending(offers[0]),false);f.dom.window.close();
});
test('changelog content is text, not HTML',async()=>{const f=fixture();f.catalogs.A=cat('A',[release('0.1.6',16,'<img src=x onerror=alert(1)>')]);await f.app.check();assert.equal(f.dom.window.document.querySelector('img'),null);f.dom.window.close();});

test('B is the default and legacy implicit A migrates without losing snoozes',()=>{
 const f=fixture({defaultB:true}); assert.equal(f.app.getState().channel,'B');
 f.dom.window.localStorage.setItem('inhouse-services-updater:youtube',JSON.stringify({channel:'A',snooze:{A:123}}));
 assert.equal(f.app.getState().channel,'B');assert.equal(f.app.getState().snooze.A,123);f.dom.window.close();
});
test('A needs acknowledgement and completed slide; cancelling and partial slides keep B',async()=>{
 const f=fixture({defaultB:true});f.app.settings();f.button('Version A').click();
 assert.equal(f.requests.length,0);assert.equal(f.app.getState().channel,'B');assert.match(f.dom.window.document.body.textContent,/untested development updates/);
 f.button('Cancel').click();f.button('Version A').click();
 const slider=f.dom.window.document.querySelector('input');assert.equal(slider.parentElement.hidden,true);
 slider.value='100';slider.dispatchEvent(new f.dom.window.Event('change'));assert.equal(f.app.getState().channel,'B');
 f.button('I understand').click();slider.value='80';slider.dispatchEvent(new f.dom.window.Event('change'));assert.equal(f.app.getState().channel,'B');assert.equal(slider.value,'0');
 slider.value='100';slider.dispatchEvent(new f.dom.window.Event('change'));await new Promise(r=>setTimeout(r,20));
 assert.equal(f.app.getState().channel,'A');assert.equal(U.create(f.config).getState().developmentConsent,1);
 f.app.settings();f.button('Version B').click();await new Promise(r=>setTimeout(r,20));assert.equal(f.app.getState().developmentConsent,0);
 assert.equal(f.dom.window.document.querySelector('.isu-github').href,'https://github.com/'+repo);f.dom.window.close();
});

test('ready state leaves Later available and shows how to finish',async()=>{
 const f=fixture();await f.app.check();f.button('Update').click();
 const doc=f.dom.window.document;assert.equal(doc.querySelector('.isu-dock').dataset.state,'busy');
 f.app.result({status:'downloading',downloadedBytes:1000,totalBytes:2000});assert.equal(doc.querySelector('progress').value,50);
 f.app.result({status:'ready'});assert.equal(doc.querySelector('.isu-dock').dataset.state,'idle');assert.equal(f.button('Later').disabled,false);
 assert.equal(f.button('Installing…').disabled,true);assert.match(doc.querySelector('[data-isu-status]').textContent,/Confirm the installation/);f.dom.window.close();
});
test('tapping outside the sheet defers like Later, but never while downloading',async()=>{
 const f=fixture();await f.app.check();const doc=f.dom.window.document;
 f.button('Update').click();doc.querySelector('.isu-overlay').click();assert.ok(doc.querySelector('[role=dialog]'));
 f.app.result({status:'error',message:'Offline'});doc.querySelector('.isu-overlay').click();
 assert.equal(doc.querySelector('[role=dialog]'),null);assert.ok(f.app.getState().snooze.A>100000);f.dom.window.close();
});
test('offer links back to channel settings',async()=>{
 const f=fixture();await f.app.check();f.button('Details').click();f.button('Change channel').click();
 assert.equal(f.button('Version A').getAttribute('aria-pressed'),'true');assert.ok(f.button('Check for updates'));f.dom.window.close();
});
