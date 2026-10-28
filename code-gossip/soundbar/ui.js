'use strict';
const demo = window.soundbarDemo || null;
const $ = id => document.getElementById(id);
const TABS = {effects:{name:'Effects',icon:'wave'}, clips:{name:'Clips',icon:'film'}, phrases:{name:'Phrases',icon:'chat'}, ai:{name:'AI commentary',icon:'spark'}};
const modeNames = Object.fromEntries(Object.entries(TABS).map(([id,tab]) => [id, tab.name]));
const profileModes = {senior:'phrases', narrator:'ai'};
const CLIP_META = {
 generals:'Commander-style radio calls, generated with macOS speech.',
 empires:'Rough workers, scouts, scholars, and commanders. Familiar Age of Empires and Rise of Nations phrases plus new calls, performed by generated voices.',
};
const profileMode = profile => profileModes[profile] || (saved?.preview_catalog?.voice?.[profile] ? 'clips' : 'phrases');
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
 ['events','Audition sounds','Press an event to hear it. Nothing changes until you save.'],
 ['phrases','Edit phrases','Pick an event on the left and rewrite its lines.'],
 ['provider','Connect AI commentary','Pick a provider. Cloud checks run only when you ask.'],
 ['state','Save and use','Save keeps edits. Use switches what agents play.'],
 ['settings','Settings','Theme, pacing, and Codex approval cues.'],
];

let saved, state, activeSelection, setup, voiceChoices, styleNames;
let checkedAI = null, busy = false, savingSound = false, savingVolume = false, mediaBusy = false, installPoll = null;
const setupChecks = {}, filters = {effects:'All', clips:'All'}, cursors = {}, guideDone = new Set();
let setupChecksReady = false, setupCheckTimer = null, enabledLayers, generatedSample = null, modelList = null;
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

