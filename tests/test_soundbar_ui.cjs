// Browser regression checks use mocked APIs: no audio, downloads, LLM calls, or personal settings.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(__dirname, '../code-gossip');
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
const manifest = read('data/sounds.json');
const state = {
 ...read('configs/config.defaults.json'),
 effects_profiles: Object.fromEntries(Object.keys(manifest.effects).map(key => [key, {}])),
 narrator_styles: read('configs/narrator_styles.defaults.json'),
 narrator_providers: {claude_cli:{name:'Claude CLI',needs_key:false,default_model:'haiku'},openai:{name:'OpenAI',needs_key:true,default_model:'model'}},
 phrases: read('configs/phrases.defaults.json'), events: ['edit','subagent_start','subagent_stop','stop'],
 voices: [{name:'Tara',locale:'en_US'},{name:'Aman',locale:'en_US'},{name:'Samantha',locale:'en_US'}],
 kokoro_voices: [{id:'af_heart',name:'Heart'},{id:'af_bella',name:'Bella'},{id:'am_adam',name:'Adam'}],
 preview_catalog:Object.fromEntries(Object.entries(manifest).map(([layer,profiles])=>[layer,Object.fromEntries(Object.entries(profiles).map(([name,profile])=>[name,Object.fromEntries(Object.entries(profile.events).map(([event,spec])=>[event,(spec.sequence||spec.files?.map(file=>[file])||[[spec.file||'Synthesized cue']]).map(files=>files.join(' → '))]))]))])),
 setup:{effects:Object.fromEntries(Object.keys(manifest.effects).map(name=>[name,{ready:name!=='sci-fi',sox:name==='sci-fi',message:name==='sci-fi'?'Install SoX':'Ready',missing:[]}])),clips:Object.fromEntries(Object.keys(manifest.voice).map(name=>[name,{ready:true,message:'Ready'}])),say:true,kokoro:false},
};
state.phrases_defaults = structuredClone(state.phrases);
const server = http.createServer((req,res)=>{
 const file={'/':'ui.html','/ui.js':'ui.js'}[req.url];
 if(!file){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':'text/html');res.end(fs.readFileSync(path.join(root,'soundbar',file)));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[],writes=[],previews=[],checks=[],modelRequests=[];let saveGate=null,releaseSave;let modelGate=null,releaseModels,failModels=false;let failGeneration=false,failSave=false,failShutdown=true,installations=0,checkGate=null,releaseCheck,failCheck=false;
  let versionState={installed:'0.8.0',available:false,release:null,checked_at:1,development:false,running:false,phase:'idle',message:''},updateChecks=0,updateStarts=0,failUpdateCheck=false;
  page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.route('**/api/**',async route=>{
   const req=route.request(),endpoint=new URL(req.url()).pathname;
   let reply={ok:true};
   if(endpoint==='/api/status')reply=state;
   else if(endpoint==='/api/updates')reply=versionState;
   else if(endpoint==='/api/update-check'){assert.equal(req.headers()['x-soundbar-request'],'ui');updateChecks++;reply=failUpdateCheck?{ok:false,error:'GitHub is unavailable'}:versionState;}
   else if(endpoint==='/api/update'){assert.equal(req.headers()['x-soundbar-request'],'ui');updateStarts++;Object.assign(versionState,{running:true,phase:'downloading',message:'Downloading Code Gossip 0.9.0…'});reply=versionState;}
   else if(endpoint==='/api/setup')reply=state.setup;
   else if(endpoint==='/api/activate'||endpoint==='/api/save'){
    const body=req.postDataJSON();writes.push({endpoint,...body});if(saveGate)await saveGate;
    if(failSave)reply={ok:false,error:'Save failed'};
    else {
     Object.assign(state,body.config);
     if(endpoint==='/api/activate'){Object.assign(state,{effects_on:body.enabled&&body.mode==='effects',voice_on:body.enabled&&body.mode!=='effects',soundbar_mode:body.mode});if(body.mode!=='effects')state.voice_profile={clips:state.clips_profile,phrases:'senior',ai:'narrator'}[body.mode];}
     else if(body.mode==='clips' && manifest.voice[state.voice_profile])state.voice_profile=state.clips_profile;
     if(body.phrases)state.phrases=body.phrases;
    }
   }else if(endpoint==='/api/config') {const body=req.postDataJSON();writes.push(body);if(failSave)reply={ok:false,error:'Save failed'};else Object.assign(state,body);}
   else if(endpoint==='/api/draft-preview'){const body=req.postDataJSON();previews.push(body);reply=failGeneration&&body.action==='generate'?{ok:false,message:'Generation failed'}:{ok:true,text:'Preview result'};}
   else if(endpoint==='/api/narrator-models'){const body=req.postDataJSON();modelRequests.push(body);if(modelGate)await modelGate;reply=failModels?{ok:false,message:'Could not load models'}:body.config.narrator_provider==='claude_cli'?{ok:true,models:[],supported:false,message:'Claude CLI has no live model list.'}:{ok:true,models:['live-model-a','live-model-b'],supported:true};}
   else if(endpoint==='/api/draft-check'){checks.push(req.postDataJSON());if(checkGate)await checkGate;reply=failCheck?{ok:false,error:'Check failed'}:{ok:true,message:'Ready'};}
   else if(endpoint==='/api/kokoro-install'){installations++;state.setup.kokoro=true;state.setup.installing=false;state.setup.installStatus='done';reply={ok:true,status:'done'};}
   else if(endpoint==='/api/kokoro-status')reply={ok:true,status:'done',installed:state.setup.kokoro};
   else if(endpoint==='/api/shutdown'){assert.equal(req.headers()['x-soundbar-request'],'ui');reply={ok:!failShutdown};}
   else throw new Error('Unexpected endpoint: '+endpoint);
   await route.fulfill({json:reply});
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const ready = text => page.waitForFunction(value => document.getElementById('statusText').textContent === value, text);
  await page.waitForFunction(() => document.getElementById('statusText').textContent === 'In use · Effects · System sounds');
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Audio available');
  assert.equal(checks.length, 1, 'Only the visible Effects pack is checked on load');
  assert.equal(checks[0].mode, 'effects');
  assert.equal(await page.locator('#checkStatus-effects').evaluate(el => getComputedStyle(el).color), 'rgb(127, 211, 154)');
  assert.equal(await page.locator('#topicTips,.topic-tip').count(), 0);
  assert.equal(await page.locator('[role=tab]').count(), 4);
  assert.equal(await page.locator('#activateSelection').count(), 0, 'The mode already in use has no extra apply button');

  await page.locator('#settingsButton').click();
  await page.locator('[data-theme-choice=mint]').click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'mint');
  assert.equal(await page.evaluate(() => localStorage.getItem('code-gossip.soundbar-theme')), 'mint');
  await page.keyboard.press('Escape');
  await page.reload();
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Audio available');
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'mint');
  await page.locator('#settingsButton').click();
  await page.locator('[data-theme-choice=amber]').click();
  await page.keyboard.press('Escape');

  const beforeHelp = {writes:writes.length, previews:previews.length, checks:checks.length, models:modelRequests.length};
  await page.locator('#helpButton').click();
  assert.equal(await page.locator('#helpPopover').isVisible(), true);
  await page.locator('[data-guide=events]').click();
  assert.equal(await page.locator('#helpPopover').isVisible(), false);
  assert.deepEqual({writes:writes.length, previews:previews.length, checks:checks.length, models:modelRequests.length}, beforeHelp, 'Getting started does not save, play, or check');

  await page.locator('#packList label', {hasText:'Sci-fi'}).click();
  assert(await page.locator('#panel-effects [data-act=save]').isDisabled(), 'Saving the active pack must not bypass missing audio dependencies');
  const beforePackSample = previews.length;
  await page.getByRole('button', {name:'Play a System sounds sample', exact:true}).click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.length, beforePackSample + 1, 'A ready pack can be auditioned even when the selected pack is unavailable');
  assert.equal(previews.at(-1).config.effects_profile, 'default');
  await page.locator('#panel-effects [data-act=discard]').click();

  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.selectOption('#provider', 'openai');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai [data-act=discard]').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  assert.equal(await page.locator('#provider').inputValue(), 'claude_cli', 'Discard restores the visible provider as well as the request configuration');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.selectOption('#phraseEngine', 'kokoro');
  await page.locator('#closeDrawer').click();
  await page.locator('#tab-phrases').click();
  assert.equal(await page.locator('#phraseEngineLabel').innerText(), 'macOS speech', 'An AI engine draft must not change the Phrases draft');
  assert.equal(await page.locator('#badges-phrases .dirty-dot').count(), 0);
  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai [data-act=discard]').click();
  await page.locator('#tab-effects').click();

  // Hold the automatic setup check until a save error is visible, then let it run.
  await page.clock.install();
  await page.clock.pauseAt(new Date());
  await page.locator('#packList label', {hasText:'Paper'}).click();
  assert.equal(writes.filter(item => item.endpoint).length, 0, 'Choosing a pack stays a draft');
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave = true;
  await page.locator('#activateSelection').click();
  await page.getByText('Save failed', {exact:true}).waitFor();
  await page.clock.runFor(200);
  await page.locator('#checkStatus-effects').getByText('Audio available', {exact:true}).waitFor();
  assert.equal(await page.locator('#errorBanner').innerText(), 'Save failed', 'An automatic setup check must preserve a save error');
  await page.clock.resume();
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave = false;
  saveGate = new Promise(resolve => { releaseSave = resolve; });
  await page.locator('#activateSelection').click();
  assert.equal(await page.locator('#activateSelection').getAttribute('aria-busy'), 'true');
  assert.equal(await page.locator('#activationProgress').textContent(), 'Saving selection…');
  releaseSave(); saveGate = null;
  await page.waitForFunction(() => document.getElementById('statusText').textContent.endsWith('Paper'));
  assert.equal(writes.at(-1).endpoint, '/api/save', 'Saving the mode already in use does not switch channels');
  assert.equal(writes.at(-1).config.effects_profile, 'paper');
  assert.equal(state.soundbar_mode, 'effects');

  await page.locator('#effectsEvents button', {hasText:'Stop'}).first().click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.at(-1).event, 'stop');
  assert.equal(previews.at(-1).config.effects_profile, 'paper');
  assert(await page.locator('#previewMainAgent').isEnabled(), 'Speech preview controls recover after an effects preview');
  await page.locator('#packList label', {hasText:'Silent'}).click();
  assert.equal(await page.locator('#effectsEvents [data-preview]').count(), 0);
  await page.locator('#packList label', {hasText:'Paper'}).click();
  assert.equal(await page.locator('#activateSelection').count(), 0, 'Returning to the saved pack clears the draft');
  assert.equal(await page.locator('#statusText').innerText(), 'In use · Effects · Paper');

  await page.getByRole('tab', {name:'Phrases', exact:true}).click();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Engine available');
  await page.selectOption('#mainAgentVoice', 'Samantha');
  await page.selectOption('#subagentVoice', 'Aman');
  await page.locator('#phraseRows input').first().fill('Please investigate');
  await page.locator('#panel-phrases .strip [data-drawer=speech]').click();
  failCheck = true;
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('speechCheck').dataset.status === 'failed');
  assert.equal(await page.locator('#checkStatus-phrases').evaluate(el => getComputedStyle(el).color), 'rgb(242, 134, 122)');
  await page.locator('#closeDrawer').click();
  const blockedPreview = previews.length;
  await page.getByRole('button', {name:'Preview alternative 1', exact:true}).click();
  assert.equal(previews.length, blockedPreview, 'A failed speech check blocks phrase playback');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-phrases .strip [data-drawer=speech]').click();
  failCheck = false;
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Engine available');
  await page.locator('#closeDrawer').click();
  await page.getByRole('button', {name:'Preview alternative 1', exact:true}).click();
  assert.equal(previews.at(-1).variant, 0);
  await page.getByRole('button', {name:'Preview alternative 2', exact:true}).click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert(await page.locator('#previewMainAgent').isEnabled());
  assert(await page.locator('#previewSubagent').isEnabled());
  assert.equal(previews.at(-1).variant, 1);
  assert.equal(previews.at(-1).config.voice_main, 'Samantha');
  assert.equal(previews.at(-1).config.voice_sub, 'Aman');
  assert.equal(previews.at(-1).phrases.subagent_start[0][0], 'Please investigate');
  assert.equal(state.voice_on, false);
  await page.locator('#activateSelection').click();
  await ready('In use · Phrases · Senior');
  assert.equal(writes.at(-1).endpoint, '/api/activate');
  assert.equal(state.voice_main, 'Samantha');
  assert.equal(state.phrases.subagent_start[0][0], 'Please investigate');
  assert.equal(state.effects_on, false);
  assert.equal(state.voice_on, true);
  assert.equal(await page.locator('#badges-ai .dirty-dot').count(), 0, 'Saving a shared voice must not manufacture an AI draft');
  await page.reload();
  await page.locator('#tab-phrases[aria-selected=true]').waitFor();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Engine available');
  assert.equal(await page.locator('#mainAgentVoice').inputValue(), 'Samantha');

  const beforeAI = checks.length;
  await page.getByRole('tab', {name:/^AI commentary/}).click();
  await page.waitForFunction(() => document.getElementById('checkStatus-ai').textContent === 'CLI found');
  assert(checks.slice(beforeAI).some(check => check.scope === 'provider'), 'A free CLI check can run when AI commentary is opened');
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.selectOption('#provider', 'openai');
  assert.equal(await page.locator('#checkConnection').innerText(), 'Check connection');
  assert.equal(checks.at(-1).config.narrator_provider, 'claude_cli', 'Switching to a cloud provider does not check it');
  await page.locator('#sampleKey').fill('dummy-test-key');
  await page.locator('#model').fill('test-model');
  checkGate = new Promise(resolve => { releaseCheck = resolve; });
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkConnection').textContent === 'Connecting…');
  assert.equal(await page.locator('#checkStatus-ai').isHidden(), true);
  assert(await page.locator('#activateSelection').isDisabled());
  releaseCheck(); checkGate = null;
  await page.waitForFunction(() => document.getElementById('checkConnection').dataset.status === 'checked');
  await page.waitForFunction(() => document.querySelectorAll('#modelChoices option').length === 2);
  assert.equal(await page.locator('#model').inputValue(), 'test-model');
  assert.equal(modelRequests.at(-1).config.narrator_api_key, 'dummy-test-key');
  failModels = true;
  await page.locator('#refreshModels').click();
  await page.waitForFunction(() => document.getElementById('modelStatus').dataset.status === 'failed');
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  failModels = false;
  await page.locator('#refreshModels').click();
  await page.waitForFunction(() => document.querySelectorAll('#modelChoices option').length === 2);
  modelGate = new Promise(resolve => { releaseModels = resolve; });
  await page.locator('#refreshModels').click();
  await page.waitForFunction(() => document.getElementById('modelStatus').dataset.status === 'loading');
  await page.selectOption('#provider', 'claude_cli');
  releaseModels(); modelGate = null;
  await page.waitForFunction(() => document.getElementById('modelStatus').textContent.includes('Claude CLI'));
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  assert(await page.locator('#refreshModels').isDisabled());
  await page.selectOption('#provider', 'openai');
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  assert(await page.locator('#refreshModels').isDisabled());
  await page.locator('#sampleKey').fill('dummy-test-key');
  await page.locator('#model').fill('test-model');
  await page.waitForFunction(() => document.querySelectorAll('#modelChoices option').length === 2);
  await page.locator('#sampleKey').fill('replacement-key');
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  await page.locator('#sampleKey').fill('dummy-test-key');
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-ai').textContent === 'Connection verified');
  assert.equal(checks.at(-1).scope, 'provider');
  assert.equal(checks.at(-1).config.narrator_api_key, 'dummy-test-key');
  assert.equal(state.narrator_provider, 'claude_cli');
  await page.locator('#closeDrawer').click();

  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.selectOption('#phraseEngine', 'kokoro');
  assert(await page.locator('#kokoroInfo').isVisible());
  await page.locator('#kokoroInfo summary').click();
  assert((await page.locator('#kokoroInfo').innerText()).includes('~/.code-gossip/state/.venv'));
  assert((await page.locator('#kokoroInfo').innerText()).includes('10 minutes'));
  assert((await page.locator('#kokoroInfo').innerText()).includes('Hugging Face'));
  assert.equal(installations, 0);
  assert.equal(await page.locator('#engineStatus').innerText(), 'Not installed');
  assert.equal(await page.locator('#verificationRow').isHidden(), true);
  await page.locator('#installKokoro').click();
  await page.waitForFunction(() => document.getElementById('installKokoro').hidden);
  assert.equal(installations, 1);
  await page.selectOption('#speaker', 'af_bella');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkConnection').dataset.status === 'checked');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  failCheck = true;
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('speechCheck').dataset.status === 'failed');
  assert.equal(await page.locator('#checkStatus-ai').innerText(), 'Connection verified');
  assert.equal(await page.locator('#installKokoro').innerText(), 'Repair installation');
  assert.equal(checks.at(-1).scope, 'speech');
  failCheck = false;
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Engine available');
  await page.locator('#closeDrawer').click();

  failGeneration = true;
  const beforeFailedSample = previews.length;
  await page.locator('#sampleBtn').click();
  await page.getByText('Generation failed', {exact:true}).waitFor();
  assert.deepEqual(previews.slice(beforeFailedSample).map(request => request.action), ['generate']);
  assert.equal(await page.locator('#sampleLabel').innerText(), 'Play sample');
  failGeneration = false;
  const firstSample = previews.length;
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleLabel').textContent === 'Replay');
  assert.equal(await page.locator('#commentarySample').innerText(), 'Preview result');
  assert.deepEqual(previews.slice(firstSample).map(request => request.action), ['generate', 'play']);
  assert.equal(previews.at(-1).config.kokoro_voice, 'af_bella');
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleBtn').getAttribute('aria-busy') === 'false');
  assert.deepEqual(previews.slice(firstSample).map(request => request.action), ['generate', 'play', 'play']);

  await page.locator('#soundOn').uncheck();
  await page.waitForFunction(() => document.getElementById('powerLabel').textContent === 'Sound off');
  await page.locator('#activateSelection').click();
  await page.waitForFunction(() => document.getElementById('statusText').textContent.startsWith('Muted · AI commentary'));
  assert.equal(state.voice_on, false);
  assert.equal(state.effects_on, false);
  assert.equal(state.narrator_provider, 'openai');
  assert.equal(await page.locator('#sampleKey').inputValue(), '', 'A saved API key is no longer an unsaved edit');
  assert.equal(await page.locator('#badges-ai .dirty-dot').count(), 0);
  assert.equal(await page.locator('#checkStatus-ai').innerText(), 'Connection verified');
  assert.equal(await page.locator('#sampleLabel').innerText(), 'Replay', 'Saving a key preserves the generated sample');
  assert(await page.locator('#previewAIVoice').isEnabled());
  const beforeReload = checks.length;
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Engine available');
  assert.equal(checks.slice(beforeReload).some(check => check.scope === 'provider'), false, 'Reload does not repeat a cloud provider check');
  assert.equal(await page.locator('#soundOn').isChecked(), false);
  const beforeStyle = checks.length;
  await page.locator('#styleList label').nth(1).click();
  assert.equal(await page.locator('#activateSelection').innerText(), 'Save changes');
  assert(await page.locator('#activateSelection').isEnabled());
  assert.equal(checks.length, beforeStyle, 'A style edit does not check the provider');
  await page.locator('#activateSelection').click();
  await page.waitForFunction(() => document.getElementById('activateSelection') === null);
  await page.locator('#soundOn').check();
  await page.waitForFunction(() => document.getElementById('powerLabel').textContent === 'Sound on');
  assert.equal(state.voice_on, true);
  assert.equal(state.effects_on, false);

  await page.getByRole('tab', {name:/^Effects/}).click();
  await page.locator('#packList label', {hasText:'Sci-fi'}).click();
  assert(await page.locator('#activateSelection').isDisabled());
  const saveInactivePack = page.waitForResponse('**/api/save');
  await page.locator('#panel-effects [data-act=save]').click();
  await saveInactivePack;
  assert.equal(state.effects_profile, 'sci-fi', 'An unavailable inactive pack can still be saved for later');
  assert.equal(state.soundbar_mode, 'ai');
  assert((await page.locator('#panel-effects .state-issue').innerText()).includes('Install SoX'));
  await page.locator('#panel-effects .state-issue .link').click();
  assert(await page.locator('#soxCommand').isHidden(), true);
  await page.locator('#installSox').click();
  assert(await page.locator('#soxCommand').isVisible(), true);
  assert.equal(state.soundbar_mode, 'ai');
  await page.locator('#closeDrawer').click();

  await page.locator('#tab-ai').click();
  await page.locator('#tab-ai').press('ArrowLeft');
  assert.equal(await page.locator('#tab-phrases').getAttribute('aria-selected'), 'true');
  await page.setViewportSize({width:390, height:844});
  for (const name of ['Effects', 'Clips', 'Phrases', 'AI commentary']) {
   await page.getByRole('tab', {name:new RegExp('^' + name)}).click();
   assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No overflow in ' + name);
  }
  await page.setViewportSize({width:1280, height:900});
  await page.locator('#tab-effects').click();
  await page.locator('#packList label', {hasText:'Paper'}).click();
  const restorePack = page.waitForResponse('**/api/save');
  await page.locator('#panel-effects [data-act=save]').click();
  await restorePack;
  Object.assign(state, {effects_on:true, voice_on:true, voice_profile:'senior'});
  await page.reload();
  await page.waitForFunction(() => document.getElementById('statusText').textContent.includes(' + Phrases'));
  await page.locator('#tab-effects').click();
  await page.getByRole('button', {name:'Use Effects', exact:true}).click();
  await ready('In use · Effects · Paper');
  assert.equal(state.voice_on, false, 'Using an already-playing mode exits combined playback');
  assert.equal(writes.at(-1).endpoint, '/api/activate');
  Object.assign(state, {effects_on:false, voice_on:true, voice_profile:'narrator', soundbar_mode:'ai'});
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  await page.locator('#settingsButton').click();
  const preferenceSaved = page.waitForResponse('**/api/config');
  await page.locator('#approvalCues').uncheck();
  await preferenceSaved;
  assert.equal(state.codex_permission_sound_on, false);
  await page.keyboard.press('Escape');

  // A Clips collection is a draft until saved; saving it while AI is active keeps AI.
  await page.locator('#tab-clips').click();
  await page.locator('#clipList label', {hasText:'Empires'}).click();
  assert.equal(await page.locator('#clipTitle').innerText(), 'Empires');
  assert.equal(state.voice_profile, 'narrator');
  await page.locator('#clipsEvents [data-event=edit]').click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.at(-1).config.clips_profile, 'empires');
  assert.equal(previews.at(-1).variant, 0);
  await page.locator('#clipsEvents [data-event=edit]').click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.at(-1).variant, 1);
  await page.locator('#panel-clips [data-act=discard]').click();
  assert.equal(await page.locator('#clipTitle').innerText(), 'Generals');
  await page.locator('#clipList label', {hasText:'Empires'}).click();
  await page.locator('#panel-clips [data-act=save]').click();
  await page.waitForFunction(() => !document.querySelector('#panel-clips [data-act=save]'));
  assert.equal(state.clips_profile, 'empires');
  assert.equal(state.voice_profile, 'narrator');
  await page.reload();
  await page.locator('#tab-clips').click();
  assert.equal(await page.locator('#clipTitle').innerText(), 'Empires');
  await page.getByRole('button', {name:'Use Clips', exact:true}).click();
  await ready('In use · Clips · Empires');
  assert.equal(state.voice_profile, 'empires');
  await page.reload();
  await ready('In use · Clips · Empires');
  assert.equal(await page.locator('#tab-clips').getAttribute('aria-selected'), 'true');
  await page.locator('#clipList label', {hasText:'Generals'}).click();
  assert((await page.locator('#statusText').innerText()).endsWith('Empires'));
  await page.locator('#panel-clips [data-act=save]').click();
  await ready('In use · Clips · Generals');
  assert.equal(state.voice_profile, 'generals');
  Object.assign(state, {effects_on:false, voice_on:true, voice_profile:'narrator', soundbar_mode:'ai'});

  state.setup.installing = true; state.setup.kokoro = false; state.setup.installStatus = 'running'; state.setup.installMessage = 'Installing packages';
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installing…');
  assert.equal(await page.locator('#verificationRow').isHidden(), true);
  assert.equal(await page.locator('#installKokoro').isHidden(), true);
  await page.locator('#closeDrawer').click();
  await page.locator('#settingsButton').click();
  assert(await page.locator('#closeSoundbar').isDisabled());
  assert(await page.locator('#closeInstallHint').isVisible());
  await page.keyboard.press('Escape');
  state.setup.installing = false; state.setup.kokoro = false; state.setup.installStatus = 'error';
  state.setup.installMessage = 'Package installation failed: could not download dependencies. Check your network connection and retry installation.';
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installation failed');
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  assert.equal(await page.locator('#engineStatus').getAttribute('data-tone'), 'error');
  assert((await page.locator('#engineDetail').innerText()).includes('could not download'));
  assert.equal(await page.locator('#installKokoro').innerText(), 'Retry installation');
  const installsBeforeRetry = installations;
  await page.locator('#installKokoro').click();
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installed');
  assert.equal(installations, installsBeforeRetry + 1);
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Engine available');
  assert.equal(checks.at(-1).scope, 'speech');
  await page.locator('#closeDrawer').click();

  Object.assign(versionState, {available:true, release:{version:'0.9.0', notes_url:'https://github.com/zorhay/code-gossip/releases/tag/0.9.0'}});
  await page.evaluate(() => refreshVersions());
  assert((await page.locator('#versionNotice').innerText()).includes('0.8.0 → 0.9.0'));
  assert.equal(updateStarts, 0);
  await page.locator('#versionNotice').click();
  failUpdateCheck = true;
  await page.locator('#checkUpdates').click();
  await page.getByText('GitHub is unavailable', {exact:true}).waitFor();
  assert(await page.locator('#applyUpdate').isEnabled());
  failUpdateCheck = false;
  await page.locator('#checkUpdates').click();
  await page.waitForFunction(() => document.getElementById('checkUpdates').textContent === 'Check for updates');
  assert.equal(updateChecks, 2);
  await page.locator('#applyUpdate').click();
  await page.waitForFunction(() => document.getElementById('applyUpdate').textContent === 'Updating…');
  assert.equal(updateStarts, 1);
  assert(await page.locator('#closeSoundbar').isDisabled());
  Object.assign(versionState, {running:false, phase:'failed', message:'Update failed. Previous version restored.'});
  await page.evaluate(() => refreshVersions());
  assert.equal(await page.locator('#applyUpdate').innerText(), 'Retry update');
  Object.assign(versionState, {development:true});
  await page.evaluate(() => refreshVersions());
  assert.equal(await page.locator('#applyUpdate').isVisible(), false);
  assert((await page.locator('#updateExplanation').innerText()).startsWith('Development installation'));
  Object.assign(versionState, {development:false, available:false, phase:'done', message:'Updated successfully.'});
  await page.evaluate(() => refreshVersions());
  await page.keyboard.press('Escape');
  await page.locator('#settingsButton').click();
  await page.locator('#closeSoundbar').click();
  await page.getByText('Could not stop Soundbar', {exact:true}).waitFor();
  assert(await page.locator('#closeSoundbar').isEnabled());
  failShutdown = false;
  await page.locator('#closeSoundbar').click();
  await page.locator('#closedDialog[open]').waitFor();
  await page.keyboard.press('Escape');
  assert(await page.locator('#closedDialog').isVisible());
  assert.deepEqual(errors, []);
  console.log('Soundbar UI passed: compact layout, save versus use, themes, draft checks, previews, models, Kokoro, mute, updates, shutdown.');
 }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);server.closeAllConnections();server.close();process.exitCode=1;});
