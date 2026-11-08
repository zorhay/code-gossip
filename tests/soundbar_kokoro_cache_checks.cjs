// Exercises the real shared UI with an isolated, stateful Kokoro transport.
const assert = require('node:assert/strict');

module.exports = async function checkKokoroCache(browser, url, fixture) {
 for (const [theme, width] of [['amber',1280], ['mint',390]]) {
  const page = await browser.newPage({viewport:{width,height:900}});
  const saved = structuredClone(fixture);
  Object.assign(saved, {tts_engine:'kokoro', kokoro_voice:'af_heart', kokoro_voice_sub:'am_adam', narrator_provider:'codex_cli'});
  Object.assign(saved.setup, {kokoro:true, installStatus:'done'});
  saved.kokoro_voices.push({id:'af_nicole',name:'Nicole'}, {id:'af_sarah',name:'Sarah'});
  const loaded = new Set(['af_heart','am_adam','af_bella']);
  const failed = new Set(), checks = [], writes = [], previews = [], errors = [], held = new Map();
  let installs = 0, setupRequests = 0;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
   const endpoint = new URL(route.request().url()).pathname;
   const body = route.request().method() === 'POST' ? route.request().postDataJSON() : null;
   let reply = {ok:true};
   if (endpoint === '/api/status') reply = saved;
   else if (endpoint === '/api/setup') { setupRequests++; reply = saved.setup; }
   else if (endpoint === '/api/updates') reply = {installed:'development',development:true};
   else if (endpoint === '/api/narrator-models') reply = {ok:true,models:[],supported:false};
   else if (endpoint === '/api/config') { writes.push(body); Object.assign(saved, body); }
   else if (endpoint === '/api/kokoro-install') { installs++; reply = {ok:true,status:'done'}; }
   else if (endpoint === '/api/draft-preview') { previews.push(body); reply = {ok:true,text:'Sample'}; }
   else if (endpoint === '/api/draft-check') {
    if (body.scope === 'speech') {
     checks.push(body);
     const voices = body.mode === 'phrases' ? [body.config.kokoro_voice,body.config.kokoro_voice_sub] : [body.config.kokoro_voice];
     const ready = voices.every(voice => loaded.has(voice));
     const failure = voices.some(voice => failed.has(voice));
     reply = {ok:ready,pending:!ready && !failure,message:ready ? 'Ready' : failure ? 'Voice unavailable' : 'Downloading voice',
      model:{ready,state:ready ? 'ready' : failure ? 'error' : 'downloading',voices:[...loaded],
       ...(!ready && !failure ? {file:'voices/'+voices[0]+'.pt',completed:250000,total:1000000} : {})}};
     // Capture the old response before waiting, to expose stale-response races.
     const hold = held.get(voices[0]);
     if (hold) { held.delete(voices[0]); hold.started(); await hold.gate; }
    }
   } else throw new Error('Unexpected cache-test endpoint: '+endpoint);
   await route.fulfill({json:reply});
  });
  const hold = voice => {
   let release, started;
   const gate = new Promise(resolve => { release=resolve; });
   const request = new Promise(resolve => { started=resolve; });
   held.set(voice,{gate,started});
   return {release,request};
  };
  const speechReady = mode => page.waitForFunction(mode => document.getElementById('checkStatus-'+mode).textContent==='Ready',mode);
  const idle = () => page.waitForFunction(() => !savingAISettings && [...kokoroChecks.values()].every(check=>!check.requesting));
  const openSpeech = async mode => {
   if (await page.locator('#drawer').isVisible()) await page.locator('#closeDrawer').click();
   await page.locator('#tab-'+mode).click();
   await page.locator('#panel-'+mode+' .strip [data-drawer=speech]').click();
  };
  try {
   await page.goto(url);
   await speechReady('phrases'); await speechReady('aiSpeech'); await idle();
   assert.equal(checks.filter(check=>check.config.kokoro_voice==='af_heart').length,1,'Both sections share the in-flight initial main-voice check');
   await page.evaluate(theme=>applyTheme(theme),theme);
   await page.clock.install();
   await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+1000)));
   await page.evaluate(() => {
    window.cacheFlashes=[];
    window.cacheObserver=new MutationObserver(() => {
     for (const node of document.querySelectorAll('[data-status-for],.activation-notice')) {
      if (/Checking|Not checked|Check the speech engine/.test(node.textContent)) cacheFlashes.push(node.textContent);
     }
    });
    cacheObserver.observe(document.querySelector('main'),{subtree:true,childList:true,characterData:true});
   });
   const initial = checks.length;
   await openSpeech('ai');
   await page.selectOption('#speaker','af_bella');
   await idle(); await speechReady('aiSpeech');
   await openSpeech('phrases');
   await page.locator('#closeDrawer').click();
   await page.selectOption('#mainAgentVoice','am_adam');
   await page.selectOption('#subagentVoice','af_bella');
   await speechReady('phrases');
   const phrase = page.locator('#phraseRows input').first();
   await phrase.fill('Keep this unsaved phrase');
   await page.locator('#previewMainAgent').click();
   await page.waitForFunction(()=>!mediaBusy);
   assert.equal(previews.at(-1).config.kokoro_voice,'am_adam');
   assert.equal(checks.length,initial,'Loaded voices can change roles and sections without rechecking');
   assert.deepEqual(await page.evaluate(()=>{cacheObserver.disconnect();return cacheFlashes;}),[],'Ready voice switches never flash a setup prompt');

   // A new voice starts preparation once. Both sections join it; phrase drafts
   // remain local even when AI autosaves the same voice.
   const pending = hold('af_nicole');
   await page.selectOption('#mainAgentVoice','af_nicole');
   await pending.request;
   assert(await page.locator('#previewMainAgent').isDisabled());
   await openSpeech('ai');
   await page.selectOption('#speaker','af_nicole');
   await page.waitForFunction(()=>!savingAISettings);
   assert(await page.locator('#previewAIVoice').isDisabled());
   assert.equal(checks.filter(check=>check.config.kokoro_voice==='af_nicole').length,1);
   assert(writes.every(write=>!('phrases' in write)),'Readiness and AI autosaves do not save phrase content');
   pending.release();
   await idle();
   await page.waitForFunction(()=>document.getElementById('modelDownloadDetails').textContent.includes('af_nicole.pt'));
   assert.equal(await page.locator('#modelDownloadProgress').getAttribute('value'),'250000');

   // A late failure for a previously selected voice must not spoil the new
   // selection. Returning to the failed voice shares its cached retry state.
   await page.selectOption('#speaker','af_heart');
   await page.waitForFunction(()=>!savingAISettings);
   await openSpeech('phrases'); await page.locator('#closeDrawer').click();
   await page.selectOption('#mainAgentVoice','af_heart');
   failed.add('af_nicole');
   await page.clock.runFor(2500); await idle();
   await speechReady('phrases'); await speechReady('aiSpeech');
   assert.equal(await page.locator('#errorBanner').innerText(),'');
   assert.equal(await phrase.inputValue(),'Keep this unsaved phrase');
   const failedCount = checks.length;
   await openSpeech('ai'); await page.selectOption('#speaker','af_nicole');
   await idle();
   assert.equal(await page.locator('#checkStatus-aiSpeech').innerText(),'Load failed');
   await openSpeech('phrases');
   assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Load failed');
   await page.clock.runFor(30000);
   assert.equal(checks.length,failedCount,'Failures do not poll or retry when switching sections');
   loaded.add('af_nicole'); failed.delete('af_nicole');
   await page.locator('#speechCheck').click();
   await speechReady('phrases'); await speechReady('aiSpeech'); await idle();
   assert.deepEqual(checks.slice(failedCount).map(check=>[check.config.kokoro_voice,check.retry]),[['af_nicole',true]],'Retry targets only the failed voice, preserving the ready partner');
   await page.locator('#closeDrawer').click();
   await page.locator('#previewMainAgent').click();
   await page.waitForFunction(()=>!mediaBusy);
   assert.equal(previews.at(-1).config.kokoro_voice,'af_nicole');
   assert.equal(await phrase.inputValue(),'Keep this unsaved phrase');

   // Explicit checks share pending work too, including the setup refresh.
   await openSpeech('ai');
   const explicit = hold('af_nicole'), beforeExplicit = checks.length, beforeSetup = setupRequests;
   await page.evaluate(()=>{checkSetup('aiSpeech');checkSetup('aiSpeech');});
   await explicit.request;
   assert.equal(checks.length,beforeExplicit+1);
   assert.equal(setupRequests,beforeSetup+1);
   explicit.release(); await idle();

   // Repair must discard old readiness, including responses already in flight.
   await openSpeech('ai');
   loaded.add('af_sarah');
   const old = hold('af_sarah');
   await page.selectOption('#speaker','af_sarah'); await old.request;
   await page.waitForFunction(()=>!savingAISettings);
   loaded.delete('af_sarah');
   await page.evaluate(()=>installKokoro());
   assert.equal(installs,1);
   await idle();
   assert(await page.locator('#previewAIVoice').isDisabled());
   old.release();
   await page.clock.runFor(250);
   assert(await page.locator('#previewAIVoice').isDisabled(),'An old success cannot resurrect readiness after repair');
   loaded.add('af_sarah');
   await page.clock.runFor(2500); await speechReady('aiSpeech'); await idle();
   const complete = checks.length;
   await page.clock.runFor(30000);
   assert.equal(checks.length,complete,'Ready voices stop polling');
   await page.clock.resume();
   page.on('dialog',dialog=>dialog.accept());
   await page.reload(); await speechReady('aiSpeech'); await speechReady('phrases'); await idle();
   assert(checks.length>complete,'Page reload revalidates local readiness');
   assert.deepEqual(errors,[]);
  } finally { await page.close(); }
 }
 console.log('Kokoro cache passed: shared voices, preparation, failures, retry, repair, reload, and drafts in both themes/layouts.');
};
