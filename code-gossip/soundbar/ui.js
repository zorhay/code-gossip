'use strict';
const $ = id => document.getElementById(id);
const modeNames = {effects:'Effects', clips:'Clips', phrases:'Phrases', ai:'AI commentary'};
const profileModes = {senior:'phrases', generals:'clips', narrator:'ai'};
let saved, state, activeSelection, setup, voiceChoices, styleNames, packs;
let checkedAI = null, busy = false, savingSound = false, savingVolume = false, installPoll = null;
const setupChecks = {}, errorMessages = new WeakMap();
let setupChecksReady=false,setupCheckTimer=null;
let enabledLayers, mediaBusy=false, generatedSample=null, modelList=null;
const tipsKey='code-gossip.topic-tips.v1';
let tipsState={hidden:false,dismissed:[]},tipScenario=null;
const tipTopics=[
 {id:'profile',title:'Select a profile'},
 {id:'speech',title:'Set up sound engine'},
 {id:'llm',title:'Configure LLM'},
 {id:'phrases',title:'Edit phrases'},
 {id:'preview',title:'Preview & Apply'},
 {id:'settings',title:'Settings'},
];
function scenarioSteps(id){
 const mode=state.viewMode, panel='#panel-'+mode;
 const speechMode=mode==='ai'?'ai':'phrases',prefix=speechMode==='ai'?'ai':'phrase';
 const speechSetup='#setup-'+(speechMode==='ai'?'aiSpeech':'phrases');
 const step=(target,title,text,extra={})=>({target,title,text,...extra});
 const apply=step('#activateSelection','Apply your selection','Apply saves and activates this selection. Green Applied means it matches your saved settings. Browsing and previews leave the active selection unchanged.');
 return {
 profile:[step('.mode-tabs','Choose a category','Effects, recorded Clips, editable Phrases, or AI commentary. Each category offers a different way to hear your agent.'),step(panel+' .customize','Choose your profile','Choose a sound pack, voices, or commentary style here. Clips uses the Generals collection. Your choices remain a draft until you Apply.'),apply],
 speech:[step('#'+(prefix==='ai'?'engine':'phraseEngine'),'Choose a speech engine','macOS speech is built in. Kokoro provides local neural voices and needs a separate installation.',{mode:speechMode,open:speechSetup}),step(speechSetup+' .installation-row','Review installation','Kokoro installs only when you request it. The explanation below lists its downloads and how it runs on your computer. Installation and engine verification are separate states.'),step(speechSetup,'Verify the engine','After installation, the automatic check verifies the engine. Check retries verification; Preview lets you hear the selected voice. Failed verification offers repair for Kokoro.')],
 llm:[step('#provider','Choose a provider','Use your Claude CLI sign-in, a cloud API, or local Ollama. Cloud providers receive event context; Ollama runs locally.',{mode:'ai',open:'#setup-ai'}),step('#model','Select a model','Choose from the live model list or enter a model ID. Cloud APIs also need an API key in the field below; CLI and Ollama do not.'),step('#checkConnection','Check the connection','Check verifies a cloud connection, the Ollama server, or CLI availability. Then Play sample tests generation and speech. Apply activates the configuration.')],
 phrases:[step('#panel-phrases .customize','Choose the voices','Set separate voices for the main agent and subagent. Speech setup below selects the engine.',{mode:'phrases'}),step('#phraseEditor','Edit event phrases','Choose an event in the preview area, then edit its alternatives here. Subagent events have a line for each speaker.',{open:'#phraseEditor'}),step('#panel-phrases .preview-actions','Preview and save','Preview plays the selected alternative using your chosen voices. Apply saves your phrase edits and activates Phrases.')],
 preview:[step(panel+' .audition','Hear the draft','Preview plays the event and alternative shown here. AI Play sample generates and speaks a line; clicking again replays that line.'),apply],
 settings:[step('#reduceRepeats','Reduce repeated sounds','Adjust Effects and Voice gaps to make rapid activity less distracting. These settings save immediately.',{settings:true}),step('#approvalCues','Control approval cues','Enable or disable Codex approval sounds. This changes audio only; agent permissions stay unchanged.')],
 }[id];
}
function startTipScenario(tip){
 if(tipScenario||busy||mediaBusy)return;
 clearTimeout(setupCheckTimer);
 tipScenario={tip,index:0,steps:scenarioSteps(tip.id),mode:state.viewMode,scrollY:scrollY,settingsOpen:$('settingsDialog').open,details:[...document.querySelectorAll('details')].map(el=>[el,el.open])};
 $('topicTips').hidden=true;
 if(tip.id==='settings')$('settingsDialog').showModal();
 $('tipScenario').showModal();renderTipScenario();
}
function renderTipScenario(){
 const step=tipScenario.steps[tipScenario.index];
 if(step.mode)selectMode(step.mode,false);
 if(step.open)document.querySelector(step.open).open=true;
 $('tipScenarioTitle').textContent=step.title;$('tipScenarioText').textContent=step.text;
 $('tipScenarioProgress').textContent=tipScenario.tip.title+' · '+(tipScenario.index+1)+' of '+tipScenario.steps.length;
 $('tipScenarioBack').disabled=tipScenario.index===0;
 $('tipScenarioNext').textContent=tipScenario.index===tipScenario.steps.length-1?'Done':'Next';
 document.querySelector(step.target).scrollIntoView({block:'center',behavior:'instant'});
 positionTipScenario();$('tipScenarioTitle').focus({preventScroll:true});
}
function positionTipScenario(){
 if(!tipScenario)return;
 const target=document.querySelector(tipScenario.steps[tipScenario.index].target),rect=target.getBoundingClientRect(),card=$('tipScenario');
 const width=card.offsetWidth,height=card.offsetHeight,below=rect.bottom+14,above=rect.top-height-14;
 const top=below+height<=innerHeight-16?below:above>=16?above:innerHeight-height-16;
 Object.assign(card.style,{left:Math.max(16,Math.min(rect.right-width,innerWidth-width-16))+'px',top:Math.max(16,top)+'px'});
 Object.assign($('tipScenarioHighlight').style,{left:Math.max(2,rect.left-4)+'px',top:rect.top-4+'px',width:Math.min(innerWidth-4,rect.width+8)+'px',height:rect.height+8+'px'});
}
function closeTipScenario(){
 if(!tipScenario)return;
 const previous=tipScenario;
 $('tipScenario').close();
 if(!previous.settingsOpen)$('settingsDialog').close();
 selectMode(previous.mode,false);previous.details.forEach(([el,open])=>el.open=open);
 tipScenario=null;renderTips();window.scrollTo({top:previous.scrollY,behavior:'instant'});
 document.querySelector('[data-topic="'+previous.tip.id+'"] .topic-tip-start').focus({preventScroll:true});
}
function saveTips(){try{localStorage.setItem(tipsKey,JSON.stringify(tipsState));}catch{}}
function renderTips(){
 const visible=tipTopics.filter(tip=>!tipsState.dismissed.includes(tip.id));
 $('topicTips').hidden=tipsState.hidden||!visible.length;
 $('helpButton').setAttribute('aria-expanded',String(!$('topicTips').hidden));
 for(const tip of tipTopics)document.querySelector('[data-topic="'+tip.id+'"]').hidden=tipsState.dismissed.includes(tip.id);
}
function mountTips(){
 try{const stored=JSON.parse(localStorage.getItem(tipsKey));if(stored&&Array.isArray(stored.dismissed))tipsState={hidden:stored.hidden===true,dismissed:stored.dismissed.filter(id=>tipTopics.some(tip=>tip.id===id))};}catch{}
 for(const tip of tipTopics){
  const card=document.createElement('section');card.className='topic-tip';card.dataset.topic=tip.id;
  const heading=document.createElement('div');heading.className='topic-tip-heading';
  const start=document.createElement('button');start.className='topic-tip-start';start.textContent=tip.title;start.setAttribute('aria-haspopup','dialog');start.setAttribute('aria-controls','tipScenario');start.onclick=()=>startTipScenario(tip);
  const dismiss=document.createElement('button');dismiss.className='topic-tip-dismiss';dismiss.textContent='×';dismiss.setAttribute('aria-label','Dismiss '+tip.title+' tip');
  dismiss.onclick=()=>{tipsState.dismissed.push(tip.id);saveTips();renderTips();$('helpButton').focus();};
  heading.append(start,dismiss);card.append(heading);$('topicTips').append(card);
 }
 renderTips();
}
function toggleTips(){
 if($('topicTips').hidden){tipsState.hidden=false;tipsState.dismissed=[];}else{tipsState.hidden=true;}
 saveTips();renderTips();
}
const sampleSelections={effects:{event:'edit',variant:0},clips:{event:'edit',variant:0}};
const eventLabel=value=>value.replaceAll('_',' ').replace(/^./,letter=>letter.toUpperCase());
function mountSpeechSetups(){
 document.querySelectorAll('[data-speech-setup]').forEach(host=>{
  const prefix=host.dataset.speechSetup,fragment=$('speechSetupTemplate').content.cloneNode(true);
  fragment.querySelectorAll('[data-part]').forEach(element=>{
   const part=element.dataset.part;
   element.id=part==='Engine'?(prefix==='phrase'?'phraseEngine':'engine'):prefix+part;
  });
  fragment.querySelector('label').htmlFor=prefix==='phrase'?'phraseEngine':'engine';
  const check=fragment.querySelector('[data-part=SpeechCheck]');
  check.dataset.checkSetup=prefix==='phrase'?'phrases':'aiSpeech';
  host.append(fragment);
 });
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || data.message || 'Request failed');
  return data;
}
function errorAnchor(target) {
  return target.closest('.preview-actions,.setup-row,.preference,.volume-bar,.topbar') || target;
}
function clearError(target) {errorMessages.get(errorAnchor(target))?.remove();}
function showError(message,target) {
  const anchor=errorAnchor(target);clearError(target);
  const text=document.createElement('p');text.className='inline-error';text.setAttribute('role','alert');text.textContent=message;
  anchor.insertAdjacentElement('afterend',text);errorMessages.set(anchor,text);
}
async function action(work,target=document.activeElement) {
  clearError(target);
  try { return await work(); } catch(error) { showError(error.message,target); return null; }
}
function options(id, entries, selected) {
  $(id).replaceChildren(...entries.map(([value,label])=>new Option(label,value)));
  if (selected && !entries.some(([value])=>value===selected)) $(id).add(new Option(selected+' (unavailable)',selected));
  $(id).value=selected || entries[0]?.[0] || '';
}
function labelOfVoice(engine,voice) {return voiceChoices[engine].find(([id])=>id===voice)?.[1] || voice;}
function needsKey(){return !!saved.narrator_providers[state.provider]?.needs_key;}
function connectionIdentity(){return JSON.stringify([state.provider,state.model,state.apiKey]);}
function aiIdentity(){return connectionIdentity();}
function speechIdentity(mode){
 const engine=mode==='phrases'?state.phraseEngine:state.engine;
 return JSON.stringify([engine,mode==='phrases'?state.phraseVoices[engine]:state.voices[engine]]);
}
function sampleIdentity(){return JSON.stringify([connectionIdentity(),state.style]);}
function speechReadiness(mode){
 const engine=mode==='phrases'?state.phraseEngine:state.engine;
 const installation=speechInstallation(engine);
 if(!installation.available)return {ready:false,message:installation.message};
 const voices=mode==='phrases'?Object.values(state.phraseVoices[engine]):[state.voices[engine]];
 if(voices.some(voice=>!voiceChoices[engine].some(([id])=>id===voice)))return {ready:false,message:'Choose installed voices'};
 const check=setupChecks[mode==='phrases'?'phrases':'aiSpeech'];
 const current=check?.identity===speechIdentity(mode);
 if(current&&check.status==='failed')return {ready:false,message:'Check failed'};
 if(current&&check.status==='checking')return {ready:false,message:'Checking speech…'};
 return {ready:true,message:current&&check.status==='checked'?'Engine available':'Not checked'};
}
function selectionDraft(mode=state.viewMode) {
  if(mode==='effects')return {mode,pack:state.pack};
  if(mode==='clips')return {mode,profile:'generals'};
  if(mode==='phrases')return {mode,engine:state.phraseEngine,voices:structuredClone(state.phraseVoices[state.phraseEngine]),phrases:structuredClone(state.phrases)};
  return {mode,style:state.style,engine:state.engine,voice:state.voices[state.engine],provider:state.provider,model:state.model,context:state.context,apiKey:state.apiKey};
}
function selectionLabel(selection) {
  if(selection.mode==='combined') return 'Effects + '+modeNames[profileModes[saved.voice_profile]];
  if(selection.mode==='effects')return 'Effects · '+(packs[selection.pack] || selection.pack);
  if(selection.mode==='clips')return 'Clips · Generals';
  if(selection.mode==='phrases')return 'Phrases · Senior';
  return 'AI commentary · '+(styleNames[selection.style] || selection.style);
}
function draftConfig(mode=state.viewMode) {
  if(mode==='effects')return {effects_profile:state.pack};
  if(mode==='clips')return {};
  const engine=mode==='phrases'?state.phraseEngine:state.engine;
  const config={tts_engine:engine};
  if(mode==='phrases') {
    const voices=state.phraseVoices[engine];
    Object.assign(config,engine==='kokoro'?{kokoro_voice:voices.main,kokoro_voice_sub:voices.sub}:{voice_main:voices.main,voice_sub:voices.sub});
  } else {
    config[engine==='kokoro'?'kokoro_voice':'voice_main']=state.voices[engine];
    Object.assign(config,{narrator_provider:state.provider,narrator_model:state.model,narrator_style:state.style,narrator_deep_context:state.context});
    if(state.apiKey || state.provider!==saved.narrator_provider)config.narrator_api_key=state.apiKey;
  }
  return config;
}
function setupReadiness(mode) {
  if(mode==='effects'||mode==='clips'){
    const available=mode==='effects'?setup.effects[state.pack]:setup.clips.generals;
    if(!available?.ready)return available||{ready:false,message:'Audio unavailable'};
    const check=setupChecks[mode],current=check?.identity===checkIdentity(mode);
    if(current&&check.status==='failed')return {ready:false,message:'Check failed'};
    if(current&&check.status==='checking')return {ready:false,message:'Checking…'};
    return {ready:true,message:current&&check.status==='checked'?'Audio available':'Not checked'};
  }
  const speech=speechReadiness(mode);
  if(!speech.ready)return speech;
  if(mode==='ai'&&checkedAI!==aiIdentity())return {ready:false,message:'Check connection'};
  return speech;
}
function openSetup(mode,scope) {
 const key=mode==='ai'&&(scope==='speech'||(!scope&&!speechReadiness('ai').ready))?'aiSpeech':mode;
 const panel=$('setup-'+key);panel.open=true;panel.querySelector('summary').focus();
}
function updateActivation() {
  if(!state)return;
  const draft=selectionDraft(), same=JSON.stringify(draft)===JSON.stringify(activeSelection);
  const checking=modeCheckKeys().some(key=>setupChecks[key]?.status==='checking');
  const readiness=setupReadiness(state.viewMode);
  $('activateSelection').disabled=busy || mediaBusy || savingSound || savingVolume || same || checking || !readiness.ready;
  $('soundOn').disabled=busy || mediaBusy || savingSound;
  $('volume').disabled=busy || mediaBusy || savingVolume;
  $('activateSelection').textContent=same?'Applied':'Apply';
  $('activateSelection').classList.toggle('applied',same);
  $('activateSelection').setAttribute('aria-busy',String(busy));
  const blocked=!same&&!busy&&!mediaBusy&&!readiness.ready&&!checking;
  $('activationHelp').hidden=!blocked;
  $('activationReason').textContent=blocked?readiness.message:'';
  $('activationProgress').textContent=busy?'Saving selection…':'';
}
function updateStatus() {
  $('powerLabel').textContent=state.enabled?'Sound on':'Sound off';$('soundOn').checked=state.enabled;
  $('statusText').textContent=(state.enabled?'Active · ':'Sound off · ')+selectionLabel(activeSelection);
  $('modeStatus').classList.toggle('muted',!state.enabled);updateActivation();
}
function selectMode(mode,check=true) {
  if(!Object.hasOwn(modeNames,mode))return;
  const button=$('activateSelection'),slot=document.querySelector('[data-activation-slot="'+mode+'"]');
  if(button.parentElement!==slot){clearError(button);slot.append(button);}
  slot.after($('activationHelp'),$('activationProgress'));
  state.viewMode=mode;
  for(const key of Object.keys(modeNames)){const selected=key===mode;$('tab-'+key).setAttribute('aria-selected',String(selected));$('tab-'+key).tabIndex=selected?0:-1;$('panel-'+key).hidden=!selected;}
  updateActivation();if(check)scheduleSetupChecks(0);
}
async function activateSelection() {
  if(busy||mediaBusy||savingSound||savingVolume)return;
  if(!setupReadiness(state.viewMode).ready){openSetup(state.viewMode);return;}
  const draft=selectionDraft(),config=draftConfig(),mode=state.viewMode;
  busy=true;clearError($('activateSelection'));updateActivation();
  try {
    await api('/api/activate',{mode,enabled:state.enabled,config,...(mode==='phrases'?{phrases:draft.phrases}:{})});
    Object.assign(saved,config,{soundbar_mode:mode,effects_on:state.enabled&&mode==='effects',voice_on:state.enabled&&mode!=='effects'});
    if(mode!=='effects')saved.voice_profile={clips:'generals',phrases:'senior',ai:'narrator'}[mode];
    if(mode==='phrases')saved.phrases=structuredClone(draft.phrases);
    activeSelection=draft;
    enabledLayers={effects_on:mode==='effects',voice_on:mode!=='effects'};
  } catch(error) {showError(error.message,$('activateSelection'));} finally {busy=false;updateStatus();}
}
function catalog(mode){return mode==='effects'?saved.preview_catalog.effects[state.pack]:saved.preview_catalog.voice.generals;}
function renderAudioSample(mode){
 const events=catalog(mode)||{},selection=sampleSelections[mode],keys=Object.keys(events);
 if(!keys.includes(selection.event)){selection.event=keys.includes('edit')?'edit':keys[0];selection.variant=0;}
 options(mode+'Event',keys.map(event=>[event,eventLabel(event)]),selection.event);
 const samples=events[selection.event]||[];
 if(selection.variant>=samples.length)selection.variant=0;
 options(mode+'Variant',samples.map((sample,index)=>[String(index),'Alternative '+(index+1)]),String(selection.variant));
 $(mode+'VariantField').hidden=samples.length<2;
 $(mode+'Event').disabled=!keys.length;
 $(mode+'Sample').textContent=samples[selection.variant]||'Silent · no audio for this pack';
 updatePreviewControls();
}
function renderPack(){renderAudioSample('effects');}
function renderStyle(){
 if(generatedSample?.identity!==sampleIdentity())generatedSample=null;
 $('commentarySample').textContent=generatedSample?.text||'';
 $('commentarySample').hidden=!generatedSample;
 updatePreviewControls();
}
function renderSpeakers() {options('speaker',voiceChoices[state.engine],state.voices[state.engine]);}
function phraseRoles(event){return event==='subagent_start'?['main','sub']:event==='subagent_stop'?['sub','main']:['main'];}
function phraseVoiceName(role){return labelOfVoice(state.phraseEngine,state.phraseVoices[state.phraseEngine][role]);}
function renderPhraseVoices(){for(const [role,id] of [['main','mainAgentVoice'],['sub','subagentVoice']])options(id,voiceChoices[state.phraseEngine],state.phraseVoices[state.phraseEngine][role]);updatePhrasePreview();}
function updatePhrasePreview(){
 const items=state.phrases[state.phraseEvent]||[];
 state.phraseIndex=Math.min(state.phraseIndex,Math.max(0,items.length-1));
 const phrase=items[state.phraseIndex],roles=phraseRoles(state.phraseEvent);
 options('phraseVariant',items.map((item,index)=>[String(index),'Alternative '+(index+1)]),String(state.phraseIndex));
 $('phraseVariant').disabled=!items.length;
 $('phrasePreviewCopy').textContent=phrase===undefined?'No phrases for this event.':(Array.isArray(phrase)?phrase:[phrase]).map((text,i)=>(roles[i]==='main'?'Main agent':'Subagent')+' · '+phraseVoiceName(roles[i])+': “'+text+'”').join('\n');
 $('phraseEditorTitle').textContent=eventLabel(state.phraseEvent)+' · Alternatives';
 [...$('phraseRows').children].forEach((row,index)=>row.classList.toggle('selected',index===state.phraseIndex));
 updatePreviewControls();
}
function updatePhrase(event,index,part,text){const items=state.phrases[event];if(Array.isArray(items[index]))items[index][part]=text;else items[index]=text;updatePhrasePreview();}
function addPhrase(){state.phrases[state.phraseEvent].push(phraseRoles(state.phraseEvent).length===2?['','']:'');state.phraseIndex=state.phrases[state.phraseEvent].length-1;renderPhraseEditor();$('phraseRows').lastElementChild.querySelector('input').focus();updateActivation();}
function removePhrase(index){state.phrases[state.phraseEvent].splice(index,1);renderPhraseEditor();const rows=$('phraseRows').children;(rows[Math.min(index,rows.length-1)]?.querySelector('input')||$('addPhrase')).focus();updateActivation();}
function renderPhraseEditor(){
 const event=state.phraseEvent,roles=phraseRoles(event),items=state.phrases[event];
 $('phraseEventHint').textContent=roles.length===2?(event==='subagent_start'?'Main agent speaks first; the subagent replies.':'Subagent reports back; the main agent responds.'):'Spoken by the main agent.';
 $('addPhrase').textContent=roles.length===2?'+ Add exchange':'+ Add phrase';$('phraseRows').replaceChildren();
 items.forEach((item,index)=>{const row=document.createElement('div');row.className='phrase-edit-row'+(roles.length===1?' single':'');
 (Array.isArray(item)?item:[item]).forEach((text,part)=>{const label=document.createElement('label');label.className='phrase-input';const caption=document.createElement('span');caption.textContent=(roles[part]==='main'?'Main agent':'Subagent')+' · '+(index+1);const input=document.createElement('input');input.type='text';input.value=text;input.placeholder='Write a phrase…';input.oninput=()=>updatePhrase(event,index,part,input.value);label.append(caption,input);row.append(label);});
 const play=document.createElement('button');play.className='quiet-button row-preview';play.textContent='▶';play.setAttribute('aria-label','Preview alternative '+(index+1));play.onclick=()=>{state.phraseIndex=index;updatePhrasePreview();preview('phrases',null,play);};row.append(play);
 const remove=document.createElement('button');remove.className='quiet-button row-remove';remove.textContent='×';remove.setAttribute('aria-label','Remove '+(roles.length===2?'exchange ':'phrase ')+(index+1));remove.onclick=()=>removePhrase(index);row.append(remove);$('phraseRows').append(row);});updatePhrasePreview();
}
function updatePreviewControls(){
 if(!state)return;
 for(const mode of ['effects','clips','phrases','ai']){
  const button=document.querySelector('[data-preview="'+mode+'"]');
  const empty=mode==='ai'?false:mode==='phrases'?!state.phrases[state.phraseEvent]?.length:!Object.keys(catalog(mode)||{}).length;
  button.disabled=mediaBusy||empty;
 }
 for(const id of ['previewMainAgent','previewSubagent','previewAIVoice'])$(id).disabled=mediaBusy;
 document.querySelectorAll('.row-preview').forEach(button=>button.disabled=mediaBusy);
}
async function mediaAction(button,label,work){
 if(mediaBusy)return;
 const original=button.textContent;mediaBusy=true;button.textContent=label;button.setAttribute('aria-busy','true');
 updatePreviewControls();updateActivation();
 const fields=[...document.querySelectorAll('.mode-panel input,.mode-panel select,.row-remove,#addPhrase')].filter(element=>!element.disabled);
 fields.forEach(element=>element.disabled=true);
 try{await action(work,button);}finally{
  fields.forEach(element=>element.disabled=false);mediaBusy=false;button.textContent=original;button.setAttribute('aria-busy','false');
  updatePhrasePreview();renderSetup();updatePreviewControls();updateActivation();
 }
}
async function preview(mode,role,button) {
 const readiness=['phrases','ai'].includes(mode)?speechReadiness(mode):setupReadiness(mode);
 if(!readiness.ready){openSetup(mode,['ai','phrases'].includes(mode)?'speech':undefined);return;}
 if(mode==='ai'&&!role){await playCommentarySample(button);return;}
 const config=draftConfig(mode);
 const body={mode,config,role,event:mode==='phrases'?state.phraseEvent:sampleSelections[mode]?.event,
  variant:mode==='phrases'?state.phraseIndex:sampleSelections[mode]?.variant,
  ...(mode==='phrases'&&!role?{phrases:state.phrases}:{}),...(mode==='ai'&&!role?{action:'play',text:generatedSample?.text}:{} )};
 await mediaAction(button,'Playing…',()=>api('/api/draft-preview',body));
}
async function playCommentarySample(button){
 if(!generatedSample&&checkedAI!==aiIdentity()){openSetup('ai','provider');return;}
 const identity=sampleIdentity(),config=draftConfig('ai');
 await mediaAction(button,generatedSample?'Playing…':'Generating…',async()=>{
  if(!generatedSample){
   const result=await api('/api/draft-preview',{mode:'ai',action:'generate',config});
   if(identity!==sampleIdentity())return;
   generatedSample={identity,text:result.text};renderStyle();
  }
  button.textContent='Playing…';
  await api('/api/draft-preview',{mode:'ai',action:'play',config,text:generatedSample.text});
 });
}
function renderSetup(){
 if(!state)return;
 const effect=setup.effects[state.pack] || {};
 $('effectsRequirement').textContent=effect.sox?'SoX':state.pack==='default'?'macOS sounds':'Audio files';
 $('effectsRequirementDetail').textContent=effect.missing?.length?'Missing: '+effect.missing.join(', '):'';
 $('soxInfo').hidden=!effect.sox;$('installSox').hidden=!effect.sox||effect.ready;
 for(const [prefix,engine] of [['phrase',state.phraseEngine],['ai',state.engine]]){
  const kokoro=engine==='kokoro',installation=speechInstallation(engine);$(prefix+'EngineName').textContent=kokoro?'Installation':'Availability';
  $(prefix+'EngineDetail').textContent=kokoro?(setup.installing||setup.installStatus==='error'?setup.installMessage:'Local speech · ~1.5 GB environment'):'';
  $(prefix+'EngineDetail').hidden=!kokoro;
  $(prefix+'EngineStatus').textContent=installation.message;$(prefix+'EngineStatus').dataset.tone=installation.tone;
  $(prefix+'VerificationRow').hidden=!installation.available;
  $(prefix+'KokoroInfo').hidden=!kokoro;
  const key=prefix==='phrase'?'phrases':'aiSpeech',repair=setupChecks[key]?.status==='failed';
  $(prefix+'InstallKokoro').textContent=setup.installStatus==='error'?'Retry installation':repair?'Repair installation':'Install Kokoro';
  $(prefix+'InstallKokoro').hidden=!kokoro||(setup.kokoro&&!repair)||setup.installing;$(prefix+'InstallKokoro').disabled=!!setup.installing;
 }
 $('providerHint').textContent=state.provider==='claude_cli'?'Checks that Claude CLI is installed. Play a sample to test sign-in and model access.':state.provider==='ollama'?'Checks the local server. Play a sample to test the selected model.':saved.narrator_providers[state.provider]?.description || '';
 $('providerCheckLabel').textContent=state.provider==='claude_cli'?'CLI availability':state.provider==='ollama'?'Local server':'Connection';
 $('keyField').hidden=!needsKey();
 $('closeSoundbar').disabled=!!setup.installing;
 $('closeInstallHint').hidden=!setup.installing;
 renderChecks();renderStyle();updateActivation();
}
async function refreshSetup() {setup={...setup,...await api('/api/setup')};renderSetup();}
const checkModes={effects:'effects',clips:'clips',phrases:'phrases',aiSpeech:'ai',ai:'ai'};
function checkButton(key){return key==='ai'?$('checkConnection'):document.querySelector('[data-check-setup="'+key+'"]');}
function checkIdentity(key){
 if(key==='ai')return aiIdentity();
 if(key==='phrases'||key==='aiSpeech')return speechIdentity(checkModes[key]);
 return JSON.stringify(draftConfig(checkModes[key]));
}
function mountCheckStatuses(){
 for(const key of Object.keys(checkModes)){
  const button=checkButton(key),group=document.createElement('div'),status=document.createElement('span');
  group.className='setup-check-row';status.className='setup-check-status';status.id='checkStatus-'+key;
  status.setAttribute('role','status');button.setAttribute('aria-describedby',status.id);
  button.before(group);group.append(button,status);
 }
}
function speechInstallation(engine){
 if(engine==='say')return {available:setup.say,message:setup.say?'Built into macOS':'Unavailable',tone:setup.say?'neutral':'error'};
 if(setup.installing)return {available:false,message:'Installing…',tone:'warning'};
 if(setup.installStatus==='error')return {available:false,message:'Installation failed',tone:'error'};
 return {available:setup.kokoro,message:setup.kokoro?'Installed':'Not installed',tone:setup.kokoro?'success':'warning'};
}
function checkPresentation(key){
 const check=setupChecks[key],current=check?.identity===checkIdentity(key),status=current?check.status:'unchecked';
 const provider=key==='ai',cli=provider&&state.provider==='claude_cli';
 const action=provider?(cli?'Check CLI':'Check connection'):'Check';
 const pending=provider&&!cli?'Connecting…':'Checking…';
 const success=provider?(cli?'CLI found':state.provider==='ollama'?'Server reachable':'Connection verified'):key==='effects'||key==='clips'?'Audio available':'Engine available';
 const failure=provider&&!cli?'Connection failed':'Check failed';
 let prerequisite=null;
 if(provider&&!hasProviderKey())prerequisite={message:'API key required',tone:'warning'};
 if(key==='effects'||key==='clips'){
  const resource=key==='effects'?setup.effects[state.pack]:setup.clips.generals;
  if(!resource?.ready)prerequisite={message:resource?.message||'Audio unavailable',tone:resource?.missing?.length?'error':'warning'};
 }
 if(key==='phrases'||key==='aiSpeech'){
  const mode=checkModes[key],installation=speechInstallation(mode==='phrases'?state.phraseEngine:state.engine);
  if(!installation.available)prerequisite=installation;
  else if(!speechReadiness(mode).ready&&status!=='failed'&&status!=='checking')prerequisite={message:'Choose installed voices',tone:'warning'};
 }
 const result={message:status==='checked'?success:status==='failed'?failure:status==='checking'?pending:provider&&!cli?'Not tested':'Not checked',tone:status==='checked'?'success':status==='failed'?'error':'warning'};
 return {action,pending,status,checking:check?.status==='checking',prerequisite,...(prerequisite||result)};
}
function renderChecks(){
 for(const key of Object.keys(checkModes)){
  const button=checkButton(key),view=checkPresentation(key);
  button.textContent=view.checking?view.pending:view.action;
  button.disabled=view.checking||!!view.prerequisite&&!['effects','clips'].includes(key);button.setAttribute('aria-busy',String(view.checking));
  button.title=key==='phrases'||key==='aiSpeech'?'Checks speech dependencies. Use Preview to hear the selected voice.':'';
  button.dataset.status=view.checking?'checking':view.status;
  const result=$('checkStatus-'+key);result.dataset.status=view.status;result.dataset.tone=view.tone;
  result.textContent=view.message;result.hidden=view.checking&&!view.prerequisite;
  const summary=$('setupStatus-'+key);summary.textContent=view.message;summary.dataset.tone=view.tone;
  if(setupChecks[key]&&view.status==='unchecked'&&!view.checking)clearError(button);
 }
}
function modeCheckKeys(){return state.viewMode==='ai'?['aiSpeech','ai']:[state.viewMode];}
function scheduleSetupChecks(delay=150){
 if(!setupChecksReady||tipScenario)return;
 clearTimeout(setupCheckTimer);
 const run=()=>{
  if(tipScenario)return;
  for(const key of modeCheckKeys()){
   const check=setupChecks[key];
   if(check?.status==='checking'||check?.identity===checkIdentity(key)||checkPresentation(key).prerequisite)continue;
   checkSetup(key);
  }
 };
 if(delay)setupCheckTimer=setTimeout(run,delay);else run();
}
async function checkSetup(key) {
 if(setupChecks[key]?.status==='checking'||checkPresentation(key).prerequisite&&!['effects','clips'].includes(key))return;
 const mode=checkModes[key],config=draftConfig(mode),identity=checkIdentity(key),button=checkButton(key);
 const check=setupChecks[key]={identity,status:'checking'};
 if(key==='ai')checkedAI=null;
 clearError(button);renderSetup();
 try{
  await refreshSetup();
  await api('/api/draft-check',{mode,config,scope:key==='ai'?'provider':'speech'});
  check.status='checked';
  if(identity===checkIdentity(key)&&key==='ai'){checkedAI=identity;refreshModels();}
 }catch(error){
  check.status='failed';
  if(identity===checkIdentity(key)){
   if(key==='ai')checkedAI=null;
   showError(error.message,button);
  }
 }finally{renderSetup();if(identity!==checkIdentity(key))scheduleSetupChecks();}
}
async function installKokoro(target){
 if(setup.installing)return;
 const repair=!!setup.kokoro||['phrases','aiSpeech'].some(key=>setupChecks[key]?.status==='failed');
 for(const key of ['phrases','aiSpeech']){delete setupChecks[key];clearError(checkButton(key));}
 clearError(target);setup.installing=true;setup.installStatus='running';setup.installMessage='';renderSetup();
 try{
  const result=await api('/api/kokoro-install',{repair});setup.installing=result.status==='running';
  await pollInstall();
 }catch(error){
  setup.installing=false;setup.installStatus='error';setup.installMessage=error.message;
 }finally{renderSetup();}
}
async function pollInstall(){
 clearTimeout(installPoll);
 try{
  await refreshSetup();
  if(setup.installing)installPoll=setTimeout(pollInstall,2000);
  else scheduleSetupChecks();
 }catch(error){
  for(const prefix of ['phrase','ai'])showError(error.message,$(prefix+'InstallKokoro'));
  installPoll=setTimeout(pollInstall,5000);
 }
}
async function saveConfig(changes){await api('/api/config',changes);Object.assign(saved,changes);}
async function toggleSound(){
 const enabled=$('soundOn').checked;savingSound=true;updateActivation();
 const changes={effects_on:enabled&&enabledLayers.effects_on,voice_on:enabled&&enabledLayers.voice_on,soundbar_mode:activeSelection.mode};
 await action(async()=>{await saveConfig(changes);state.enabled=enabled;});savingSound=false;updateStatus();
}
async function closeSoundbar(){
 if(setup.installing)return;
 const button=$('closeSoundbar');button.disabled=true;
 const result=await action(async()=>{const response=await fetch('/api/shutdown',{method:'POST',headers:{'X-Soundbar-Request':'ui'}});if(!response.ok||!(await response.json()).ok)throw new Error('Could not stop Soundbar');clearTimeout(installPoll);clearTimeout(setupCheckTimer);$('settingsDialog').close();$('closedDialog').showModal();$('closedTitle').focus();return true;});
 if(!result)button.disabled=false;
}
function modelListIdentity(){return JSON.stringify([state.provider,state.apiKey]);}
function hasProviderKey(){return !needsKey()||!!state.apiKey.trim()||state.provider===saved.narrator_provider&&!!saved.narrator_api_key;}
function renderModelList(){
 const current=modelList?.identity===modelListIdentity()?modelList:null;
 $('modelChoices').replaceChildren(...(current?.models||[]).map(name=>new Option(name,name)));
 $('refreshModels').disabled=current?.status==='loading'||!hasProviderKey()||current?.supported===false;
 $('refreshModels').setAttribute('aria-busy',String(current?.status==='loading'));
 $('modelStatus').dataset.status=current?.status||'idle';
 $('modelStatus').textContent=current?.message||(!hasProviderKey()?'Enter an API key to load models.':'Suggestions load from your provider.');
}
async function refreshModels(force=false){
 if(!hasProviderKey()){renderModelList();return;}
 const identity=modelListIdentity();
 if(modelList?.identity===identity&&(modelList.status==='loading'||!force&&modelList.status==='loaded'))return;
 const request=modelList={identity,status:'loading',models:[],message:'Loading available models…'};
 renderModelList();
 const config={narrator_provider:state.provider};
 if(state.apiKey||state.provider!==saved.narrator_provider)config.narrator_api_key=state.apiKey;
 try{
  const result=await api('/api/narrator-models',{config});
  if(modelList!==request||identity!==modelListIdentity())return;
  Object.assign(request,{status:'loaded',models:result.models,supported:result.supported,
   message:result.message||(result.models.length?result.models.length+' models available':'No models available. Refresh after adding access or installing a model.')});
 }catch(error){
  if(modelList!==request||identity!==modelListIdentity())return;
  Object.assign(request,{status:'failed',models:[],message:error.message});
 }
 renderModelList();
}
function renderProvider(){
 $('model').placeholder='Provider default';
 modelList=null;renderModelList();
 $('sampleKey').placeholder=state.provider===saved.narrator_provider&&saved.narrator_api_key?'Key saved — enter to replace':'Enter API key';
 if($('setup-ai').open)refreshModels();
}
async function load(){
 saved=await api('/api/status'); setup=saved.setup;
 packs=Object.fromEntries(Object.keys(saved.effects_profiles).sort((a,b)=>Number(b==='default')-Number(a==='default')).map(name=>[name,name==='default'?'System sounds':name.charAt(0).toUpperCase()+name.slice(1)]));
 styleNames=Object.fromEntries(Object.entries(saved.narrator_styles).map(([id,s])=>[id,s.label || id]));
 voiceChoices={say:saved.voices.map(v=>[v.name,v.name]),kokoro:saved.kokoro_voices.map(v=>[v.id,v.name])};
 const mode=saved.effects_on&&saved.voice_on?'combined':saved.voice_on?profileModes[saved.voice_profile]:saved.effects_on?'effects':saved.soundbar_mode || 'effects';
 const viewMode=mode==='combined'?profileModes[saved.voice_profile]:mode;
 enabledLayers=mode==='combined'?{effects_on:true,voice_on:true}:{effects_on:mode==='effects',voice_on:mode!=='effects'};
 state={viewMode,enabled:saved.effects_on||saved.voice_on,volume:mode==='effects'||mode==='combined'?saved.effects_volume:saved.voice_volume,
 pack:saved.effects_profile,style:saved.narrator_style,engine:saved.tts_engine,voices:{say:saved.voice_main,kokoro:saved.kokoro_voice},
 provider:saved.narrator_provider,model:saved.narrator_model,apiKey:'',context:saved.narrator_deep_context,
 phraseEvent:'subagent_start',phraseIndex:0,phraseEngine:saved.tts_engine,phraseVoices:{say:{main:saved.voice_main,sub:saved.voice_sub},kokoro:{main:saved.kokoro_voice,sub:saved.kokoro_voice_sub || 'am_adam'}},
 phrases:Object.fromEntries(saved.events.map(event=>[event,structuredClone(saved.phrases[event] || [])]))};
 activeSelection=mode==='combined'?{mode}:selectionDraft(mode);
 options('soundPack',Object.entries(packs),state.pack);renderPack();
 renderAudioSample('clips');options('commentaryStyle',Object.entries(styleNames),state.style);renderStyle();renderSpeakers();
 options('provider',Object.entries(saved.narrator_providers).map(([id,p])=>[id,p.name]),state.provider);
 $('model').value=state.model;renderProvider();$('engine').value=state.engine;$('phraseEngine').value=state.phraseEngine;
 options('phraseEvent',saved.events.map(event=>[event,eventLabel(event)]),state.phraseEvent);renderPhraseVoices();renderPhraseEditor();
 $('sessionContext').checked=state.context;$('volume').value=state.volume;$('volumeValue').textContent=state.volume+'%';
 $('reduceRepeats').checked=saved.sound_spacing_on;$('approvalCues').checked=saved.codex_permission_sound_on;
 for(const [id,key] of [['effectsGap','effects_cooldown_ms'],['voiceGap','voice_cooldown_ms']]){$(id).value=saved[key];$(id).disabled=!saved.sound_spacing_on;$(id+'Value').textContent=(saved[key]/1000)+'s';}
 selectMode(state.viewMode);renderSetup();updateStatus();if(setup.installing)installPoll=setTimeout(pollInstall,0);
}
function wire(){
 $('tipScenarioClose').onclick=closeTipScenario;
 $('tipScenario').oncancel=event=>{event.preventDefault();closeTipScenario();};
 $('tipScenarioBack').onclick=()=>{if(tipScenario.index>0){tipScenario.index--;renderTipScenario();}};
 $('tipScenarioNext').onclick=()=>{if(tipScenario.index===tipScenario.steps.length-1)closeTipScenario();else{tipScenario.index++;renderTipScenario();}};
 window.addEventListener('resize',positionTipScenario);window.addEventListener('scroll',positionTipScenario,{passive:true});
 $('openSelectionSetup').onclick=()=>openSetup(state.viewMode);
 document.querySelectorAll('[data-mode]').forEach(button=>{button.onclick=()=>selectMode(button.dataset.mode);button.onkeydown=e=>{const keys=Object.keys(modeNames);let index=keys.indexOf(state.viewMode);if(e.key==='ArrowRight')index=(index+1)%keys.length;else if(e.key==='ArrowLeft')index=(index+keys.length-1)%keys.length;else if(e.key==='Home')index=0;else if(e.key==='End')index=keys.length-1;else return;e.preventDefault();selectMode(keys[index]);$('tab-'+keys[index]).focus();};});
 document.querySelectorAll('[data-preview]').forEach(button=>button.onclick=()=>preview(button.dataset.preview,null,button));
 document.querySelectorAll('[data-check-setup]').forEach(button=>button.onclick=()=>checkSetup(button.dataset.checkSetup));
 $('phraseVariant').onchange=e=>{state.phraseIndex=Number(e.target.value);updatePhrasePreview();};
 $('phraseEvent').onchange=e=>{state.phraseEvent=e.target.value;state.phraseIndex=0;renderPhraseEditor();};
 $('phraseEngine').onchange=e=>{state.phraseEngine=e.target.value;renderPhraseVoices();};
 $('mainAgentVoice').onchange=e=>{state.phraseVoices[state.phraseEngine].main=e.target.value;updatePhrasePreview();};
 $('subagentVoice').onchange=e=>{state.phraseVoices[state.phraseEngine].sub=e.target.value;updatePhrasePreview();};
 $('previewMainAgent').onclick=()=>preview('phrases','main',$('previewMainAgent'));
 $('previewSubagent').onclick=()=>preview('phrases','sub',$('previewSubagent'));
 $('previewAIVoice').onclick=()=>preview('ai','main',$('previewAIVoice'));
 for(const mode of ['effects','clips']){
  $(mode+'Event').onchange=e=>{sampleSelections[mode]={event:e.target.value,variant:0};renderAudioSample(mode);};
  $(mode+'Variant').onchange=e=>{sampleSelections[mode].variant=Number(e.target.value);renderAudioSample(mode);};
 }
 $('addPhrase').onclick=addPhrase;$('soundOn').onchange=toggleSound;
 $('volume').oninput=e=>$('volumeValue').textContent=e.target.value+'%';
 $('volume').onchange=e=>action(async()=>{const volume=Number(e.target.value);savingVolume=true;updateActivation();try{await saveConfig({effects_volume:volume,voice_volume:volume});state.volume=volume;}finally{savingVolume=false;updateActivation();$('volume').value=state.volume;$('volumeValue').textContent=state.volume+'%';}});
 $('soundPack').onchange=e=>{state.pack=e.target.value;renderPack();};
 $('commentaryStyle').onchange=e=>{state.style=e.target.value;renderStyle();};
 $('speaker').onchange=e=>state.voices[state.engine]=e.target.value;
 $('engine').onchange=e=>{state.engine=e.target.value;renderSpeakers();};
 $('provider').onchange=e=>{state.provider=e.target.value;state.model='';state.apiKey='';$('model').value='';$('sampleKey').value='';renderProvider();};
 $('model').oninput=e=>state.model=e.target.value;
 $('sampleKey').oninput=e=>{state.apiKey=e.target.value;modelList=null;renderModelList();};
 $('sampleKey').onchange=()=>refreshModels();
 $('refreshModels').onclick=()=>refreshModels(true);
 $('setup-ai').ontoggle=()=>{if($('setup-ai').open&&!tipScenario)refreshModels();};
 $('sessionContext').onchange=e=>state.context=e.target.checked;
 $('settingsButton').onclick=()=>$('settingsDialog').showModal();$('closeSettings').onclick=()=>$('settingsDialog').close();
 $('helpButton').onclick=toggleTips;
 $('closedDialog').oncancel=e=>e.preventDefault();$('closeSoundbar').onclick=closeSoundbar;
 $('reduceRepeats').onchange=()=>action(async()=>{try{await saveConfig({sound_spacing_on:$('reduceRepeats').checked});}finally{$('reduceRepeats').checked=saved.sound_spacing_on;for(const id of ['effectsGap','voiceGap'])$(id).disabled=!saved.sound_spacing_on;}});
 for(const [id,key] of [['effectsGap','effects_cooldown_ms'],['voiceGap','voice_cooldown_ms']]) {$(id).oninput=e=>$(id+'Value').textContent=(e.target.value/1000)+'s';$(id).onchange=()=>action(async()=>{try{await saveConfig({[key]:Number($(id).value)});}finally{$(id).value=saved[key];$(id+'Value').textContent=(saved[key]/1000)+'s';}});}
 $('approvalCues').onchange=()=>action(async()=>{try{await saveConfig({codex_permission_sound_on:$('approvalCues').checked});}finally{$('approvalCues').checked=saved.codex_permission_sound_on;}});
 $('checkConnection').onclick=()=>checkSetup('ai');$('installSox').onclick=()=>{$('soxCommand').hidden=false;};
 $('phraseInstallKokoro').onclick=e=>installKokoro(e.currentTarget);$('aiInstallKokoro').onclick=e=>installKokoro(e.currentTarget);
 $('activateSelection').onclick=activateSelection;
 document.addEventListener('input',renderSetup);document.addEventListener('change',()=>{renderSetup();scheduleSetupChecks();});
}
window.addEventListener('DOMContentLoaded',async()=>{
 mountSpeechSetups();mountCheckStatuses();
 const controls=[...document.querySelectorAll('button,input,select')];controls.forEach(el=>el.disabled=true);
 try{await load();controls.forEach(el=>el.disabled=false);wire();setupChecksReady=true;scheduleSetupChecks(0);renderPack();renderAudioSample('clips');updatePhrasePreview();renderSetup();updateStatus();mountTips();for(const id of ['effectsGap','voiceGap'])$(id).disabled=!saved.sound_spacing_on;}
 catch(error){$('loadError').hidden=false;$('loadError').querySelector('button').disabled=false;$('statusText').textContent='Disconnected';showError(error.message,$('loadError'));}
});
