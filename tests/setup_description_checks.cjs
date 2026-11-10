const assert = require('node:assert/strict');

module.exports = async function checkSetupDescriptions(page, mode) {
 if (!['effects','clips'].includes(mode)) return;
 const original = await page.evaluate(() => state.pack);
 const packs = mode === 'effects' ? await page.evaluate(() => packIds()) : [null];
 try {
  for (const pack of packs) {
   if (pack) await page.evaluate(pack => {state.pack=pack; renderEffectsDetail();},pack);
   const layout = await page.locator(`#panel-${mode} .strip-detail`).evaluate(node => {
    const rect = node.getBoundingClientRect(), strip = node.closest('.strip').getBoundingClientRect();
    return {
     text:node.textContent,
     fits:node.scrollWidth <= node.clientWidth && node.scrollHeight <= node.clientHeight,
     contained:rect.left >= strip.left && rect.right <= strip.right && rect.bottom <= strip.bottom,
     ellipsis:getComputedStyle(node).textOverflow === 'ellipsis',
    };
   });
   assert(layout.fits && layout.contained && !layout.ellipsis,`Full setup description is visible: ${layout.text}`);
  }
 } finally {
  if (mode === 'effects') await page.evaluate(pack => {state.pack=pack; renderEffectsDetail();},original);
 }
};
