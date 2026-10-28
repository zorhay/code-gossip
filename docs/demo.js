/* Static transport for the shared Soundbar UI. Never contacts a local API. */
'use strict';
window.soundbarDemo = (() => {
 let data, melodyHistory, active = null, cancelAudio = null, generation = 0, volume = 1, enabled = true;
 const $ = id => document.getElementById(id);
 const aborted = () => new DOMException('Playback stopped', 'AbortError');
 function clearHighlight() { document.querySelectorAll('.demo-event').forEach(node => node.classList.remove('demo-event')); }
 function stop() {
  generation++;
  if (active) active.pause();
  cancelAudio?.();
  clearHighlight();
 }
 function playFile(file, token) {
  if (token !== generation) return Promise.reject(aborted());
  if (!file) return Promise.reject(new Error('This recording is missing. Please reload the page.'));
  return new Promise((resolve, reject) => {
   const audio = new Audio(new URL('preview-audio/' + file, document.baseURI));
   active = audio;
   audio.volume = volume;
   audio.muted = !enabled;
   let timer;
   const finish = error => {
    clearTimeout(timer);
    audio.onended = audio.onerror = null;
    audio.pause();
    if (active === audio) { active = null; cancelAudio = null; }
    error ? reject(error) : resolve();
   };
   cancelAudio = () => finish(aborted());
   audio.onended = () => finish();
   audio.onerror = () => finish(new Error('Could not load the audio sample. Check your connection and try again.'));
   timer = setTimeout(() => finish(new Error('The audio sample took too long to load. Please try again.')), 30000);
   audio.play().catch(error => finish(new Error(error.name === 'NotAllowedError' ? 'Press Play again to enable audio in this browser.' : 'Could not play this recording. Please try again.')));
  });
 }
 async function speak(text, voice, token) { await playFile(data.speech[voice]?.[text], token); }
 async function preview(body, token = generation) {
  const {mode, config = {}, role, event = 'edit', variant = 0} = body;
  if (role) return speak(data.voiceSample, role === 'sub' ? config.kokoro_voice_sub : config.kokoro_voice, token);
  if (mode === 'effects' || mode === 'clips') {
   const layer = mode === 'effects' ? 'effects' : 'voice', pack = mode === 'effects' ? config.effects_profile : config.clips_profile;
   // Unmapped events and Silent are intentionally silent, just like the app.
   if (!data.status.preview_catalog[layer]?.[pack]?.[event]) return;
   const profile = mode === 'effects' ? data.status.effects_profiles[pack] : null;
   const spec = profile?.events[event]?.melody;
   const file = spec ? data.melodies[`${layer}/${pack}/${event}`]?.[
    melodyHistory.next(profile.melody, spec, [layer, pack]).join(',')
   ] : data.sounds[`${layer}/${pack}/${event}/${variant}`];
   return playFile(file, token);
  }
  if (mode === 'ai') {
   const text = data.commentary.styles[config.narrator_style][data.commentary.events.indexOf(event)];
   if (body.action === 'generate') return {ok:true, text};
   await speak(body.text || text, config.kokoro_voice, token);
   return {ok:true};
  }
  const phrase = data.status.phrases[event]?.[variant];
  if (phrase === undefined) throw new Error('This phrase recording is missing.');
  const roles = event === 'subagent_stop' ? ['sub','main'] : ['main','sub'];
  for (const [index, text] of [phrase].flat().entries()) {
   await speak(text, roles[index] === 'sub' ? config.kokoro_voice_sub : config.kokoro_voice, token);
  }
 }
 async function request(path, body) {
  if (path === '/api/status') {
   const response = await fetch(new URL('demo-data.json', document.baseURI));
   if (!response.ok) throw new Error('Could not load the preview catalog. Please reload.');
   data = await response.json();
   melodyHistory = SoundbarMelody.createHistory({idleSeconds:data.melodyIdleSeconds});
   volume = (data.status.effects_on ? data.status.effects_volume : data.status.voice_volume) / 100;
   enabled = !!(data.status.effects_on || data.status.voice_on);
   return structuredClone(data.status);
  }
  if (path === '/api/draft-preview') return (await preview(body)) || {ok:true};
  if (path === '/api/config') {
   const allowed = ['effects_volume','voice_volume','effects_on','voice_on','soundbar_mode'];
   if (Object.keys(body).some(key => !allowed.includes(key))) throw new Error('Install Code Gossip to change agent settings.');
   if ('effects_volume' in body) volume = body.effects_volume / 100;
   if ('effects_on' in body) enabled = !!(body.effects_on || body.voice_on);
   if (active) { active.volume = volume; active.muted = !enabled; }
   return {ok:true};
  }
  throw new Error('This setting is available in the installed Soundbar.');
 }
 async function session(mode, config, onEvent) {
  const token = generation;
  try {
   for (const [index, event] of data.commentary.events.entries()) {
    if (token !== generation) throw aborted();
    clearHighlight();
    onEvent(event, data.commentary.styles[config.narrator_style]?.[index]);
    const node = document.querySelector(`[data-preview="${mode}"][data-event="${event}"]`) || document.querySelector(`[data-phrase-event="${event}"]`);
    node?.classList.add('demo-event');
    $('demoProgress').textContent = `${index + 1}/${data.commentary.events.length} · ${data.commentary.labels[index]}`;
    await preview({mode, config, event, variant:0, action:'play'}, token);
    if (token !== generation) throw aborted();
    await new Promise(resolve => setTimeout(resolve, 400));
   }
   $('demoProgress').textContent = 'Session complete. Try another sound pack, voice, or style.';
  } finally { clearHighlight(); }
 }
 function ready(startSession, selectMode) {
  document.querySelector('#panel-phrases .panel-head p').textContent = 'Prerecorded Kokoro phrases. Install to edit the lines for your agents.';
  $('demoSession').onclick = startSession;
  $('demoStop').onclick = () => { stop(); $('demoProgress').textContent = 'Playback stopped.'; };
  $('copy-install').onclick = async () => {
   try {
    await navigator.clipboard.writeText($('install-command').textContent);
    $('copy-status').textContent = 'Command copied.';
   } catch { $('copy-status').textContent = 'Select and copy the command above.'; }
  };
  const followHash = () => {
   const mode = {default:'effects', senior:'phrases', narrator:'ai', effects:'effects', clips:'clips', phrases:'phrases', ai:'ai'}[location.hash.slice(1)];
   if (mode) { selectMode(mode); $('tabs').scrollIntoView({block:'start'}); }
  };
  window.addEventListener('hashchange', followHash);
  followHash();
  document.addEventListener('change', event => {
   if (event.target.matches('[name=pack],[name=style],#mainAgentVoice,#subagentVoice,#speaker')) stop();
  }, true);
  window.addEventListener('pagehide', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
 }
 return {request, stop, session, ready};
})();