async function api(path, body) {
 if (demo) return demo.request(path, body);
 const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Soundbar-Request':'ui'}, body:JSON.stringify(body)});
 const data = await response.json();
 if (!response.ok || data.ok === false) throw new Error(data.error || data.message || 'Request failed');
 return data;
}
function toast(message) {
 $('toastText').textContent = message;
 $('toast').classList.add('show');
 clearTimeout(toastTimer);
 toastTimer = setTimeout(() => $('toast').classList.remove('show'), 2400);
}
function showError(message) { $('errorBanner').textContent = message || ''; }
function clearError() { if ($('errorBanner')) $('errorBanner').textContent = ''; }

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
function providerKey() { return state.apiKey || (state.provider === saved.narrator_provider ? saved.narrator_api_key : '') || ''; }
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
 return saved.preview_catalog?.voice?.[state.clip] || {};
}
function savedClipProfile() {
 const clips = saved.preview_catalog?.voice || {};
 return clips[saved.voice_profile] ? saved.voice_profile : clips[saved.clips_profile] ? saved.clips_profile : Object.keys(clips)[0] || 'generals';
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
 if (mode === 'clips') return {mode, profile:state.clip};
 if (mode === 'phrases') return {mode, engine:state.phraseEngine, voices:clone(state.phraseVoices[state.phraseEngine]), phrases:clone(state.phrases)};
 return {mode, style:state.style, engine:state.engine, voice:state.voices[state.engine], provider:state.provider, model:state.model, context:state.context, apiKey:state.apiKey};
}
function savedDraft(mode) {
 if (mode === 'effects') return {mode, pack:saved.effects_profile};
 if (mode === 'clips') return {mode, profile:savedClipProfile()};
 const engine = saved.tts_engine;
 if (mode === 'phrases') {
  const voices = engine === 'kokoro' ? {main:saved.kokoro_voice, sub:saved.kokoro_voice_sub || 'am_adam'} : {main:saved.voice_main, sub:saved.voice_sub};
  return {mode, engine, voices, phrases:normalizePhrases(saved.phrases)};
 }
 return {mode, style:saved.narrator_style, engine, voice:engine === 'kokoro' ? saved.kokoro_voice : saved.voice_main, provider:saved.narrator_provider, model:saved.narrator_model || '', context:!!saved.narrator_deep_context, apiKey:''};
}
function isDirty(mode) { return !demo && !same(selectionDraft(mode), savedDraft(mode)); }
function modeInUse(mode) {
 if (demo) return false;
 if (activeSelection.mode === 'combined') return mode === 'effects' || mode === profileMode(saved.voice_profile);
 return activeSelection.mode === mode;
}
function selectionLabel(selection=activeSelection) {
 const mode = selection.mode;
 if (mode === 'combined') return `Effects · ${packName(saved.effects_profile)} + ${modeNames[profileMode(saved.voice_profile)]}`;
 if (mode === 'effects') return `Effects · ${packName(selection.pack || saved.effects_profile)}`;
 if (mode === 'clips') return `Clips · ${packName(selection.profile || savedClipProfile())}`;
 if (mode === 'phrases') return 'Phrases · Senior';
 const style = selection.style || saved.narrator_style;
 return `AI commentary · ${styleNames[style] || style}`;
}
function draftConfig(mode=state.viewMode) {
 if (mode === 'effects') return {effects_profile:state.pack};
 if (mode === 'clips') return {clips_profile:state.clip};
 const engine = speechEngine(mode), config = {tts_engine:engine};
 if (mode === 'phrases') {
  const voices = state.phraseVoices[engine];
  Object.assign(config, engine === 'kokoro' ? {kokoro_voice:voices.main, kokoro_voice_sub:voices.sub} : {voice_main:voices.main, voice_sub:voices.sub});
 } else {
  config[engine === 'kokoro' ? 'kokoro_voice' : 'voice_main'] = state.voices[engine];
  Object.assign(config, {narrator_provider:state.provider, narrator_model:state.model, narrator_style:state.style, narrator_deep_context:state.context});
  if (state.apiKey || state.provider !== saved.narrator_provider) config.narrator_api_key = state.apiKey;
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
 if (!installation.available) return {ready:false, message:installation.message};
 const voices = mode === 'phrases' ? Object.values(state.phraseVoices[engine]) : [state.voices[engine]];
 if (voices.some(voice => !(voiceChoices[engine] || []).some(([id]) => id === voice))) return {ready:false, message:'Choose installed voices'};
 const key = mode === 'phrases' ? 'phrases' : 'aiSpeech';
 const check = setupChecks[key], current = check?.identity === speechIdentity(mode);
 if (current && check.status === 'failed') return {ready:false, message:'Check failed'};
 if (current && check.status === 'checking') return {ready:false, message:'Checking speech…'};
 return {ready:true, message:current && check.status === 'checked' ? 'Engine available' : 'Not checked'};
}
function setupReadiness(mode, pack=state.pack) {
 if (mode === 'effects' || mode === 'clips') {
  const available = mode === 'effects' ? setup.effects?.[pack] : setup.clips?.[state.clip];
  if (!available?.ready) return available || {ready:false, message:'Audio unavailable'};
  const check = setupChecks[mode], current = check?.identity === checkIdentity(mode, pack);
  if (current && check.status === 'failed') return {ready:false, message:'Check failed'};
  if (current && check.status === 'checking') return {ready:false, message:'Checking…'};
  return {ready:true, message:current && check.status === 'checked' ? 'Audio available' : 'Not checked'};
 }
 const speech = speechReadiness(mode);
 if (!speech.ready) return speech;
 if (mode === 'ai' && checkedAI !== aiIdentity()) return {ready:false, message:'Check the provider first'};
 return speech;
}
function saveReadiness(mode) {
 if (mode === 'effects' && modeInUse(mode)) return setupReadiness(mode);
 if (mode === 'clips' && modeInUse(mode)) return setupReadiness(mode);
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
 const check = setupChecks[key], current = check?.identity === checkIdentity(key), status = current ? check.status : 'unchecked';
 const provider = key === 'ai', cli = provider && state.provider === 'claude_cli';
 const action = provider ? (cli ? 'Check CLI' : state.provider === 'ollama' ? 'Check server' : 'Check connection') : 'Check';
 const pending = provider && !cli ? 'Connecting…' : 'Checking…';
 const success = provider ? (cli ? 'CLI found' : state.provider === 'ollama' ? 'Server reachable' : 'Connection verified') : key === 'effects' || key === 'clips' ? 'Audio available' : 'Engine available';
 let prerequisite = null;
 if (provider && !hasProviderKey()) prerequisite = {message:'API key required', tone:'warning'};
 if (key === 'effects' || key === 'clips') {
  const resource = key === 'effects' ? setup.effects?.[state.pack] : setup.clips?.[state.clip];
  if (!resource?.ready) prerequisite = {message:resource?.message || 'Audio unavailable', tone:resource?.missing?.length ? 'error' : 'warning'};
 }
 if (key === 'phrases' || key === 'aiSpeech') {
  const installation = speechInstallation(speechEngine(checkModes[key]));
  if (!installation.available) prerequisite = installation;
  else if (!speechReadiness(checkModes[key]).ready && status !== 'failed' && status !== 'checking') prerequisite = {message:'Choose installed voices', tone:'warning'};
 }
 const result = {message:status === 'checked' ? success : status === 'failed' ? 'Check failed' : status === 'checking' ? pending : provider && !cli ? 'Not checked' : 'Not checked', tone:status === 'checked' ? 'success' : status === 'failed' ? 'error' : 'warning'};
 return {action, pending, status, checking:check?.status === 'checking', prerequisite, ...(prerequisite || result)};
}
function paintStatus(node, view) {
 const tone = {success:'ok', warning:'warn', error:'err'}[view.tone] || '';
 node.className = 'status' + (tone ? ' ' + tone : '');
 node.dataset.tone = view.tone || 'neutral';
 node.textContent = view.message;
 node.hidden = !!(view.checking && !view.prerequisite);
}
function modeCheckKeys() {
 if (state.viewMode === 'ai') return needsKey() ? ['aiSpeech'] : ['aiSpeech', 'ai'];
 return [state.viewMode === 'phrases' ? 'phrases' : state.viewMode];
}
function scheduleSetupChecks(delay=150) {
 if (demo || !setupChecksReady) return;
 clearTimeout(setupCheckTimer);
 const run = () => {
  for (const key of modeCheckKeys()) {
   const check = setupChecks[key];
   if (check?.status === 'checking' || check?.identity === checkIdentity(key) || checkPresentation(key).prerequisite) continue;
   checkSetup(key, {automatic:true});
  }
 };
 if (delay) setupCheckTimer = setTimeout(run, delay); else run();
}
async function refreshSetup() { setup = {...setup, ...await api('/api/setup')}; }
async function checkSetup(key, {automatic=false}={}) {
 if (setupChecks[key]?.status === 'checking' || (checkPresentation(key).prerequisite && key !== 'effects' && key !== 'clips')) return;
 const mode = checkModes[key], config = draftConfig(mode), identity = checkIdentity(key), button = checkButton(key);
 const check = setupChecks[key] = {identity, status:'checking'};
 if (key === 'ai') checkedAI = null;
 if (!automatic) clearError();
 renderChecks();
 try {
  await refreshSetup();
  await api('/api/draft-check', {mode, config, scope:key === 'ai' ? 'provider' : 'speech'});
  check.status = 'checked';
  if (identity === checkIdentity(key) && key === 'ai') { checkedAI = identity; refreshModels(); }
 } catch (error) {
  check.status = 'failed';
  if (identity === checkIdentity(key)) showError(error.message);
 } finally {
  render();
  if (identity !== checkIdentity(key)) scheduleSetupChecks();
 }
}

function providerNote() {
 if (state.provider === 'claude_cli') return 'Checks that Claude CLI is installed. Play a sample to test sign-in and model access. Cloud providers are checked only when you ask.';
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
 if (state.apiKey || state.provider !== saved.narrator_provider) config.narrator_api_key = state.apiKey;
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
  if (!demo && id === 'ai' && checkedAI !== aiIdentity()) badges += `<span title="Provider not checked">${icon('warn','tab-warn')}</span>`;
  $('badges-' + id).innerHTML = badges;
 }
}
function renderNow() {
 $('now').classList.toggle('muted', !state.enabled);
 $('now').classList.toggle('is-playing', mediaBusy);
 $('statusText').textContent = `${state.enabled ? demo ? 'Preview' : 'In use' : 'Muted'} · ${selectionLabel(demo ? selectionDraft() : activeSelection)}`;
 $('powerLabel').textContent = state.enabled ? 'Sound on' : 'Sound off';
 $('soundOn').checked = state.enabled;
 $('soundOn').disabled = busy || !demo && mediaBusy || savingSound;
 $('volume').disabled = busy || !demo && mediaBusy || savingVolume;
 if (demo) { $('demoSession').disabled = mediaBusy; $('demoStop').disabled = !mediaBusy; }
}
function renderPanelState(mode) {
 if (demo) return;
 const inUse = modeInUse(mode), exclusive = activeSelection.mode === mode, dirty = isDirty(mode), issue = dirty ? saveIssue(mode) : '';
 const readiness = setupReadiness(mode), blocked = !readiness.ready, drawer = blockerDrawer(mode);
 const saveReady = saveReadiness(mode), saving = busy || mediaBusy || savingSound || savingVolume;
 const link = `<button type="button" class="link" data-drawer="${drawer}">${drawer === 'provider' ? 'Configure' : 'Details'}</button>`;
 let html = '';
 if (dirty) {
  html += '<span class="unsaved"><i class="dirty-dot"></i>Unsaved changes</span>';
  if (issue) html += `<span class="state-issue">${icon('warn')}${esc(issue)}</span>`;
  else if (!saveReady.ready || !exclusive && blocked) html += `<span class="state-issue">${icon('warn')}${esc(!saveReady.ready ? saveReady.message : readiness.message)} · ${link}</span>`;
  const saveDisabled = busy || mediaBusy || !!issue;
  html += `<button type="button" class="btn ghost" data-act="discard" ${busy || mediaBusy ? 'disabled' : ''}>Discard</button>`;
  html += `<button type="button" class="btn ${exclusive ? 'primary' : ''}" data-act="save" ${saveDisabled || saving || !saveReady.ready ? 'disabled' : ''}${mode === state.viewMode && exclusive ? ' id="activateSelection"' : ''}${busy ? ' aria-busy="true"' : ''}>${inUse ? 'Save changes' : 'Save'}</button>`;
  if (!exclusive) html += `<button type="button" class="btn primary" data-act="save-use" ${saveDisabled || saving || blocked ? 'disabled' : ''}${mode === state.viewMode ? ' id="activateSelection"' : ''}${busy ? ' aria-busy="true"' : ''}>Save &amp; use</button>`;
 } else if (exclusive) html += `<span class="pill success">${icon('check')}In use</span>`;
 else {
  if (inUse) html += `<span class="pill success">${icon('check')}In use</span>`;
  if (blocked) html += `<span class="state-issue">${icon('warn')}${esc(readiness.message)} · ${link}</span>`;
  html += `<button type="button" class="btn primary" data-act="use" ${saving || blocked ? 'disabled' : ''}${mode === state.viewMode ? ' id="activateSelection"' : ''}${busy ? ' aria-busy="true"' : ''}>Use ${esc(modeNames[mode])}</button>`;
 }
 document.querySelector(`[data-state="${mode}"]`).innerHTML = html;
}
function renderChrome() {
 renderTabs();
 renderNow();
 for (const mode of Object.keys(TABS)) renderPanelState(mode);
 renderEventList();
 const defaults = saved.phrases_defaults?.[state.phraseEvent];
 $('resetEvent').hidden = !defaults;
 $('resetEvent').disabled = !!defaults && same(state.phrases[state.phraseEvent], defaults);
 $('activationProgress').textContent = busy ? 'Saving selection…' : '';
}

