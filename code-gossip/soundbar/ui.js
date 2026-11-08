'use strict';
const demo = window.soundbarDemo || null;
const $ = id => document.getElementById(id);
const TABS = {effects:{name:'Effects',icon:'wave'}, clips:{name:'Clips',icon:'film'}, phrases:{name:'Phrases',icon:'chat'}, ai:{name:'AI commentary',icon:'spark'}};
const modeNames = Object.fromEntries(Object.entries(TABS).map(([id,tab]) => [id, tab.name]));
const profileModes = {senior:'phrases', generals:'clips', narrator:'ai'};
const GROUPS = [
 ['Session',['session_start','user_prompt','stop','session_end','interrupt']],
 ['Work',['edit','read','search','bash','tool','plan']],
 ['Checks',['test','build']],
 ['Git',['git','git_status','git_history','git_commit','git_push']],
 ['Subagents',['subagent_start','subagent_stop']],
 ['Attention',['permission','error']],
 ['Memory',['pre_compact','compact']],
];
const PACK_ORDER = ['default','wood-thrush','paper','construction','minimal','sci-fi','submarine','attention','silent'];
const PROFILE_SESSION_EVENTS = ['session_start','read','edit','test','stop'];
const PACK_META = {
 default:{desc:'Classic macOS alert sounds. Nothing to install.', kind:'macOS sounds'},
 'wood-thrush':{desc:'A birdsong melody that evolves as the session goes on.', kind:'Generated'},
 paper:{desc:'Pencils, page flips, and a typewriter.', kind:'Recorded'},
 construction:{desc:'Saws and ratchets while working, a hammer at the finish.', kind:'Recorded'},
 minimal:{desc:'Short, quiet synthesized tones.', kind:'Generated'},
 'sci-fi':{desc:'Console chirps and sweeps.', kind:'Generated'},
 submarine:{desc:'Sonar pings and hull tones.', kind:'Generated'},
 attention:{desc:'Only approvals and completion. Everything else stays quiet.', kind:'Generated'},
 silent:{desc:'No effects at all.', kind:'Empty'},
};
const themeKey = 'code-gossip.soundbar-theme';
const GUIDE = [
 ['effects','Choose a mode','Effects, recorded clips, spoken phrases, or AI commentary.'],
 ['events','Audition sounds','Preview any sound. Use applies your selection.'],
 ['phrases','Edit phrases','Pick an event on the left and rewrite its lines.'],
 ['provider','Connect AI commentary','Pick a provider. Cloud checks run only when you ask.'],
 ['state','Save and use','Save keeps edits. Use switches what agents play.'],
 ['settings','Settings','Theme, pacing, and Codex approval cues.'],
];

let saved, state, activeSelection, setup, voiceChoices, styleNames;
let busy = false, savingSound = false, savingVolume = false, mediaBusy = false, installPoll = null;
let activePreview = null, modelPoll = null;
let savingAISettings = 0, aiSettingsQueue = Promise.resolve();
const setupChecks = new Map(), filters = {effects:'All', clips:'All'}, cursors = {}, guideDone = new Set();
let enabledLayers, generatedSample = null, modelList = null;
let versions = null, versionPoll = null, versionChecking = false, versionStarting = false, versionError = '', loadedVersion = null;
let toastTimer;

