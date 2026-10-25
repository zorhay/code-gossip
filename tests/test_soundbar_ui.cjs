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
 setup:{effects:Object.fromEntries(Object.keys(manifest.effects).map(name=>[name,{ready:name!=='sci-fi',sox:name==='sci-fi',message:name==='sci-fi'?'Install SoX':'Ready',missing:[]}])),clips:{generals:{ready:true,message:'Ready'}},say:true,kokoro:false},
};
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
   else if(endpoint==='/api/activate'){
    const body=req.postDataJSON();writes.push(body);if(saveGate)await saveGate;
    if(failSave)reply={ok:false,error:'Save failed'};
    else {Object.assign(state,body.config,{effects_on:body.enabled&&body.mode==='effects',voice_on:body.enabled&&body.mode!=='effects',soundbar_mode:body.mode});if(body.mode!=='effects')state.voice_profile={clips:'generals',phrases:'senior',ai:'narrator'}[body.mode];if(body.phrases)state.phrases=body.phrases;}
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
  await page.waitForFunction(()=>document.getElementById('statusText').textContent==='Active · Effects · System sounds').catch(async error=>{console.error(await page.locator('body').innerText());throw error;});
  await page.waitForFunction(()=>document.getElementById('checkStatus-effects').textContent==='Audio available');
  assert.equal(checks.length,1,'Effects availability is checked automatically on load');
  assert(await page.locator('#topicTips').isVisible());
  assert.equal(await page.locator('.topic-tip').count(),6);
  assert.equal(await page.locator('#guideDialog,#onboardingInvite').count(),0);
  assert.equal(await page.locator('.topic-tip').first().evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(164, 143, 49, 0.5)');
  const beforeTips={writes:writes.length,previews:previews.length,checks:checks.length,models:modelRequests.length};
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:900});
    assert(await page.locator('#topicTips').evaluate(el=>{const r=el.getBoundingClientRect();return r.right<=innerWidth&&r.left>=0&&r.top<120&&r.bottom<=innerHeight;}));
    if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`topic-stack-${width}.png`)});
  }
  await page.setViewportSize({width:1280,height:900});
  assert.equal(await page.locator('.topic-tip-body,.topic-tip-show').count(),0,'Topic cards never unfold');
  for(const [id,count] of [['profile',3],['speech',3],['llm',3],['phrases',3],['preview',2],['settings',2]]){
    await page.locator(`[data-topic="${id}"] .topic-tip-start`).click();
    await page.locator('#tipScenario[open]').waitFor();
    assert.equal(await page.locator('#topicTips').isVisible(),false);
    for(let step=0;step<count;step++){
      assert((await page.locator('#tipScenarioProgress').innerText()).endsWith(`${step+1} of ${count}`));
      for(const width of [1280,390]){
        await page.setViewportSize({width,height:900});
        if(id==='llm'&&step===2&&width===390){
          await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
          assert(await page.locator('#checkConnection').evaluate(el=>el.getBoundingClientRect().top>innerHeight),'Mobile connection target is below the viewport');
        }
        await page.waitForFunction(()=>{const r=document.getElementById('tipScenario').getBoundingClientRect();return r.left>=16&&r.right<=innerWidth-16&&r.top>=16&&r.bottom<=innerHeight-16;});
        assert(await page.locator('#tipScenarioHighlight').evaluate(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0;}));
        if(process.env.SCREENSHOT_DIR&&step===0)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,`scenario-${id}-${width}.png`)});
      }
      await page.locator('#tipScenarioNext').click();
    }
    assert.equal(await page.locator('#tipScenario').isVisible(),false);
    assert.equal(await page.locator('#tab-effects').getAttribute('aria-selected'),'true');
    assert.equal(await page.locator('#settingsDialog').isVisible(),false);
  }
  await page.locator('[data-topic="llm"] .topic-tip-start').click();await page.locator('#tipScenarioNext').click();
  await page.locator('#tipScenarioBack').click();assert((await page.locator('#tipScenarioProgress').innerText()).endsWith('1 of 3'));
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.getElementById('tipScenario').open&&document.getElementById('tab-effects').getAttribute('aria-selected')==='true');
  await page.setViewportSize({width:1280,height:900});
  assert.deepEqual({writes:writes.length,previews:previews.length,checks:checks.length,models:modelRequests.length},beforeTips,'Topic navigation does not save, play, or contact providers');
  await page.locator('[data-topic="profile"] .topic-tip-dismiss').click();
  await page.reload();await page.waitForFunction(()=>document.getElementById('checkStatus-effects').textContent==='Audio available');
  assert.equal(await page.locator('[data-topic="profile"]').isVisible(),false,'Each dismissed topic stays dismissed after reload');
  await page.locator('#helpButton').click();assert.equal(await page.locator('#topicTips').isVisible(),false);
  await page.locator('#helpButton').click();assert.equal(await page.locator('.topic-tip:visible').count(),6,'Help restores all topics');
  await page.locator('#helpButton').click();
  assert.equal(await page.locator('[role=tab]').count(),4);
  assert.equal(await page.locator('#activateSelection').innerText(),'Applied');
  assert(await page.locator('#activateSelection').isDisabled());
  assert.equal(await page.locator('.selection-bar button').count(),0);
  assert.equal(await page.locator('table').count(),0);
  assert.equal(await page.locator('#soundPack option').first().getAttribute('value'),'default');
  const tab=async name=>{await page.getByRole('tab',{name,exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.mode-panel:not([hidden]) button[aria-busy=true]'));assert.equal(await page.locator('.mode-panel:not([hidden]) .preview-actions #activateSelection').count(),1);assert(await page.locator('#activateSelection').evaluate(button=>Math.abs(button.getBoundingClientRect().right-button.parentElement.getBoundingClientRect().right)<2),'Apply aligns with the right edge of the action row');};
  assert.equal(await page.locator('#toast,#saveStatus').count(),0,'No transient or duplicate success notifications');
  await page.locator('#setup-effects > summary').click();
  const effectCheck=page.locator('[data-check-setup=effects]');
  assert.equal(await effectCheck.innerText(),'Check');
  checkGate=new Promise(resolve=>releaseCheck=resolve);
  await effectCheck.click();await page.waitForFunction(()=>document.querySelector('[data-check-setup=effects]').textContent==='Checking…');
  assert.equal(await effectCheck.isEnabled(),false);
  releaseCheck();checkGate=null;
  await page.waitForFunction(()=>document.getElementById('checkStatus-effects').textContent==='Audio available');
  assert.equal(await effectCheck.innerText(),'Check');
  assert.equal(await page.locator('#checkStatus-effects').evaluate(el=>getComputedStyle(el).color),'rgb(138, 199, 138)');
  await page.selectOption('#soundPack','paper');assert.equal(await effectCheck.innerText(),'Check');
  assert.equal(await page.locator('#checkStatus-effects').innerText(),'Not checked');
  assert.equal(await page.locator('#checkStatus-effects').evaluate(el=>getComputedStyle(el).color),'rgb(228, 173, 76)');
  failCheck=true;await effectCheck.click();await page.locator('#setup-effects [role=alert]').waitFor();
  assert.equal(await effectCheck.innerText(),'Check');assert(await effectCheck.isEnabled());
  assert.equal(await page.locator('#checkStatus-effects').innerText(),'Check failed');
  assert.equal(await page.locator('#checkStatus-effects').evaluate(el=>getComputedStyle(el).color),'rgb(237, 154, 135)');
  failCheck=false;await effectCheck.click();await page.waitForFunction(()=>document.getElementById('checkStatus-effects').textContent==='Audio available');
  assert.equal(await page.getByText('Check failed',{exact:true}).count(),0);
  assert.equal(writes.length,0);
  assert.equal(await page.locator('#setupStatus-effects').isVisible(),false);
  assert.equal(await page.locator('#setup-effects').getByText('Audio available',{exact:true}).filter({visible:true}).count(),1);
  await page.locator('#setup-effects > summary').click();assert.equal(await page.locator('#setupStatus-effects').isVisible(),true);

  await tab('Phrases');await tab('Clips');await tab('Effects');
  await page.selectOption('#soundPack','paper');await page.locator('[data-preview=effects]').click();
  assert.equal(previews.at(-1).event,'edit');
  await page.selectOption('#effectsEvent','stop');await page.locator('[data-preview=effects]').click();assert.equal(previews.at(-1).event,'stop');
  await page.selectOption('#soundPack','silent');assert(await page.locator('[data-preview=effects]').isDisabled());
  await page.selectOption('#soundPack','paper');await page.locator('[data-preview=effects]').click();
  assert.equal(previews.at(-1).config.effects_profile,'paper');assert.equal(writes.length,0);
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave=true;await page.locator('#activateSelection').click();await page.getByText('Save failed',{exact:true}).first().waitFor();
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  failSave=false;saveGate=new Promise(resolve=>releaseSave=resolve);
  await page.locator('#activateSelection').click();
  assert.equal(await page.locator('#activateSelection').getAttribute('aria-busy'),'true');
  assert.equal(await page.locator('#activationProgress').textContent(),'Saving selection…');
  assert((await page.locator('#statusText').innerText()).includes('System sounds'));
  releaseSave();saveGate=null;
  await page.waitForFunction(()=>document.getElementById('statusText').textContent.endsWith('Paper'));
  await tab('Phrases');await page.selectOption('#mainAgentVoice','Samantha');await page.selectOption('#subagentVoice','Aman');
  assert.equal(await page.locator('#phraseEditor').getAttribute('open'),null);
  await page.locator('#phraseEditor > summary').click();
  await page.locator('#phraseRows input').first().fill('Please investigate');
  await page.locator('#phraseEditor > summary').click();assert.equal(await page.locator('#phraseRows').isVisible(),false);
  await page.locator('#phraseEditor > summary').click();assert.equal(await page.locator('#phraseRows input').first().inputValue(),'Please investigate');
  await page.locator('#setup-phrases > summary').click();
  failCheck=true;await page.locator('#phraseSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('phraseSpeechCheck').dataset.status==='failed');
  assert.equal(await page.locator('#setupStatus-phrases').innerText(),'Check failed');
  assert.equal(await page.locator('#activateSelection').innerText(),'Apply');
  const blockedPreview=previews.length;await page.locator('[data-preview=phrases]').click();assert.equal(previews.length,blockedPreview);
  failCheck=false;await page.locator('#phraseSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('phraseSpeechCheck').dataset.status==='checked');
  await page.locator('[data-preview=phrases]').click();
  assert.equal(previews.at(-1).variant,0);
  await page.selectOption('#phraseVariant','1');await page.locator('[data-preview=phrases]').click();assert.equal(previews.at(-1).variant,1);
  assert((await page.locator('#phrasePreviewCopy').innerText()).includes(state.phrases.subagent_start[1][0]));
  await page.getByRole('button',{name:'Preview alternative 1',exact:true}).click();assert.equal(previews.at(-1).variant,0);
  assert.equal(previews.at(-1).config.voice_main,'Samantha');assert.equal(previews.at(-1).config.voice_sub,'Aman');assert.equal(previews.at(-1).phrases.subagent_start[0][0],'Please investigate');
  assert.equal(state.voice_profile,'senior');assert.equal(state.voice_on,false);
  await page.locator('#activateSelection').click();await page.waitForFunction(()=>document.getElementById('statusText').textContent==='Active · Phrases · Senior');
  assert.equal(state.voice_main,'Samantha');assert.equal(state.phrases.subagent_start[0][0],'Please investigate');
  await page.reload();await page.locator('#tab-phrases[aria-selected=true]').waitFor();await page.waitForFunction(()=>document.getElementById('checkStatus-phrases').textContent==='Engine available');assert.equal(await page.locator('#mainAgentVoice').inputValue(),'Samantha');
  const before=writes.length;
  await tab('AI commentary');
  const beforeVoiceCheck=checks.length;await page.locator('#previewAIVoice').click();assert.equal(previews.at(-1).role,'main');assert.equal(checks.length,beforeVoiceCheck);
  await page.locator('#setup-ai > summary').click();
  assert.equal(await page.locator('#checkConnection').innerText(),'Check CLI');
  await page.locator('#checkConnection').click();await page.waitForFunction(()=>document.getElementById('checkStatus-ai').textContent==='CLI found');
  await page.selectOption('#provider','openai');await page.locator('#sampleKey').fill('dummy-test-key');await page.locator('#model').fill('test-model');
  checkGate=new Promise(resolve=>releaseCheck=resolve);
  await page.locator('#checkConnection').click();
  await page.waitForFunction(()=>document.getElementById('checkConnection').textContent==='Connecting…');
  assert.equal(await page.locator('#checkStatus-ai').isVisible(),false,'Do not repeat the pending label');
  assert.equal(await page.locator('#activateSelection').innerText(),'Apply');
  assert(await page.locator('#activateSelection').isDisabled());
  releaseCheck();checkGate=null;
  await page.waitForFunction(()=>document.getElementById('checkConnection').dataset.status==='checked');
  await page.waitForFunction(()=>document.querySelectorAll('#modelChoices option').length===2);
  assert.deepEqual(await page.locator('#modelChoices option').evaluateAll(options=>options.map(option=>option.value)),['live-model-a','live-model-b']);
  assert.equal(await page.locator('#model').inputValue(),'test-model','Discovery preserves a custom model');
  assert.equal(modelRequests.at(-1).config.narrator_api_key,'dummy-test-key');
  failModels=true;await page.locator('#refreshModels').click();await page.waitForFunction(()=>document.getElementById('modelStatus').dataset.status==='failed');
  assert.equal(await page.locator('#modelChoices option').count(),0,'Failures do not show old suggestions');
  assert.equal(await page.locator('#model').inputValue(),'test-model');
  failModels=false;await page.locator('#refreshModels').click();await page.waitForFunction(()=>document.querySelectorAll('#modelChoices option').length===2);
  modelGate=new Promise(resolve=>releaseModels=resolve);
  await page.locator('#refreshModels').click();await page.waitForFunction(()=>document.getElementById('modelStatus').dataset.status==='loading');
  await page.selectOption('#provider','claude_cli');
  releaseModels();modelGate=null;
  await page.waitForFunction(()=>document.getElementById('modelStatus').textContent.includes('Claude CLI'));
  assert.equal(await page.locator('#modelChoices option').count(),0,'A stale provider response cannot repopulate suggestions');
  assert(await page.locator('#refreshModels').isDisabled());
  await page.selectOption('#provider','openai');
  assert.equal(await page.locator('#modelChoices option').count(),0);
  assert(await page.locator('#refreshModels').isDisabled(),'New provider needs its own key');
  await page.locator('#sampleKey').fill('dummy-test-key');await page.locator('#model').fill('test-model');
  await page.waitForFunction(()=>document.querySelectorAll('#modelChoices option').length===2);
  await page.locator('#sampleKey').fill('replacement-key');
  assert.equal(await page.locator('#modelChoices option').count(),0,'Editing credentials immediately clears old suggestions');
  await page.locator('#sampleKey').fill('dummy-test-key');await page.locator('#checkConnection').click();
  await page.waitForFunction(()=>document.getElementById('checkStatus-ai').textContent==='Connection verified');
  assert.equal(await page.locator('#checkConnection').innerText(),'Check connection');
  assert.equal(checks.at(-1).scope,'provider');
  assert.equal(checks.at(-1).config.narrator_api_key,'dummy-test-key');assert.equal(checks.at(-1).config.narrator_model,'test-model');assert.equal(writes.length,before);assert.equal(state.narrator_provider,'claude_cli');
  assert.equal(await page.locator('#setup-aiSpeech').getAttribute('open'),null,'Provider setup does not open speech setup');
  await page.locator('#setup-aiSpeech > summary').click();
  await page.selectOption('#engine','kokoro');
  assert(await page.locator('#aiKokoroInfo').isVisible());
  await page.locator('#aiKokoroInfo summary').click();
  assert((await page.locator('#aiKokoroInfo').innerText()).includes('~/.code-gossip/state/.venv'));
  assert((await page.locator('#aiKokoroInfo').innerText()).includes('10 minutes'));
  assert.equal(installations,0,'Reading setup does not install anything');
  assert.equal(await page.locator('#aiEngineStatus').innerText(),'Not installed');
  assert.equal(await page.locator('#aiVerificationRow').isVisible(),false);
  await page.locator('#aiInstallKokoro').click();await page.waitForFunction(()=>document.getElementById('aiInstallKokoro').hidden);assert.equal(installations,1);assert.equal(writes.length,before);
  await page.selectOption('#speaker','af_bella');await page.locator('#checkConnection').click();await page.waitForFunction(()=>document.getElementById('checkConnection').dataset.status==='checked');
  failCheck=true;await page.locator('#aiSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('aiSpeechCheck').dataset.status==='failed');
  assert.equal(await page.locator('#checkConnection').innerText(),'Check connection');
  assert.equal(await page.locator('#checkStatus-ai').innerText(),'Connection verified','Speech failure does not invalidate provider');
  assert.equal(await page.locator('#activateSelection').innerText(),'Apply');
  assert.equal(checks.at(-1).scope,'speech');
  assert(await page.locator('#activateSelection').isDisabled());
  assert.equal(await page.locator('#aiInstallKokoro').innerText(),'Repair installation');
  assert(await page.locator('#aiInstallKokoro').isVisible());
  failCheck=false;await page.locator('#aiSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('aiSpeechCheck').dataset.status==='checked');
  assert.equal(await page.locator('#providerStatus,#aiSpeechStatus,#phraseSpeechStatus').count(),0);
  assert.equal(await page.locator('#setup-aiSpeech').getByText('Engine available',{exact:true}).filter({visible:true}).count(),1);
  assert.equal(await page.locator('#setup-ai').getByText('Connection verified',{exact:true}).filter({visible:true}).count(),1);
  if(process.env.SCREENSHOT_DIR){await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'separate-setups.png'),fullPage:true});}
  assert.equal(await page.locator('#generateCommentary').count(),0);
  failGeneration=true;const beforeFailedSample=previews.length;
  await page.locator('[data-preview=ai]').click();await page.getByText('Generation failed',{exact:true}).waitFor();
  assert.deepEqual(previews.slice(beforeFailedSample).map(request=>request.action),['generate'],'Failed generation never attempts playback');
  assert.equal(await page.locator('[data-preview=ai]').innerText(),'▶ Play sample');
  assert(await page.locator('[data-preview=ai]').isEnabled());
  failGeneration=false;
  const firstSample=previews.length;
  await page.locator('[data-preview=ai]').click();await page.waitForFunction(()=>document.querySelector('[data-preview=ai]').textContent==='▶ Play sample');
  assert.equal(await page.locator('#commentarySample').innerText(),'Preview result');
  assert.deepEqual(previews.slice(firstSample).map(request=>request.action),['generate','play'],'One click generates and plays');
  assert.equal(previews.at(-1).text,'Preview result');
  assert.equal(previews.at(-1).config.kokoro_voice,'af_bella');
  await page.locator('[data-preview=ai]').click();await page.waitForFunction(()=>document.querySelector('[data-preview=ai]').textContent==='▶ Play sample');
  assert.deepEqual(previews.slice(firstSample).map(request=>request.action),['generate','play','play'],'Replay uses existing sample without generation');
  await page.locator('#soundOn').uncheck();await page.waitForFunction(()=>document.getElementById('powerLabel').textContent==='Sound off');
  await page.locator('#activateSelection').click();await page.waitForFunction(()=>document.getElementById('statusText').textContent.startsWith('Sound off · AI commentary'));
  assert.equal(state.voice_on,false);assert.equal(state.effects_on,false);
  const beforeReloadChecks=checks.length,beforeReloadWrites=writes.length;
  await page.reload();await page.locator('#tab-ai[aria-selected=true]').waitFor();assert.equal(await page.locator('#soundOn').isChecked(),false);
  await page.waitForFunction(()=>document.getElementById('checkStatus-ai').textContent==='Connection verified'&&document.getElementById('checkStatus-aiSpeech').textContent==='Engine available');
  assert.equal(checks.length,beforeReloadChecks+2,'Reload rechecks provider and speech automatically');
  assert.equal(writes.length,beforeReloadWrites,'Automatic checks do not save drafts');
  const anotherStyle=await page.locator('#commentaryStyle option').evaluateAll(options=>options.find(option=>!option.selected).value);
  const beforeStyleChecks=checks.length;
  await page.selectOption('#commentaryStyle',anotherStyle);
  assert.equal(await page.locator('#activateSelection').innerText(),'Apply','Style edit after reload needs no manual setup');
  assert(await page.locator('#activateSelection').isEnabled());
  assert.equal(checks.length,beforeStyleChecks,'Style edits do not invalidate provider verification');
  await page.locator('#soundOn').check();await page.waitForFunction(()=>document.getElementById('powerLabel').textContent==='Sound on');assert.equal(state.voice_on,true);assert.equal(state.effects_on,false);
  await tab('Effects');await page.selectOption('#soundPack','sci-fi');assert(await page.locator('#activateSelection').isDisabled());assert.equal(await page.locator('#activationReason').innerText(),'Install SoX');await page.locator('#openSelectionSetup').click();assert(await page.locator('#setup-effects[open]').isVisible());assert.equal(state.soundbar_mode,'ai');
  await page.locator('#installSox').click();assert(await page.locator('#soxCommand').isVisible());
  await page.setViewportSize({width:390,height:844});
  for(const name of ['Effects','Clips','Phrases','AI commentary']){await tab(name);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No overflow in '+name);}
  await page.locator('#tab-ai').press('ArrowLeft');assert.equal(await page.locator('#tab-phrases').getAttribute('aria-selected'),'true');assert.equal(state.soundbar_mode,'ai');
  await page.locator('#settingsButton').click();const preferenceSaved=page.waitForResponse('**/api/config');await page.locator('#approvalCues').uncheck();await preferenceSaved;assert.equal(state.codex_permission_sound_on,false);await page.keyboard.press('Escape');
  await page.locator('#setup-phrases > summary').click();await page.selectOption('#phraseEngine','kokoro');
  assert(await page.locator('#phraseKokoroInfo').isVisible());await page.locator('#phraseKokoroInfo summary').click();
  assert((await page.locator('#phraseKokoroInfo').innerText()).includes('Hugging Face'));
  await page.locator('#setup-phrases > summary').click();
  if(process.env.SCREENSHOT_DIR){
    for(const width of [1280,539]){
      await page.setViewportSize({width,height:1000});
      for(const [name,id] of [['Effects','effects'],['Clips','clips'],['Phrases','phrases'],['AI commentary','ai']]){
        await tab(name);await page.evaluate(()=>window.scrollTo(0,0));
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,id+'-'+width+'.png')});
      }
    }
  }
  state.setup.installing=true;state.setup.kokoro=false;state.setup.installMessage='Installing packages';
  await page.reload();await page.locator('#tab-ai[aria-selected=true]').waitFor();await page.locator('#setup-aiSpeech > summary').click();
  await page.waitForFunction(()=>document.getElementById('aiEngineStatus').textContent==='Installing…');
  assert.equal(await page.locator('#aiVerificationRow').isVisible(),false);
  assert.equal(await page.locator('#aiInstallKokoro').isVisible(),false);
  await page.locator('#settingsButton').click();assert(await page.locator('#closeSoundbar').isDisabled());assert(await page.locator('#closeInstallHint').isVisible());await page.keyboard.press('Escape');
  state.setup.installing=false;state.setup.kokoro=false;state.setup.installStatus='error';state.setup.installMessage='Package installation failed: could not download dependencies. Check your network connection and retry installation.';
  await page.waitForFunction(()=>document.getElementById('aiEngineStatus').textContent==='Installation failed');
  assert.equal(await page.locator('#aiEngineStatus').getAttribute('data-tone'),'error');
  for(const width of [390,1280]){
   await page.setViewportSize({width,height:900});
   assert(await page.locator('#aiEngineDetail').evaluate(el=>el.getBoundingClientRect().width>el.parentElement.getBoundingClientRect().width*.8),'Installation messages use the full content width');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'installation-failed-'+width+'.png'),fullPage:true});
  }
  assert.equal(await page.locator('#aiInstallKokoro').innerText(),'Retry installation');
  assert.equal(await page.locator('#aiVerificationRow').isVisible(),false);
  assert.equal(installations,1,'Reload resumes polling without another install');
  await page.locator('#aiInstallKokoro').click();
  await page.waitForFunction(()=>document.getElementById('aiEngineStatus').textContent==='Installed');
  assert.equal(installations,2,'Retry installation is explicit');
  assert.equal(await page.locator('#aiVerificationRow').isVisible(),true);
  await page.waitForFunction(()=>document.getElementById('checkStatus-aiSpeech').textContent==='Engine available');
  assert.equal(checks.at(-1).scope,'speech','Installation completion runs a separate verification');
  // Detection never installs. Both actions remain explicit and independently retryable.
  Object.assign(versionState,{available:true,release:{version:'0.9.0',notes_url:'https://github.com/zorhay/code-gossip/releases/tag/0.9.0'}});
  await page.evaluate(()=>refreshVersions());
  assert((await page.locator('#versionNotice').innerText()).includes('0.8.0 → 0.9.0'));
  assert.equal(updateStarts,0);
  await page.locator('#versionNotice').click();
  failUpdateCheck=true;await page.locator('#checkUpdates').click();
  await page.getByText('GitHub is unavailable',{exact:true}).waitFor();
  assert(await page.locator('#applyUpdate').isEnabled(),'A failed check preserves cached availability');
  failUpdateCheck=false;await page.locator('#checkUpdates').click();
  await page.waitForFunction(()=>document.getElementById('checkUpdates').textContent==='Check for updates');
  assert.equal(updateChecks,2);assert.equal(updateStarts,0);
  for(const width of [390,1280]){
   await page.setViewportSize({width,height:900});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'update-available-'+width+'.png')});
  }
  await page.locator('#applyUpdate').click();await page.waitForFunction(()=>document.getElementById('applyUpdate').textContent==='Updating…');
  assert.equal(updateStarts,1);assert(await page.locator('#closeSoundbar').isDisabled());
  Object.assign(versionState,{running:false,phase:'failed',message:'Update failed. Previous version restored.'});
  await page.evaluate(()=>refreshVersions());assert.equal(await page.locator('#applyUpdate').innerText(),'Retry update');
  Object.assign(versionState,{development:true});await page.evaluate(()=>refreshVersions());
  assert.equal(await page.locator('#applyUpdate').isVisible(),false);
  assert((await page.locator('#updateExplanation').innerText()).startsWith('Development installation'));
  Object.assign(versionState,{development:false,available:false,phase:'done',message:'Updated successfully.'});
  await page.evaluate(()=>refreshVersions());await page.keyboard.press('Escape');
  await page.locator('#settingsButton').click();await page.locator('#closeSoundbar').click();await page.getByText('Could not stop Soundbar',{exact:true}).first().waitFor();assert(await page.locator('#closeSoundbar').isEnabled());
  failShutdown=false;await page.locator('#closeSoundbar').click();await page.locator('#closedDialog[open]').waitFor();await page.keyboard.press('Escape');assert(await page.locator('#closedDialog').isVisible());
  assert.deepEqual(errors,[]);console.log('Soundbar UI passed: draft isolation, explicit activation, failure recovery, previews, check lifecycle, inline errors, Kokoro transparency, phrase voices, mute/reload, keyboard, mobile, shutdown.');
 }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);server.closeAllConnections();server.close();process.exitCode=1;});