function renderFilters(mode) {
 $('filters-' + mode).innerHTML = ['All', ...groupedEvents().map(([group]) => group)].map(group => `<button type="button" class="filter" data-filter="${mode}:${esc(group)}" aria-pressed="${filters[mode] === group}">${esc(group)}</button>`).join('');
}
function renderEvents(container, mode, pack) {
 const events = catalog(mode, pack);
 if (!Object.keys(events).length) {
  container.innerHTML = '<p class="empty">This pack is intentionally silent. Agents make no effect sounds while it is in use.</p>';
  return;
 }
 const groups = filters[mode] === 'All' ? groupedEvents() : groupedEvents().filter(([group]) => group === filters[mode]);
 container.innerHTML = `<div class="ev-grid">${groups.map(([group, names]) => (filters[mode] === 'All' ? `<p class="group-label">${esc(group)}</p>` : '') + names.map(event => {
  const samples = events[event];
  if (!samples?.length) return `<div class="ev-tile silent"><span class="ev-ico">–</span><span class="ev-body"><span class="ev-name">${esc(eventLabel(event))}</span><span class="ev-sound">Silent</span></span></div>`;
  const key = mode + ':' + pack + ':' + event, index = (cursors[key] || 0) % samples.length;
  return `<button type="button" class="ev-tile" data-preview="${mode}" data-event="${esc(event)}" ${mode === 'effects' ? `data-pack="${esc(pack)}"` : ''}><span class="ev-ico">${icon('play')}</span><span class="ev-body"><span class="ev-name">${esc(eventLabel(event))}</span><span class="ev-sound">${esc(samples[index])}</span></span>${samples.length > 1 ? `<span class="ev-count" title="${samples.length} alternatives">×${samples.length}</span>` : ''}</button>`;
 }).join('')).join('')}</div>`;
}
function renderPacks() {
 $('packCount').textContent = packIds().length;
 $('packList').innerHTML = packIds().map(id => {
  const meta = PACK_META[id] || {kind:'Custom'}, effect = setup.effects?.[id] || {}, count = Object.keys(catalog('effects', id)).length;
  const selected = state.pack === id, inUse = modeInUse('effects') && saved.effects_profile === id;
  const sample = catalog('effects', id).edit ? 'edit' : Object.keys(catalog('effects', id))[0];
  return `<div class="list-row ${selected ? 'selected' : ''}"><label><input type="radio" name="pack" value="${esc(id)}" ${selected ? 'checked' : ''}><span class="row-main"><span class="row-title">${esc(packName(id))}${inUse ? '<span class="pill success sm">In use</span>' : ''}</span><span class="row-meta">${esc(meta.kind)} · ${count ? count + ' events' : 'silent'}${effect.sox ? ' · SoX' : ''}</span></span></label>${sample ? `<button class="play-btn" type="button" data-preview="effects" data-pack="${esc(id)}" data-event="${esc(sample)}" data-variant="0" aria-label="Play a ${esc(packName(id))} sample">${icon('play')}</button>` : ''}</div>`;
 }).join('');
}
function renderEffectsDetail() {
 const meta = PACK_META[state.pack] || {desc:'Custom sound pack.', kind:'Audio'}, effect = setup.effects?.[state.pack] || {};
 $('packTitle').textContent = packName(state.pack);
 $('packDesc').textContent = meta.desc || 'Custom sound pack.';
 $('packChips').innerHTML = `<span class="chip">${esc(meta.kind || 'Audio')}</span>${effect.sox ? '<span class="chip">Uses SoX</span>' : ''}`;
 $('effectsSource').textContent = `${packName(state.pack)} · ${packSource(state.pack)}`;
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
 const clips = saved.preview_catalog?.voice || {};
 $('clipCount').textContent = Object.keys(clips).length;
 $('clipList').innerHTML = Object.entries(clips).map(([id, events]) => {
  const inUse = modeInUse('clips') && saved.voice_profile === id;
  return `<div class="list-row ${state.clip === id ? 'selected' : ''}"><label><input type="radio" name="clip" value="${esc(id)}" ${state.clip === id ? 'checked' : ''}><span class="row-main"><span class="row-title">${esc(packName(id))}${inUse ? '<span class="pill success sm">In use</span>' : ''}</span><span class="row-meta">Recorded clips · ${Object.keys(events).length} events</span></span></label></div>`;
 }).join('');
 $('clipTitle').textContent = packName(state.clip);
 $('clipDesc').textContent = CLIP_META[state.clip] || 'A custom collection of recorded voice lines.';
 $('drawerClip').textContent = packName(state.clip);
 renderFilters('clips');
 renderEvents($('clipsEvents'), 'clips', state.clip);
}
function renderEventList() {
 const list = $('evList'), scroll = list.scrollTop;
 $('eventCount').textContent = saved.events.length;
 list.innerHTML = groupedEvents().map(([group, events]) => `<p class="group-label">${esc(group)}</p>` + events.map(event => {
  const changed = !same(state.phrases[event], saved.phrases[event]);
  const empty = state.phrases[event].flat().some(text => !String(text).trim());
  return `<button type="button" class="ev-item" data-phrase-event="${esc(event)}" aria-current="${event === state.phraseEvent}"><span>${esc(eventLabel(event))}</span><span class="ev-meta">${empty ? icon('warn') : ''}${changed ? '<i class="dirty-dot" title="Unsaved"></i>' : ''}${state.phrases[event].length}</span></button>`;
 }).join('')).join('');
 list.scrollTop = scroll;
}
function renderPhraseRows() {
 const event = state.phraseEvent, items = state.phrases[event] || [], roles = phraseRoles(event);
 $('editorTitle').textContent = eventLabel(event);
 $('editorHint').textContent = roles ? (event === 'subagent_start' ? 'The main agent speaks first, then the subagent replies.' : 'The subagent reports back, then the main agent responds.') : 'Spoken by the main agent. One alternative plays at random.';
 $('addLabel').textContent = roles ? 'Add exchange' : 'Add phrase';
 const head = roles && items.length ? `<div class="row row-head"><span></span><div class="inputs pair"><span>${esc(roleName(roles[0]))}</span><span>${esc(roleName(roles[1]))}</span></div><span></span><span></span></div>` : '';
 $('phraseRows').innerHTML = items.length ? head + items.map((item, index) => {
  const texts = [item].flat(), playable = texts.every(text => String(text).trim());
  return `<div class="row"><span class="row-num">${index + 1}</span><div class="inputs ${roles ? 'pair' : ''}">${texts.map((text, part) => `<input type="text" value="${esc(text)}" data-index="${index}" data-part="${part}" class="${String(text).trim() ? '' : 'invalid'}" placeholder="${part ? 'Reply…' : 'Write a phrase…'}" aria-label="${esc(roles ? roleName(roles[part]) : 'Phrase')} ${index + 1}">`).join('')}</div><button class="play-btn" type="button" data-preview="phrases" data-event="${esc(event)}" data-variant="${index}" aria-label="Preview alternative ${index + 1}" ${playable ? '' : 'disabled'}>${icon('play')}</button><button class="icon-sm" type="button" data-remove="${index}" aria-label="Remove ${index + 1}">${icon('x')}</button></div>`;
 }).join('') : '<p class="empty">No phrases yet, so this event stays silent. Add one below.</p>';
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
}
function renderStyles() {
 $('styleCount').textContent = Object.keys(styleNames).length;
 $('styleList').innerHTML = Object.entries(styleNames).map(([id, name]) => {
  const selected = state.style === id, inUse = modeInUse('ai') && saved.narrator_style === id;
  return `<label class="list-row ${selected ? 'selected' : ''}"><input type="radio" name="style" value="${esc(id)}" ${selected ? 'checked' : ''}><span class="row-main"><span class="row-title">${esc(name)}${inUse ? '<span class="pill success sm">In use</span>' : ''}</span></span></label>`;
 }).join('');
 $('styleTitle').textContent = styleNames[state.style] || state.style;
}
function renderSample() {
 const current = generatedSample?.identity === sampleIdentity() ? generatedSample : null;
 if (!current) generatedSample = null;
 $('commentarySample').textContent = current ? current.text : 'Play a sample to hear ' + (styleNames[state.style] || state.style) + '.';
 $('commentarySample').classList.toggle('placeholder', !current);
 const name = saved.narrator_providers[state.provider]?.name || state.provider;
 $('sampleNote').textContent = demo ? 'Prerecorded sample · Kokoro. Example commentary written for this demo. Install to generate fresh lines and edit phrases.' : current ? 'Replay uses this line and does not ask the provider again.' : `The first play writes one line with ${name}${needsKey() ? ', which may be billed' : ''}. A successful sample also verifies the provider.`;
 if (demo) document.querySelector('.sample-context').textContent = 'Example event · ' + (current?.event ? eventLabel(current.event) : 'Edit src/app.ts');
 if (!mediaBusy) $('sampleLabel').textContent = current ? 'Replay' : 'Play sample';
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
 $('kokoroInfo').hidden = !kokoro;
 $('verificationRow').hidden = !installation.available;
 const repair = ['phrases','aiSpeech'].some(key => setupChecks[key]?.status === 'failed' && setupChecks[key]?.identity === checkIdentity(key));
 $('installKokoro').hidden = !kokoro || (setup.kokoro && !repair) || !!setup.installing;
 $('installKokoro').disabled = !!setup.installing;
 $('installKokoro').textContent = setup.installStatus === 'error' ? 'Retry installation' : repair ? 'Repair installation' : 'Install Kokoro';
}
function renderChecks() {
 for (const key of Object.keys(checkModes)) {
  const view = checkPresentation(key);
  document.querySelectorAll(`[data-status-for="${key}"]`).forEach(node => paintStatus(node, view));
  const button = checkButton(key);
  if ((key === 'phrases' || key === 'aiSpeech') && key !== speechKey()) continue;
  button.textContent = view.checking ? view.pending : view.action;
  button.disabled = !!(view.checking || view.prerequisite && key !== 'effects' && key !== 'clips');
  button.setAttribute('aria-busy', String(!!view.checking));
  button.dataset.status = view.checking ? 'checking' : view.status;
  if (key === 'phrases' || key === 'aiSpeech') button.dataset.checkSetup = key;
 }
 renderChrome();
}
function render() {
 renderPacks();
 renderEffectsDetail();
 renderClips();
 renderPhraseRows();
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
 $('stripProvider').textContent = name + (state.model ? ' · ' + state.model : '');
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
 if (demo) demo.stop();
 state.viewMode = mode;
 render();
 scheduleSetupChecks();
 if (mode === 'phrases') requestAnimationFrame(scrollEventIntoView);
}
function scrollEventIntoView() {
 const list = $('evList'), current = list.querySelector('[aria-current=true]');
 if (!current) return;
 if (current.offsetTop < list.scrollTop || current.offsetTop + current.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = current.offsetTop - list.clientHeight / 2;
}

async function commit(mode, activate) {
 if (busy || mediaBusy || savingSound || savingVolume) return;
 const issue = saveIssue(mode);
 if (issue) { showError(issue); return; }
 if (activate && !setupReadiness(mode).ready) { openDrawer(blockerDrawer(mode)); return; }
 if (!activate && !saveReadiness(mode).ready) { openDrawer(blockerDrawer(mode)); return; }
 const draft = selectionDraft(mode), config = draftConfig(mode);
 busy = true; clearError(); renderChrome();
 try {
  const body = {mode, config, ...(mode === 'phrases' ? {phrases:draft.phrases} : {})};
  if (activate) body.enabled = state.enabled;
  await api(activate ? '/api/activate' : '/api/save', body);
  syncSpeechDrafts(config);
  Object.assign(saved, config);
  if (mode === 'ai' && state.provider === draft.provider && state.apiKey === draft.apiKey) {
   state.apiKey = '';
   $('sampleKey').value = '';
  }
  if (mode === 'phrases') saved.phrases = clone(draft.phrases);
  if (activate) {
   saved.soundbar_mode = mode;
   saved.effects_on = state.enabled && mode === 'effects';
   saved.voice_on = state.enabled && mode !== 'effects';
   if (mode !== 'effects') saved.voice_profile = {clips:draft.profile, phrases:'senior', ai:'narrator'}[mode];
   activeSelection = draft;
   enabledLayers = {effects_on:mode === 'effects', voice_on:mode !== 'effects'};
   toast('Saved · now using ' + selectionLabel());
  } else {
   if (mode === 'clips' && profileMode(saved.voice_profile) === 'clips') saved.voice_profile = draft.profile;
   if (activeSelection.mode === mode) activeSelection = draft;
   toast('Saved');
  }
 } catch (error) { showError(error.message); }
 finally { busy = false; render(); }
}
function syncSpeechDrafts(config) {
 // Rebase untouched shared fields without overwriting edits in the other tab.
 const fields = {
  tts_engine:[[state,'engine'], [state,'phraseEngine']],
  voice_main:[[state.voices,'say'], [state.phraseVoices.say,'main']],
  voice_sub:[[state.phraseVoices.say,'sub']],
  kokoro_voice:[[state.voices,'kokoro'], [state.phraseVoices.kokoro,'main']],
  kokoro_voice_sub:[[state.phraseVoices.kokoro,'sub']],
 };
 for (const [key, targets] of Object.entries(fields)) {
  if (!Object.hasOwn(config, key)) continue;
  for (const [target, field] of targets) if (target[field] === saved[key]) target[field] = config[key];
 }
}
function discard(mode) {
 if (mode === 'clips') state.clip = savedClipProfile();
 if (mode === 'effects') state.pack = saved.effects_profile;
 if (mode === 'phrases') {
  state.phraseEngine = saved.tts_engine;
  state.phraseVoices = {say:{main:saved.voice_main, sub:saved.voice_sub}, kokoro:{main:saved.kokoro_voice, sub:saved.kokoro_voice_sub || 'am_adam'}};
  state.phrases = normalizePhrases(saved.phrases);
 }
 if (mode === 'ai') {
  state.engine = saved.tts_engine;
  state.voices = {say:saved.voice_main, kokoro:saved.kokoro_voice};
  state.style = saved.narrator_style;
  state.provider = saved.narrator_provider;
  state.model = saved.narrator_model || '';
  state.apiKey = '';
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
 const event = button?.dataset.event || 'edit', pack = mode === 'clips' ? state.clip : button?.dataset.pack || state.pack;
 const samples = (mode === 'effects' ? catalog('effects', pack) : catalog('clips'))[event] || [];
 const key = mode + ':' + pack + ':' + event, variant = cursors[key] || 0;
 if (samples.length) cursors[key] = (variant + 1) % samples.length;
 return variant;
}
async function mediaAction(button, work) {
 if (mediaBusy) return;
 clearError();
 mediaBusy = true;
 button?.setAttribute('aria-busy', 'true');
 const controls = [...document.querySelectorAll('[data-preview]')].map(control => [control, control.disabled]);
 controls.forEach(([control]) => { control.disabled = true; });
 renderChrome();
 try { await work(); }
 catch (error) { if (error.name !== 'AbortError') showError(error.message); }
 finally {
  mediaBusy = false;
  button?.setAttribute('aria-busy', 'false');
  controls.forEach(([control, disabled]) => { control.disabled = disabled; });
  render();
 }
}
async function preview(mode, button) {
 const role = button?.dataset.role || null;
 if (mode === 'ai' && !role) { await playCommentarySample(button); return; }
 const pack = button?.dataset.pack;
 const readiness = mode === 'phrases' || mode === 'ai' ? speechReadiness(mode) : setupReadiness(mode, pack);
 if (pack && !setup.effects?.[pack]?.ready) { openDrawer('effects'); showError(setup.effects?.[pack]?.message || 'Audio unavailable'); return; }
 if (!readiness.ready) { openDrawer(blockerDrawer(mode)); return; }
 const event = button?.dataset.event || (mode === 'phrases' ? state.phraseEvent : 'edit');
 const variant = variantFor(button, mode);
 const config = pack ? {effects_profile:pack} : draftConfig(mode);
 const body = {mode, config, role, event, variant};
 if (mode === 'phrases' && !role) body.phrases = {[event]: state.phrases[event]};
 await mediaAction(button, () => api('/api/draft-preview', body));
}
async function playCommentarySample(button) {
 if (!speechReadiness('ai').ready) { openDrawer('speech'); return; }
 if ((!generatedSample || generatedSample.identity !== sampleIdentity()) && !hasProviderKey()) { openDrawer('provider'); showError('API key required'); return; }
 const config = draftConfig('ai'), identity = sampleIdentity();
 await mediaAction(button, async () => {
  if (!generatedSample || generatedSample.identity !== identity) {
   $('sampleLabel').textContent = 'Generating…';
   const result = await api('/api/draft-preview', {mode:'ai', action:'generate', config});
   if (identity !== sampleIdentity()) return;
   generatedSample = {identity, text:result.text};
   checkedAI = aiIdentity();
   setupChecks.ai = {identity:checkedAI, status:'checked'};
   renderSample();
  }
  $('sampleLabel').textContent = 'Playing…';
  await api('/api/draft-preview', {mode:'ai', action:'play', config, text:generatedSample.text});
 });
}

async function installKokoro() {
 if (setup.installing) return;
 const repair = !!setup.kokoro || ['phrases','aiSpeech'].some(key => setupChecks[key]?.status === 'failed' && setupChecks[key]?.identity === checkIdentity(key));
 for (const key of ['phrases','aiSpeech']) delete setupChecks[key];
 clearError();
 setup.installing = true; setup.installStatus = 'running'; setup.installMessage = '';
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
  else scheduleSetupChecks(0);
 } catch (error) {
  showError(error.message);
  installPoll = setTimeout(pollInstall, 5000);
 }
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
 $('availableVersion').textContent = versions.development ? 'Updates come from your checkout.' : versions.available ? 'Available: ' + versions.release.version : versions.checked_at ? 'You have the latest stable release.' : 'Updates are checked automatically while Soundbar runs.';
 $('releaseNotes').hidden = !versions.release;
 if (versions.release) $('releaseNotes').href = versions.release.notes_url;
 $('checkUpdates').disabled = versions.development || running || versionChecking;
 $('checkUpdates').textContent = versionChecking ? 'Checking…' : 'Check for updates';
 $('checkUpdates').setAttribute('aria-busy', String(versionChecking));
 $('applyUpdate').hidden = versions.development || !versions.available && !needsAttention && !running;
 $('applyUpdate').disabled = running || versionChecking || !!setup?.installing;
 $('applyUpdate').textContent = running ? 'Updating…' : needsAttention ? 'Retry update' : 'Update';
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
  clearTimeout(installPoll); clearTimeout(setupCheckTimer); clearTimeout(versionPoll);
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
 checkedAI = null;
 generatedSample = null;
 if (setupChecks.ai) setupChecks.ai.identity = '';
 if (options.clearModels) modelList = null;
}

function wire() {
 document.querySelectorAll('[data-theme-choice]').forEach(button => button.onclick = () => applyTheme(button.dataset.themeChoice));
 $('helpButton').onclick = event => { event.stopPropagation(); toggleHelp(); };
 document.addEventListener('click', event => {
  const target = event.target;
  const tab = target.closest('[data-mode]');
  if (tab?.closest('#tabs')) { selectTab(tab.dataset.mode); return; }
  const act = target.closest('[data-act]');
  if (act) { ({save:() => commit(state.viewMode, false), use:() => commit(state.viewMode, true), 'save-use':() => commit(state.viewMode, true), discard:() => discard(state.viewMode)})[act.dataset.act](); return; }
  const drawer = target.closest('[data-drawer]');
  if (drawer) { openDrawer(drawer.dataset.drawer); return; }
  const filter = target.closest('[data-filter]');
  if (filter) { const [mode, group] = filter.dataset.filter.split(':'); filters[mode] = group; mode === 'effects' ? renderEffectsDetail() : renderClips(); return; }
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
 $('packList').addEventListener('change', event => { if (event.target.name !== 'pack') return; state.pack = event.target.value; render(); scheduleSetupChecks(); });
 $('clipList').addEventListener('change', event => { if (event.target.name !== 'clip') return; state.clip = event.target.value; render(); scheduleSetupChecks(); });
 $('styleList').addEventListener('change', event => { if (event.target.name !== 'style') return; state.style = event.target.value; generatedSample = null; renderStyles(); renderSample(); renderChrome(); });
 $('phraseEngine').onchange = () => { state[state.viewMode === 'ai' ? 'engine' : 'phraseEngine'] = $('phraseEngine').value; render(); scheduleSetupChecks(); };
 $('mainAgentVoice').onchange = () => { state.phraseVoices[state.phraseEngine].main = $('mainAgentVoice').value; renderPhraseRows(); renderChrome(); scheduleSetupChecks(); };
 $('subagentVoice').onchange = () => { state.phraseVoices[state.phraseEngine].sub = $('subagentVoice').value; renderPhraseRows(); renderChrome(); scheduleSetupChecks(); };
 $('speaker').onchange = () => { state.voices[state.engine] = $('speaker').value; renderChrome(); scheduleSetupChecks(); };
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
  state.provider = $('provider').value; state.model = ''; state.apiKey = '';
  $('model').value = ''; $('sampleKey').value = '';
  invalidateProvider({clearModels:true});
  delete setupChecks.ai;
  showProvider(); renderSample(); renderChecks();
  if (!needsKey()) { refreshModels(); scheduleSetupChecks(0); }
 };
 $('model').oninput = () => { state.model = $('model').value; invalidateProvider(); showProvider(); renderChrome(); if (!needsKey()) scheduleSetupChecks(); };
 $('sampleKey').oninput = () => { state.apiKey = $('sampleKey').value; invalidateProvider({clearModels:true}); renderModelList(); renderChecks(); };
 $('sampleKey').onchange = () => refreshModels();
 $('refreshModels').onclick = () => refreshModels(true);
 $('sessionContext').onchange = () => { state.context = $('sessionContext').checked; renderChrome(); };
 document.querySelectorAll('[data-check-setup]').forEach(button => button.onclick = () => checkSetup(button.dataset.checkSetup));
 $('installKokoro').onclick = installKokoro;
 $('installSox').onclick = () => { $('soxCommand').hidden = false; };
 $('closeDrawer').onclick = () => $('drawer').close();
 $('drawer').addEventListener('click', event => { if (event.target === $('drawer')) $('drawer').close(); });
 $('settingsButton').onclick = () => $('settingsDialog').showModal();
 $('closeSettings').onclick = () => $('settingsDialog').close();
 $('versionNotice').onclick = () => { $('settingsDialog').showModal(); $('versionPreferences').scrollIntoView({block:'nearest'}); };
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
 const voiceMode = profileMode(saved.voice_profile);
 const active = saved.effects_on && saved.voice_on ? 'combined' : saved.voice_on ? voiceMode : saved.effects_on ? 'effects' : (TABS[saved.soundbar_mode] ? saved.soundbar_mode : 'effects');
 const viewMode = active === 'combined' ? voiceMode : active;
 enabledLayers = active === 'combined' ? {effects_on:true, voice_on:true} : {effects_on:viewMode === 'effects', voice_on:viewMode !== 'effects'};
 saved.phrases = normalizePhrases(saved.phrases);
 state = {
  viewMode, enabled:!!(saved.effects_on || saved.voice_on),
  volume:viewMode === 'effects' || active === 'combined' ? saved.effects_volume : saved.voice_volume,
  pack:saved.effects_profile, clip:savedClipProfile(), style:saved.narrator_style, engine:saved.tts_engine, phraseEngine:saved.tts_engine,
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
  if (demo) demo.ready(() => mediaAction($('demoSession'), async () => {
   const mode = state.viewMode, config = clone(draftConfig(mode));
   await demo.session(mode, config, (event, text) => {
    if (mode === 'phrases') { state.phraseEvent = event; renderPhraseRows(); renderEventList(); }
    if (mode === 'ai') { generatedSample = {identity:sampleIdentity(), text, event}; renderSample(); }
   });
  }), selectTab);
  setupChecksReady = true;
  scheduleSetupChecks(0);
  refreshVersions();
 } catch (error) {
  $('loadError').hidden = false;
  if ($('statusText')) $('statusText').textContent = 'Disconnected';
  showError(error.message);
 }
});
