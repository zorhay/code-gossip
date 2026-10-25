// Real installers, HTTP APIs, browser UI, and uninstall in disposable normal/dev homes.
// The OS browser opener and GitHub release requests are intercepted.
// Requires Python, jq, Node and Playwright. Never installs Kokoro or calls an LLM.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { execFile, execFileSync } = require('node:child_process');
const { promisify } = require('node:util');
const exec = promisify(execFile);
const repo = path.resolve(__dirname, '..');
const releaseVersion = fs.readFileSync(path.join(repo, 'code-gossip/VERSION'), 'utf8').trim();
const python = process.env.E2E_PYTHON || execFileSync('/usr/bin/which', ['python3'], { encoding: 'utf8' }).trim();
const jq = execFileSync('/usr/bin/which', ['jq'], { encoding: 'utf8' }).trim();
async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function until(check, description) {
  for (let n = 0; n < 60; n++) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out: ${description}`);
}
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  try {
    for (const dev of [false, true]) {
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'code gossip e2e-'));
      const home = path.join(temp, 'home with spaces');
      const checkout = path.join(temp, 'checkout');
      const runtime = path.join(home, '.code-gossip');
      const bin = path.join(temp, 'bin');
      const support = path.join(temp, 'support');
      const opened = path.join(temp, 'opened.txt');
      const port = await freePort();
      for (const directory of [home, bin, support, checkout]) fs.mkdirSync(directory, { recursive: true });
      for (const agent of ['codex', 'cursor', 'claude']) fs.mkdirSync(path.join(home, '.' + agent));
      for (const [name, source] of Object.entries({ python3: python, dirname: '/usr/bin/dirname', jq })) fs.symlinkSync(source, path.join(bin, name));
      const excluded = new Set(['state', 'version_state', '__pycache__', '.venv', 'config.json', 'phrases.json', 'narrator_styles.json']);
      fs.cpSync(path.join(repo, 'code-gossip'), path.join(checkout, 'code-gossip'), {
        recursive: true, filter: source => !excluded.has(path.basename(source)) && source !== path.join(repo, 'code-gossip/configs/sounds.json'),
      });
      fs.copyFileSync(path.join(repo, 'install.sh'), path.join(checkout, 'install.sh'));
      fs.writeFileSync(path.join(support, 'sitecustomize.py'), `import os, subprocess\n_real_run = subprocess.run\ndef run(args, *a, **kw):\n    if isinstance(args, list) and args[:1] == ['/usr/bin/open']:\n        with open(os.environ['E2E_OPENED'], 'a') as f: f.write(args[1] + '\\n')\n        return subprocess.CompletedProcess(args, 0)\n    return _real_run(args, *a, **kw)\nsubprocess.run = run\n`);
      fs.appendFileSync(path.join(support, 'sitecustomize.py'), fs.readFileSync(path.join(repo, 'tests/support/sitecustomize.py'), 'utf8'));
      const releaseDirectory=path.join(temp,'release');fs.mkdirSync(releaseDirectory);
      fs.writeFileSync(path.join(releaseDirectory,'release.json'),JSON.stringify({tag_name:releaseVersion,id:9,draft:false,prerelease:false}));
      execFileSync(python,['-c',`import pathlib,sys,zipfile
source=pathlib.Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], 'w', zipfile.ZIP_DEFLATED) as bundle:
    for file in source.rglob('*'):
        if file.is_file():
            bundle.writestr('release/'+str(file.relative_to(source)),file.read_bytes())
