// Run with Node and Playwright available (NODE_PATH may point to its installation).
// Uses shipped defaults and mocked APIs: no audio, provider requests, or preference writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(__dirname, '../code-gossip');
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
const defaults = read('configs/config.defaults.json');
const manifest = read('data/sounds.json');
const state = {
  ...defaults,
  tts_engines: { say: { name: 'macOS speech' }, kokoro: { name: 'Kokoro' } },
  effects_profiles: Object.fromEntries(Object.keys(manifest.effects).sort().map(key => [key, {}])),
  voice_profiles: {}, voice_profile_names: ['senior', 'generals', 'narrator'],
  phrases: read('configs/phrases.defaults.json'), events: ['edit', 'test', 'stop'], dialogue_events: [], voices: [],
  narrator_styles: read('configs/narrator_styles.defaults.json'),
  narrator_providers: { claude_cli: { name: 'Claude CLI', needs_key: false, models: [], default_model: 'default' } },
};
const server = http.createServer((req, res) => {
  const file = { '/': 'ui.html', '/onboarding.js': 'onboarding.js', '/onboarding.css': 'onboarding.css' }[req.url];
  if (!file) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html');
  res.end(fs.readFileSync(path.join(root, 'soundbar', file)));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    const writes = [];
    let kokoroInstalled = false;
    let installationRequests = 0;
    let shutdownFails = true;
    let shutdownRequests = 0;
    await page.route('**/api/**', async route => {
      const req = route.request();
      const endpoint = new URL(req.url()).pathname;
      let reply = { ok: true, message: 'Ready' };
      if (endpoint === '/api/shutdown') {
        shutdownRequests++;
        assert.equal(req.method(), 'POST');
        assert.equal(req.headers()['x-soundbar-request'], 'ui');
        reply = { ok: !shutdownFails };
      }
      else if (endpoint === '/api/kokoro-status') reply = { installed: kokoroInstalled };
      else if (endpoint === '/api/kokoro-install') installationRequests++;
      else if (endpoint === '/api/status') reply = state;
      else if (endpoint === '/api/config') { const changes = req.postDataJSON(); writes.push(changes); Object.assign(state, changes); }
      await route.fulfill({ json: reply });
    });
    const url = `http://127.0.0.1:${server.address().port}`;
    await page.goto(url);
    await page.locator('#welcomeDialog[open]').waitFor();
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'soundbar-welcome.png') });
    await page.getByRole('button', { name: 'Let’s try it' }).click();
    assert.equal(await page.locator('.tip-item').count(), 5);
    assert.equal(await page.locator('#effectsProfile option').first().getAttribute('value'), 'default');
    assert.equal(await page.locator('#effectsProfile option[value=ambient], #effectsProfile option[value=organic]').count(), 0);
    const appearance = await page.locator('.tip-item').first().evaluate(el => {
      const s = getComputedStyle(el);
      return [s.backgroundColor, s.backdropFilter, s.boxShadow];
    });
    assert.deepEqual(appearance, ['rgba(132, 92, 24, 0.5)', 'none', 'none']);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'soundbar-floating-tips.png') });
    const start = async name => page.getByRole('button', { name, exact: true }).click();
    const next = async () => page.locator('#tourNext').click();
    const assertHighlight = async selector => {
      const boxes = await page.evaluate(sel => {
        const target = document.querySelector(sel).getBoundingClientRect();
        const highlight = document.getElementById('tourHighlight').getBoundingClientRect();
        const card = document.getElementById('tourCard').getBoundingClientRect();
        return { target: target.toJSON(), highlight: highlight.toJSON(), card: card.toJSON(), width: innerWidth, height: innerHeight };
      }, selector);
      assert(Math.abs(boxes.target.x - boxes.highlight.x - 4) < 1);
      assert(boxes.card.x >= 0 && boxes.card.right <= boxes.width);
      assert(boxes.card.y >= 0 && boxes.card.bottom <= boxes.height);
      assert(boxes.card.bottom <= boxes.target.y || boxes.card.y >= boxes.target.bottom || boxes.card.right <= boxes.target.x || boxes.card.x >= boxes.target.right, 'Tip must not cover its target');
    };
    await start('Pick profiles');
    await assertHighlight('#effectsProfile');
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'soundbar-profiles.png') });
    await next(); await assertHighlight('#voiceProfile'); await next();
    assert.equal(await page.locator('.tip-item').count(), 4);
    await start('Mix layers');
    await assertHighlight('#effectsOn + .toggle-track');
    await next(); await assertHighlight('#voiceOn + .toggle-track');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#tourCard').isVisible(), false);
    await page.getByRole('button', { name: 'Dismiss Mix layers suggestion permanently' }).click();
    await start('Set up Narrator');
    assert(await page.locator('#tourNext').isDisabled());
    assert.equal(writes.length, 0, 'Tours must not change preferences');
    await page.selectOption('#voiceProfile', 'narrator');
    await page.waitForFunction(() => !document.getElementById('tourNext').disabled);
    await next();
    await assertHighlight('#narrProvider');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#narrProvider').scrollIntoViewIfNeeded();
    await assertHighlight('#narrProvider');
    await next();
    assert.equal(writes.length, 1, 'Only the explicit profile choice should save');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.selectOption('#voiceProfile', 'generals');
    await start('Install Kokoro');
    await assertHighlight('#voiceProfile');
    assert(await page.locator('#tourNext').isDisabled());
    assert.equal(writes.length, 2);
    await page.selectOption('#voiceProfile', 'senior');
    await page.waitForFunction(() => !!document.getElementById('ttsEngine'));
    await assertHighlight('#ttsEngine');
    assert(await page.locator('#tourNext').isDisabled());
    await page.selectOption('#ttsEngine', 'kokoro');
    await page.waitForFunction(() => !document.getElementById('tourNext').disabled);
    await next();
    await assertHighlight('#kokoroSetup');
    assert(await page.locator('#kokoroInstallBtn').isVisible());
    kokoroInstalled = true;
    await page.evaluate(() => updateKokoroInstallBtn());
    assert.equal(await page.locator('#kokoroInstallBtn').isVisible(), false);
    await assertHighlight('#kokoroSetup');
    assert.equal(installationRequests, 0, 'Guidance must not start a download');
    assert.equal(writes.length, 4, 'Only explicit profile/engine choices should save');
    await next();
    await start('Tune settings');
    await assertHighlight('#spacingSettings');
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'soundbar-mobile-tip.png') });
    await next(); await assertHighlight('#codexSettings'); await next();
    await page.reload();
    await page.locator('#voiceProfile').waitFor();
    assert.equal(await page.locator('#welcomeDialog').isVisible(), false);
    assert.equal(await page.locator('#quickTips').isVisible(), false);
    // Corrupt or blocked browser storage must not break the mixer.
    await page.evaluate(() => localStorage.setItem('code-gossip.soundbar.onboarding.v1', 'invalid'));
    await page.reload();
    await page.locator('#welcomeDialog[open]').waitFor();
    await page.keyboard.press('Escape');
    await start('Pick profiles');
    await assertHighlight('#effectsProfile');
    await next(); await assertHighlight('#voiceProfile');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No mobile overflow');
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'CLOSE SOUNDBAR', exact: true }).click();
    await page.locator('#closeSoundbarError:not([hidden])').waitFor();
    assert(await page.locator('#closeSoundbar').isEnabled());
    assert.equal(await page.locator('#closedDialog').isVisible(), false);
    shutdownFails = false;
    await page.getByRole('button', { name: 'CLOSE SOUNDBAR', exact: true }).click();
    await page.locator('#closedDialog[open]').waitFor();
    assert.equal(shutdownRequests, 2);
    await page.keyboard.press('Escape');
    assert(await page.locator('#closedDialog').isVisible());
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'soundbar-closed.png') });
    assert.deepEqual(errors, []);
    console.log('Soundbar UI passed: welcome, all five tours, no implicit saves, persisted dismissal, keyboard, desktop/mobile positioning.');
  } finally { await browser.close(); server.closeAllConnections(); server.close(); }
})().catch(err => { console.error(err); server.closeAllConnections(); server.close(); process.exitCode = 1; });
