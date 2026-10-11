(() => {
  'use strict';
  const KEY = 'code-gossip.soundbar.onboarding.v1';
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (_) { /* Storage is optional. */ }
  if (typeof saved !== 'object' || Array.isArray(saved)) saved = {};
  const dismissed = new Set(Array.isArray(saved.dismissed) ? saved.dismissed : []);
  let active = null;
  let step = 0;
  let previousFocus = null;
  const tips = {
    profiles: { label: 'Pick profiles', steps: [
      ['#effectsProfile', 'Find your sound', 'Choose an Effects profile: system sounds, sampled audio, or generated tones. Use the play buttons in the event mixer to listen.'],
      ['#voiceProfile', 'Give it a voice', 'Senior speaks fixed phrases, Generals plays recorded clips, and Narrator comments on your agent’s work. Profiles save as you choose them.'],
    ] },
    layers: { label: 'Mix layers', steps: [
      ['#effectsOn', 'Effects on or off', 'This switch controls all Effects cues. Turn it off for voice-only feedback; your selected profile stays saved.'],
      ['#voiceOn', 'Voice on or off', 'Enable Voice for spoken feedback. Both layers can play together, or turn both off for silence. Adjust their volumes independently.'],
    ] },
    narrator: { label: 'Set up Narrator', steps: [
      ['#voiceProfile', 'Choose Narrator', 'Select narrator in the Voice profile menu to reveal its LLM settings, then press Next. Enable Voice when you want live commentary.'],
      ['#narrProvider', 'Connect your LLM', 'Choose a provider and model, add an API key if required, then Check connection. Use Test narration alongside these settings to hear a sample.'],
    ] },
    kokoro: { label: 'Install Kokoro', steps: [
      ['#ttsEngine', 'Choose Kokoro speech', 'For local neural speech, choose Kokoro in the TTS menu. It works with Senior and Narrator. Then press Next.'],
      ['#kokoroSetup', 'Install the speech engine', 'Click Install to download Kokoro, then wait for Installed. Choose a voice and preview it. If Installed is already shown, you’re ready to go.'],
    ] },
    settings: { label: 'Tune settings', steps: [
      ['#spacingSettings', 'Keep the chatter comfortable', 'Reduce repeated sounds and set a separate repeat gap for each layer. Important cues stay responsive. Changes save automatically.'],
      ['#codexSettings', 'Choose approval cues', 'Control Codex approval sounds independently here. This changes audio only; your agent’s permissions stay the same.'],
    ] },
  };
  const bar = document.getElementById('quickTips');
  const welcome = document.getElementById('welcomeDialog');
  const card = document.getElementById('tourCard');
  const highlight = document.getElementById('tourHighlight');
  const next = document.getElementById('tourNext');
  const close = document.getElementById('tourClose');

  function persist() {
    saved.dismissed = [...dismissed];
    try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (_) { /* Keep usable without storage. */ }
  }
  function renderTips() {
    bar.replaceChildren();
    const label = document.createElement('span');
    label.className = 'quick-tips-label';
    label.textContent = 'Tips';
    bar.append(label);
    for (const [id, tip] of Object.entries(tips)) {
      if (dismissed.has(id)) continue;
      const item = document.createElement('span');
      item.className = 'tip-item';
      const button = document.createElement('button');
      button.textContent = tip.label;
      button.onclick = () => start(id);
      const dismiss = document.createElement('button');
      dismiss.className = 'tip-dismiss';
      dismiss.textContent = '×';
      dismiss.setAttribute('aria-label', `Dismiss ${tip.label} suggestion permanently`);
      dismiss.title = 'Don’t show again';
      dismiss.onclick = () => {
        dismissed.add(id);
        persist();
        if (active === id) finish(false);
        renderTips();
        bar.querySelector('button')?.focus();
      };
      item.append(button, dismiss);
      bar.append(item);
    }
    bar.hidden = Object.keys(tips).every(id => dismissed.has(id));
  }
  function target() {
    if (!active) return null;
    const element = active === 'kokoro' && step === 0
      ? document.getElementById('ttsEngine') || document.getElementById('voiceProfile')
      : document.querySelector(tips[active].steps[step][0]);
    // Toggle inputs are visually hidden; frame their visible switch instead.
    return element?.matches('input[type="checkbox"]') ? element.closest('label') : element;
  }
  function position() {
    const element = target();
    if (!element || !element.getClientRects().length) {
      highlight.hidden = true;
      return;
    }
    highlight.hidden = false;
    const rect = element.getBoundingClientRect();
    Object.assign(highlight.style, { left: `${rect.left - 4}px`, top: `${rect.top - 4}px`, width: `${rect.width + 8}px`, height: `${rect.height + 8}px` });
    const width = card.offsetWidth;
    const height = card.offsetHeight;
    const left = Math.max(16, Math.min(rect.right - width, innerWidth - width - 16));
    let top = rect.bottom + 14;
    if (top + height > innerHeight - 16) top = rect.top - height - 14;
    if (top < 16) top = innerHeight - height - 16;
    Object.assign(card.style, { left: `${left}px`, top: `${Math.max(16, top)}px` });
  }
  function showStep(scroll = true) {
    if (!active) return;
    // A profile change may hide the settings currently being explained.
    if (active === 'narrator' && step === 1 && !document.getElementById('narratorSection').classList.contains('visible')) step = 0;
    if (active === 'kokoro' && step === 1 && !document.getElementById('kokoroSetup')) step = 0;
    const tip = tips[active];
    const [, title, body] = tip.steps[step];
    document.getElementById('tourProgress').textContent = `${tip.label} · ${step + 1} of ${tip.steps.length}`;
    document.getElementById('tourTitle').textContent = title;
    document.getElementById('tourText').textContent = active === 'kokoro' && step === 0 && !document.getElementById('ttsEngine')
      ? 'Choose Senior or Narrator here to reveal the TTS menu, then select Kokoro. Press Next to find its installation controls.'
      : body;
    next.textContent = step === tip.steps.length - 1 ? 'Got it' : 'Next';
    next.disabled = (active === 'narrator' && step === 0 && !document.getElementById('narratorSection').classList.contains('visible'))
      || (active === 'kokoro' && step === 0 && !document.getElementById('kokoroSetup'));
    card.hidden = false;
    if (scroll) target()?.scrollIntoView({ block: 'center', behavior: 'instant' });
    position();
  }
  function start(id) {
    previousFocus = document.activeElement;
    active = id;
    step = 0;
    document.body.classList.add('tour-active');
    showStep();
    close.focus({ preventScroll: true });
  }
  function finish(complete) {
    if (complete && active) {
      dismissed.add(active);
      persist();
    }
    active = null;
    card.hidden = true;
    highlight.hidden = true;
    document.body.classList.remove('tour-active');
    if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    if (complete) {
      renderTips();
      bar.querySelector('button')?.focus({ preventScroll: true });
    }
  }
  next.onclick = () => {
    if (step === tips[active].steps.length - 1) finish(true);
    else { step++; showStep(); next.focus({ preventScroll: true }); }
  };
  close.onclick = () => finish(false);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && active) finish(false);
  });
  window.addEventListener('resize', position);
  window.addEventListener('scroll', position, { passive: true });
  document.addEventListener('soundbar:render', () => {
    renderTips();
    showStep(false);
    if (!saved.welcomed && !welcome.open) welcome.showModal();
  });
  const dismissWelcome = () => { saved.welcomed = true; persist(); welcome.close(); };
  document.getElementById('welcomeStart').onclick = dismissWelcome;
  welcome.addEventListener('cancel', event => { event.preventDefault(); dismissWelcome(); });
})();