`,checkout,path.join(releaseDirectory,'release.zip')]);
      // Only the old installation is simulated; the candidate archive stays unchanged.
      fs.writeFileSync(path.join(checkout,'code-gossip/VERSION'),'0.8.0\n');
      const env = { ...process.env, TEST_RELEASE_DIRECTORY:releaseDirectory, HOME: home, CODEX_HOME: path.join(home, '.codex'), PATH: bin,
        PORT: String(port), PYTHONPATH: support, PYTHONDONTWRITEBYTECODE: '1', E2E_OPENED: opened };
      const run = async (script, ...args) => (await exec('/bin/bash', [script, ...args], { env, cwd: checkout, timeout: 30000 })).stdout;
      const install = (...extra) => run(path.join(checkout, 'install.sh'), '--agents', 'codex,cursor,claude', ...(dev ? ['--dev'] : []), ...extra);
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      try {
        // A dry run must never start a server or open the browser.
        await install('--dry-run');
        assert(!fs.existsSync(runtime)); assert(!fs.existsSync(opened));
        await install();
        assert.equal(fs.lstatSync(runtime).isSymbolicLink(), dev);
        const url = fs.readFileSync(opened, 'utf8').trim();
        assert.equal(url, `http://localhost:${port}`);
        const status = async () => (await fetch(url + '/api/status')).json();
        const pidFile = path.join(runtime, 'state/.server.pid');
        const pid = fs.readFileSync(pidFile, 'utf8');
        const before = fs.readFileSync(path.join(runtime, 'configs/config.json'), 'utf8');
        // Reinstallation reloads server code, while a manual open reuses that server.
        await install();
        assert.notEqual(fs.readFileSync(pidFile, 'utf8'), pid);
        const refreshedPid = fs.readFileSync(pidFile, 'utf8');
        await run(path.join(runtime, 'soundbar/panel.sh'), '--background');
        assert.equal(fs.readFileSync(pidFile, 'utf8'), refreshedPid);
        assert.equal(fs.readFileSync(path.join(runtime, 'configs/config.json'), 'utf8'), before);
        assert.equal(fs.readFileSync(opened, 'utf8').trim().split('\n').length, 3);
        for (const [agent, file] of [['codex', 'hooks.json'], ['cursor', 'hooks.json'], ['claude', 'settings.json']]) {
          const doc = JSON.parse(fs.readFileSync(path.join(home, '.' + agent, file), 'utf8'));
          assert(Object.keys(doc.hooks).length > 0);
        }
        await page.goto(url);
        await page.waitForFunction(() => document.getElementById('statusText').textContent.startsWith('Active'));
        assert.equal(await page.locator('[role=tab]').count(), 4);
        await page.selectOption('#soundPack', 'paper');
        assert.equal((await status()).effects_profile, 'default', 'Browsing does not save');
        await page.locator('#activateSelection').click();
        await until(async () => (await status()).effects_profile === 'paper', 'activated Effects profile');
        if(!dev){
          await page.locator('#settingsButton').click();
          await page.locator('#checkUpdates').click();
          await page.waitForFunction(version=>document.getElementById('availableVersion').textContent==='Available: '+version,releaseVersion);
          await page.locator('#applyUpdate').click();
          await page.waitForFunction(version=>document.getElementById('installedVersion').textContent==='Installed: '+version,releaseVersion,{timeout:30000});
          assert.equal((await status()).effects_profile,'paper','Update preserves saved preferences');
          assert.notEqual(fs.readFileSync(pidFile,'utf8'),refreshedPid,'Update restarts Soundbar');
          assert.equal(fs.readFileSync(path.join(runtime,'VERSION'),'utf8').trim(),releaseVersion);
          assert(!fs.existsSync(path.join(runtime,'version_state/recovery')));
        }
        await page.getByRole('tab', { name: 'Phrases', exact: true }).click();
        assert.equal((await status()).effects_profile, 'paper');
        await page.locator('#setup-phrases > summary').click();
        await page.selectOption('#phraseEngine', 'kokoro');
        assert.equal((await status()).tts_engine, 'say', 'Setup choices stay in the draft');
        assert(!fs.existsSync(path.join(runtime, 'state/.venv')));
        await page.reload();
        await page.locator('#tab-effects[aria-selected=true]').waitFor();
        await page.locator('#settingsButton').click();await page.locator('#closeSoundbar').click();
        await page.locator('#closedDialog[open]').waitFor();
        await until(() => !fs.existsSync(pidFile), 'server shutdown and PID cleanup');
        await assert.rejects(fetch(url + '/api/health'));
        // --no-panel preserves settings while keeping the panel stopped.
        await install('--no-panel');
        assert(!fs.existsSync(pidFile));
        assert.equal(JSON.parse(fs.readFileSync(path.join(runtime, 'configs/config.json'))).effects_profile, 'paper');
        await run(path.join(runtime, 'soundbar/panel.sh'), '--background');
        assert.equal((await status()).effects_profile, 'paper');
        await run(path.join(runtime, 'uninstall.sh'), '--agents', 'codex');
        assert((await fetch(url + '/api/health')).ok, 'Partial uninstall keeps the shared panel');
        await run(path.join(runtime, 'uninstall.sh'), '--all', '--purge');
        await until(async () => { try { await fetch(url + '/api/health'); return false; } catch { return true; } }, 'uninstall stops panel');
        assert(!fs.existsSync(runtime));
        assert(fs.existsSync(path.join(checkout, 'code-gossip/installer.py')), 'Dev checkout survives uninstall');
        assert.deepEqual(errors, []);
        console.log(`${dev ? 'Dev' : 'Normal'} end-to-end passed: install, browser opening, reuse, explicit activation, setup drafts, UI shutdown, reopen, partial/full uninstall.`);
      } finally {
        await context.close();
        if (fs.existsSync(path.join(runtime, 'uninstall.sh'))) await run(path.join(runtime, 'uninstall.sh'), '--all', '--purge').catch(() => {});
        fs.rmSync(temp, { recursive: true, force: true });
      }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
