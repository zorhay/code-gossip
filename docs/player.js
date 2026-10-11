// Native controls work without JavaScript. Do not autoplay or mute the demos.
const players = [...document.querySelectorAll('video')];
for (const player of players) {
  const card = player.closest('.player');
  player.addEventListener('play', () => {
    for (const other of players) {
      if (other !== player) other.pause();
    }
    card.classList.add('is-playing');
  });
  for (const event of ['pause', 'ended']) {
    player.addEventListener(event, () => card.classList.remove('is-playing'));
  }
  player.addEventListener('error', () => { card.querySelector('.error').hidden = false; });
  player.querySelector('source').addEventListener('error', () => {
    card.querySelector('.error').hidden = false;
  });
}
