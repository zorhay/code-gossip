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
 narrator_providers: {claude_cli:{name:'Claude CLI',needs_key:false,models:['haiku'],default_model:'haiku'},openai:{name:'OpenAI',needs_key:true,models:[],default_model:'model'}},
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
  const errors=[],writes=[],previews=[],checks=[];let failSave=false,failShutdown=true,installations=0,checkGate=null,releaseCheck,failCheck=false;
  page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.route('**/api/**',async route=>{
   const req=route.request(),endpoint=new URL(req.url()).pathname;
   let reply={ok:true};
   if(endpoint==='/api/status')reply=state;
   else if(endpoint==='/api/setup')reply=state.setup;
   else if(endpoint==='/api/activate'){
    const body=req.postDataJSON();writes.push(body);
    if(failSave)reply={ok:false,error:'Save failed'};
    else {Object.assign(state,body.config,{effects_on:body.enabled&&body.mode==='effects',voice_on:body.enabled&&body.mode!=='effects',soundbar_mode:body.mode});if(body.mode!=='effects')state.voice_profile={clips:'generals',phrases:'senior',ai:'narrator'}[body.mode];if(body.phrases)state.phrases=body.phrases;}
   }else if(endpoint==='/api/config') {const body=req.postDataJSON();writes.push(body);if(failSave)reply={ok:false,error:'Save failed'};else Object.assign(state,body);}
   else if(endpoint==='/api/draft-preview'){previews.push(req.postDataJSON());reply={ok:true,text:'Preview result'};}
   else if(endpoint==='/api/draft-check'){checks.push(req.postDataJSON());if(checkGate)await checkGate;reply=failCheck?{ok:false,error:'Check failed'}:{ok:true,message:'Ready'};}
   else if(endpoint==='/api/kokoro-install'){installations++;state.setup.kokoro=true;state.setup.installing=false;reply={ok:true,status:'done'};}
   else if(endpoint==='/api/kokoro-status')reply={ok:true,status:'done',installed:state.setup.kokoro};
   else if(endpoint==='/api/shutdown'){assert.equal(req.headers()['x-soundbar-request'],'ui');reply={ok:!failShutdown};}
   else throw new Error('Unexpected endpoint: '+endpoint);
   await route.fulfill({json:reply});
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(()=>document.getElementById('statusText').textContent==='Active · Effects · System sounds').catch(async error=>{console.error(await page.locator('body').innerText());throw error;});
  assert.equal(await page.locator('[role=tab]').count(),4);
  assert.equal(await page.locator('table').count(),0);
  assert.equal(await page.locator('#soundPack option').first().getAttribute('value'),'default');
  const tab=async name=>page.getByRole('tab',{name,exact:true}).click();
  assert.equal(await page.locator('#toast,#saveStatus').count(),0,'No transient or duplicate success notifications');
  await page.locator('#setup-effects > summary').click();
  const effectCheck=page.locator('[data-check-setup=effects]');
  assert.equal(await effectCheck.innerText(),'Check');
  checkGate=new Promise(resolve=>releaseCheck=resolve);
  await effectCheck.click();await page.waitForFunction(()=>document.querySelector('[data-check-setup=effects]').textContent==='Checking…');
  assert.equal(await effectCheck.isEnabled(),false);
  releaseCheck();checkGate=null;
  await page.waitForFunction(()=>document.querySelector('[data-check-setup=effects]').textContent==='Checked');
  await page.selectOption('#soundPack','paper');assert.equal(await effectCheck.innerText(),'Check');
  failCheck=true;await effectCheck.click();await page.locator('#setup-effects [role=alert]').waitFor();
  assert.equal(await effectCheck.innerText(),'Check');assert(await effectCheck.isEnabled());
  failCheck=false;await effectCheck.click();await page.waitForFunction(()=>document.querySelector('[data-check-setup=effects]').textContent==='Checked');
  assert.equal(await page.getByText('Check failed',{exact:true}).count(),0);
  assert.equal(writes.length,0);
  assert.equal(await page.locator('#setupStatus-effects').isVisible(),false);
  assert.equal(await page.locator('#setup-effects').getByText('Checked',{exact:true}).filter({visible:true}).count(),1);
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
  failSave=false;await page.locator('#activateSelection').click();await page.waitForFunction(()=>document.getElementById('statusText').textContent.endsWith('Paper'));
  await tab('Phrases');await page.selectOption('#mainAgentVoice','Samantha');await page.selectOption('#subagentVoice','Aman');
  assert.equal(await page.locator('#phraseEditor').getAttribute('open'),null);
  await page.locator('#phraseEditor > summary').click();
  await page.locator('#phraseRows input').first().fill('Please investigate');
  await page.locator('#phraseEditor > summary').click();assert.equal(await page.locator('#phraseRows').isVisible(),false);
  await page.locator('#phraseEditor > summary').click();assert.equal(await page.locator('#phraseRows input').first().inputValue(),'Please investigate');
  await page.locator('#setup-phrases > summary').click();
  failCheck=true;await page.locator('#phraseSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('phraseSpeechCheck').dataset.status==='failed');
  assert.equal(await page.locator('#setupStatus-phrases').innerText(),'Speech check failed');
  assert.equal(await page.locator('#activateSelection').innerText(),'Complete setup');
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
  await page.reload();await page.locator('#tab-phrases[aria-selected=true]').waitFor();assert.equal(await page.locator('#mainAgentVoice').inputValue(),'Samantha');
  const before=writes.length;
  await tab('AI commentary');
  const beforeVoiceCheck=checks.length;await page.locator('#previewAIVoice').click();assert.equal(previews.at(-1).role,'main');assert.equal(checks.length,beforeVoiceCheck);
  await page.locator('#setup-ai > summary').click();await page.selectOption('#provider','openai');await page.locator('#sampleKey').fill('dummy-test-key');await page.locator('#model').fill('test-model');await page.locator('#checkConnection').click();
  await page.waitForFunction(()=>document.getElementById('checkConnection').dataset.status==='checked');
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
  await page.locator('#aiInstallKokoro').click();await page.waitForFunction(()=>document.getElementById('aiInstallKokoro').hidden);assert.equal(installations,1);assert.equal(writes.length,before);
  await page.selectOption('#speaker','af_bella');await page.locator('#checkConnection').click();await page.waitForFunction(()=>document.getElementById('checkConnection').dataset.status==='checked');
  failCheck=true;await page.locator('#aiSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('aiSpeechCheck').dataset.status==='failed');
  assert.equal(await page.locator('#checkConnection').innerText(),'Checked','Speech failure does not invalidate provider');
  assert.equal(await page.locator('#activateSelection').innerText(),'Complete setup');
  assert.equal(checks.at(-1).scope,'speech');
  failCheck=false;await page.locator('#aiSpeechCheck').click();await page.waitForFunction(()=>document.getElementById('aiSpeechCheck').dataset.status==='checked');
  assert.equal(await page.locator('#providerStatus,#aiSpeechStatus,#phraseSpeechStatus').count(),0);
  assert.equal(await page.locator('#setup-aiSpeech').getByText('Checked',{exact:true}).filter({visible:true}).count(),1);
  assert.equal(await page.locator('#setup-ai').getByText('Checked',{exact:true}).filter({visible:true}).count(),1);
  if(process.env.SCREENSHOT_DIR){await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'separate-setups.png'),fullPage:true});}
  await page.locator('#generateCommentary').click();await page.waitForFunction(()=>document.getElementById('commentarySample').textContent==='Preview result');
  assert.equal(previews.at(-1).action,'generate');
  await page.locator('[data-preview=ai]').click();assert.equal(previews.at(-1).config.kokoro_voice,'af_bella');assert.equal(previews.at(-1).text,'Preview result');assert.equal(previews.at(-1).action,'play');
  await page.locator('#soundOn').uncheck();await page.waitForFunction(()=>document.getElementById('powerLabel').textContent==='Sound off');
  await page.locator('#activateSelection').click();await page.waitForFunction(()=>document.getElementById('statusText').textContent.startsWith('Sound off · AI commentary'));
  assert.equal(state.voice_on,false);assert.equal(state.effects_on,false);
  await page.reload();await page.locator('#tab-ai[aria-selected=true]').waitFor();assert.equal(await page.locator('#soundOn').isChecked(),false);
  await page.locator('#soundOn').check();await page.waitForFunction(()=>document.getElementById('powerLabel').textContent==='Sound on');assert.equal(state.voice_on,true);assert.equal(state.effects_on,false);
  await tab('Effects');await page.selectOption('#soundPack','sci-fi');await page.locator('#activateSelection').click();assert(await page.locator('#setup-effects[open]').isVisible());assert.equal(state.soundbar_mode,'ai');
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
  await page.waitForFunction(()=>document.getElementById('aiInstallKokoro').textContent==='Installing…');
  assert(await page.locator('#aiInstallKokoro').isDisabled());
  state.setup.installing=false;state.setup.kokoro=true;state.setup.installMessage='';
  await page.waitForFunction(()=>document.getElementById('aiEngineStatus').textContent==='Installed');
  assert.equal(installations,1,'Reload resumes status polling without another install');
  await page.locator('#settingsButton').click();await page.locator('#closeSoundbar').click();await page.getByText('Could not stop Soundbar',{exact:true}).first().waitFor();assert(await page.locator('#closeSoundbar').isEnabled());
  failShutdown=false;await page.locator('#closeSoundbar').click();await page.locator('#closedDialog[open]').waitFor();await page.keyboard.press('Escape');assert(await page.locator('#closedDialog').isVisible());
  assert.deepEqual(errors,[]);console.log('Soundbar UI passed: draft isolation, explicit activation, failure recovery, previews, check lifecycle, inline errors, Kokoro transparency, phrase voices, mute/reload, keyboard, mobile, shutdown.');
 }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);server.closeAllConnections();server.close();process.exitCode=1;});
