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
 narrator_providers: {codex_cli:{name:'Codex CLI',needs_key:false,default_model:''},claude_cli:{name:'Claude CLI',needs_key:false,default_model:'haiku'},openai:{name:'OpenAI',needs_key:true,default_model:'model'}},
 phrases: read('configs/phrases.defaults.json'), events: ['session_start','read','edit','test','subagent_start','subagent_stop','stop'],
 voices: [{name:'Tara',locale:'en_US'},{name:'Aman',locale:'en_US'},{name:'Samantha',locale:'en_US'}],
 kokoro_voices: [{id:'af_heart',name:'Heart'},{id:'af_bella',name:'Bella'},{id:'am_adam',name:'Adam'}],
 preview_catalog:Object.fromEntries(Object.entries(manifest).map(([layer,profiles])=>[layer,Object.fromEntries(Object.entries(profiles).map(([name,profile])=>[name,Object.fromEntries(Object.entries(profile.events).map(([event,spec])=>[event,(spec.sequence||spec.files?.map(file=>[file])||[[spec.file||'Synthesized cue']]).map(files=>files.join(' → '))]))]))])),
 setup:{effects:Object.fromEntries(Object.keys(manifest.effects).map(name=>[name,{ready:name!=='sci-fi',sox:name==='sci-fi',message:name==='sci-fi'?'Install SoX':'Ready',missing:[]}])),clips:{generals:{ready:true,message:'Ready'}},say:true,kokoro:false},
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
  await require('./soundbar_kokoro_cache_checks.cjs')(browser, `http://127.0.0.1:${server.address().port}`, state);
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[],writes=[],previews=[],checks=[],modelRequests=[];let saveGate=null,releaseSave;let modelGate=null,releaseModels,failModels=false;let failGeneration=false,failSave=false,failShutdown=true,installations=0,checkGate=null,releaseCheck,failCheck=false;
  let configGate=null,releaseConfig,checkError='Check failed',modelState={ok:true,message:'Kokoro model and selected voices are ready.',model:{state:'ready',ready:true,voices:['af_heart','af_bella','am_adam']}};
  let setupRequests=0, statusRequests=0, checkStarted=null;
  let previewGate=null,releasePreview,previewStarted=null,generationGate=null,releaseGeneration,failPreview=false;
  let versionState={installed:'0.8.0',available:false,release:null,checked_at:1,development:false,running:false,phase:'idle',message:''},updateChecks=0,updateStarts=0,failUpdateCheck=false;
  page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.route('**/api/**',async route=>{
   const req=route.request(),endpoint=new URL(req.url()).pathname;
   let reply={ok:true};
   if(endpoint==='/api/status'){statusRequests++;reply=state;}
   else if(endpoint==='/api/updates')reply=versionState;
   else if(endpoint==='/api/update-check'){assert.equal(req.headers()['x-soundbar-request'],'ui');updateChecks++;reply=failUpdateCheck?{ok:false,error:'GitHub is unavailable'}:versionState;}
   else if(endpoint==='/api/update'){assert.equal(req.headers()['x-soundbar-request'],'ui');updateStarts++;Object.assign(versionState,{running:true,phase:'downloading',message:'Downloading Code Gossip 0.9.0…'});reply=versionState;}
   else if(endpoint==='/api/setup'){setupRequests++;reply=state.setup;}
   else if(endpoint==='/api/activate'||endpoint==='/api/save'){
    const body=req.postDataJSON();writes.push({endpoint,...body});if(saveGate)await saveGate;
    if(failSave)reply={ok:false,error:'Save failed'};
    else {
     Object.assign(state,body.config);
     if(endpoint==='/api/activate'){Object.assign(state,{effects_on:body.enabled&&body.mode==='effects',voice_on:body.enabled&&body.mode!=='effects',soundbar_mode:body.mode});if(body.mode!=='effects')state.voice_profile={clips:'generals',phrases:'senior',ai:'narrator'}[body.mode];}
     if(body.phrases)state.phrases=body.phrases;
    }
   }else if(endpoint==='/api/config') {const body=req.postDataJSON();writes.push(body);if(configGate)await configGate;if(failSave)reply={ok:false,error:'Save failed'};else Object.assign(state,body);}
   else if(endpoint==='/api/draft-preview'){const body=req.postDataJSON();previews.push(body);previewStarted?.(body);if(body.action==='generate'&&generationGate)await generationGate;else if(previewGate)await previewGate;reply=failPreview?{ok:false,message:'Playback failed'}:failGeneration&&body.action==='generate'?{ok:false,message:'Generation failed'}:{ok:true,text:'Preview result'};}
   else if(endpoint==='/api/narrator-models'){const body=req.postDataJSON();modelRequests.push(body);if(modelGate)await modelGate;reply=failModels?{ok:false,message:'Could not load models'}:['claude_cli','codex_cli'].includes(body.config.narrator_provider)?{ok:true,models:[],supported:false,message:(body.config.narrator_provider==='codex_cli'?'Codex CLI':'Claude CLI')+' has no live model list.'}:{ok:true,models:['live-model-a','live-model-b'],supported:true};}
   else if(endpoint==='/api/draft-check'){const body=req.postDataJSON();checks.push(body);checkStarted?.();if(checkGate)await checkGate;reply=failCheck?{ok:false,message:checkError}:body.scope==='speech' && body.config.tts_engine==='kokoro'?modelState:{ok:true,message:'Ready'};}
   else if(endpoint==='/api/kokoro-install'){installations++;state.setup.kokoro=true;state.setup.installing=false;state.setup.installStatus='done';reply={ok:true,status:'done'};}
   else if(endpoint==='/api/kokoro-status')reply={ok:true,status:'done',installed:state.setup.kokoro};
   else if(endpoint==='/api/shutdown'){assert.equal(req.headers()['x-soundbar-request'],'ui');reply={ok:!failShutdown};}
   else throw new Error('Unexpected endpoint: '+endpoint);
   await route.fulfill({json:reply});
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const settingsIdle = () => page.waitForFunction(() => document.getElementById('activationProgress').textContent !== 'Saving settings…');
  const ready = text => page.waitForFunction(value => document.getElementById('statusText').textContent === value, text);
  await page.waitForFunction(() => document.getElementById('statusText').textContent === 'In use · Effects · System sounds');
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Ready');
  await page.waitForFunction(() => ['phrases','aiSpeech','ai'].every(key => cachedCheck(key)?.status === 'checked'));
  assert.equal(checks.length, 3, 'Load checks both speech configurations and the local provider once');
  assert(checks.every(check => ['phrases','ai'].includes(check.mode)), 'Audio uses the readiness snapshot already included in status');
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
  await page.waitForFunction(() => ['phrases','aiSpeech','ai'].every(key => cachedCheck(key)?.status === 'checked'));
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'mint');
  await page.locator('#settingsButton').click();
  await page.locator('[data-theme-choice=amber]').click();
  await page.keyboard.press('Escape');
  await require('./soundbar_settings_checks.cjs')(page);

  // Readiness belongs to this page, including sections and packs not visited yet.
  assert.equal(statusRequests,2,'Reload fetches a fresh setup snapshot');
  assert.equal(checks.length,6,'Reload repeats initial speech/local-provider checks exactly once');
  await page.clock.install();
  await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+1000)));
  const cachedRequests={checks:checks.length,setup:setupRequests};
  await page.evaluate(() => {
   window.readinessFlashes=[];
   window.readinessObserver=new MutationObserver(() => {
    for(const node of document.querySelectorAll('[data-status-for],.activation-notice')) {
     if (/Checking|Connecting/.test(node.textContent)) readinessFlashes.push(node.textContent);
    }
   });
   readinessObserver.observe(document.querySelector('main'),{subtree:true,childList:true,characterData:true});
  });
  for (const theme of ['mint','amber']) for (const width of [390,1280]) {
   await page.setViewportSize({width,height:900});
   await page.locator('#settingsButton').click();
   await page.locator(`[data-theme-choice=${theme}]`).click();
   await page.keyboard.press('Escape');
   for(const mode of ['effects','clips','phrases','ai','effects']) {
    await page.locator('#tab-'+mode).click();
    const selector={effects:'#packList input',clips:'#filters-clips button',phrases:'#evList button',ai:'#styleList input'}[mode];
    for(const control of await page.locator(selector).all()) {
     await control.evaluate(node=>node.click());
     await page.clock.runFor(250);
    }
   }
  }
  await page.clock.runFor(30000);
  assert.deepEqual({checks:checks.length,setup:setupRequests},cachedRequests,'Browsing every section and profile never rechecks cached readiness');
  assert.deepEqual(await page.evaluate(()=>{readinessObserver.disconnect();return readinessFlashes;}),[],'Browsing produces no transient Checking status');
  await page.locator('#packList input[value="default"]').evaluate(node=>node.click());
  await page.evaluate(()=>{state.phraseEvent='subagent_start';state.style=saved.narrator_style;render();});
  await page.clock.resume();

  await page.locator('#tab-phrases').click();
  const originalVoice=await page.locator('#mainAgentVoice').inputValue();
  await page.selectOption('#mainAgentVoice','Samantha');
  assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Not checked','New voice settings do not inherit a different configuration’s readiness');
  const beforeVoiceCheck=checks.length;
  checkGate=new Promise(resolve=>{releaseCheck=resolve;});
  const voiceRequest=new Promise(resolve=>{checkStarted=resolve;});
  const pendingVoiceIdentity=await page.evaluate(()=>{const id=checkIdentity('phrases');checkSetup('phrases');checkSetup('phrases');return id;});
  await voiceRequest;checkStarted=null;
  assert.equal(checks.length,beforeVoiceCheck+1,'Concurrent checks for the same configuration share one request');
  await page.selectOption('#mainAgentVoice',originalVoice);
  assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Ready','Returning to a checked configuration restores its cached result immediately');
  failCheck=true;
  releaseCheck();checkGate=null;
  await page.waitForFunction(identity=>cachedCheck('phrases',identity)?.status==='failed',pendingVoiceIdentity);
  failCheck=false;
  assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Ready','A late failure cannot overwrite the current configuration');
  assert.equal(await page.locator('#errorBanner').innerText(),'','A late failure from another selection does not show a current error');
  await page.selectOption('#mainAgentVoice','Samantha');
  assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Check failed','Failures are cached too');
  await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+1000)));
  await page.clock.runFor(30000);
  assert.equal(checks.length,beforeVoiceCheck+1,'Returning to a failed configuration does not retry automatically');
  await page.clock.resume();
  await page.evaluate(()=>checkSetup('phrases'));
  assert.equal(checks.length,beforeVoiceCheck+2,'Explicit Check retries a cached failure');
  await page.locator('#panel-phrases [data-act=discard]').click();
  assert.equal(await page.locator('#checkStatus-phrases').innerText(),'Ready');
  await page.locator('#tab-effects').click();

  const beforeHelp = {writes:writes.length, previews:previews.length, checks:checks.length, models:modelRequests.length};
  await page.locator('#helpButton').click();
  assert.equal(await page.locator('#helpPopover').isVisible(), true);
  assert.equal(await page.locator('[data-guide=events] small').innerText(), 'Preview any sound. Use applies your selection.');
  await page.locator('[data-guide=events]').click();
  assert.equal(await page.locator('#helpPopover').isVisible(), false);
  assert.deepEqual({writes:writes.length, previews:previews.length, checks:checks.length, models:modelRequests.length}, beforeHelp, 'Getting started does not save, play, or check');

  await page.locator('#packList label', {hasText:'Sci-fi'}).click();
  assert(await page.locator('#panel-effects .panel-head [data-act=use]').isDisabled(), 'Applying a pack must not bypass missing audio dependencies');
  assert.equal(await page.locator('#panel-effects [data-act=save],#panel-effects [data-act=discard]').count(),0,'Browsing packs is not content editing');
  const beforePackSample = previews.length;
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.getByRole('button', {name:'Play a System sounds sample', exact:true}).click();
  const packPreview=page.getByRole('button', {name:'Play a System sounds sample', exact:true});
  assert.equal(await packPreview.locator('use').getAttribute('href'), '#i-wave');
  assert(await packPreview.locator('svg').isVisible());
  await page.locator('#tab-clips').click();
  assert.equal(await page.locator('[data-preview]:not(:disabled)').count(), 0);
  await page.locator('#tab-effects').click();
  assert.equal(await packPreview.locator('use').getAttribute('href'), '#i-wave', 'Playback indicator survives a rerender');
  releasePreview(); previewGate=null;
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(await packPreview.locator('use').getAttribute('href'), '#i-play');
  assert.equal(previews.length, beforePackSample + 1, 'Leaving a profile session cancels its remaining cues');
  assert.equal(previews.at(-1).config.effects_profile, 'default');
  await page.locator('#packList label', {hasText:'System sounds'}).click();

  // Profile playback follows the Pages session, using only existing controls.
  const sessionEvents=read('../docs/demo-commentary.json').events;
  await page.evaluate(()=>{cursors['effects:paper:session_start']=1;});
  const sessionStatus=await page.locator('#statusText').innerText(), sessionWrites=writes.length;
  for (const [theme,width] of [['amber',1280],['mint',390]]) {
   await page.evaluate(theme=>applyTheme(theme),theme);
   await page.setViewportSize({width,height:900});
   await page.locator('#filters-effects [data-filter="effects:Work"]').click();
   let finishCue;
   for (const [index,event] of sessionEvents.entries()) {
    const started=new Promise(resolve=>{previewStarted=resolve;});
    previewGate=new Promise(resolve=>{releasePreview=resolve;});
    if (!index) await page.getByRole('button',{name:'Play a Paper sample',exact:true}).click();
    else finishCue();
    const request=await started;
    finishCue=releasePreview;
    assert.equal(request.event,event);
    assert.equal(request.config.effects_profile,'paper');
    assert.equal(await page.locator('#effectsEvents .is-playing .ev-sound').innerText(),state.preview_catalog.effects.paper[event][0],'Session labels describe the actual first alternative');
    assert.equal(await page.locator('#packList input:checked').inputValue(),'paper');
    assert.equal(await page.locator('#filters-effects [aria-pressed=true]').innerText(),'All');
    assert.deepEqual(await page.locator('#effectsEvents .is-playing').evaluateAll(nodes=>nodes.map(node=>node.dataset.event)),[event]);
    assert.equal(await page.getByRole('button',{name:'Play a Paper sample',exact:true}).locator('use').getAttribute('href'),'#i-wave');
    await page.evaluate(()=>render());
    assert.equal(await page.locator('#effectsEvents .is-playing').getAttribute('data-event'),event,'Rerenders preserve the current session cue');
    assert.equal(await page.locator('#statusText').innerText(),sessionStatus,'Auditioning never activates a pack');
   }
   previewStarted=null;previewGate=null;finishCue();
   await page.waitForFunction(()=>!mediaBusy);
   assert.equal(await page.locator('[data-preview].is-playing').count(),0);
   assert.equal(await page.locator('#demoSession,#demoStop,#demoProgress').count(),0,'Installed Soundbar gains no session UI');
  }
  assert.equal(writes.length,sessionWrites,'Profile sessions do not save settings');
  await page.setViewportSize({width:1280,height:900});
  await page.evaluate(()=>applyTheme('amber'));
  const sparseStart=previews.length;
  await page.getByRole('button',{name:'Play a Attention sample',exact:true}).click();
  await page.waitForFunction(()=>!mediaBusy);
  assert.deepEqual(previews.slice(sparseStart).map(request=>request.event),['stop'],'Sparse packs skip unmapped session events');
  failPreview=true;
  const failedSession=previews.length;
  await page.getByRole('button',{name:'Play a Paper sample',exact:true}).click();
  await page.waitForFunction(()=>!mediaBusy);
  assert.equal(previews.length,failedSession+1,'A failed cue stops the session');
  assert.equal(await page.locator('[data-preview].is-playing').count(),0,'Failure clears all session highlights');
  failPreview=false;
  await page.evaluate(()=>clearError());
  await page.locator('#packList input[value="default"]').evaluate(node=>node.click());

  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.selectOption('#provider', 'openai');
  await settingsIdle();
  assert.equal(state.narrator_provider, 'openai', 'Provider selection saves immediately');
  assert.equal(state.soundbar_mode, 'effects', 'Saving provider settings does not activate AI');
  assert.equal(await page.locator('#panel-ai [data-act=discard]').count(), 0);
  failSave=true;
  await page.selectOption('#provider', 'claude_cli');
  await settingsIdle();
  assert.equal(await page.locator('#provider').inputValue(), 'openai', 'A failed save restores the selected provider');
  assert.equal(state.narrator_provider, 'openai');
  await page.getByText('Save failed', {exact:true}).waitFor();
  failSave=false;
  configGate=new Promise(resolve=>{releaseConfig=resolve;});
  const beforeQueued=writes.length;
  await page.selectOption('#provider', 'claude_cli');
  await page.selectOption('#provider', 'openai');
  await page.selectOption('#provider', 'claude_cli');
  assert.equal(writes.length,beforeQueued+1,'Rapid setting writes are serialized');
  releaseConfig(); configGate=null;
  await settingsIdle();
  assert.equal(state.narrator_provider, 'claude_cli', 'The last provider selection wins');
  assert.equal(await page.locator('#provider').inputValue(), 'claude_cli');
  await page.locator('#closeDrawer').click();

  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  for (const [id, field, intermediate, latest] of [
   ['phraseEngine', 'tts_engine', 'kokoro', 'say'],
   ['speaker', 'voice_main', 'Samantha', 'Tara'],
  ]) {
   configGate=new Promise(resolve=>{releaseConfig=resolve;});
   const firstRequest=page.waitForRequest(req=>new URL(req.url()).pathname==='/api/config');
   await page.selectOption('#'+id, intermediate);
   await firstRequest;
   await page.selectOption('#'+id, latest);
   const releaseFirst=releaseConfig;
   configGate=new Promise(resolve=>{releaseConfig=resolve;});
   const secondRequest=page.waitForRequest(req=>new URL(req.url()).pathname==='/api/config');
   releaseFirst();
   await secondRequest;
   assert.equal(state[field], intermediate, 'The older request completed while the newer save is pending');
   assert.equal(await page.locator('#'+id).inputValue(), latest, 'An older save must not replace the latest speech selection');
   if (id==='speaker') {
    assert.equal(await page.locator('#phraseRows .row-head .inputs > span').first().textContent(), 'Main agent · Samantha', 'Shared voice labels still follow saved settings');
    assert.equal(await page.locator('#phraseRows input').first().getAttribute('aria-label'), 'Main agent · Samantha 1');
   }
   releaseConfig(); configGate=null;
   await settingsIdle();
   assert.equal(state[field], latest, 'The latest speech selection is persisted');
   assert.equal(await page.locator('#'+id).inputValue(), latest);
  }
  await page.locator('#closeDrawer').click();

  for (const saveFails of [false, true]) {
   await page.locator('#tab-ai').click();
   await page.locator('#panel-ai .strip [data-drawer=provider]').click();
   configGate=new Promise(resolve=>{releaseConfig=resolve;});
   const pendingRequest=page.waitForRequest(req=>new URL(req.url()).pathname==='/api/config');
   await page.selectOption('#provider', state.narrator_provider==='claude_cli' ? 'openai' : 'claude_cli');
   await pendingRequest;
   await page.locator('#closeDrawer').click();
   await page.locator('#tab-phrases').click();
   await page.waitForFunction(()=>document.getElementById('checkStatus-phrases').textContent==='Ready');
   checkGate=new Promise(resolve=>{releaseCheck=resolve;});
   const pendingCheck=page.waitForRequest(req=>new URL(req.url()).pathname==='/api/draft-check' && req.postDataJSON().mode==='phrases');
   await page.selectOption('#mainAgentVoice', saveFails ? 'Aman' : 'Samantha');
   await page.evaluate(() => { checkSetup('phrases'); });
   await pendingCheck;
   const phraseInput=page.locator('#phraseRows input').first();
   await phraseInput.fill('Draft phrase');
   await phraseInput.evaluate(input=>input.setSelectionRange(0,5));
   failSave=saveFails;
   releaseConfig(); configGate=null;
   await settingsIdle();
   failSave=false;
   assert.deepEqual(await phraseInput.evaluate(input=>({focused:document.activeElement===input,start:input.selectionStart,end:input.selectionEnd})),
    {focused:true,start:0,end:5}, 'A completed or failed autosave preserves phrase focus and selection');
   releaseCheck(); checkGate=null;
   await page.waitForFunction(()=>document.getElementById('checkStatus-phrases').textContent==='Ready');
   assert.deepEqual(await phraseInput.evaluate(input=>({focused:document.activeElement===input,start:input.selectionStart,end:input.selectionEnd})),
    {focused:true,start:0,end:5}, 'The follow-up setup check also preserves phrase focus and selection');
   await page.keyboard.type('New');
   assert.equal(await phraseInput.inputValue(), 'New phrase', 'Typing continues at the selected text after an autosave');
   await page.locator('#panel-phrases [data-act=discard]').click();
  }
  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.selectOption('#provider', 'claude_cli');
  await settingsIdle();
  await page.locator('#closeDrawer').click();
  await page.locator('#tab-phrases').click();
  await page.locator('#phraseRows input').first().fill('Keep this phrase draft');
  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.selectOption('#phraseEngine', 'kokoro');
  await settingsIdle();
  assert.equal(state.tts_engine, 'kokoro', 'Speech engine selection saves immediately, even before installation');
  assert.equal(state.phrases.subagent_start[0][0], 'Look into this', 'Saving speech settings does not save phrase edits');
  await page.locator('#closeDrawer').click();
  await page.locator('#tab-phrases').click();
  assert.equal(await page.locator('#phraseEngineLabel').innerText(), 'Kokoro', 'Untouched shared engine settings follow the saved value');
  assert.equal(await page.locator('#phraseRows input').first().inputValue(), 'Keep this phrase draft');
  await page.locator('#panel-phrases [data-act=discard]').click();
  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  failSave=true;
  await page.selectOption('#phraseEngine', 'say');
  await settingsIdle();
  assert.equal(await page.locator('#phraseEngine').inputValue(), 'kokoro', 'A failed engine save restores the selected engine');
  failSave=false;
  await page.selectOption('#phraseEngine', 'say');
  await settingsIdle();
  assert.equal(state.tts_engine, 'say');
  await page.locator('#closeDrawer').click();
  await page.reload();
  await page.locator('#tab-effects[aria-selected=true]').waitFor();
  assert.equal(await page.locator('#provider').inputValue(), 'claude_cli', 'Immediate provider settings survive reload');
  assert.equal(await page.locator('#phraseEngine').inputValue(), 'say', 'Immediate speech settings survive reload');

  // Browsing cached audio must not start a check or erase an activation error.
  await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+1000)));
  await page.locator('#packList label', {hasText:'Paper'}).click();
  assert.equal(writes.filter(item => item.endpoint).length, 0, 'Browsing a pack does not apply it');
  assert.equal(await page.locator('#panel-effects .panel-head .pill.success').count(),0,'The newly selected pack is not marked In use');
  assert.equal(await page.locator('#panel-effects .panel-head [data-act=use]').textContent(),'Use profile');
  assert.equal(await page.locator('#panel-effects [data-act=save],#panel-effects [data-act=discard],#badges-effects .dirty-dot').count(),0);
  assert((await page.locator('#packList .list-row').filter({hasText:'System sounds'}).innerText()).includes('In use'));
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave = true;
  await page.locator('#activateSelection').click();
  await page.getByText('Save failed', {exact:true}).waitFor();
  await page.clock.runFor(200);
  await page.locator('#checkStatus-effects').getByText('Ready', {exact:true}).waitFor();
  assert.equal(await page.locator('#errorBanner').innerText(), 'Save failed', 'Cached readiness preserves a save error');
  await page.clock.resume();
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave = false;
  saveGate = new Promise(resolve => { releaseSave = resolve; });
  await page.locator('#activateSelection').click();
  assert.equal(await page.locator('#activateSelection').getAttribute('aria-busy'), 'true');
  assert.equal(await page.locator('#activationProgress').textContent(), 'Saving selection…');
  for (const id of ['provider','model','sampleKey','phraseEngine','speaker']) assert(await page.locator('#'+id).isDisabled(), 'Settings cannot race an explicit mode save');
  releaseSave(); saveGate = null;
  await page.waitForFunction(() => document.getElementById('statusText').textContent.endsWith('Paper'));
  assert.equal(writes.at(-1).endpoint, '/api/activate', 'A different pack applies through Use even when Effects is already active');
  assert.equal(writes.at(-1).config.effects_profile, 'paper');
  assert.equal(state.soundbar_mode, 'effects');
  assert.equal(await page.locator('#panel-effects .panel-head .pill.success').textContent(),'In use');
  assert.equal(await page.locator('#panel-effects .panel-head [data-act=use]').count(),0);
  await page.reload();
  await page.locator('#tab-effects[aria-selected=true]').waitFor();
  assert.equal(await page.locator('#statusText').textContent(),'In use · Effects · Paper','Applied pack survives reload');
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Ready');

  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#effectsEvents button', {hasText:'Stop'}).first().click();
  assert.equal(await page.locator('#effectsEvents .is-playing use').getAttribute('href'), '#i-wave');
  releasePreview(); previewGate=null;
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.at(-1).event, 'stop');
  assert.equal(previews.at(-1).config.effects_profile, 'paper');
  assert(await page.locator('#previewMainAgent').isEnabled(), 'Speech preview controls recover after an effects preview');
  const beforeBrowsing=writes.length;
  await page.locator('#packList label', {hasText:'Silent'}).click();
  assert.equal(await page.locator('#effectsEvents [data-preview]').count(), 0);
  await page.locator('#packList label', {hasText:'Paper'}).click();
  assert.equal(await page.locator('#activateSelection').count(), 0, 'Returning to the active pack restores In use');
  assert.equal(writes.length,beforeBrowsing,'Browsing away and back does not write settings');
  assert.equal(await page.locator('#statusText').textContent(), 'In use · Effects · Paper');

  await page.getByRole('tab', {name:'Phrases', exact:true}).click();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Ready');
  await page.selectOption('#mainAgentVoice', 'Samantha');
  await page.selectOption('#subagentVoice', 'Aman');
  await page.locator('#phraseRows input').first().fill('Please investigate');
  assert.equal(await page.locator('.panel-head [data-act=save],.panel-head [data-act=discard]').count(), 0, 'Draft actions stay outside the activation header');
  assert(await page.locator('[data-draft-actions=phrases] [data-act=save]').isVisible());
  assert(await page.locator('[data-draft-actions=phrases] [data-act=discard]').isVisible());
  assert.equal(await page.locator('#panel-phrases .panel-head [data-act=use]').innerText(), 'Use profile');
  const editorBottom = await page.locator('#phraseRows').evaluate(el => el.closest('.pane-body').getBoundingClientRect().bottom);
  const actionsTop = await page.locator('[data-draft-actions=phrases]').evaluate(el => el.getBoundingClientRect().top);
  assert(actionsTop >= editorBottom, 'Phrase draft actions appear below the editor');

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
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Ready');
  await page.locator('#closeDrawer').click();
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.getByRole('button', {name:'Preview alternative 1', exact:true}).click();
  assert.equal(await page.locator('#phraseRows .is-playing use').getAttribute('href'), '#i-wave');
  releasePreview(); previewGate=null;
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.equal(previews.at(-1).variant, 0);
  await page.getByRole('button', {name:'Preview alternative 2', exact:true}).click();
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert(await page.locator('#previewMainAgent').isEnabled());
  assert(await page.locator('#previewSubagent').isEnabled());
  assert.equal(previews.at(-1).variant, 1);
  assert.equal(previews.at(-1).config.voice_main, 'Samantha');
  assert.equal(previews.at(-1).config.voice_sub, 'Aman');
  assert.equal(previews.at(-1).phrases.subagent_start[0][0], 'Please investigate');

  for (const id of ['previewMainAgent','previewSubagent']) {
   previewGate=new Promise(resolve=>{releasePreview=resolve;});
   await page.locator('#'+id).click();
   assert.equal(await page.locator('#'+id+' use').getAttribute('href'), '#i-wave');
   assert(await page.locator('#'+id+' svg').isVisible());
   releasePreview(); previewGate=null;
   await page.waitForFunction(id => document.getElementById(id).getAttribute('aria-busy')==='false',id);
   assert.equal(await page.locator('#'+id+' use').getAttribute('href'), '#i-play');
  }
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
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Ready');
  assert.equal(await page.locator('#mainAgentVoice').inputValue(), 'Samantha');

  const beforePhraseBrowse = writes.length;
  await page.locator('#evList button').last().click();
  assert.equal(await page.locator('#panel-phrases [data-act=save],#panel-phrases [data-act=discard]').count(), 0, 'Event browsing is not editing');
  assert.equal(writes.length, beforePhraseBrowse);
  const phraseInput = page.locator('#phraseRows input').first();
  await phraseInput.fill('Edited active phrase');
  assert.equal(await page.locator('#panel-phrases .panel-head .pill.success').innerText(), 'In use');
  assert.equal(await page.locator('#activateSelection').count(), 0, 'Save never acts as an activation control');
  await page.locator('#panel-phrases [data-act=save]').click();
  await page.waitForFunction(() => document.querySelector('#panel-phrases [data-act=save]') === null);
  assert.equal(writes.at(-1).endpoint, '/api/save');
  assert.equal(state.soundbar_mode, 'phrases');
  await page.locator('#tab-clips').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-clips').textContent === 'Ready');
  assert.equal(await page.locator('#panel-clips [data-act=save],#panel-clips [data-act=discard]').count(), 0);
  await page.getByRole('button', {name:'Use profile', exact:true}).click();
  await ready('In use · Clips · Generals');
  assert.equal(writes.at(-1).endpoint, '/api/activate');
  assert.equal(await page.locator('#panel-clips .panel-head .pill.success').innerText(), 'In use');
  await page.locator('#tab-phrases').click();
  await page.getByRole('button', {name:'Use profile', exact:true}).click();
  await ready('In use · Phrases · Senior');

  const beforeAI = checks.length;
  await page.getByRole('tab', {name:/^AI commentary/}).click();
  await page.waitForFunction(() => document.getElementById('checkStatus-ai').textContent === 'Detected');
  assert.equal(checks.length, beforeAI, 'Opening AI commentary uses the provider result from page load');
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.selectOption('#provider', 'openai');
  await settingsIdle();
  assert.equal(await page.locator('#checkConnection').innerText(), 'Check connection');
  assert.equal(checks.length, beforeAI, 'Switching to a cloud provider does not check it');
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
  const checkedProviderRequests=checks.length;
  await page.locator('#model').fill('another-model');
  assert.equal(await page.locator('#checkStatus-ai').innerText(),'Not checked');
  await page.locator('#model').fill('test-model');
  assert.equal(await page.locator('#checkStatus-ai').innerText(),'Connected','Returning to the checked provider/model/key restores its cached result');
  assert.equal(checks.length,checkedProviderRequests);
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
  await settingsIdle();
  releaseModels(); modelGate = null;
  await page.waitForFunction(() => document.getElementById('modelStatus').textContent.includes('Claude CLI'));
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  assert(await page.locator('#refreshModels').isDisabled());
  await page.selectOption('#provider', 'codex_cli');
  await settingsIdle();
  await page.waitForFunction(() => document.getElementById('modelStatus').textContent.includes('Codex CLI'));
  assert.equal(await page.locator('#checkStatus-ai').innerText(), 'Not checked');
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-ai').textContent === 'Detected');
  assert.equal(await page.locator('#checkConnection').textContent(), 'Check CLI');
  assert.equal(state.narrator_provider, 'codex_cli');
  assert.equal(state.narrator_api_key, '');
  assert(await page.locator('#refreshModels').isDisabled());
  assert.equal(checks.at(-1).config.narrator_provider, 'codex_cli');

  await page.selectOption('#provider', 'openai');
  await settingsIdle();
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  assert(await page.locator('#refreshModels').isDisabled());
  await page.locator('#sampleKey').fill('dummy-test-key');
  await page.locator('#model').fill('test-model');
  await page.waitForFunction(() => document.querySelectorAll('#modelChoices option').length === 2);
  await page.locator('#sampleKey').fill('replacement-key');
  assert.equal(await page.locator('#modelChoices option').count(), 0);
  await page.locator('#sampleKey').fill('dummy-test-key');
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-ai').textContent === 'Connected');
  assert.equal(checks.at(-1).scope, 'provider');
  assert.equal(checks.at(-1).config.narrator_api_key, 'dummy-test-key');
  await settingsIdle();
  assert.equal(state.narrator_provider, 'openai');
  assert.equal(state.narrator_model, 'test-model');
  assert.equal(state.narrator_api_key, 'dummy-test-key');
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
  modelState={ok:false,pending:true,message:'Downloading Kokoro model',model:{state:'downloading',ready:false,file:'kokoro-v1_0.pth',completed:0,total:327000000,transferred:12000000}};
  await page.locator('#installKokoro').click();
  await page.waitForFunction(() => document.getElementById('installKokoro').hidden);
  assert.equal(installations, 1);
  await page.waitForFunction(() => document.getElementById('modelDownloadDetails').textContent.includes('12.0 MB received'));
  assert(await page.locator('#sampleBtn').isDisabled(), 'AI previews wait for the model');
  assert(await page.locator('#previewAIVoice').isDisabled());
  assert.equal(await page.locator('#modelDownloadProgress').getAttribute('value'), '0', 'Received Xet bytes are not treated as reconstructed model bytes');
  checkGate=new Promise(resolve=>{releaseCheck=resolve;});
  await new Promise(resolve=>{checkStarted=resolve;});
  checkStarted=null;
  assert.equal(await page.locator('#checkStatus-aiSpeech').innerText(),'Downloading…','Progress polling retains its current status while the request runs');
  assert(await page.locator('#checkStatus-aiSpeech').isVisible());
  assert.equal(await page.locator('#speechCheck').innerText(),'Check','Automatic progress polling never flashes Checking');
  releaseCheck();checkGate=null;
  await page.waitForFunction(()=>[...setupChecks.values(),...kokoroChecks.values()].every(check=>!check.requesting));
  const beforeModelPreview=previews.length;
  await page.reload();
  await page.locator('#tab-phrases').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent==='Downloading…');
  assert(await page.locator('#previewMainAgent').isDisabled());
  assert(await page.locator('#previewSubagent').isDisabled());
  assert(await page.locator('#phraseRows [data-preview]').first().isDisabled());
  const loadingPhrase=page.locator('#phraseRows input').first();
  const originalPhrase=await loadingPhrase.inputValue();
  await loadingPhrase.fill('Keep typing while downloading');
  await loadingPhrase.evaluate(input=>input.setSelectionRange(5,11));
  modelState.model.completed=100000000;modelState.model.transferred=150000000;
  await page.waitForFunction(() => document.getElementById('modelDownloadDetails').textContent.includes('150.0 MB received'));
  assert.deepEqual(await loadingPhrase.evaluate(input=>[document.activeElement===input,input.selectionStart,input.selectionEnd]),[true,5,11]);
  assert.equal(await loadingPhrase.inputValue(),'Keep typing while downloading');
  assert.equal(previews.length,beforeModelPreview,'Polling never starts audio');
  modelState={ok:false,pending:false,message:'Kokoro model download failed. Retry model loading.',model:{state:'error',ready:false}};
  await page.waitForFunction(() => document.getElementById('speechCheck').textContent==='Retry model loading');
  await page.locator('#panel-phrases .strip [data-drawer=speech]').click();
  assert(await page.locator('#installKokoro').isHidden(), 'A failed model download does not request package reinstallation');
  assert(await page.locator('#previewMainAgent').isDisabled());
  modelState={ok:false,pending:true,message:'Downloading voice',model:{state:'downloading',ready:false,file:'voices/am_adam.pt',completed:250000,total:null}};
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('modelDownloadDetails').textContent.includes('voices/am_adam.pt'));
  assert.equal(checks.at(-1).retry,true,'Model retry is explicit');
  assert.equal(await page.locator('#modelDownloadProgress').getAttribute('value'),null,'Unknown size uses indeterminate progress');
  modelState={ok:true,message:'Kokoro model and selected voices are ready.',model:{state:'ready',ready:true,voices:['af_heart','af_bella','am_adam']}};
  await page.waitForFunction(() => !document.getElementById('previewMainAgent').disabled);
  assert(await page.locator('#modelDownloadProgress').isHidden());
  assert(await page.locator('#phraseRows [data-preview]').first().isEnabled());
  await page.waitForFunction(()=>[...setupChecks.values(),...kokoroChecks.values()].every(check=>!check.requesting && check.status!=='loading'));
  const afterModelReady=checks.length;
  await page.clock.pauseAt(new Date(await page.evaluate(()=>Date.now()+1000)));
  await page.clock.runFor(30000);
  assert.equal(checks.length,afterModelReady,'Kokoro stops polling after readiness or failure');
  await page.clock.resume();
  await page.locator('#closeDrawer').click();
  await loadingPhrase.fill(originalPhrase);
  await page.locator('#tab-ai').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => !document.getElementById('previewAIVoice').disabled);
  await page.selectOption('#speaker', 'af_bella');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkConnection').dataset.status === 'checked');
  await page.locator('#closeDrawer').click();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  failCheck = true; checkError='Kokoro daemon could not load the voice model.';
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('speechCheck').dataset.status === 'failed');
  assert.equal(await page.locator('#checkStatus-ai').innerText(), 'Connected');
  assert.equal(await page.locator('#installKokoro').innerText(), 'Repair installation');
  assert((await page.locator('#panel-ai .panel-head .state-issue').innerText()).includes(checkError));
  assert.equal(await page.locator('#panel-ai .panel-head [data-drawer=speech]').count(),0,'Speech errors show information instead of a duplicate Details button');
  assert.equal(await page.locator('#panel-ai .strip [data-drawer=speech]').count(),1);

  assert.equal(checks.at(-1).scope, 'speech');
  failCheck = false;
  await page.locator('#speechCheck').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Ready');
  await page.locator('#closeDrawer').click();

  failGeneration = true;
  const beforeFailedSample = previews.length;
  await page.locator('#sampleBtn').click();
  await page.getByText('Generation failed', {exact:true}).waitFor();
  assert.deepEqual(previews.slice(beforeFailedSample).map(request => request.action), ['generate']);
  assert.equal(await page.locator('#sampleLabel').innerText(), 'Play sample');
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'), '#i-play');
  failGeneration = false;
  const firstSample = previews.length;
  generationGate=new Promise(resolve=>{releaseGeneration=resolve;});
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#sampleBtn').click();
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'), '#i-reset');
  assert.equal(await page.locator('#sampleLabel').innerText(), 'Generating…');
  releaseGeneration(); generationGate=null;
  await page.waitForFunction(() => document.getElementById('sampleLabel').textContent==='Playing…');
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'), '#i-wave');
  assert(await page.locator('#sampleBtn svg').isVisible());
  releasePreview(); previewGate=null;
  await page.waitForFunction(() => document.getElementById('sampleLabel').textContent === 'Replay');
  assert.equal(await page.locator('#commentarySample').innerText(), 'Preview result');
  assert.deepEqual(previews.slice(firstSample).map(request => request.action), ['generate', 'play']);
  assert.equal(previews.at(-1).config.kokoro_voice, 'af_bella');
  await page.evaluate(()=>{window.replayLabels=[];window.replayObserver=new MutationObserver(()=>replayLabels.push(document.getElementById('sampleLabel').textContent));replayObserver.observe(document.getElementById('sampleLabel'),{childList:true,subtree:true,characterData:true});});
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleBtn').getAttribute('aria-busy') === 'false');
  assert.equal(await page.evaluate(()=>{replayObserver.disconnect();return replayLabels.includes('Generating…');}),false,'Cached replay never flashes a generation status');
  assert.deepEqual(previews.slice(firstSample).map(request => request.action), ['generate', 'play', 'play']);
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'), '#i-play');
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  failPreview=true;
  await page.locator('#previewAIVoice').click();
  assert.equal(await page.locator('#previewAIVoice use').getAttribute('href'), '#i-wave');
  assert(await page.locator('#previewAIVoice svg').isVisible());
  releasePreview(); previewGate=null;
  await page.getByText('Playback failed', {exact:true}).waitFor();
  assert.equal(await page.locator('#previewAIVoice use').getAttribute('href'), '#i-play');
  assert(await page.locator('#previewAIVoice').isEnabled());
  assert.equal(await page.locator('[data-preview].is-playing').count(), 0);
  failPreview=false;


  const controlLayout = () => page.locator('.now,.controls,.power,.volume,.controls .divider,#settingsButton,#helpButton,#tabs,.panel:not([hidden]) .workspace').evaluateAll(elements => elements.map(el => {
   const {x,y,width,height}=el.getBoundingClientRect();
   return {name:el.id || el.className,x,y,width,height};
  }));
  for (const width of [1280,900,390]) {
   await page.setViewportSize({width,height:900});
   const before=await controlLayout();
   await page.locator('#soundOn').uncheck();
   await page.waitForFunction(() => document.getElementById('powerLabel').textContent==='Sound off' && !document.getElementById('soundOn').disabled);
   assert.deepEqual(await controlLayout(),before,`Muting does not move or resize panels at ${width}px`);
   await page.locator('#soundOn').check();
   await page.waitForFunction(() => document.getElementById('powerLabel').textContent==='Sound on' && !document.getElementById('soundOn').disabled);
   assert.deepEqual(await controlLayout(),before,`Unmuting does not move or resize panels at ${width}px`);
  }
  await page.setViewportSize({width:1280,height:900});

  await page.locator('#soundOn').uncheck();
  await page.waitForFunction(() => document.getElementById('powerLabel').textContent === 'Sound off');
  await page.locator('#activateSelection').click();
  await page.waitForFunction(() => document.getElementById('statusText').textContent.startsWith('Muted · AI commentary'));
  assert.equal(state.voice_on, false);
  assert.equal(state.effects_on, false);
  assert.equal(state.narrator_provider, 'openai');
  assert.equal(await page.locator('#sampleKey').inputValue(), '', 'A saved API key is no longer an unsaved edit');
  assert.equal(await page.locator('#badges-ai .dirty-dot').count(), 0);
  assert.equal(await page.locator('#checkStatus-ai').innerText(), 'Connected');
  assert.equal(await page.locator('#sampleLabel').innerText(), 'Replay', 'Saving a key preserves the generated sample');
  assert(await page.locator('#previewAIVoice').isEnabled());
  const beforeReload = checks.length;
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Ready');
  assert.equal(checks.slice(beforeReload).some(check => check.scope === 'provider'), false, 'Reload does not repeat a cloud provider check');
  assert.equal(await page.locator('#soundOn').isChecked(), false);
  const beforeStyle = checks.length, beforeStyleWrites = writes.length;
  const activeStyle = state.narrator_style, activeStatus = await page.locator('#statusText').innerText();
  const otherStyle = await page.locator('#styleList input').nth(1).getAttribute('value');
  await page.locator('#styleList label').nth(1).click();
  assert.equal(await page.locator('#activateSelection').innerText(), 'Use profile');
  assert(await page.locator('#activateSelection').isDisabled(), 'Applying a style requires provider readiness after reload');
  assert.equal(await page.locator('#panel-ai .panel-head .pill.success').count(), 0);
  assert.equal(await page.locator('#panel-ai [data-act=save],#panel-ai [data-act=discard],#badges-ai .dirty-dot').count(), 0);
  assert.equal(checks.length, beforeStyle, 'Browsing a style does not check the provider');
  assert.equal(writes.length, beforeStyleWrites, 'Browsing a style does not save or activate it');
  assert.equal(await page.locator('#statusText').innerText(), activeStatus);
  assert.equal(await page.locator(`#styleList input[value="${activeStyle}"]`).locator('..').locator('.pill').innerText(), 'In use');
  await page.locator(`#styleList input[value="${activeStyle}"]`).locator('..').click();
  assert.equal(await page.locator('#panel-ai .panel-head .pill.success').innerText(), 'In use');
  assert.equal(await page.locator('#activateSelection').count(), 0);
  await page.locator('#styleList label').nth(1).click();
  await page.locator('#panel-ai .strip [data-drawer=provider]').click();
  await page.locator('#checkConnection').click();
  await page.waitForFunction(() => document.getElementById('checkConnection').dataset.status === 'checked');
  await page.locator('#closeDrawer').click();
  assert(await page.locator('#activateSelection').isEnabled());
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleBtn').getAttribute('aria-busy') === 'false');
  assert.equal(previews.at(-1).config.narrator_style, otherStyle, 'Preview uses the browsed style');
  assert.equal(state.narrator_style, activeStyle, 'Preview preserves the active style');

  const originalContext = state.narrator_deep_context;
  await page.locator('#sessionContext').setChecked(!originalContext);
  await page.locator('#panel-ai [data-act=discard]').click();
  assert.equal(await page.locator('#sessionContext').isChecked(), originalContext);
  assert.equal(await page.locator('#styleList input:checked').inputValue(), otherStyle, 'Discard only reverts edits, not browsing');
  await page.locator('#sessionContext').setChecked(!originalContext);
  failSave = true;
  await page.locator('#panel-ai [data-act=save]').click();
  await page.getByText('Save failed', {exact:true}).waitFor();
  assert.equal(state.narrator_deep_context, originalContext);
  assert.equal(state.narrator_style, activeStyle);
  failSave = false;
  await page.locator('#panel-ai [data-act=save]').click();
  await page.waitForFunction(() => document.querySelector('#panel-ai [data-act=save]') === null);
  assert.equal(writes.at(-1).endpoint, '/api/save');
  assert.equal(Object.hasOwn(writes.at(-1).config, 'narrator_style'), false, 'Saving settings must not apply the browsed style');
  assert.equal(state.narrator_deep_context, !originalContext);
  assert.equal(state.narrator_style, activeStyle);
  assert.equal(await page.locator('#statusText').innerText(), activeStatus);
  assert.equal(await page.locator('#styleList input:checked').inputValue(), otherStyle);
  assert.equal(await page.locator('#activateSelection').innerText(), 'Use profile');
  failSave = true;
  await page.locator('#activateSelection').click();
  await page.getByText('Save failed', {exact:true}).waitFor();
  assert.equal(state.narrator_style, activeStyle, 'Failed activation preserves the active style');
  failSave = false;
  await page.locator('#activateSelection').click();
  await page.waitForFunction(() => document.getElementById('activateSelection') === null);
  assert.equal(writes.at(-1).endpoint, '/api/activate');
  assert.equal(state.narrator_style, otherStyle);
  assert.equal(state.voice_on, false, 'Applying a style preserves mute');
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  assert.equal(await page.locator('#styleList input:checked').inputValue(), otherStyle, 'Applied style survives reload');
  assert.equal(await page.locator('#panel-ai .panel-head .pill.success').innerText(), 'In use');
  await page.locator('#soundOn').check();
  await page.waitForFunction(() => document.getElementById('powerLabel').textContent === 'Sound on');
  assert.equal(state.voice_on, true);
  assert.equal(state.effects_on, false);

  await page.getByRole('tab', {name:/^Effects/}).click();
  await page.locator('#packList label', {hasText:'Sci-fi'}).click();
  assert(await page.locator('#activateSelection').isDisabled());
  assert.equal(await page.locator('#panel-effects [data-act=save]').count(),0);
  assert.equal(state.effects_profile, 'paper', 'Browsing an unavailable inactive pack does not change the saved selection');
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
  Object.assign(state, {effects_on:true, voice_on:true, voice_profile:'senior'});
  await page.reload();
  await page.waitForFunction(() => document.getElementById('statusText').textContent.includes(' + Phrases'));
  await page.locator('#tab-effects').click();
  await page.getByRole('button', {name:'Use profile', exact:true}).click();
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

  state.setup.installing = true; state.setup.kokoro = false; state.setup.installStatus = 'running'; state.setup.installMessage = 'Installing packages';
  Object.assign(state.setup, {installElapsed:603, installQuiet:12, installTimeout:1200, installOutput:['Collecting torch', 'Downloading torch (138.6 MB)']});
  await page.reload();
  await page.locator('#tab-ai[aria-selected=true]').waitFor();
  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installing…');
  assert.equal(await page.locator('#verificationRow').isHidden(), true);
  assert.equal(await page.locator('#installKokoro').isHidden(), true);
  assert.equal(await page.locator('#installTiming').innerText(), '10:03 elapsed · 20 minute limit · Last output 0:12 ago; waiting for the installer');
  assert((await page.locator('#installActivity').innerText()).includes('Downloading torch (138.6 MB)'));
  Object.assign(state.setup, {installElapsed:605, installQuiet:0, installOutput:['Installing collected packages: torch']});
  await page.waitForFunction(() => document.getElementById('installActivity').textContent === 'Installing collected packages: torch');
  assert.equal(await page.locator('#installTiming').innerText(), '10:05 elapsed · 20 minute limit');
  await page.locator('#closeDrawer').click();
  await page.locator('#settingsButton').click();
  assert(await page.locator('#closeSoundbar').isDisabled());
  assert(await page.locator('#closeInstallHint').isVisible());
  await page.keyboard.press('Escape');
  state.setup.installing = false; state.setup.kokoro = false; state.setup.installStatus = 'error';
  state.setup.installMessage = 'Package installation failed: could not download dependencies. Check your network connection and retry installation.';
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installation failed');
  await page.locator('#panel-ai .panel-head .state-issue').getByText('Kokoro: ' + state.setup.installMessage,{exact:true}).waitFor();
  assert.equal(await page.locator('#panel-ai .panel-head [data-drawer=speech]').count(),0);

  await page.locator('#panel-ai .strip [data-drawer=speech]').click();
  assert.equal(await page.locator('#engineStatus').getAttribute('data-tone'), 'error');
  assert((await page.locator('#engineDetail').innerText()).includes('could not download'));
  assert.equal(await page.locator('#installKokoro').innerText(), 'Retry installation');
  const installsBeforeRetry = installations;
  await page.locator('#installKokoro').click();
  await page.waitForFunction(() => document.getElementById('engineStatus').textContent === 'Installed');
  assert(await page.locator('#installTiming').isHidden());
  assert(await page.locator('#installActivity').isHidden());
  assert.equal(installations, installsBeforeRetry + 1);
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Ready');
  assert.equal(checks.at(-1).scope, 'speech');
  await page.locator('#closeDrawer').click();

  // A blocked profile preview must explain the requested pack, not the browsed one.
  await page.locator('#tab-effects').click();
  await page.locator('#packList input[value="paper"]').evaluate(node=>node.click());
  const blockedPackPreviews=previews.length;
  await page.getByRole('button',{name:'Play a Sci-fi sample',exact:true}).click();
  assert.equal(await page.locator('#drawerPack').innerText(),'Sci-fi');
  assert.equal(await page.locator('#packList input:checked').inputValue(),'sci-fi');
  assert.equal(previews.length,blockedPackPreviews);
  await page.locator('#closeDrawer').click();

  // Playback belongs to the requested content, not whichever control occupies its place.
  Object.assign(state, {tts_engine:'say',voice_main:'Tara',voice_sub:'Aman',narrator_provider:'claude_cli',narrator_model:'',narrator_api_key:'',narrator_style:'pair_programmer',effects_profile:'default',soundbar_mode:'effects',effects_on:true,voice_on:false});
  await page.reload();
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Ready');
  const finishPreview = async () => {
   releasePreview(); previewGate=null;
   await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
   assert.equal(await page.locator('[data-preview].is-playing,[data-preview].is-generating').count(),0);
  };
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#effectsEvents [data-preview]').first().click();
  await page.locator('#packList label', {hasText:'Paper'}).click();
  assert.equal(await page.locator('#effectsEvents .is-playing').count(),0);
  await page.locator('#packList label', {hasText:'System sounds'}).click();
  assert.equal(await page.locator('#effectsEvents .is-playing').count(),1,'Returning to the playing pack restores its waveform');
  await finishPreview();
  assert(await page.locator('#effectsEvents [data-preview]').first().isEnabled(),'Rebuilt controls recover after playback');

  // The sounding alternative remains visible through rerenders and profile sessions.
  await page.locator('#packList input[value="paper"]').evaluate(node=>node.click());
  const paperEdit=page.locator('#effectsEvents [data-event=edit]');
  const originalAlternative=await paperEdit.locator('.ev-sound').innerText();
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await paperEdit.click();
  await page.evaluate(()=>render());
  assert.equal(await paperEdit.locator('.ev-sound').innerText(),originalAlternative);
  await finishPreview();
  const nextAlternative=await paperEdit.locator('.ev-sound').innerText();
  assert.notEqual(nextAlternative,originalAlternative,'Completion advances the audition cursor');
  await page.locator('#tab-clips').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-clips').textContent === 'Ready');
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#clipsEvents [data-preview]').first().click();
  await page.locator('#filters-clips [data-filter="clips:Work"]').click();
  assert.equal(await page.locator('#clipsEvents .is-playing').count(),0);
  await page.locator('#filters-clips [data-filter="clips:All"]').click();
  assert.equal(await page.locator('#clipsEvents .is-playing').count(),1,'Filtering preserves the original clip identity');
  await finishPreview();
  assert(await page.locator('#clipsEvents [data-preview]').first().isEnabled());

  await page.evaluate(()=>{window.originalClips=saved.preview_catalog.voice.generals.edit;saved.preview_catalog.voice.generals.edit=['First clip','Second clip'];render();});
  const clipEdit=page.locator('#clipsEvents [data-event=edit]');
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await clipEdit.click();
  await page.evaluate(()=>render());
  assert.equal(await clipEdit.locator('.ev-sound').innerText(),'First clip');
  await finishPreview();
  await page.locator('#tab-effects').click();
  await page.locator('#packList input[value="default"]').evaluate(node=>node.click());
  await page.locator('#tab-clips').click();
  assert.equal(await clipEdit.locator('.ev-sound').innerText(),'Second clip','Effects browsing cannot reset the Clips audition cursor');
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await clipEdit.click();
  await page.evaluate(()=>render());
  assert.equal(await clipEdit.locator('.ev-sound').innerText(),'Second clip');
  await finishPreview();
  await page.evaluate(()=>{saved.preview_catalog.voice.generals.edit=window.originalClips;render();});

  await page.locator('#tab-phrases').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-phrases').textContent === 'Ready');
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#phraseRows [data-preview]').first().click();
  await page.locator('#phraseRows [data-remove]').first().click();
  assert.equal(await page.locator('#phraseRows .is-playing').count(),0,'Removing a playing row must not transfer its waveform to the next row');
  const typing = page.locator('#phraseRows input').first();
  await typing.fill('Keep typing while audio finishes');
  await typing.evaluate(input => { input.focus(); input.setSelectionRange(5,11); });
  await finishPreview();
  assert(await typing.evaluate(input => document.activeElement === input));
  assert.deepEqual(await typing.evaluate(input => [input.selectionStart,input.selectionEnd]),[5,11]);
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#previewMainAgent').click();
  await page.selectOption('#mainAgentVoice','Samantha');
  assert.equal(await page.locator('#previewMainAgent use').getAttribute('href'),'#i-play','A different selected voice is not marked as playing');
  await page.selectOption('#mainAgentVoice','Tara');
  assert.equal(await page.locator('#previewMainAgent use').getAttribute('href'),'#i-wave');
  await finishPreview();

  await page.locator('#tab-ai').click();
  await page.waitForFunction(() => document.getElementById('checkStatus-aiSpeech').textContent === 'Ready');
  generationGate=Promise.resolve();
  previewGate=new Promise(resolve=>{releasePreview=resolve;});
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleLabel').textContent === 'Playing…');
  assert.equal(previews.at(-1).config.narrator_style,'pair_programmer');
  await page.locator('#styleList label').nth(1).click();
  assert.equal(await page.locator('#sampleLabel').innerText(),'Play sample');
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'),'#i-play');
  assert.equal(await page.locator('#sampleBtn').getAttribute('aria-busy'),'false');
  assert(await page.locator('#sampleBtn').isDisabled(),'Another selection cannot start concurrent playback');
  await page.locator('#styleList input[value="pair_programmer"]').locator('..').click();
  assert.equal(await page.locator('#sampleLabel').innerText(),'Playing…');
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'),'#i-wave');
  await finishPreview();
  generationGate=null;
  generationGate=new Promise(resolve=>{releaseGeneration=resolve;});
  const beforeChangedGeneration=previews.length;
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => document.getElementById('sampleLabel').textContent === 'Generating…');
  await page.locator('#styleList label').nth(1).click();
  assert.equal(await page.locator('#sampleLabel').innerText(),'Play sample');
  assert.equal(await page.locator('#sampleBtn use').getAttribute('href'),'#i-play');
  releaseGeneration();generationGate=null;
  await page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  assert.deepEqual(previews.slice(beforeChangedGeneration).map(request=>request.action),['generate'],'A stale generated sample never starts playback');

  // Background readiness updates preserve keyboard navigation across every section.
  Object.assign(state,{tts_engine:'kokoro'});
  await page.reload();
  await page.waitForFunction(() => document.getElementById('checkStatus-effects').textContent === 'Ready');
  for (const [theme,width] of [['amber',1280],['mint',390]]) {
   await page.setViewportSize({width,height:900});
   await page.locator('#settingsButton').click();
   await page.locator(`[data-theme-choice=${theme}]`).click();
   await page.keyboard.press('Escape');
   for (const [mode,key,selector] of [
    ['effects','effects','#packList input[value="paper"]'],
    ['clips','clips','#filters-clips button'],
    ['phrases','phrases','#evList button'],
    ['ai','aiSpeech','#styleList input[value="sports"]'],
   ]) {
    await page.locator('#tab-'+mode).click();
    await page.waitForFunction(key => !cachedCheck(key)?.requesting, key);
    const control=page.locator(selector).first();
    await control.focus();
    await control.evaluate(node => { window.focusedControl=node; });
    await page.evaluate(key => checkSetup(key),key);
    assert(await page.evaluate(() => document.activeElement===window.focusedControl),`${mode} preserves the mounted focused control in ${theme}`);
    if (mode==='effects'||mode==='ai') {
     await page.keyboard.press('ArrowDown');
     assert(await page.evaluate(() => document.activeElement.matches('input[type=radio]')),'Keyboard selection retains focus when selected markup changes');
    }
   }
  }
  await page.setViewportSize({width:1280,height:900});
  await page.locator('#styleList input').nth(1).focus();
  await page.locator('#styleList input').nth(1).evaluate(node => { window.focusedControl=node; });
  await page.evaluate(() => checkSetup('aiSpeech'));
  assert(await page.evaluate(() => document.activeElement===window.focusedControl),'An explicit Kokoro refresh preserves focus too');

  // Transient labels must not resize controls or move the surrounding layout.
  const geometry = selector => page.locator(selector).evaluateAll(nodes => nodes.map(node => {
   const {x,y,width,height}=node.getBoundingClientRect();
   return {x:x+scrollX,y:y+scrollY,width,height};
  }));
  const headerGeometry='.topbar,.brand,.now,.controls,.power,.volume,.volume output,#volume,#volumeValue,#settingsButton,#helpButton';
  const stableGeometry=headerGeometry+',#tabs,.tab,.tab > .i,.tab > span:not(.tab-badges),.panel:not([hidden]) .workspace';
  for (const theme of ['amber','mint']) {
   await page.evaluate(theme=>applyTheme(theme),theme);
   for (const width of [1280,901,900,561,560,390,320]) {
    await page.setViewportSize({width,height:900});
    for (const mode of ['effects','clips','phrases','ai']) {
     await page.locator('#tab-'+mode).click();
     await page.evaluate(mode => checkSetup({effects:'effects',clips:'clips',phrases:'phrases',ai:'aiSpeech'}[mode],{automatic:true}),mode);
     const before=await geometry(stableGeometry);
     for (const volume of [0,9,10,99,100,99]) {
      await page.locator('#volume').evaluate((input,value)=>{input.value=value;input.dispatchEvent(new Event('input'));},String(volume));
      assert.equal(await page.locator('#volumeValue').innerText(),volume+'%');
      assert.deepEqual(await geometry(stableGeometry),before,`Volume ${volume}% keeps ${mode}/${theme}/${width} stationary`);
     }
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No overflow in ${mode}/${theme}/${width}`);
     await require('./setup_description_checks.cjs')(page,mode);
     const stripSelector=`#panel-${mode} .strip,#panel-${mode} .strip > *,#panel-${mode} .strip [data-status-for]`;
     const stripBefore=await geometry(stripSelector);
     for (const [message,checking] of [['Ready',false],['Downloading…',false],['Load failed',false],['Install failed',false],['Choose voices',false],['Key required',false],['Missing files',false],['Checking…',true]]) {
      await page.locator(`#panel-${mode} .strip [data-status-for]`).evaluateAll((nodes,view)=>nodes.forEach(node=>paintStatus(node,view)),{message,checking,tone:'warning'});
      assert.deepEqual(await geometry(stripSelector),stripBefore,`${mode} status ${message} keeps strip controls stationary in ${theme}/${width}`);
     }
     await page.evaluate(()=>renderChecks());
     const key={effects:'effects',clips:'clips',phrases:'phrases',ai:'aiSpeech'}[mode];
     const frameSelector=`#panel-${mode} .panel-head,#panel-${mode} .activation-actions,#panel-${mode} .workspace,#panel-${mode} .strip`;
     const frameBefore=await geometry(frameSelector);
     checkGate=new Promise(resolve=>{releaseCheck=resolve;});
     await page.evaluate(key=>{checkSetup(key);},key);
     assert.deepEqual(await geometry(frameSelector),frameBefore,`Pending ${mode} checks do not move the workspace in ${theme}/${width}`);
     releaseCheck();checkGate=null;
     await page.waitForFunction(key=>!cachedCheck(key).requesting,key);
     assert.deepEqual(await geometry(frameSelector),frameBefore);
     failCheck=true;
     checkError='The selected engine could not finish its readiness check. Check the connection and selected voices, then retry. '.repeat(3);
     await page.evaluate(key=>checkSetup(key),key);
     assert.deepEqual(await geometry(frameSelector),frameBefore,`Long ${mode} errors do not reflow the section in ${theme}/${width}`);
     assert.equal((await page.locator('#errorMessage').innerText()).trim(),checkError.trim());
     await page.locator('[data-dismiss-error]').click();
     assert.equal(await page.locator('#errorBanner').innerText(),'');
     assert.deepEqual(await geometry(frameSelector),frameBefore);
     failCheck=false;
     await page.evaluate(key=>checkSetup(key),key);
     assert.deepEqual(await geometry(frameSelector),frameBefore);
    }
    const notificationGeometry=headerGeometry+',#tabs,.panel:not([hidden]) .workspace';
    const beforeNotification=await geometry(notificationGeometry);
    Object.assign(versionState,{available:true,release:{version:'0.9.0',notes_url:'https://github.com/zorhay/code-gossip/releases/tag/0.9.0'}});
    await page.evaluate(()=>refreshVersions());
    assert.deepEqual(await geometry(notificationGeometry),beforeNotification,`Discovering an update does not move the page in ${theme}/${width}`);
    assert((await page.locator('#settingsButton').getAttribute('aria-label')).includes('Update available'));
    Object.assign(versionState,{available:false,release:null});
    await page.evaluate(()=>refreshVersions());
    assert.deepEqual(await geometry(notificationGeometry),beforeNotification);
    const headerBefore=await geometry(headerGeometry);
    const tabBefore=await geometry('#tabs,.tab,.tab > .i,.tab > span:not(.tab-badges)');
    await page.evaluate(()=>{window.layoutSelection=activeSelection;window.layoutContext=state.context;window.layoutChecked=cachedCheck('ai');});
    for (const selection of [{mode:'effects',pack:'default'},{mode:'clips'},{mode:'phrases'},{mode:'ai',style:'sports'},{mode:'ai',style:'A long custom commentary style name'}]) {
     await page.evaluate(selection=>{activeSelection=selection;state.context=!state.context;rememberCheck('ai',{identity:aiIdentity(),status:'failed'});renderChrome();},selection);
     assert.deepEqual(await geometry(headerGeometry),headerBefore,`Active selection does not move header controls in ${theme}/${width}`);
     assert.deepEqual(await geometry('#tabs,.tab,.tab > .i,.tab > span:not(.tab-badges)'),tabBefore,`Badges do not move tabs or their labels in ${theme}/${width}`);
    }
    await page.evaluate(()=>{activeSelection=window.layoutSelection;state.context=window.layoutContext;if(window.layoutChecked) rememberCheck('ai',window.layoutChecked);renderChrome();});
    const sampleBefore=await geometry('#sampleBtn,#styleTitle');
    for (const label of ['Play sample','Generating…','Playing…','Replay']) {
     await page.locator('#sampleLabel').evaluate((node,label)=>{node.textContent=label;},label);
     assert.deepEqual(await geometry('#sampleBtn,#styleTitle'),sampleBefore,`Sample label ${label} stays stationary in ${theme}/${width}`);
    }
    await page.evaluate(()=>renderSample());
    const aiEditor='#panel-ai .workspace,#panel-ai .pane-body.pad,#panel-ai .sample-settings,#speaker,#sessionContext,#panel-ai .strip';
    const aiBefore=await geometry(aiEditor);
    await page.locator('#sessionContext').evaluate(input=>{input.checked=!input.checked;input.dispatchEvent(new Event('change'));});
    assert(await page.locator('#panel-ai [data-act=save]').isVisible());
    assert.deepEqual(await geometry(aiEditor),aiBefore,`AI edit actions retain their space in ${theme}/${width}`);
    await page.locator('#panel-ai [data-act=discard]').evaluate(button=>button.click());
    assert.deepEqual(await geometry(aiEditor),aiBefore);
    await page.evaluate(()=>{window.layoutSample=generatedSample;generatedSample={identity:sampleIdentity(),text:'A detailed generated sample with enough text to fill several lines. '.repeat(40)};renderSample();});
    assert.deepEqual(await geometry(aiEditor),aiBefore,`Generated text does not displace AI settings in ${theme}/${width}`);
    assert(await page.locator('#panel-ai .pane-body.pad').evaluate(node=>{node.scrollTop=node.scrollHeight;return node.scrollTop>0;}),'Long samples remain scrollable');
    const sampleScroll=await page.locator('#panel-ai .pane-body.pad').evaluate(node=>node.scrollTop);
    await page.evaluate(()=>renderSample());
    assert.equal(await page.locator('#panel-ai .pane-body.pad').evaluate(node=>node.scrollTop),sampleScroll,'Background rendering preserves the sample reading position');
    await page.evaluate(()=>{generatedSample=window.layoutSample;renderSample();});
    assert.equal(await page.locator('#panel-ai .pane-body.pad').evaluate(node=>node.scrollTop),0,'A different sample starts at its beginning');
    await page.locator('#tab-phrases').click();
    const phraseEditor='#phrasesWorkspace,#phrasesWorkspace .pane-body,#addPhrase,#panel-phrases .strip';
    const phrasesBefore=await geometry(phraseEditor);
    for (const text of ['A new phrase','']) {
     await page.locator('#phraseRows input').first().evaluate((input,text)=>{input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));},text);
     assert.deepEqual(await geometry(phraseEditor),phrasesBefore,`Phrase edits and validation keep the editor stable in ${theme}/${width}`);
    }
    await page.locator('#panel-phrases [data-act=discard]').evaluate(button=>button.click());
    assert.deepEqual(await geometry(phraseEditor),phrasesBefore);
   }
  }
  await page.setViewportSize({width:1280,height:900});
  const volumeBefore=await geometry(headerGeometry);
  configGate=new Promise(resolve=>{releaseConfig=resolve;});
  await page.locator('#volume').evaluate(input=>{input.value='100';input.dispatchEvent(new Event('input'));input.dispatchEvent(new Event('change'));});
  await page.waitForFunction(()=>document.getElementById('volume').disabled);
  assert.deepEqual(await geometry(headerGeometry),volumeBefore,'Pending volume save does not shift controls');
  releaseConfig();configGate=null;
  await page.waitForFunction(()=>!document.getElementById('volume').disabled);
  assert.deepEqual(await geometry(headerGeometry),volumeBefore,'Saved volume does not shift controls');
  await page.locator('#settingsButton').click();
  const gapBefore=await geometry('.range-row,.range-row input,.range-row output');
  for (const id of ['effectsGap','voiceGap']) {
   for (const value of ['0','250','9750','10000']) {
    await page.locator('#'+id).evaluate((node,value)=>{node.value=value;node.dispatchEvent(new Event('input'));},value);
    assert.deepEqual(await geometry('.range-row,.range-row input,.range-row output'),gapBefore,'Pacing values keep sliders stationary');
   }
  }
  await page.keyboard.press('Escape');

  Object.assign(versionState, {available:true, release:{version:'0.9.0', notes_url:'https://github.com/zorhay/code-gossip/releases/tag/0.9.0'}});
  await page.evaluate(() => refreshVersions());
  assert((await page.locator('#versionNotice').innerText()).includes('0.8.0 → 0.9.0'));
  assert.equal(updateStarts, 0);
  await page.locator('#versionNotice').click();
  const updateControlsBefore = await geometry('.version-row > *');
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
  assert.deepEqual(await geometry('.version-row > *'),updateControlsBefore,'Updating labels do not move neighboring update controls');
  assert(await page.locator('#closeSoundbar').isDisabled());
  Object.assign(versionState, {running:false, phase:'failed', message:'Update failed. Previous version restored.'});
  await page.evaluate(() => refreshVersions());
  assert.equal(await page.locator('#applyUpdate').innerText(), 'Retry update');
  assert.deepEqual(await geometry('.version-row > *'),updateControlsBefore,'Retry labels keep update controls stationary');
  Object.assign(versionState, {development:true});
  await page.evaluate(() => refreshVersions());
  assert.equal(await page.locator('#applyUpdate').isVisible(), false);
  assert.equal(await page.locator('#availableVersion').innerText(),'Development installation');
  assert.equal(await page.locator('#updateExplanation').textContent(),'Update your checkout, then rerun install.sh --dev.');
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
 }catch(error){console.error(error);throw error;}
 finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);server.closeAllConnections();server.close();process.exitCode=1;});
