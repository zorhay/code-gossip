// Exercise the real static Pages artifact and real MP3 playback, with no API mocks.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const site = path.resolve(process.env.PAGES_DIRECTORY || 'dist/pages');
const data = JSON.parse(fs.readFileSync(path.join(site, 'demo-data.json')));
const metadata = JSON.parse(fs.readFileSync(path.join(site, 'build.json')));
const melody = require(path.join(site, 'melody.js'));
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.mp3':'audio/mpeg'};
const server = http.createServer((req,res) => {
 const url = new URL(req.url, 'http://localhost');
 if (req.method !== 'GET' || !url.pathname.startsWith('/code-gossip/')) {res.writeHead(404);res.end();return;}
 const relative = decodeURIComponent(url.pathname.slice('/code-gossip/'.length)) || 'index.html';
 const file = path.resolve(site, relative);
 if (!file.startsWith(site + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404);res.end();return;}
 const bytes = fs.readFileSync(file);
 res.writeHead(200, {'Content-Type':mime[path.extname(file)] || 'application/octet-stream','Content-Length':bytes.length});
 res.end(bytes);
});
(async () => {
 await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
 const base = `http://127.0.0.1:${server.address().port}/code-gossip/`;
 const browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors = [], requests = [], failures = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push({url:request.url(),method:request.method()}));
  page.on('response', response => {if(response.status() >= 400) failures.push(response.url());});
  // Observe native Audio instances without changing playback or event behavior.
  await page.addInitScript(() => {
   Math.random = () => .37; // Repeatable choices, while preserving real audio playback.
   window.audioLog = [];
   const NativeAudio = window.Audio;
   window.Audio = function(src) {
    const audio = new NativeAudio(src);
    window.lastAudio = audio;
    for (const event of ['playing','ended','pause','error']) audio.addEventListener(event, () => window.audioLog.push({event,src:audio.src,volume:audio.volume,muted:audio.muted}));
    return audio;
   };
  });
  await page.goto(base);
  await page.waitForFunction(() => document.getElementById('statusText').textContent.startsWith('Preview'));
  const idle = () => page.waitForFunction(() => !document.getElementById('now').classList.contains('is-playing'));
  async function playAndStop(locator, expectedFile) {
   const count = await page.evaluate(() => audioLog.filter(x=>x.event==='playing').length);
   await locator.click();
   await page.waitForFunction(n => audioLog.filter(x=>x.event==='playing').length > n, count);
   if (expectedFile) assert((await page.evaluate(() => lastAudio.src)).endsWith('/' + expectedFile));
   if (await page.locator('#demoStop').isEnabled()) await page.locator('#demoStop').click();
   await idle();
   assert.equal(await page.locator('#errorBanner').textContent(), '');
  }
  assert.equal(await page.locator('video').count(),0);
  assert.equal(await page.locator('[role=tab]').count(),4);
  assert.equal(await page.locator('[data-act]:visible').count(),0);
  assert.equal(await page.locator('[data-drawer]:visible').count(),0);
  assert.equal(await page.evaluate(() => audioLog.length),0,'No autoplay');
  assert.equal(requests.filter(r=>r.url.endsWith('.mp3')).length,0,'Audio loads only on demand');
  if (metadata.tag !== 'development') assert((await page.locator('#install-command').textContent()).includes(`--release ${metadata.tag} --all`));

  // A full real recording reaches ended; subsequent previews and failure recovery work.
  await page.locator('[data-preview=effects][data-pack=default]').first().click();
  await page.waitForFunction(() => audioLog.some(x=>x.event==='ended'));
  await idle();
  const wood = data.status.effects_profiles['wood-thrush'];
  let melodyNotes = [];
  const melodyFile = event => {
   const notes = melody.compose(wood.melody, wood.events[event].melody, melodyNotes, () => .37);
   melodyNotes = [...melodyNotes, ...notes].slice(-4);
   return data.melodies[`effects/wood-thrush/${event}`][notes.join(',')];
  };
  for (const pack of Object.keys(data.status.effects_profiles)) {
   await page.locator(`input[name=pack][value="${pack}"]`).locator('..').click();
   const button = page.locator('#effectsEvents [data-preview]').first();
   if (pack === 'silent') {assert.equal(await button.count(),0);continue;}
   const event = await button.getAttribute('data-event');
   await playAndStop(button, pack === 'wood-thrush' ? melodyFile(event) : data.sounds[`effects/${pack}/${event}/0`]);
  }
  // Consecutive cues, Stop, and pack changes retain the composer's recent-note history.
  await page.locator('input[name=pack][value="wood-thrush"]').locator('..').click();
  const woodFiles = [];
  for (const event of ['edit','edit','read','permission','error','stop']) {
   const file = melodyFile(event);
   await playAndStop(page.locator(`#effectsEvents [data-event=${event}]`), file);
   woodFiles.push(file);
  }
  assert.notEqual(woodFiles[0], woodFiles[1], 'Repeated work cues compose different pitches');
  await page.locator('input[name=pack][value=paper]').locator('..').click();
  await playAndStop(page.locator('#effectsEvents [data-event=edit]'));
  await page.locator('input[name=pack][value="wood-thrush"]').locator('..').click();
  await playAndStop(page.locator('#effectsEvents [data-event=edit]'), melodyFile('edit'));
  const woodStart = await page.evaluate(() => audioLog.length);
  const woodSession = data.commentary.events.map(melodyFile);
  await page.locator('#demoSession').click();
  await page.waitForFunction(() => document.getElementById('demoProgress').textContent.startsWith('Session complete'));
  await idle();
  assert.deepEqual(await page.evaluate(n => audioLog.slice(n).filter(x=>x.event==='playing').map(x=>x.src.split('/').at(-1)), woodStart),
   woodSession, 'The example session composes all five Wood Thrush events with shared history');
  await page.locator('#tab-clips').click();
  await playAndStop(page.locator('#clipsEvents [data-event=edit]'),data.sounds['voice/generals/edit/0']);
  await page.locator('#clipList label', {hasText:'Empires'}).click();
  await playAndStop(page.locator('#clipsEvents [data-event=edit]'),data.sounds['voice/empires/edit/0']);
  await playAndStop(page.locator('#clipsEvents [data-event=subagent_start]'),data.sounds['voice/empires/subagent_start/0']);
  await page.locator('#clipList label', {hasText:'Generals'}).click();
  await page.locator('#tab-phrases').click();
  assert(await page.locator('#phraseRows input').first().getAttribute('readonly') !== null);
  assert.equal(await page.locator('#mainAgentVoice option').count(),data.status.kokoro_voices.length);
  for (const voice of data.status.kokoro_voices) {
   await page.selectOption('#mainAgentVoice',voice.id);
   await playAndStop(page.locator('#previewMainAgent'),data.speech[voice.id][data.voiceSample]);
  }
  await page.selectOption('#mainAgentVoice','af_heart');
  await page.selectOption('#subagentVoice','am_adam');
  await page.locator('[data-phrase-event=subagent_stop]').click();
  const dialogue = data.status.phrases.subagent_stop[0];
  const before = await page.evaluate(() => audioLog.length);
  await page.getByRole('button',{name:'Preview alternative 1',exact:true}).click();
  await idle();
  const played = await page.evaluate(n => audioLog.slice(n).filter(x=>x.event==='playing').map(x=>x.src.split('/').at(-1)),before);
  assert.deepEqual(played,[data.speech.am_adam[dialogue[0]],data.speech.af_heart[dialogue[1]]],'Dialogue follows subagent/main voice order');

  // Every style selects its own text and recording, with the chosen Kokoro voice.
  await page.locator('#tab-ai').click();
  await page.selectOption('#speaker','bf_emma');
  for (const style of Object.keys(data.status.narrator_styles)) {
   await page.locator(`input[name=style][value="${style}"]`).locator('..').click();
   const text = data.commentary.styles[style][data.commentary.events.indexOf('edit')];
   await playAndStop(page.locator('#sampleBtn'),data.speech.bf_emma[text]);
   assert.equal(await page.locator('#commentarySample').textContent(),text);
  }
  assert((await page.locator('#sampleNote').textContent()).includes('Prerecorded sample'));

  // Stop cancels a sequence; selection changes stop audio; volume/mute act during playback.
  await page.locator('#demoSession').click();
  await page.waitForFunction(() => window.lastAudio && !lastAudio.paused);
  await page.locator('#volume').evaluate(input => {
   input.value = '27';
   input.dispatchEvent(new Event('input',{bubbles:true}));
   input.dispatchEvent(new Event('change',{bubbles:true}));
  });
  assert.equal(await page.evaluate(() => lastAudio.volume),.27);
  await page.locator('#soundOn').uncheck();
  assert.equal(await page.evaluate(() => lastAudio.muted),true);
  await page.locator('#soundOn').check();
  await page.locator('#demoStop').click();
  await idle();
  const stopped = await page.evaluate(() => audioLog.filter(x=>x.event==='playing').length);
  await page.waitForTimeout(700);
  assert.equal(await page.evaluate(() => audioLog.filter(x=>x.event==='playing').length),stopped);
  assert.equal(await page.locator('.demo-event').count(),0);
  await page.locator('#sampleBtn').click();
  await page.waitForFunction(() => !lastAudio.paused);
  await page.locator('#tab-effects').click();
  await idle();
  assert(await page.evaluate(() => lastAudio.paused));

  // Run all five events in order with the selected effects pack.
  await page.locator('input[name=pack][value=minimal]').locator('..').click();
  const sessionStart = await page.evaluate(() => audioLog.length);
  await page.locator('#demoSession').click();
  await page.waitForFunction(() => document.getElementById('demoProgress').textContent.startsWith('Session complete'));
  await idle();
  const sessionFiles = await page.evaluate(n=>audioLog.slice(n).filter(x=>x.event==='playing').map(x=>x.src.split('/').at(-1)),sessionStart);
  assert.deepEqual(sessionFiles,data.commentary.events.map(e=>data.sounds[`effects/minimal/${e}/0`]));
  for (const mode of ['clips','phrases','ai']) {
   await page.locator('#tab-'+mode).click();
   const start = await page.evaluate(() => audioLog.length);
   await page.locator('#demoSession').click();
   await page.waitForFunction(() => document.getElementById('demoProgress').textContent.startsWith('Session complete'));
   await idle();
   const files = await page.evaluate(n=>audioLog.slice(n).filter(x=>x.event==='playing').map(x=>x.src.split('/').at(-1)),start);
   const expected = data.commentary.events.map((event,index) => mode === 'clips' ? data.sounds[`voice/generals/${event}/0`] :
    mode === 'phrases' ? data.speech.af_heart[data.status.phrases[event][0]] : data.speech.bf_emma[data.commentary.styles.zen_master[index]]);
   assert.deepEqual(files,expected,`${mode} session follows the selected voices and style`);
  }
  await page.locator('#tab-effects').click();

  // Missing audio is an actionable error and does not leave the controls stuck.
  await page.locator('input[name=pack][value="wood-thrush"]').locator('..').click();
  await page.route('**/preview-audio/*.mp3',route=>route.fulfill({status:404,body:''}));
  await page.locator('#effectsEvents [data-event=edit]').click();
  await page.waitForFunction(() => document.getElementById('errorBanner').textContent.includes('Could not load'));
  await idle();
  await page.unroute('**/preview-audio/*.mp3');
  await playAndStop(page.locator('#effectsEvents [data-event=edit]'));

  // Decode every shipped file in the browser; reject empty/silent/corrupt assets.
  const files = Object.keys(metadata.files).filter(name=>name.endsWith('.mp3'));
  const decoded = await page.evaluate(async names => {
   const context = new AudioContext();
   let count = 0;
   for (const name of names) {
    const response = await fetch(name);
    if (!response.ok) throw new Error('Missing '+name);
    const buffer = await context.decodeAudioData(await response.arrayBuffer());
    if (!(buffer.duration > .02 && buffer.duration < 30)) throw new Error('Invalid duration '+name);
    let audible = false;
    for (let channel=0;channel<buffer.numberOfChannels;channel++) {
     if (buffer.getChannelData(channel).some(sample=>Math.abs(sample)>.0001)) audible=true;
    }
    if (!audible) throw new Error('Silent recording '+name);
    count++;
   }
   await context.close();
   return count;
  },files);
  assert.equal(decoded,files.length);

  // Shared layout remains usable at desktop and narrow/mobile widths, in both themes.
  const screenshotDir = process.env.PAGES_SCREENSHOTS;
  if (screenshotDir) fs.mkdirSync(screenshotDir,{recursive:true});
  for (const width of [1440,768,390,320]) {
   await page.setViewportSize({width,height:1000});
   for (const mode of ['effects','clips','phrases','ai']) {
    await page.locator('#tab-'+mode).click();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No horizontal page overflow: ${width}/${mode}`);
    const pane = page.locator('#panel-'+mode+' .workspace');
    assert(await pane.isVisible());
    if(screenshotDir && [1440,390].includes(width)) await page.screenshot({path:path.join(screenshotDir,`${width}-${mode}.png`),fullPage:true});
   }
  }
  await page.locator('#settingsButton').click();
  await page.locator('[data-theme-choice=mint]').click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('html').getAttribute('data-theme'),'mint');
  await page.goto(base+'#senior');
  await page.waitForFunction(()=>document.getElementById('tab-phrases')?.getAttribute('aria-selected')==='true');
  assert.equal(await page.locator('html').getAttribute('data-theme'),'mint');
  await page.locator('#tab-phrases').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#tab-ai').getAttribute('aria-selected'),'true');
  assert.equal(requests.filter(r=>r.method!=='GET'||r.url.includes('/api/')).length,0);
  assert(requests.every(r=>r.url.startsWith(base)),'All requests stay under the project Pages subpath');
  assert.equal(failures.length,1,'Only the intentionally missing recording failed');
  assert.deepEqual(errors,[]);
  console.log(`Pages passed: ${decoded} real audio files decoded; evolving Wood Thrush phrases/history/session; all packs, Kokoro voices, styles, dialogue, errors, mute, volume, mobile, keyboard, and release data.`);
 } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
