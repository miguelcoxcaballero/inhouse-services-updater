const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const { webcrypto } = require('node:crypto');
function setup(extra = {}) {
  const values = new Map();
  const storage = { getItem:k=>values.get(k)||null, setItem:(k,v)=>values.set(k,v), removeItem:k=>values.delete(k) };
  const context = { crypto:webcrypto, URLSearchParams, TextEncoder, Uint8Array, AbortController, btoa,
    setTimeout, clearTimeout, localStorage:storage, ...extra };
  vm.createContext(context); vm.runInContext(fs.readFileSync('auth/google-oauth.js','utf8'),context);
  return { context, storage, create:options=>context.InhouseGoogleOAuth.create({ clientId:'web-client', scope:'drive', ...options }) };
}
const tick = () => new Promise(resolve=>setTimeout(resolve,20));
test('PKCE binds callback to random state, rejects forgery and consumes once', async () => {
  let url, exchanges=0;
  const env=setup({ fetch:async (_url, options)=>{
    exchanges++; const body=new URLSearchParams(options.body);
    assert.equal(body.get('grant_type'),'authorization_code'); assert.ok(body.get('code_verifier').length>=43);
    return {ok:true,json:async()=>({access_token:'token',scope:'drive',expires_in:3600,refresh_token:'refresh'})};
  }});
  const client=env.create({androidClientId:'android',redirectUri:'example:/callback',openAuthUrl:value=>url=new URL(value)});
  const request=client.request(true);await tick();
  assert.equal(url.searchParams.get('code_challenge_method'),'S256');
  assert.equal(await client.handleCallback('state=forged&code=code'),false);assert.equal(exchanges,0);
  await client.handleCallback('state='+url.searchParams.get('state')+'&code=code');
  assert.equal((await request).access_token,'token');assert.equal(exchanges,1);
  assert.equal(await client.handleCallback('state='+url.searchParams.get('state')+'&code=code'),false);
});
test('closing session during code exchange cannot resurrect a grant', async () => {
  let url, respond;
  const env=setup({fetch:()=>new Promise(resolve=>respond=resolve)});
  const client=env.create({androidClientId:'android',redirectUri:'example:/callback',openAuthUrl:value=>url=new URL(value)});
  const request=client.request(true); const rejected=assert.rejects(request,/cancelled/); await tick();
  const callback=client.handleCallback('state='+url.searchParams.get('state')+'&code=code');
  client.signOut(); respond({ok:true,json:async()=>({access_token:'late',scope:'drive',expires_in:3600})});
  await assert.rejects(callback,/cancelled/);await rejected;assert.equal(client.session(),null);
});
test('concurrent web requests share a popup and reject missing scopes', async () => {
  let options, count=0;
  const env=setup({google:{accounts:{oauth2:{initTokenClient:value=>{options=value;return {requestAccessToken(){count++}}}}}}});
  const client=env.create();const first=client.request(true);const second=client.request(true);
  assert.equal(first,second);assert.equal(count,1);
  options.callback({access_token:'token',scope:'other',expires_in:3600});await assert.rejects(first,/permissions/);
  assert.equal(client.session(),null);
});
test('new Android installation refreshes with the originating client, not its own client ID', async () => {
  let requestedClient;
  const shared={access_token:'expired',refresh_token:'shared-refresh',client_id:'notes-client',scope:'drive',expiresAt:1,updatedAt:1,email:'test@example.com'};
  let bridge;
  const env=setup({fetch:async (_url,options)=>{
    requestedClient=new URLSearchParams(options.body).get('client_id');
    return {ok:true,json:async()=>({access_token:'new',scope:'drive',expires_in:3600})};
  }});
  bridge={postMessage(raw){const msg=JSON.parse(raw);queueMicrotask(()=>bridge.onmessage({data:JSON.stringify({id:msg.id,session:msg.method==='read'?shared:null})}));}};
  env.context.InhouseOAuthNative=bridge;
  const client=env.create({androidClientId:'read-client',openAuthUrl:()=>assert.fail('must not open Google')});
  assert.equal((await client.request(false)).access_token,'new');assert.equal(requestedClient,'notes-client');
  assert.equal(client.session().refresh_token,'shared-refresh');assert.equal(client.session().client_id,'notes-client');
});
test('local logout persists and does not silently reimport another app session', async () => {
  const env=setup();let called=0;
  env.context.InhouseOAuthNative={postMessage(){called++}};
  env.storage.setItem('inhouse-google-session-v1:signed-out','1');
  const client=env.create();await assert.rejects(client.request(false),/cancelled/);assert.equal(called,0);
});
test('temporary refresh failures preserve the grant; invalid_grant clears it', async () => {
  let error='temporarily_unavailable';
  const env=setup({fetch:async()=>({ok:false,json:async()=>({error})})});
  env.storage.setItem('inhouse-google-session-v1',JSON.stringify({refresh_token:'refresh',client_id:'original',scope:'drive',expiresAt:1}));
  const client=env.create({androidClientId:'android',openAuthUrl:()=>{}});
  await assert.rejects(client.request(false));assert.equal(client.session().refresh_token,'refresh');
  error='invalid_grant';await assert.rejects(client.request(false));assert.equal(client.session(),null);
});
test('concurrent first-install requests wait for discovery instead of opening Google', async () => {
  let readRequest, opened=0;
  const env=setup();const bridge={postMessage(raw){readRequest=JSON.parse(raw)}};
  env.context.InhouseOAuthNative=bridge;
  const client=env.create({androidClientId:'read',openAuthUrl:()=>opened++});
  const first=client.request(false), second=client.request(true);
  bridge.onmessage({data:JSON.stringify({id:readRequest.id,session:{access_token:'shared',scope:'drive',expiresAt:Date.now()+3600000,updatedAt:1}})});
  assert.equal((await first).access_token,'shared');assert.equal((await second).access_token,'shared');assert.equal(opened,0);
});
test('a new account without a refresh token never borrows an old account refresh token', async () => {
  const env=setup({fetch:()=>assert.fail('must not renew the wrong account')});
  env.storage.setItem('legacy-refresh','old-account-refresh');
  env.storage.setItem('inhouse-google-session-v1',JSON.stringify({access_token:'expired',expiresAt:1,scope:'drive',client_id:'different',email:'new@example.com'}));
  const client=env.create({androidClientId:'android',refreshKey:'legacy-refresh',openAuthUrl:()=>{}});
  await assert.rejects(client.request(false),/required/);
});
test('legacy Paellas routing prefix remains bound to fresh random state', async () => {
  let url;
  const env=setup();const client=env.create({statePrefix:'android.',redirectUri:'https://paellas.net',openAuthUrl:value=>url=new URL(value)});
  const request=client.request(true);const rejected=assert.rejects(request,/cancelled/);await tick();
  assert.match(url.searchParams.get('state'),/^android\.[A-Za-z0-9_-]{43}$/);client.cancel();await rejected;
});