const clone = value => structuredClone(value);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const icon = (name, extra='') => `<svg class="i ${extra}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const eventLabel = event => event.replaceAll('_',' ').replace(/^./, letter => letter.toUpperCase());
const packName = id => id === 'default' ? 'System sounds' : id === 'wood-thrush' ? 'Wood Thrush' : id.charAt(0).toUpperCase() + id.slice(1);
const phraseRoles = event => event === 'subagent_start' ? ['main','sub'] : event === 'subagent_stop' ? ['sub','main'] : null;

function currentTheme() { return document.documentElement.dataset.theme === 'mint' ? 'mint' : 'amber'; }
function applyTheme(theme) {
 const next = theme === 'mint' ? 'mint' : 'amber';
 document.documentElement.dataset.theme = next;
 try { localStorage.setItem(themeKey, next); } catch { /* private browsing */ }
 document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === next)));
}

async function api(path, body, allowFailure=false) {
 if (demo) return demo.request(path, body);
 const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Soundbar-Request':'ui'}, body:JSON.stringify(body)});
 const data = await response.json();
 if (!response.ok || !allowFailure && data.ok === false) throw new Error(data.error || data.message || 'Request failed');
 return data;
}
function toast(message) {
 $('toastText').textContent = message;
 $('toast').classList.add('show');
 clearTimeout(toastTimer);
 toastTimer = setTimeout(() => $('toast').classList.remove('show'), 2400);
}
function showError(message) {
 setMarkup($('errorBanner'), message ? `<span id="errorMessage" class="error-message" tabindex="0">${esc(message)}</span><button type="button" class="icon-sm" data-dismiss-error aria-label="Dismiss error">${icon('x')}</button>` : '');
}
function clearError() { if ($('errorBanner')) setMarkup($('errorBanner'), ''); }

function packIds() {
 return Object.keys(saved.effects_profiles).sort((a, b) => {
  const ai = PACK_ORDER.indexOf(a), bi = PACK_ORDER.indexOf(b);
  return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b);
 });
}
function groupedEvents() {
 const known = new Set(saved.events), used = new Set();
 const groups = GROUPS.map(([name, events]) => {
  const present = events.filter(event => known.has(event));
  present.forEach(event => used.add(event));
  return [name, present];
 }).filter(([, events]) => events.length);
 const extra = saved.events.filter(event => !used.has(event));
 if (extra.length) groups.push(['Other', extra]);
 return groups;
}
function normalizePhrases(source) {
 return Object.fromEntries(saved.events.map(event => [event, clone(source?.[event] || [])]));
}
function voiceLabel(engine, id) { return (voiceChoices[engine] || []).find(([value]) => value === id)?.[1] || id; }
function speechEngine(mode=state.viewMode) { return mode === 'ai' ? state.engine : state.phraseEngine; }
function needsKey() { return !!saved.narrator_providers[state.provider]?.needs_key; }
function providerKey() { if (state.keyEdited) return state.apiKey; return state.apiKey || (state.provider === saved.narrator_provider ? saved.narrator_api_key : '') || ''; }
function hasProviderKey() { return !!demo || !needsKey() || !!providerKey().trim(); }
function connectionIdentity() { return JSON.stringify([state.provider, state.model, providerKey()]); }
function aiIdentity() { return connectionIdentity(); }
function speechIdentity(mode) {
 const engine = speechEngine(mode);
 const voices = mode === 'phrases' ? state.phraseVoices[engine] : [state.voices[engine]];
 return JSON.stringify([engine, voices]);
}
function sampleIdentity() { return JSON.stringify([connectionIdentity(), state.style]); }
function catalog(mode, pack=state.pack) {
 if (mode === 'effects') return saved.preview_catalog?.effects?.[pack] || {};
 return saved.preview_catalog?.voice?.generals || {};
}
function packSource(id) {
 const effect = setup.effects?.[id] || {};
 if (id === 'silent') return 'No audio';
 if (effect.sox) return 'Generated with SoX';
 if (id === 'default') return 'macOS system sounds';
 return 'Bundled audio files';
}

function selectionDraft(mode=state.viewMode) {
 if (mode === 'effects') return {mode, pack:state.pack};
 if (mode === 'clips') return {mode, profile:'generals'};
 if (mode === 'phrases') return {mode, engine:state.phraseEngine, voices:clone(state.phraseVoices[state.phraseEngine]), phrases:clone(state.phrases)};
 return {mode, style:state.style, engine:state.engine, voice:state.voices[state.engine], provider:state.provider, model:state.model, context:state.context, apiKey:state.apiKey};
}
function savedDraft(mode) {
 if (mode === 'effects') return {mode, pack:saved.effects_profile};
 if (mode === 'clips') return {mode, profile:'generals'};
 const engine = saved.tts_engine;
 if (mode === 'phrases') {
  const voices = engine === 'kokoro' ? {main:saved.kokoro_voice, sub:saved.kokoro_voice_sub || 'am_adam'} : {main:saved.voice_main, sub:saved.voice_sub};
  return {mode, engine, voices, phrases:normalizePhrases(saved.phrases)};
 }
 return {mode, style:saved.narrator_style, engine, voice:engine === 'kokoro' ? saved.kokoro_voice : saved.voice_main, provider:saved.narrator_provider, model:saved.narrator_model || '', context:!!saved.narrator_deep_context, apiKey:''};
}
// Browsed presets are activation choices; only editor fields are saveable edits.
function selectionIdentity({mode, pack, profile, style}) { return {mode, pack, profile, style}; }
function editableDraft({mode, pack, profile, style, ...edits}) { return edits; }
function isDirty(mode) { return !demo && !same(editableDraft(selectionDraft(mode)), editableDraft(savedDraft(mode))); }
function selectionInUse(mode) {
 return modeInUse(mode) && same(selectionIdentity(selectionDraft(mode)), selectionIdentity(savedDraft(mode)));
}
const renderedMarkup = new WeakMap();
function setMarkup(node, html) {
 // Keep unchanged controls mounted through polling and other background updates.
 if (renderedMarkup.get(node) === html) return;
 const focused = document.activeElement;
 const attributes = ['id','name','data-act','data-filter','data-phrase-event','data-preview','data-pack','data-event','data-variant','data-role','data-remove','data-index','data-part'];
 if (focused.matches('input[type=radio]')) attributes.push('value');
 const identity = attributes.filter(name => focused.hasAttribute(name));
 const selector = node.contains(focused) && identity.length
  ? focused.tagName + identity.map(name => `[${name}="${CSS.escape(focused.getAttribute(name))}"]`).join('') : null;
 const selection = selector && focused.selectionStart != null ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
 node.innerHTML = html;
 renderedMarkup.set(node, html);
 const replacement = selector && node.querySelector(selector);
 if (replacement && !replacement.disabled) {
  replacement.focus({preventScroll:true});
  if (selection) replacement.setSelectionRange(...selection);
 }
}
function modeInUse(mode) {
 if (demo) return false;
 if (activeSelection.mode === 'combined') return mode === 'effects' || mode === (profileModes[saved.voice_profile] || 'phrases');
 return activeSelection.mode === mode;
}
function selectionLabel(selection=activeSelection) {
 const mode = selection.mode;
 if (mode === 'combined') return `Effects · ${packName(saved.effects_profile)} + ${modeNames[profileModes[saved.voice_profile]] || 'Voice'}`;
 if (mode === 'effects') return `Effects · ${packName(selection.pack || saved.effects_profile)}`;
 if (mode === 'clips') return 'Clips · Generals';
 if (mode === 'phrases') return 'Phrases · Senior';
 const style = selection.style || saved.narrator_style;
 return `AI commentary · ${styleNames[style] || style}`;
}
function draftConfig(mode=state.viewMode) {
 if (mode === 'effects') return {effects_profile:state.pack};
 if (mode === 'clips') return {};
 const engine = speechEngine(mode), config = {tts_engine:engine};
 if (mode === 'phrases') {
  const voices = state.phraseVoices[engine];
  Object.assign(config, engine === 'kokoro' ? {kokoro_voice:voices.main, kokoro_voice_sub:voices.sub} : {voice_main:voices.main, voice_sub:voices.sub});
 } else {
  config[engine === 'kokoro' ? 'kokoro_voice' : 'voice_main'] = state.voices[engine];
  Object.assign(config, {narrator_provider:state.provider, narrator_model:state.model, narrator_style:state.style, narrator_deep_context:state.context});
  if (state.keyEdited || state.apiKey || state.provider !== saved.narrator_provider) config.narrator_api_key = state.apiKey;
 }
 return config;
}
function saveIssue(mode) {
 if (mode === 'phrases') {
  const count = saved.events.reduce((total, event) => total + state.phrases[event].flat().filter(text => !String(text).trim()).length, 0);
  return count ? `${count} empty ${count === 1 ? 'line' : 'lines'}` : '';
 }
 if (mode === 'ai' && !hasProviderKey()) return 'API key required';
 return '';
}
function speechInstallation(engine=speechEngine()) {
 if (engine !== 'kokoro') return {available:!!setup.say, message:setup.say ? 'Built into macOS' : 'Unavailable', tone:setup.say ? 'neutral' : 'error'};
 if (setup.installing) return {available:false, message:'Installing…', tone:'warning'};
 if (setup.installStatus === 'error') return {available:false, message:'Installation failed', tone:'error'};
 return {available:!!setup.kokoro, message:setup.kokoro ? 'Installed' : 'Not installed', tone:setup.kokoro ? 'success' : 'warning'};
}
function speechReadiness(mode) {
 const engine = speechEngine(mode), installation = speechInstallation(engine);
 if (!installation.available) return {ready:false, message:engine === 'kokoro' ? 'Kokoro: ' + (setup.installStatus === 'error' && setup.installMessage || installation.message) : installation.message};
 const voices = mode === 'phrases' ? Object.values(state.phraseVoices[engine]) : [state.voices[engine]];
 if (voices.some(voice => !(voiceChoices[engine] || []).some(([id]) => id === voice))) return {ready:false, message:'Choose installed voices'};
 const key = mode === 'phrases' ? 'phrases' : 'aiSpeech';
 const check = cachedCheck(key), current = check?.identity === speechIdentity(mode);
 if (engine === 'kokoro' && !demo && (!current || check.status !== 'checked' || !check.model?.ready)) {
  return {ready:false, message:current ? check.message || 'Preparing speech…' : 'Check the speech engine'};
 }
 if (current && check.status === 'failed') return {ready:false, message:(engine === 'kokoro' ? 'Kokoro: ' : '') + (check.message || 'Speech check failed')};
 if (current && check.status === 'checking') return {ready:false, message:'Checking speech…'};
 return {ready:true, message:current && check.status === 'checked' ? 'Engine available' : 'Not checked'};
}
function setupReadiness(mode, pack=state.pack) {
 if (mode === 'effects' || mode === 'clips') {
  const available = mode === 'effects' ? setup.effects?.[pack] : setup.clips?.generals;
  if (!available?.ready) return available || {ready:false, message:'Audio unavailable'};
  const check = cachedCheck(mode, checkIdentity(mode, pack)), current = check?.identity === checkIdentity(mode, pack);
  if (current && check.status === 'failed') return {ready:false, message:'Check failed'};
  if (current && check.status === 'checking') return {ready:false, message:'Checking…'};
  return {ready:true, message:current && check.status === 'checked' ? 'Audio available' : 'Not checked'};
 }
 const speech = speechReadiness(mode);
 if (!speech.ready) return speech;
 if (mode === 'ai' && cachedCheck('ai')?.status !== 'checked') return {ready:false, message:'Check the provider first'};
 return speech;
}
function saveReadiness(mode) {
 if (mode === 'effects' && modeInUse(mode)) return setupReadiness(mode);
 // Both spoken modes write the runtime's shared speech settings.
 if (['phrases','ai'].includes(mode) && (modeInUse('phrases') || modeInUse('ai'))) return speechReadiness(mode);
 return {ready:true};
}
function blockerDrawer(mode) {
 if (mode === 'effects') return 'effects';
 if (mode === 'clips') return 'clips';
 if (mode === 'phrases' || !speechReadiness(mode).ready) return 'speech';
 return 'provider';
}

const checkModes = {effects:'effects', clips:'clips', phrases:'phrases', aiSpeech:'ai', ai:'ai'};
function checkIdentity(key, pack=state.pack) {
 if (key === 'ai') return aiIdentity();
 if (key === 'phrases' || key === 'aiSpeech') return speechIdentity(checkModes[key]);
 if (key === 'effects') return JSON.stringify({effects_profile:pack});
 return JSON.stringify(draftConfig(checkModes[key]));
}
function speechKey() { return state.viewMode === 'ai' ? 'aiSpeech' : 'phrases'; }
function checkButton(key) {
 if (key === 'ai') return $('checkConnection');
 if (key === 'phrases' || key === 'aiSpeech') return $('speechCheck');
 if (key === 'clips') return $('checkClips');
 return $('checkEffects');
}
function checkPresentation(key) {
 if (demo) return {status:'checked', checking:false, requesting:false, message:'Recorded', tone:'success', action:'Check'};
 const check = cachedCheck(key), current = check?.identity === checkIdentity(key), status = current ? check.status : 'unchecked';
 const provider = key === 'ai', cli = provider && ['claude_cli', 'codex_cli'].includes(state.provider);
 const action = provider ? (cli ? 'Check CLI' : state.provider === 'ollama' ? 'Check server' : 'Check connection') : 'Check';
 const pending = provider && !cli ? 'Connecting…' : 'Checking…';
 const success = provider ? (cli ? 'Detected' : 'Connected') : 'Ready';
 let prerequisite = null;
 if (provider && !hasProviderKey()) prerequisite = {message:'Key required', tone:'warning'};
 if (key === 'effects' || key === 'clips') {
  const resource = key === 'effects' ? setup.effects?.[state.pack] : setup.clips?.generals;
  if (!resource?.ready) prerequisite = {message:resource?.missing?.length ? 'Missing files' : resource?.sox ? 'Install SoX' : 'Unavailable', tone:resource?.missing?.length ? 'error' : 'warning'};
 }
 if (key === 'phrases' || key === 'aiSpeech') {
  const installation = speechInstallation(speechEngine(checkModes[key]));
  if (!installation.available) prerequisite = {...installation, message:installation.message === 'Installation failed' ? 'Install failed' : installation.message};
  else {
   const mode = checkModes[key], engine = speechEngine(mode);
   const voices = mode === 'phrases' ? Object.values(state.phraseVoices[engine]) : [state.voices[engine]];
   if (voices.some(voice => !(voiceChoices[engine] || []).some(([id]) => id === voice))) prerequisite = {message:'Choose voices', tone:'warning'};
  }
 }
 const result = {message:status === 'checked' ? success : status === 'failed' ? 'Check failed' : status === 'checking' ? pending : status === 'loading' ? 'Loading…' : 'Not checked', tone:status === 'checked' ? 'success' : status === 'failed' ? 'error' : 'warning'};
 if (current && check.model) {
  result.message = status === 'failed' ? 'Load failed' : status === 'checking' ? pending :
   ({ready:'Ready', downloading:'Downloading…', loading:'Loading…'}[check.model.state] || 'Preparing…');
  result.tone = status === 'checked' ? 'success' : status === 'failed' ? 'error' : 'warning';
 }
 return {action:current && check.model?.state === 'error' ? 'Retry model loading' : action, pending, status, checking:status === 'checking', requesting:!!check?.requesting, prerequisite, ...(prerequisite || result)};
}
function paintStatus(node, view) {
 const tone = {success:'ok', warning:'warn', error:'err'}[view.tone] || '';
 node.className = 'status' + (tone ? ' ' + tone : '');
 node.dataset.tone = view.tone || 'neutral';
 if (node.hasAttribute('data-status-for')) setSizedText(node, view.message, 'Downloading…', 'Choose voices');
 else node.textContent = view.message;
 // An in-flight check must not collapse its slot and move adjacent controls.
 node.hidden = false;
 node.style.visibility = view.checking && !view.prerequisite ? 'hidden' : '';
}
function setSizedText(node, text, widthLabel, alternate='') {
 setMarkup(node, `<span class="label-slot" data-width-label="${esc(widthLabel)}" data-alternate-label="${esc(alternate)}"><span>${esc(text)}</span></span>`);
}
// Results belong to a configuration for this page's lifetime, not to the last
// visited section. Reload creates a fresh cache; explicit Check replaces one entry.
function cachedCheck(key, identity=checkIdentity(key)) {
 return setupChecks.get(JSON.stringify([key, identity]));
}
function rememberCheck(key, check) {
 check.key = key;
 setupChecks.set(JSON.stringify([key, check.identity]), check);
 return check;
}
function cacheAudioSetup() {
 for (const [pack, resource] of Object.entries(setup.effects || {})) {
  rememberCheck('effects', {identity:checkIdentity('effects', pack), status:resource.ready ? 'checked' : 'failed', message:resource.message});
 }
 const resource = setup.clips?.generals;
 if (resource) rememberCheck('clips', {identity:checkIdentity('clips'), status:resource.ready ? 'checked' : 'failed', message:resource.message});
}
function checkInitialSpeech() {
 if (demo) return;
 for (const key of ['phrases', 'aiSpeech']) checkSetup(key, {automatic:true});
}

async function refreshSetup() { setup = {...setup, ...await api('/api/setup')}; }
function scheduleModelPoll() {
 clearTimeout(modelPoll);
 // Continue only unfinished model preparation, including while browsing elsewhere.
 const pending = [...setupChecks.values()].filter(check => check.status === 'loading' && !check.requesting);
 if (demo || !pending.length) return;
 modelPoll = setTimeout(() => {
  for (const check of pending) checkSetup(check.key, {automatic:true, pending:check});
 }, 2000);
}
async function checkSetup(key, {automatic=false, pending=null}={}) {
 const mode = checkModes[key], config = pending?.config || draftConfig(mode), identity = pending?.identity || checkIdentity(key);
 const previous = cachedCheck(key, identity);
 if (previous?.requesting || automatic && previous && previous.status !== 'loading') return;
 if (!pending && checkPresentation(key).prerequisite && key !== 'effects' && key !== 'clips') return;
 const check = rememberCheck(key, {identity, config, requesting:true,
  status:automatic ? previous?.status || 'loading' : 'checking',
  model:previous?.model, message:previous?.message});
 if (!automatic) clearError();
 renderChecks();
 try {
  if (!automatic) await refreshSetup();
  const result = await api('/api/draft-check', {mode, config, scope:key === 'ai' ? 'provider' : 'speech', retry:!automatic}, true);
  check.model = result.model;
  check.message = result.message || result.error || 'Check failed';
  check.status = result.ok ? 'checked' : result.pending ? 'loading' : 'failed';
  if (!result.ok && !result.pending && identity === checkIdentity(key) && mode === state.viewMode) showError(check.message);
  if (result.ok && identity === checkIdentity(key) && key === 'ai') refreshModels();
 } catch (error) {
  check.status = 'failed';
  check.message = error.message;
  if (identity === checkIdentity(key) && mode === state.viewMode) showError(error.message);
 } finally {
  check.requesting = false;
  render({preservePhraseEditor:true});
  scheduleModelPoll();
 }
}

function providerNote() {
 if (state.provider === 'claude_cli') return 'Checks that Claude CLI is installed. Play a sample to test sign-in and model access. Cloud providers are checked only when you ask.';
 if (state.provider === 'codex_cli') return 'Uses your Codex sign-in and usage limits. Check CLI detects installation; Play sample tests sign-in and model access. Leave Model blank for the CLI default. Requires a recent Codex CLI.';
 if (state.provider === 'ollama') return 'Checks the local server. Play a sample to test the selected model.';
 return `${saved.narrator_providers[state.provider]?.description || ''} A connection check sends a short request and may be billed. It runs only when you ask.`;
}
function modelListIdentity() { return JSON.stringify([state.provider, providerKey()]); }
function renderModelList() {
 const current = modelList?.identity === modelListIdentity() ? modelList : null;
 $('modelChoices').replaceChildren(...(current?.models || []).map(name => new Option(name, name)));
 $('refreshModels').disabled = current?.status === 'loading' || !hasProviderKey() || current?.supported === false;
 $('refreshModels').setAttribute('aria-busy', String(current?.status === 'loading'));
 $('modelStatus').dataset.status = current?.status || 'idle';
 $('modelStatus').textContent = current?.message || (!hasProviderKey() ? 'Enter an API key to load models.' : 'Suggestions load from your provider.');
}
async function refreshModels(force=false) {
 if (!hasProviderKey()) { renderModelList(); return; }
 const identity = modelListIdentity();
 if (modelList?.identity === identity && (modelList.status === 'loading' || !force && modelList.status === 'loaded')) return;
 const request = modelList = {identity, status:'loading', models:[], message:'Loading available models…'};
 renderModelList();
 const config = {narrator_provider:state.provider};
 if (state.keyEdited || state.apiKey || state.provider !== saved.narrator_provider) config.narrator_api_key = state.apiKey;
 try {
  const result = await api('/api/narrator-models', {config});
  if (modelList !== request || identity !== modelListIdentity()) return;
  Object.assign(request, {status:'loaded', models:result.models, supported:result.supported, message:result.message || (result.models.length ? result.models.length + ' models available' : 'No models available. Refresh after adding access or installing a model.')});
 } catch (error) {
  if (modelList !== request || identity !== modelListIdentity()) return;
  Object.assign(request, {status:'failed', models:[], message:error.message});
 }
 renderModelList();
}

function buildTabs() {
 $('tabs').innerHTML = Object.entries(TABS).map(([id, tab]) => `<button class="tab" type="button" role="tab" id="tab-${id}" data-mode="${id}" aria-controls="panel-${id}">${icon(tab.icon)}<span>${tab.name}</span><span class="tab-badges" id="badges-${id}"></span></button>`).join('');
}
function renderTabs() {
 for (const id of Object.keys(TABS)) {
  const tab = $('tab-' + id), selected = state.viewMode === id;
  tab.setAttribute('aria-selected', String(selected));
  tab.tabIndex = selected ? 0 : -1;
  $('panel-' + id).hidden = !selected;
  let badges = '';
  if (modeInUse(id)) badges += '<span class="tab-inuse"><i class="live-dot"></i>In use</span>';
  if (isDirty(id)) badges += '<span class="dirty-dot" title="Unsaved changes"></span>';
  if (!demo && id === 'ai' && cachedCheck('ai')?.status !== 'checked') badges += `<span title="Provider not checked">${icon('warn','tab-warn')}</span>`;
  $('badges-' + id).innerHTML = badges;
 }
}
function renderNow() {
 $('now').classList.toggle('muted', !state.enabled);
 $('now').classList.toggle('is-playing', mediaBusy);
 $('statusText').innerHTML = `<span class="label-slot" data-width-label="${demo ? 'Preview' : 'In use'}" data-alternate-label="Muted"><span>${state.enabled ? demo ? 'Preview' : 'In use' : 'Muted'}</span></span> · ${esc(selectionLabel(demo ? selectionDraft() : activeSelection))}`;
 $('now').title = 'Show the mode in use: ' + selectionLabel(demo ? selectionDraft() : activeSelection);
 $('powerLabel').textContent = state.enabled ? 'Sound on' : 'Sound off';
 $('soundOn').checked = state.enabled;
 $('soundOn').disabled = busy || !demo && mediaBusy || savingSound;
 $('volume').disabled = busy || !demo && mediaBusy || savingVolume;
}
function renderPanelState(mode) {
 if (demo) return;
 const inUse = selectionInUse(mode);
 const exclusive = activeSelection.mode === mode && inUse, dirty = isDirty(mode), issue = dirty ? saveIssue(mode) : '';
 const readiness = setupReadiness(mode), blocked = !readiness.ready, drawer = blockerDrawer(mode);
 const saveReady = saveReadiness(mode), saving = busy || mediaBusy || savingSound || savingVolume || savingAISettings;
 const link = drawer === 'speech' ? '' : `<button type="button" class="link" data-drawer="${drawer}">${drawer === 'provider' ? 'Configure' : 'Details'}</button>`;
 let actions = '', activation = '';
 if (dirty) {
  actions += `<div id="draftNotice-${mode}" class="draft-notice"${issue || !saveReady.ready ? ' tabindex="0"' : ''}><span class="unsaved"><i class="dirty-dot"></i>Unsaved changes</span>`;
  if (issue) actions += `<span class="state-issue">${icon('warn')}${esc(issue)}</span>`;
  else if (!saveReady.ready && saveReady.message !== readiness.message) actions += `<span class="state-issue">${icon('warn')}${esc(saveReady.message)}</span>`;
  actions += `</div><button type="button" class="btn ghost" data-act="discard" ${saving ? 'disabled' : ''}>Discard</button>`;
  actions += `<button type="button" class="btn primary" data-act="save" ${saving || !!issue || !saveReady.ready ? 'disabled' : ''}${busy ? ' aria-busy="true"' : ''}>Save changes</button>`;
 }
 if (inUse) activation += `<span class="pill success">${icon('check')}In use</span>`;
 if (!exclusive) {
  activation += `<button type="button" class="btn primary" data-act="use" ${saving || blocked || !!issue ? 'disabled' : ''}${mode === state.viewMode ? ' id="activateSelection"' : ''}${busy ? ' aria-busy="true"' : ''}>Use ${esc(modeNames[mode])}</button>`;
 }
 const notice = blocked ? `<span class="state-issue">${icon('warn')}<span>${esc(readiness.message)}${link ? ' · ' + link : ''}</span></span>` : '';
 const html = `<div id="activationNotice-${mode}" class="activation-notice" role="status"${blocked ? ' tabindex="0"' : ''}>${notice}</div><div class="activation-actions">${activation}</div>`;
 setMarkup(document.querySelector(`[data-state="${mode}"]`), html);
 const footer = document.querySelector(`[data-draft-actions="${mode}"]`);
 if (footer) { setMarkup(footer, actions); footer.hidden = false; footer.style.visibility = dirty ? '' : 'hidden'; footer.setAttribute('aria-hidden', String(!dirty)); }
}
function renderChrome() {
 if (!demo) for (const id of ['provider','model','sampleKey','phraseEngine','speaker']) $(id).disabled = busy;
 renderTabs();
 renderNow();
 for (const mode of Object.keys(TABS)) renderPanelState(mode);
 renderEventList();
 const defaults = saved.phrases_defaults?.[state.phraseEvent];
 $('resetEvent').hidden = !defaults;
 $('resetEvent').disabled = !!defaults && same(state.phrases[state.phraseEvent], defaults);
 $('clipsInUse').innerHTML = modeInUse('clips') ? '<span class="pill success sm">In use</span>' : '';
 $('activationProgress').textContent = busy ? 'Saving selection…' : savingAISettings ? 'Saving settings…' : '';
 renderPreviewState();
}

function renderFilters(mode) {
 setMarkup($('filters-' + mode), ['All', ...groupedEvents().map(([group]) => group)].map(group => `<button type="button" class="filter" data-filter="${mode}:${esc(group)}" aria-pressed="${filters[mode] === group}">${esc(group)}</button>`).join(''));
}
function renderEvents(container, mode, pack) {
 const events = catalog(mode, pack);
 if (!Object.keys(events).length) {
  setMarkup(container, '<p class="empty">This pack is intentionally silent. Agents make no effect sounds while it is in use.</p>');
  return;
 }
 const groups = filters[mode] === 'All' ? groupedEvents() : groupedEvents().filter(([group]) => group === filters[mode]);
 setMarkup(container, `<div class="ev-grid">${groups.map(([group, names]) => (filters[mode] === 'All' ? `<p class="group-label">${esc(group)}</p>` : '') + names.map(event => {
  const samples = events[event];
  if (!samples?.length) return `<div class="ev-tile silent"><span class="ev-ico">–</span><span class="ev-body"><span class="ev-name">${esc(eventLabel(event))}</span><span class="ev-sound">Silent</span></span></div>`;
  const index = displayedVariant(mode, pack, event, samples.length);
  return `<button type="button" class="ev-tile" data-preview="${mode}" data-event="${esc(event)}" ${mode === 'effects' ? `data-pack="${esc(pack)}"` : ''}><span class="ev-ico">${icon('play')}</span><span class="ev-body"><span class="ev-name">${esc(eventLabel(event))}</span><span class="ev-sound">${esc(samples[index])}</span></span>${samples.length > 1 ? `<span class="ev-count" title="${samples.length} alternatives">×${samples.length}</span>` : ''}</button>`;
 }).join('')).join('')}</div>`);
}
function renderPacks() {
 $('packCount').textContent = packIds().length;
 setMarkup($('packList'), packIds().map(id => {
  const meta = PACK_META[id] || {kind:'Custom'}, effect = setup.effects?.[id] || {}, count = Object.keys(catalog('effects', id)).length;
  const selected = state.pack === id, inUse = modeInUse('effects') && saved.effects_profile === id;
  const sample = catalog('effects', id).edit ? 'edit' : Object.keys(catalog('effects', id))[0];
  return `<div class="list-row ${selected ? 'selected' : ''}"><label><input type="radio" name="pack" value="${esc(id)}" ${selected ? 'checked' : ''}><span class="row-main"><span class="row-title">${esc(packName(id))}${inUse ? '<span class="pill success sm">In use</span>' : ''}</span><span class="row-meta">${esc(meta.kind)} · ${count ? count + ' events' : 'silent'}${effect.sox ? ' · SoX' : ''}</span></span></label>${sample ? `<button class="play-btn" type="button" data-preview="effects" data-pack="${esc(id)}" data-session aria-label="Play a ${esc(packName(id))} sample">${icon('play')}</button>` : ''}</div>`;
 }).join(''));
}
function renderEffectsDetail() {
 const meta = PACK_META[state.pack] || {desc:'Custom sound pack.', kind:'Audio'}, effect = setup.effects?.[state.pack] || {};
 $('packTitle').textContent = packName(state.pack);
 $('packDesc').textContent = meta.desc || 'Custom sound pack.';
 $('packChips').innerHTML = `<span class="chip">${esc(meta.kind || 'Audio')}</span>${effect.sox ? '<span class="chip">Uses SoX</span>' : ''}`;
 $('effectsSource').textContent = `${packName(state.pack)} · ${packSource(state.pack)}`;
 $('effectsSource').title = $('effectsSource').textContent;
 $('drawerPack').textContent = packName(state.pack);
 $('drawerSource').textContent = packSource(state.pack);
 $('effectsFiles').textContent = effect.missing?.length ? 'Missing: ' + effect.missing.join(', ') : effect.ready ? 'All sounds present' : (effect.message || 'Audio unavailable');
 $('effectsRequirementDetail').textContent = effect.missing?.length ? 'Missing: ' + effect.missing.join(', ') : '';
 $('installSox').hidden = !effect.sox || !!effect.ready;
 if (!effect.sox) $('soxCommand').hidden = true;
 renderFilters('effects');
 renderEvents($('effectsEvents'), 'effects', state.pack);
}
function renderClips() {
 $('clipsMeta').textContent = `Recorded clips · ${Object.keys(catalog('clips')).length} events`;
 renderFilters('clips');
 renderEvents($('clipsEvents'), 'clips', 'generals');
}
function renderEventList() {
 const list = $('evList'), scroll = list.scrollTop;
 $('eventCount').textContent = saved.events.length;
 setMarkup(list, groupedEvents().map(([group, events]) => `<p class="group-label">${esc(group)}</p>` + events.map(event => {
  const changed = !same(state.phrases[event], saved.phrases[event]);
  const empty = state.phrases[event].flat().some(text => !String(text).trim());
  return `<button type="button" class="ev-item" data-phrase-event="${esc(event)}" aria-current="${event === state.phraseEvent}"><span>${esc(eventLabel(event))}</span><span class="ev-meta">${empty ? icon('warn') : ''}${changed ? '<i class="dirty-dot" title="Unsaved"></i>' : ''}${state.phrases[event].length}</span></button>`;
 }).join('')).join(''));
 list.scrollTop = scroll;
}
function renderPhraseRows() {
 const event = state.phraseEvent, items = state.phrases[event] || [], roles = phraseRoles(event);
 $('editorTitle').textContent = eventLabel(event);
 $('editorHint').textContent = roles ? (event === 'subagent_start' ? 'The main agent speaks first, then the subagent replies.' : 'The subagent reports back, then the main agent responds.') : 'Spoken by the main agent. One alternative plays at random.';
 $('addLabel').textContent = roles ? 'Add exchange' : 'Add phrase';
 const head = roles && items.length ? `<div class="row row-head"><span></span><div class="inputs pair"><span>${esc(roleName(roles[0]))}</span><span>${esc(roleName(roles[1]))}</span></div><span></span><span></span></div>` : '';
 setMarkup($('phraseRows'), items.length ? head + items.map((item, index) => {
  const texts = [item].flat(), playable = texts.every(text => String(text).trim());
  return `<div class="row"><span class="row-num">${index + 1}</span><div class="inputs ${roles ? 'pair' : ''}">${texts.map((text, part) => `<input type="text" value="${esc(text)}" data-index="${index}" data-part="${part}" class="${String(text).trim() ? '' : 'invalid'}" placeholder="${part ? 'Reply…' : 'Write a phrase…'}" aria-label="${esc(roles ? roleName(roles[part]) : 'Phrase')} ${index + 1}">`).join('')}</div><button class="play-btn" type="button" data-preview="phrases" data-event="${esc(event)}" data-variant="${index}" aria-label="Preview alternative ${index + 1}" ${playable ? '' : 'disabled'}>${icon('play')}</button><button class="icon-sm" type="button" data-remove="${index}" aria-label="Remove ${index + 1}">${icon('x')}</button></div>`;
 }).join('') : '<p class="empty">No phrases yet, so this event stays silent. Add one below.</p>');
 if (demo) $('phraseRows').querySelectorAll('input').forEach(input => { input.readOnly = true; });
}
function roleName(role) { return (role === 'main' ? 'Main agent · ' : 'Subagent · ') + voiceLabel(state.phraseEngine, state.phraseVoices[state.phraseEngine][role]); }
function fillSelect(id, entries, selected) {
 const element = $(id), signature = entries.map(([value]) => value).join('\0');
 if (element.dataset.options !== signature) {
  element.replaceChildren(...entries.map(([value, label]) => new Option(label, value)));
  element.dataset.options = signature;
 }
 if (selected && ![...element.options].some(option => option.value === selected)) element.add(new Option(selected + ' (unavailable)', selected));
 if (element.value !== (selected || '')) element.value = selected || entries[0]?.[0] || '';
}
function renderVoices() {
 const choices = voiceChoices[state.phraseEngine] || [];
 fillSelect('mainAgentVoice', choices, state.phraseVoices[state.phraseEngine].main);
 fillSelect('subagentVoice', choices, state.phraseVoices[state.phraseEngine].sub);
 fillSelect('speaker', voiceChoices[state.engine] || [], state.voices[state.engine]);
 // Shared voice settings can change while a phrase is being edited.
 const roles = phraseRoles(state.phraseEvent);
 if (roles) {
  $('phraseRows').querySelectorAll('.row-head .inputs > span').forEach((label, part) => { label.textContent = roleName(roles[part]); });
  $('phraseRows').querySelectorAll('input').forEach(input => { input.setAttribute('aria-label', `${roleName(roles[input.dataset.part])} ${Number(input.dataset.index) + 1}`); });
 }
}
function renderStyles() {
 $('styleCount').textContent = Object.keys(styleNames).length;
 setMarkup($('styleList'), Object.entries(styleNames).map(([id, name]) => {
  const selected = state.style === id, inUse = modeInUse('ai') && saved.narrator_style === id;
  return `<label class="list-row ${selected ? 'selected' : ''}"><input type="radio" name="style" value="${esc(id)}" ${selected ? 'checked' : ''}><span class="row-main"><span class="row-title">${esc(name)}${inUse ? '<span class="pill success sm">In use</span>' : ''}</span></span></label>`;
 }).join(''));
 $('styleTitle').textContent = styleNames[state.style] || state.style;
}
function renderSample() {
 const current = generatedSample?.identity === sampleIdentity() ? generatedSample : null;
 if (!current) generatedSample = null;
 const text = current ? current.text : 'Play a sample to hear ' + (styleNames[state.style] || state.style) + '.';
 if ($('commentarySample').textContent !== text) {
  $('commentarySample').textContent = text;
  $('commentarySample').closest('.pane-body').scrollTop = 0;
 }
 $('commentarySample').classList.toggle('placeholder', !current);
 const name = saved.narrator_providers[state.provider]?.name || state.provider;
 $('sampleNote').textContent = demo ? 'Prerecorded sample · Kokoro.' : current ? 'Replay uses this line and does not ask the provider again.' : `The first play writes one line with ${name}${needsKey() ? ', which may be billed' : ''}. A successful sample also verifies the provider.`;
 renderSampleLabel();
 $('sampleBtn').disabled = mediaBusy;
}
function renderSpeech() {
 const engine = speechEngine(), kokoro = engine === 'kokoro', installation = speechInstallation(engine);
 $('phraseEngine').value = engine;
 $('phraseEngineLabel').textContent = state.phraseEngine === 'kokoro' ? 'Kokoro' : 'macOS speech';
 $('aiEngineLabel').textContent = state.engine === 'kokoro' ? 'Kokoro' : 'macOS speech';
 $('engineName').textContent = kokoro ? 'Installation' : 'Availability';
 $('engineStatus').textContent = installation.message;
 $('engineStatus').dataset.tone = installation.tone;
 $('engineStatus').className = 'status ' + ({success:'ok', warning:'warn', error:'err', neutral:''}[installation.tone] || '');
 $('engineDetail').textContent = setup.installing || setup.installStatus === 'error' ? (setup.installMessage || '') : kokoro ? 'Local speech · about 1.5 GB' : '';
 const showInstall = kokoro && (setup.installing || setup.installStatus === 'error');
 const duration = seconds => `${Math.floor((seconds || 0) / 60)}:${String((seconds || 0) % 60).padStart(2, '0')}`;
 $('installTiming').hidden = !showInstall;
 $('installTiming').textContent = `${duration(setup.installElapsed)} elapsed · ${Math.round((setup.installTimeout || 1200) / 60)} minute limit` + (setup.installing && setup.installQuiet >= 10 ? ` · Last output ${duration(setup.installQuiet)} ago; waiting for the installer` : '');
 const activity = $('installActivity'), output = (setup.installOutput || []).join('\n');
 activity.hidden = !showInstall || !output;
 if (activity.textContent !== output) { activity.textContent = output; activity.scrollTop = activity.scrollHeight; }
 const modelCheck = cachedCheck(state.viewMode === 'ai' ? 'aiSpeech' : 'phrases');
 const modelCurrent = modelCheck?.identity === speechIdentity(state.viewMode);
 const progress = modelCurrent ? modelCheck.model : null;
 $('modelPreparation').hidden = !kokoro || !installation.available || !!demo;
 paintStatus($('modelPreparationStatus'), {
  message:progress?.ready ? 'Ready' : modelCurrent ? modelCheck.message || 'Preparing…' : 'Not checked',
  tone:modelCurrent && modelCheck.status === 'failed' ? 'error' : progress?.ready ? 'success' : 'warning',
 });
 const bytes = value => (value / 1000000).toFixed(1) + ' MB';
 const details = [];
 if (progress?.file) details.push(progress.file);
 if (progress?.total > 0) details.push(`${bytes(progress.completed || 0)} of ${bytes(progress.total)} prepared`);
 else if (progress?.completed > 0) details.push(bytes(progress.completed) + ' prepared');
 if (progress?.transferred > 0) details.push(bytes(progress.transferred) + ' received');
 $('modelDownloadDetails').textContent = details.join(' · ');
 const bar = $('modelDownloadProgress');
 bar.hidden = !progress || progress.state !== 'downloading';
 if (progress?.total > 0) { bar.max = progress.total; bar.value = Math.min(progress.completed || 0, progress.total); }
 else bar.removeAttribute('value');
 $('kokoroInfo').hidden = !kokoro;
 $('verificationRow').hidden = !installation.available;
 const repair = ['phrases','aiSpeech'].some(key => cachedCheck(key)?.status === 'failed' && !cachedCheck(key)?.model && cachedCheck(key)?.identity === checkIdentity(key));
 $('installKokoro').hidden = !kokoro || (setup.kokoro && !repair) || !!setup.installing;
 $('installKokoro').disabled = !!setup.installing;
 setSizedText($('installKokoro'), setup.installStatus === 'error' ? 'Retry installation' : repair ? 'Repair installation' : 'Install Kokoro', 'Repair installation');
}
function renderChecks() {
 for (const key of Object.keys(checkModes)) {
  const view = checkPresentation(key);
  document.querySelectorAll(`[data-status-for="${key}"]`).forEach(node => paintStatus(node, view));
  const button = checkButton(key);
  if ((key === 'phrases' || key === 'aiSpeech') && key !== speechKey()) continue;
  setSizedText(button, view.checking ? view.pending : view.action,
   key === 'ai' ? 'Check connection' : ['phrases','aiSpeech'].includes(key) ? 'Retry model loading' : 'Checking…');
  button.disabled = !!(view.requesting || view.prerequisite && key !== 'effects' && key !== 'clips');
  button.setAttribute('aria-busy', String(view.requesting));
  button.dataset.status = view.checking ? 'checking' : view.status;
  if (key === 'phrases' || key === 'aiSpeech') button.dataset.checkSetup = key;
 }
 renderChrome();
}
function render({preservePhraseEditor=false}={}) {
 renderPacks();
 renderEffectsDetail();
 renderClips();
 if (!preservePhraseEditor) renderPhraseRows();
 renderStyles();
 renderVoices();
 showProvider();
 renderSample();
 renderSpeech();
 renderChecks();
 renderVersions();
}
function showProvider() {
 $('provider').value = state.provider;
 $('keyField').hidden = !needsKey();
 $('sampleKey').placeholder = state.provider === saved.narrator_provider && saved.narrator_api_key ? 'Key saved — enter a new one to replace' : 'Paste your API key';
 $('providerHint').textContent = providerNote();
 const name = saved.narrator_providers[state.provider]?.name || state.provider;
 $('stripProvider').textContent = demo ? 'Prerecorded' : name + (state.model ? ' · ' + state.model : '');
 $('stripProvider').title = $('stripProvider').textContent;
 renderModelList();
}
function openDrawer(kind) {
 if (demo) return;
 if (kind === 'provider' && state.viewMode !== 'ai') selectTab('ai');
 $('drawerTitle').textContent = {provider:'AI provider', speech:'Speech engine', effects:'Effects setup', clips:'Clips setup'}[kind];
 document.querySelectorAll('[data-drawer-section]').forEach(section => { section.hidden = section.dataset.drawerSection !== kind; });
 if (!$('drawer').open) $('drawer').showModal();
 $('drawerTitle').focus();
 if (kind === 'provider') refreshModels();
 renderChecks();
}
function selectTab(mode) {
 if (!TABS[mode] || state.viewMode === mode) { if (TABS[mode]) renderTabs(); return; }
 cancelProfileSession();
 state.viewMode = mode;
 render();
 if (mode === 'phrases') requestAnimationFrame(scrollEventIntoView);
}
function scrollEventIntoView() {
 const list = $('evList'), current = list.querySelector('[aria-current=true]');
 if (!current) return;
 if (current.offsetTop < list.scrollTop || current.offsetTop + current.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = current.offsetTop - list.clientHeight / 2;
}

async function commit(mode, activate) {
 if (busy || mediaBusy || savingSound || savingVolume || savingAISettings) return;
 const issue = saveIssue(mode);
 if (issue) { showError(issue); return; }
 if (activate && !setupReadiness(mode).ready) { openDrawer(blockerDrawer(mode)); return; }
 if (!activate && !saveReadiness(mode).ready) { openDrawer(blockerDrawer(mode)); return; }
 const draft = selectionDraft(mode), config = draftConfig(mode);
 if (!activate) {
  delete config.effects_profile;
  delete config.narrator_style;
 }
 busy = true; clearError(); renderChrome();
 try {
  const body = {mode, config, ...(mode === 'phrases' ? {phrases:draft.phrases} : {})};
  if (activate) body.enabled = state.enabled;
  await api(activate ? '/api/activate' : '/api/save', body);
  syncSpeechDrafts(config);
  Object.assign(saved, config);
  if (mode === 'ai' && state.provider === draft.provider && state.apiKey === draft.apiKey) {
   state.apiKey = ''; state.keyEdited = false;
   $('sampleKey').value = '';
  }
  if (mode === 'phrases') saved.phrases = clone(draft.phrases);
  if (activate) {
   saved.soundbar_mode = mode;
   saved.effects_on = state.enabled && mode === 'effects';
   saved.voice_on = state.enabled && mode !== 'effects';
   if (mode !== 'effects') saved.voice_profile = {clips:'generals', phrases:'senior', ai:'narrator'}[mode];
   activeSelection = draft;
   enabledLayers = {effects_on:mode === 'effects', voice_on:mode !== 'effects'};
   toast('Saved · now using ' + selectionLabel());
  } else {
   if (activeSelection.mode === mode) activeSelection = savedDraft(mode);
   toast('Saved');
  }
 } catch (error) { showError(error.message); }
 finally { busy = false; render(); }
}
function syncSpeechDrafts(config, {syncAI=true}={}) {
 // Rebase untouched shared fields without overwriting edits in the other tab.
 const fields = {
  tts_engine:[[state,'phraseEngine']],
  voice_main:[[state.phraseVoices.say,'main']],
  voice_sub:[[state.phraseVoices.say,'sub']],
  kokoro_voice:[[state.phraseVoices.kokoro,'main']],
  kokoro_voice_sub:[[state.phraseVoices.kokoro,'sub']],
 };
 if (syncAI) {
  fields.tts_engine.push([state,'engine']);
  fields.voice_main.push([state.voices,'say']);
  fields.kokoro_voice.push([state.voices,'kokoro']);
 }
 for (const [key, targets] of Object.entries(fields)) {
  if (!Object.hasOwn(config, key)) continue;
  for (const [target, field] of targets) if (target[field] === saved[key]) target[field] = config[key];
 }
}
function discard(mode) {
 if (mode === 'phrases') {
  state.phraseEngine = saved.tts_engine;
  state.phraseVoices = {say:{main:saved.voice_main, sub:saved.voice_sub}, kokoro:{main:saved.kokoro_voice, sub:saved.kokoro_voice_sub || 'am_adam'}};
  state.phrases = normalizePhrases(saved.phrases);
 }
 if (mode === 'ai') {
  state.engine = saved.tts_engine;
  state.voices = {say:saved.voice_main, kokoro:saved.kokoro_voice};
  state.provider = saved.narrator_provider;
  state.model = saved.narrator_model || '';
  state.apiKey = ''; state.keyEdited = false;
  state.context = !!saved.narrator_deep_context;
  $('model').value = state.model;
  $('sampleKey').value = '';
  $('sessionContext').checked = state.context;
  generatedSample = null;
 }
 clearError();
 render();
 toast('Changes discarded');
}
function addPhrase() {
 const roles = phraseRoles(state.phraseEvent);
 state.phrases[state.phraseEvent].push(roles ? ['',''] : '');
 renderPhraseRows();
 renderChrome();
 $('phraseRows').querySelector('.row:last-child input')?.focus();
}
function removePhrase(index) {
 state.phrases[state.phraseEvent].splice(index, 1);
 renderPhraseRows();
 renderChrome();
 const rows = [...$('phraseRows').querySelectorAll('.row:not(.row-head)')];
 (rows[Math.min(index, rows.length - 1)]?.querySelector('input') || $('addPhrase')).focus();
}
function resetPhraseEvent() {
 const defaults = saved.phrases_defaults?.[state.phraseEvent];
 if (!defaults) return;
 state.phrases[state.phraseEvent] = clone(defaults);
 renderPhraseRows();
 renderChrome();
 toast('Defaults restored. Save to keep them.');
}

function variantFor(button, mode) {
 if (button?.hasAttribute('data-variant')) return Number(button.dataset.variant);
 const event = button?.dataset.event || 'edit', pack = button?.dataset.pack || state.pack;
 const samples = (mode === 'effects' ? catalog('effects', pack) : catalog('clips'))[event] || [];
 const key = soundCursorKey(mode, pack, event), variant = cursors[key] || 0;
 if (samples.length) cursors[key] = (variant + 1) % samples.length;
 return variant;
}
function previewKey(button) {
 const {preview:mode, event, variant, role} = button.dataset;
 const content = mode === 'phrases' && !role ? state.phrases[event]?.[Number(variant)] : null;
 const speech = ['phrases','ai'].includes(mode) ? speechIdentity(mode) : null;
 return JSON.stringify([button.id, ...['preview','pack','event','variant','role'].map(key => button.dataset[key] || ''),
  content, speech, mode === 'ai' && !role ? sampleIdentity() : null]);
}
function playingCue(mode, pack, event) {
 const cue = activePreview?.cue;
 return cue?.mode === mode && cue.event === event && (mode !== 'effects' || cue.pack === pack) ? cue : null;
}
function soundCursorKey(mode, pack, event) {
 return mode + ':' + (mode === 'clips' ? 'generals' : pack) + ':' + event;
}
function displayedVariant(mode, pack, event, count) {
 return (playingCue(mode, pack, event)?.variant ?? cursors[soundCursorKey(mode, pack, event)] ?? 0) % count;
}
function renderSampleLabel() {
 const active = activePreview?.key === previewKey($('sampleBtn'));
 $('sampleLabel').textContent = active ? activePreview.phase === 'playing' ? 'Playing…' : 'Generating…'
  : generatedSample?.identity === sampleIdentity() ? 'Replay' : 'Play sample';
}
function renderPreviewState() {
 renderSampleLabel();
 document.querySelectorAll('[data-preview]').forEach(button => {
  const {preview:mode, pack, event} = button.dataset;
  const cue = button.matches('.ev-tile') ? playingCue(mode, pack, event) : null;
  const active = activePreview?.key === previewKey(button) || !!cue;
  const playing = active && activePreview.phase === 'playing';
  button.classList.toggle('is-playing', playing);
  button.classList.toggle('is-generating', active && !playing);
  button.setAttribute('aria-busy', String(active));
  button.querySelector('svg use')?.setAttribute('href', active ? playing ? '#i-wave' : '#i-reset' : '#i-play');
  if (button.matches('.ev-tile')) {
   const samples = catalog(mode, pack)[event] || [];
   button.querySelector('.ev-sound').textContent = samples[displayedVariant(mode, pack, event, samples.length)] || '';
  }
  if (['phrases','ai'].includes(mode) && !demo) {
   const empty = mode === 'phrases' && !button.dataset.role &&
    [state.phrases[button.dataset.event]?.[Number(button.dataset.variant)]].flat().some(text => !String(text || '').trim());
   const blocked = speechEngine(mode) === 'kokoro' && !speechReadiness(mode).ready;
   button.disabled = mediaBusy || empty || blocked;
   button.title = blocked ? speechReadiness(mode).message : '';
  } else button.disabled = mediaBusy;
 });
}
async function mediaAction(button, work, phase='playing', cue=null) {
 if (mediaBusy) return;
 clearError();
 mediaBusy = true;
 activePreview = button?.matches('[data-preview]') ? {key:previewKey(button), phase, cue} : null;
 button?.setAttribute('aria-busy', 'true');
 const controls = [...document.querySelectorAll('[data-preview]')].map(control => [control, control.disabled]);
 controls.forEach(([control]) => { control.disabled = true; });
 renderChrome();
 try { await work(); }
 catch (error) { if (error.name !== 'AbortError') showError(error.message); }
 finally {
  mediaBusy = false;
  activePreview = null;
  button?.setAttribute('aria-busy', 'false');
  controls.forEach(([control, disabled]) => { control.disabled = disabled; });
  render();
 }
}
async function preview(mode, button) {
 if (mediaBusy) return;
 const role = button?.dataset.role || null;
 if (mode === 'ai' && !role) { await playCommentarySample(button); return; }
 const pack = button?.dataset.pack;
 if (button?.hasAttribute('data-session')) {
  // Browsing the requested pack is independent of readiness and activation.
  state.pack = pack; filters[mode] = 'All'; render();
 }
 const readiness = mode === 'phrases' || mode === 'ai' ? speechReadiness(mode) : setupReadiness(mode, pack);
 if (pack && !setup.effects?.[pack]?.ready) { openDrawer('effects'); showError(setup.effects?.[pack]?.message || 'Audio unavailable'); return; }
 if (!readiness.ready) { openDrawer(blockerDrawer(mode)); return; }
 if (button?.hasAttribute('data-session')) { await playProfileSession(mode, pack, button); return; }
 const event = button?.dataset.event || (mode === 'phrases' ? state.phraseEvent : 'edit');
 const variant = variantFor(button, mode);
 const config = pack ? {effects_profile:pack} : draftConfig(mode);
 const body = {mode, config, role, event, variant};
 if (mode === 'phrases' && !role) body.phrases = {[event]: state.phrases[event]};
 await mediaAction(button, () => api('/api/draft-preview', body), 'playing',
  ['effects','clips'].includes(mode) ? {mode, pack, event, variant} : null);
}
function cancelProfileSession() {
 if (activePreview?.session) activePreview.session.cancelled = true;
}
async function playProfileSession(mode, pack, button) {
 const available = catalog(mode, pack);
 const sequence = PROFILE_SESSION_EVENTS.filter(event => available[event]?.length);
 const events = sequence.length ? sequence : Object.keys(available).slice(0, 5);
 await mediaAction(button, async () => {
  const session = activePreview.session = {cancelled:false};
  const token = demo?.playbackToken();
  for (const [index, event] of events.entries()) {
   if (session.cancelled || demo && token !== demo.playbackToken()) break;
   activePreview.cue = {mode, pack, event, variant:0};
   renderPreviewState();
   const container = $('effectsEvents');
   const tile = [...container.querySelectorAll('.ev-tile')].find(node => node.dataset.event === event);
   if (tile) {
    const bounds = container.getBoundingClientRect(), cue = tile.getBoundingClientRect();
    if (cue.top < bounds.top) container.scrollTop += cue.top - bounds.top;
    else if (cue.bottom > bounds.bottom) container.scrollTop += cue.bottom - bounds.bottom;
   }
   await api('/api/draft-preview', {mode, config:{effects_profile:pack}, event, variant:0});
   activePreview.cue = null;
   renderPreviewState();
   if (index < events.length - 1 && !session.cancelled) await new Promise(resolve => setTimeout(resolve, 400));
  }
 });
}
async function playCommentarySample(button) {
 if (!speechReadiness('ai').ready) { openDrawer('speech'); return; }
 if ((!generatedSample || generatedSample.identity !== sampleIdentity()) && !hasProviderKey()) { openDrawer('provider'); showError('API key required'); return; }
 const config = draftConfig('ai'), identity = sampleIdentity();
 const generate = generatedSample?.identity !== identity;
 await mediaAction(button, async () => {
  if (generate) {
   const result = await api('/api/draft-preview', {mode:'ai', action:'generate', config});
   if (identity !== sampleIdentity()) return;
   generatedSample = {identity, text:result.text};
   rememberCheck('ai', {identity:aiIdentity(), status:'checked'});
   renderSample();
  }
  activePreview.phase = 'playing';
  renderPreviewState();
  await api('/api/draft-preview', {mode:'ai', action:'play', config, text:generatedSample.text});
 }, generate && !demo ? 'generating' : 'playing');
}

async function installKokoro() {
 if (setup.installing) return;
 const repair = !!setup.kokoro || ['phrases','aiSpeech'].some(key => cachedCheck(key)?.status === 'failed' && cachedCheck(key)?.identity === checkIdentity(key));
 for (const [id, check] of setupChecks) if (check.config?.tts_engine === 'kokoro') setupChecks.delete(id);
 clearTimeout(modelPoll);
 clearError();
 setup.installing = true; setup.installStatus = 'running'; setup.installMessage = '';
 setup.installElapsed = setup.installQuiet = 0; setup.installOutput = [];
 render();
 try {
  const result = await api('/api/kokoro-install', {repair});
  setup.installing = result.status === 'running';
  await pollInstall();
 } catch (error) {
  setup.installing = false; setup.installStatus = 'error'; setup.installMessage = error.message;
  showError(error.message);
 } finally { render(); }
}
async function pollInstall() {
 clearTimeout(installPoll);
 try {
  await refreshSetup();
  render();
  if (setup.installing) installPoll = setTimeout(pollInstall, 2000);
  else checkInitialSpeech();
 } catch (error) {
  showError(error.message);
  installPoll = setTimeout(pollInstall, 5000);
 }
}
function aiSettings(kind) {
 if (kind === 'provider') {
  const config = {narrator_provider:state.provider, narrator_model:state.model};
  // Status exposes a masked saved key. Only send an explicitly edited credential.
  if (state.keyEdited || state.apiKey || state.provider !== saved.narrator_provider) config.narrator_api_key = state.apiKey;
  return config;
 }
 return {tts_engine:state.engine, [state.engine === 'kokoro' ? 'kokoro_voice' : 'voice_main']:state.voices[state.engine]};
}
function persistAISettings(kind) {
 if (demo) return;
 const changes = aiSettings(kind);
 savingAISettings++;
 clearError(); renderChrome();
 // Keep rapid edits ordered; each request contains only this settings group.
 aiSettingsQueue = aiSettingsQueue.then(async () => {
  try {
   await api('/api/config', changes);
   // AI already holds the latest selection, which may be newer than this save.
   syncSpeechDrafts(changes, {syncAI:false});
   Object.assign(saved, changes);
   if (kind === 'provider' && same(aiSettings(kind), changes)) {
    state.apiKey = ''; state.keyEdited = false; $('sampleKey').value = '';
   }
  } catch (error) {
   // A failed older request must not overwrite a newer edit waiting in the queue.
   if (same(aiSettings(kind), changes)) {
    if (kind === 'provider') {
     state.provider = saved.narrator_provider; state.model = saved.narrator_model || ''; state.apiKey = ''; state.keyEdited = false;
     $('model').value = state.model; $('sampleKey').value = '';
     invalidateProvider({clearModels:true});
    } else {
     state.engine = saved.tts_engine;
     state.voices = {say:saved.voice_main, kokoro:saved.kokoro_voice};
    }
   }
   showError(error.message);
  } finally {
   savingAISettings--;
   render({preservePhraseEditor:true});
  }
 });
 return aiSettingsQueue;
}
async function saveConfig(changes) { await api('/api/config', changes); Object.assign(saved, changes); }
async function toggleSound() {
 const enabled = $('soundOn').checked, previous = state.enabled;
 state.enabled = enabled;
 savingSound = true; renderChrome();
 try {
  await saveConfig({effects_on:enabled && enabledLayers.effects_on, voice_on:enabled && enabledLayers.voice_on, soundbar_mode:activeSelection.mode === 'combined' ? saved.soundbar_mode : activeSelection.mode});
 } catch (error) {
  showError(error.message);
  state.enabled = previous;
 } finally { savingSound = false; renderChrome(); }
}
async function saveSetting(changes, revert) {
 try { await saveConfig(changes); toast('Saved'); }
 catch (error) { showError(error.message); revert(); }
}

function renderVersions() {
 const running = !!(versions?.running || versionStarting);
 $('closeSoundbar').disabled = !!setup?.installing || running;
 $('closeInstallHint').hidden = !setup?.installing && !running;
 if (!versions) return;
 const needsAttention = ['failed','interrupted'].includes(versions.phase);
 $('installedVersion').textContent = 'Installed: ' + versions.installed;
 $('versionNotice').hidden = !versions.available && !running && !needsAttention;
 $('versionNotice').textContent = running ? 'Updating Code Gossip…' : needsAttention ? 'Update needs attention' : versions.available ? `Update available: ${versions.installed} → ${versions.release.version}` : 'Code Gossip updates';
 const settingsLabel = $('versionNotice').hidden ? 'Settings' : 'Settings · ' + $('versionNotice').textContent;
 $('settingsButton').setAttribute('aria-label', settingsLabel);
 $('settingsButton').title = settingsLabel;
 $('availableVersion').textContent = versions.development ? 'Updates come from your checkout.' : versions.available ? 'Available: ' + versions.release.version : versions.checked_at ? 'You have the latest stable release.' : 'Updates are checked automatically while Soundbar runs.';
 $('releaseNotes').hidden = !versions.release;
 if (versions.release) $('releaseNotes').href = versions.release.notes_url;
 $('checkUpdates').disabled = versions.development || running || versionChecking;
 setSizedText($('checkUpdates'), versionChecking ? 'Checking…' : 'Check for updates', 'Check for updates');
 $('checkUpdates').setAttribute('aria-busy', String(versionChecking));
 $('applyUpdate').hidden = versions.development || !versions.available && !needsAttention && !running;
 $('applyUpdate').disabled = running || versionChecking || !!setup?.installing;
 setSizedText($('applyUpdate'), running ? 'Updating…' : needsAttention ? 'Retry update' : 'Update', 'Retry update', 'Updating…');
 $('applyUpdate').setAttribute('aria-busy', String(running));
 $('updateResult').textContent = versionError || [versions.message, versions.guidance].filter(Boolean).join(' ');
 $('updateResult').dataset.tone = versionError || needsAttention ? 'error' : running ? 'warning' : 'neutral';
 $('updateExplanation').textContent = versions.development ? 'Development installation: update your checkout, then rerun install.sh --dev with your existing agents.' : 'Updates install only when you choose Update. Soundbar restarts; saved preferences are kept.';
}
async function refreshVersions() {
 if (demo) return;
 clearTimeout(versionPoll);
 try {
  versions = await api('/api/updates');
  if (!loadedVersion) loadedVersion = versions.installed;
  if (!versions.running && versions.phase === 'done' && loadedVersion !== versions.installed) { location.reload(); return; }
  renderVersions();
 } catch { if (versions?.running) $('updateResult').textContent = 'Soundbar is restarting. Reconnecting…'; }
 if (!$('closedDialog').open) versionPoll = setTimeout(refreshVersions, versions?.running ? 1000 : 30000);
}
async function checkUpdates() {
 versionChecking = true; versionError = ''; renderVersions();
 try { versions = await api('/api/update-check', {}); }
 catch (error) { versionError = error.message; }
 finally { versionChecking = false; renderVersions(); }
}
async function applyUpdate() {
 versionStarting = true; versionError = ''; renderVersions();
 try { versions = await api('/api/update', {}); }
 catch (error) { versionError = error.message; }
 finally { versionStarting = false; renderVersions(); refreshVersions(); }
}
async function closeSoundbar() {
 if (setup?.installing || versions?.running) return;
 const button = $('closeSoundbar');
 button.disabled = true;
 try {
  const response = await fetch('/api/shutdown', {method:'POST', headers:{'X-Soundbar-Request':'ui'}});
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error('Could not stop Soundbar');
  clearTimeout(installPoll); clearTimeout(modelPoll); clearTimeout(versionPoll);
  $('settingsDialog').close();
  $('closedDialog').showModal();
  $('closedTitle').focus();
 } catch (error) {
  showError(error.message);
  button.disabled = false;
 }
}

function toggleHelp(open=$('helpPopover').hidden) {
 $('helpPopover').hidden = !open;
 $('helpButton').setAttribute('aria-expanded', String(open));
 if (open) $('guideList').querySelector('button')?.focus();
}
function flash(element) {
 if (!element) return;
 element.scrollIntoView({block:'nearest'});
 element.classList.remove('flash');
 void element.offsetWidth;
 element.classList.add('flash');
}
function gotoGuide(target) {
 if (target === 'settings') { $('settingsDialog').showModal(); return; }
 if (target === 'provider') { openDrawer('provider'); return; }
 const tab = {effects:'effects', events:'effects', phrases:'phrases', state:state.viewMode}[target];
 if (tab) selectTab(tab);
 const element = {effects:$('tabs'), events:$('effectsWorkspace'), phrases:$('phrasesWorkspace'), state:document.querySelector(`[data-state="${state.viewMode}"]`)}[target];
 requestAnimationFrame(() => flash(element));
}
function invalidateProvider(options={}) {
 generatedSample = null;
 if (options.clearModels) modelList = null;
}

function wire() {
 document.querySelectorAll('[data-theme-choice]').forEach(button => button.onclick = () => applyTheme(button.dataset.themeChoice));
 $('helpButton').onclick = event => { event.stopPropagation(); toggleHelp(); };
 document.addEventListener('click', event => {
  const target = event.target;
  if (target.closest('[data-dismiss-error]')) { clearError(); return; }
  const tab = target.closest('[data-mode]');
  if (tab?.closest('#tabs')) { selectTab(tab.dataset.mode); return; }
  const act = target.closest('[data-act]');
  if (act) { ({save:() => commit(state.viewMode, false), use:() => commit(state.viewMode, true), discard:() => discard(state.viewMode)})[act.dataset.act](); return; }
  const drawer = target.closest('[data-drawer]');
  if (drawer) { openDrawer(drawer.dataset.drawer); return; }
  const filter = target.closest('[data-filter]');
  if (filter) { const [mode, group] = filter.dataset.filter.split(':'); filters[mode] = group; mode === 'effects' ? renderEffectsDetail() : renderClips(); renderPreviewState(); return; }
  const phraseEvent = target.closest('[data-phrase-event]');
  if (phraseEvent) { state.phraseEvent = phraseEvent.dataset.phraseEvent; renderPhraseRows(); renderChrome(); $('phraseRows').parentElement.scrollTop = 0; return; }
  const remove = target.closest('[data-remove]');
  if (remove) { removePhrase(Number(remove.dataset.remove)); return; }
  const play = target.closest('[data-preview]');
  if (play) { preview(play.dataset.preview, play); return; }
  const guide = target.closest('[data-guide]');
  if (guide) { guideDone.add(guide.dataset.guide); guide.classList.add('done'); toggleHelp(false); gotoGuide(guide.dataset.guide); return; }
  if (!$('helpPopover').hidden && !target.closest('.help-wrap')) toggleHelp(false);
 });
 document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('helpPopover').hidden && !document.querySelector('dialog[open]')) { toggleHelp(false); $('helpButton').focus(); }
 });
 $('tabs').addEventListener('keydown', event => {
  const ids = Object.keys(TABS); let index = ids.indexOf(state.viewMode);
  if (event.key === 'ArrowRight') index = (index + 1) % ids.length;
  else if (event.key === 'ArrowLeft') index = (index + ids.length - 1) % ids.length;
  else if (event.key === 'Home') index = 0;
  else if (event.key === 'End') index = ids.length - 1;
  else return;
  event.preventDefault();
  selectTab(ids[index]);
  $('tab-' + ids[index]).focus();
 });
 $('now').onclick = () => { if (!demo) selectTab(activeSelection.mode === 'combined' ? 'effects' : activeSelection.mode); };
 $('soundOn').onchange = toggleSound;
 $('volume').oninput = () => { $('volumeValue').textContent = $('volume').value + '%'; };
 $('volume').onchange = async () => {
  const volume = Number($('volume').value);
  savingVolume = true; renderChrome();
  try { await saveConfig({effects_volume:volume, voice_volume:volume}); state.volume = volume; }
  catch (error) { showError(error.message); }
  finally { savingVolume = false; $('volume').value = state.volume; $('volumeValue').textContent = state.volume + '%'; renderChrome(); }
 };
 $('packList').addEventListener('change', event => { if (event.target.name !== 'pack') return; cancelProfileSession(); state.pack = event.target.value; render(); });
 $('styleList').addEventListener('change', event => { if (event.target.name !== 'style') return; state.style = event.target.value; generatedSample = null; renderStyles(); renderSample(); renderChrome(); });
 $('phraseEngine').onchange = () => { state[state.viewMode === 'ai' ? 'engine' : 'phraseEngine'] = $('phraseEngine').value; render(); if (state.viewMode === 'ai') persistAISettings('speech'); };
 $('mainAgentVoice').onchange = () => { state.phraseVoices[state.phraseEngine].main = $('mainAgentVoice').value; render(); };
 $('subagentVoice').onchange = () => { state.phraseVoices[state.phraseEngine].sub = $('subagentVoice').value; render(); };
 $('speaker').onchange = () => { state.voices[state.engine] = $('speaker').value; render(); persistAISettings('speech'); };
 $('phraseRows').addEventListener('input', event => {
  const input = event.target;
  if (input.tagName !== 'INPUT') return;
  const items = state.phrases[state.phraseEvent], index = Number(input.dataset.index), part = Number(input.dataset.part);
  if (Array.isArray(items[index])) items[index][part] = input.value; else items[index] = input.value;
  input.classList.toggle('invalid', !input.value.trim());
  const play = input.closest('.row')?.querySelector('[data-preview]');
  if (play) play.disabled = [items[index]].flat().some(text => !String(text).trim());
  renderChrome();
 });
 $('phraseRows').addEventListener('keydown', event => {
  if (demo) return;
  if (event.key !== 'Enter' || event.target.tagName !== 'INPUT') return;
  event.preventDefault();
  const next = event.target.closest('.row').nextElementSibling;
  if (next) next.querySelector('input').focus(); else addPhrase();
 });
 $('addPhrase').onclick = addPhrase;
 $('resetEvent').onclick = resetPhraseEvent;
 $('provider').onchange = () => {
  state.provider = $('provider').value; state.model = ''; state.apiKey = ''; state.keyEdited = true;
  $('model').value = ''; $('sampleKey').value = '';
  invalidateProvider({clearModels:true});
  showProvider(); renderSample(); renderChecks();
  persistAISettings('provider');
  if (!needsKey()) { refreshModels(); }
 };
 $('model').oninput = () => { state.model = $('model').value; invalidateProvider(); showProvider(); renderChecks(); };
 $('sampleKey').oninput = () => { state.apiKey = $('sampleKey').value; state.keyEdited = true; invalidateProvider({clearModels:true}); renderModelList(); renderChecks(); };
 $('model').onchange = () => persistAISettings('provider');
 $('sampleKey').onchange = () => { persistAISettings('provider'); refreshModels(); };
 $('refreshModels').onclick = () => refreshModels(true);
 $('sessionContext').onchange = () => { state.context = $('sessionContext').checked; renderChrome(); };
 document.querySelectorAll('[data-check-setup]').forEach(button => button.onclick = () => checkSetup(button.dataset.checkSetup));
 $('installKokoro').onclick = installKokoro;
 $('installSox').onclick = () => { $('soxCommand').hidden = false; };
 $('closeDrawer').onclick = () => $('drawer').close();
 $('drawer').addEventListener('click', event => { if (event.target === $('drawer')) $('drawer').close(); });
 $('settingsButton').onclick = () => $('settingsDialog').showModal();
 $('closeSettings').onclick = () => $('settingsDialog').close();
 $('versionNotice').onclick = event => { event.stopPropagation(); $('settingsDialog').showModal(); $('versionPreferences').scrollIntoView({block:'nearest'}); };
 $('checkUpdates').onclick = checkUpdates;
 $('applyUpdate').onclick = applyUpdate;
 $('closeSoundbar').onclick = closeSoundbar;
 $('closedDialog').oncancel = event => event.preventDefault();
 $('reduceRepeats').onchange = () => saveSetting({sound_spacing_on:$('reduceRepeats').checked}, () => { $('reduceRepeats').checked = saved.sound_spacing_on; for (const id of ['effectsGap','voiceGap']) $(id).disabled = !saved.sound_spacing_on; });
 $('reduceRepeats').addEventListener('change', () => { for (const id of ['effectsGap','voiceGap']) $(id).disabled = !$('reduceRepeats').checked; });
 for (const [id, key] of [['effectsGap','effects_cooldown_ms'],['voiceGap','voice_cooldown_ms']]) {
  $(id).oninput = () => { $(id + 'Value').textContent = ($(id).value / 1000) + 's'; };
  $(id).onchange = () => saveSetting({[key]:Number($(id).value)}, () => { $(id).value = saved[key]; $(id + 'Value').textContent = (saved[key] / 1000) + 's'; });
 }
 $('approvalCues').onchange = () => saveSetting({codex_permission_sound_on:$('approvalCues').checked}, () => { $('approvalCues').checked = saved.codex_permission_sound_on; });
 $('guideList').innerHTML = GUIDE.map(([id, title, text], index) => `<button type="button" class="guide-item" data-guide="${id}"><span class="step"><span>${index + 1}</span>${icon('check')}</span><span><strong>${title}</strong><small>${text}</small></span></button>`).join('');
 window.addEventListener('beforeunload', event => { if (saved && Object.keys(TABS).some(isDirty)) { event.preventDefault(); event.returnValue = ''; } });
}

async function load() {
 saved = await api('/api/status');
 setup = saved.setup;
 styleNames = Object.fromEntries(Object.entries(saved.narrator_styles).map(([id, style]) => [id, style.label || id]));
 voiceChoices = {say:saved.voices.map(voice => [voice.name, voice.name]), kokoro:saved.kokoro_voices.map(voice => [voice.id, voice.name])};
 const voiceMode = profileModes[saved.voice_profile] || 'phrases';
 const active = saved.effects_on && saved.voice_on ? 'combined' : saved.voice_on ? voiceMode : saved.effects_on ? 'effects' : (TABS[saved.soundbar_mode] ? saved.soundbar_mode : 'effects');
 const viewMode = active === 'combined' ? voiceMode : active;
 enabledLayers = active === 'combined' ? {effects_on:true, voice_on:true} : {effects_on:viewMode === 'effects', voice_on:viewMode !== 'effects'};
 saved.phrases = normalizePhrases(saved.phrases);
 state = {
  viewMode, enabled:!!(saved.effects_on || saved.voice_on),
  volume:viewMode === 'effects' || active === 'combined' ? saved.effects_volume : saved.voice_volume,
  pack:saved.effects_profile, style:saved.narrator_style, engine:saved.tts_engine, phraseEngine:saved.tts_engine,
  voices:{say:saved.voice_main, kokoro:saved.kokoro_voice},
  phraseVoices:{say:{main:saved.voice_main, sub:saved.voice_sub}, kokoro:{main:saved.kokoro_voice, sub:saved.kokoro_voice_sub || 'am_adam'}},
  provider:saved.narrator_provider, model:saved.narrator_model || '', apiKey:'', context:!!saved.narrator_deep_context,
  phraseEvent:saved.events.includes('subagent_start') ? 'subagent_start' : saved.events[0],
  phrases:normalizePhrases(saved.phrases),
 };
 // The demo preserves shipped defaults in its catalog; only its audition engine is fixed.
 if (demo) { state.engine = state.phraseEngine = 'kokoro'; state.phraseEvent = 'edit'; }
 activeSelection = active === 'combined' ? {mode:'combined'} : selectionDraft(viewMode);
 fillSelect('provider', Object.entries(saved.narrator_providers).map(([id, provider]) => [id, provider.name]), state.provider);
 $('model').value = state.model;
 $('sessionContext').checked = state.context;
 $('volume').value = state.volume;
 $('volumeValue').textContent = state.volume + '%';
 $('reduceRepeats').checked = !!saved.sound_spacing_on;
 $('approvalCues').checked = !!saved.codex_permission_sound_on;
 for (const [id, key] of [['effectsGap','effects_cooldown_ms'],['voiceGap','voice_cooldown_ms']]) {
  $(id).value = saved[key];
  $(id).disabled = !saved.sound_spacing_on;
  $(id + 'Value').textContent = (saved[key] / 1000) + 's';
 }
 if (!demo) cacheAudioSetup();
 applyTheme(currentTheme());
 buildTabs();
 render();
 if (setup.installing) installPoll = setTimeout(pollInstall, 0);
}

window.refreshVersions = refreshVersions;
window.addEventListener('DOMContentLoaded', async () => {
 try {
  await load();
  wire();
  if (demo) demo.ready(selectTab);
  if (!demo) {
   checkInitialSpeech();
   if (!needsKey()) checkSetup('ai', {automatic:true});
  }
  refreshVersions();
 } catch (error) {
  $('loadError').hidden = false;
  if ($('statusText')) $('statusText').textContent = 'Disconnected';
  showError(error.message);
 }
});
