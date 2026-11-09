const assert = require('node:assert/strict');

module.exports = async function checkSettings(page) {
 const initial = await page.evaluate(() => ({versions, setup, theme:document.documentElement.dataset.theme}));
 const geometry = selector => page.locator(selector).evaluateAll(nodes => nodes.map(node => {
  const {x,y,width,height} = node.getBoundingClientRect();
  return {x,y,width,height};
 }));
 for (const theme of ['amber','mint']) for (const [width,height] of [[1280,900],[390,640],[320,568]]) {
  await page.setViewportSize({width,height});
  await page.evaluate(theme => applyTheme(theme), theme);
  await page.locator('#settingsButton').click();
  const frame = '#settingsDialog,#settingsDialog .dlg-head,#settingsDialog .dlg-foot,#closeSettings,#closeSoundbar';
  const before = await geometry(frame);
  assert(await page.evaluate(() => {
   const dialog = document.getElementById('settingsDialog'), rect = dialog.getBoundingClientRect();
   return rect.top >= 0 && rect.bottom <= innerHeight && dialog.scrollWidth <= dialog.clientWidth;
  }), `Settings fits ${theme}/${width}`);
  await page.locator('#settingsBody').evaluate(node => {node.scrollTop = node.scrollHeight;});
  assert.deepEqual(await geometry(frame),before,'Scrolling leaves close controls in place');
  const controls = await geometry('.version-row');
  for (const change of [
   {available:true,release:{version:'100.100.100',notes_url:'https://example.com/notes'}},
   {running:true,phase:'downloading',message:'Downloading…'},
   {running:false,phase:'failed',message:'A long error with recovery details. '.repeat(30)},
   {available:false,release:null,phase:'idle',message:'',development:true},
  ]) {
   await page.evaluate(change => {Object.assign(versions,change); renderVersions();},change);
   assert.deepEqual(await geometry(frame),before,`Update state keeps Settings stable at ${width}`);
   assert.deepEqual(await geometry('.version-row'),controls,'Update feedback does not move the action row');
   assert(await page.evaluate(() => {
    const body = document.getElementById('settingsBody');
    return body.scrollWidth <= body.clientWidth;
   }),'Long update messages do not overflow horizontally');
  }
  await page.evaluate(initial => {versions=structuredClone(initial.versions); setup=structuredClone(initial.setup); renderVersions();},initial);
  await page.keyboard.press('Escape');
  assert(await page.locator('#settingsButton').evaluate(node => node === document.activeElement),'Escape restores focus to Settings');
 }
 await page.setViewportSize({width:1280,height:900});
 await page.evaluate(theme => applyTheme(theme),initial.theme);
 await page.locator('#settingsButton').click();
 await page.locator('#settingsBody').evaluate(node => {node.scrollTop=0;});
 const checked = await page.locator('#reduceRepeats').isChecked();
 await page.locator('label[for=reduceRepeats] strong').click();
 await page.waitForFunction(value => saved.sound_spacing_on === value,!checked);
 assert.equal(await page.locator('#effectsGap').isDisabled(),checked);
 assert.equal(await page.locator('#voiceGap').isDisabled(),checked);
 await page.locator('label[for=reduceRepeats] strong').click();
 await page.waitForFunction(value => saved.sound_spacing_on === value,checked);
 const approval = await page.locator('#approvalCues').isChecked();
 await page.locator('label[for=approvalCues] strong').click();
 await page.waitForFunction(value => saved.codex_permission_sound_on === value,!approval);
 await page.locator('label[for=approvalCues] strong').click();
 await page.waitForFunction(value => saved.codex_permission_sound_on === value,approval);
 await page.keyboard.press('Escape');
};
