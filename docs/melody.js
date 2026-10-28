/* Browser counterpart of engine/melody.py; Python/JavaScript parity is tested in CI. */
'use strict';
const SoundbarMelody = (() => {
 const pitchClass = (note, root) => ((note - root) % 12 + 12) % 12;
 function scaleNotes(settings) {
  const {root, scale, range:[low, high]} = settings;
  if (![root, low, high, ...scale].every(Number.isInteger) || root < 0 || root > 127 ||
      low < 0 || low >= high || high > 127 || !scale.length || scale.some(n => n < 0 || n >= 12)) {
   throw new Error('Invalid melody scale or range');
  }
  const notes = [];
  for (let note = low; note <= high; note++) if (scale.includes(pitchClass(note, root))) notes.push(note);
  if (notes.length < 3) throw new Error('Melodies need at least three notes');
  return notes;
 }
 function weightedChoice(candidates, weights, random) {
  const total = weights.reduce((sum, weight) => sum + weight, 0), draw = random() * total;
  let cumulative = 0;
  for (let index = 0; index < candidates.length - 1; index++) {
   cumulative += weights[index];
   if (draw < cumulative) return candidates[index];
  }
  return candidates.at(-1);
 }
 function chooseNote(notes, history, random, candidates = notes) {
  const previous = history.at(-1);
  candidates = candidates.filter(note => candidates.length === 1 || note !== previous);
  const weights = candidates.map(note => {
   if (previous === undefined) return 1 / (1 + Math.abs(notes.indexOf(note) - (notes.length - 1) / 2));
   const distance = Math.abs(notes.indexOf(note) - notes.indexOf(previous));
   let weight = ({0:.1, 1:12, 2:5, 3:1.5})[distance] ?? .3;
   if (history.slice(-4).includes(note)) weight *= .2;
   if (history.length > 1) {
    const leap = previous - history.at(-2);
    if (Math.abs(leap) >= 5 && leap * (note - previous) < 0) weight *= 2;
   }
   return weight;
  });
  return weightedChoice(candidates, weights, random);
 }
 function compose(settings, spec, history = [], random = Math.random) {
  const notes = scaleNotes(settings), phrase = spec.phrase || 'note';
  history = history.filter(n => Number.isInteger(n) && notes.includes(n)).slice(-4);
  if (!['note','rise','fall','question','resolve'].includes(phrase)) throw new Error('Unknown melody phrase');
  if (phrase === 'resolve') {
   const cadences = [];
   for (const tonic of notes) if (pitchClass(tonic, settings.root) === 0) {
    for (const fifth of [tonic - 5, tonic + 7]) if (notes.includes(fifth)) cadences.push([fifth, tonic]);
   }
   if (!cadences.length) throw new Error('Resolution needs a tonic and fifth in range');
   const previous = history.at(-1) ?? notes[Math.floor(notes.length / 2)];
   return weightedChoice(cadences, cadences.map(([fifth]) => 1 / (1 + Math.abs(fifth - previous))), random);
  }
  const followers = first => notes.filter(note => (phrase === 'rise' ? note > first : note < first) &&
   !(pitchClass(first, settings.root) === 7 && pitchClass(note, settings.root) === 0));
  const directional = phrase === 'rise' || phrase === 'fall';
  const first = chooseNote(notes, history, random, directional ? notes.filter(note => followers(note).length) : notes);
  if (phrase === 'question') return [first, first];
  if (directional) return [first, chooseNote(notes, [...history, first], random, followers(first))];
  return [first];
 }
 function createHistory({idleSeconds, random = Math.random, now = () => performance.now() / 1000}) {
  if (!(idleSeconds > 0)) throw new Error('Missing melody history expiry');
  const histories = new Map();
  return {
   next(settings, spec, identity) {
    const time = now(), key = JSON.stringify([identity, settings]);
    for (const [id, entry] of histories) if (time - entry.time < 0 || time - entry.time >= idleSeconds) histories.delete(id);
    const history = histories.get(key)?.notes || [];
    const selected = compose(settings, spec, history, random);
    histories.delete(key);
    histories.set(key, {time, notes:[...history, ...selected].slice(-4)});
    if (histories.size > 64) histories.delete(histories.keys().next().value);
    return selected;
   },
  };
 }
 return {compose, createHistory};
})();
if (typeof module !== 'undefined') module.exports = SoundbarMelody;
