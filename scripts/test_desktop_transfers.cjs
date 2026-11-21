const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('windows/review-transfers.js', 'utf8');
const owned = Array.from({length: 15}, (_, i) => i + 1);
const plan = {reference: 20, event: 10, owned, incoming: [16,17], outgoing: [1,2]};
const updated = [...owned.slice(2), 16, 17];
const playerName = id => 'Player ' + id;
const elements = [...owned, 16, 17].map(id => ({
 id, web_name: playerName(id), element_type: id === 1 || id === 17 ? 1 : 2,
}));

async function fixture({
 preparing = true, current = owned, reference = plan.reference, nextEvent = plan.event,
 wrongReview = false, origin = 'https://fantasy.premierleague.com',
} = {}) {
 let draft = [...current], searched = '', dialogOpen = false;
 const calls = [], clicks = [], messages = [];
 const button = (label, click, textContent = '') => ({
  getAttribute: name => name === 'aria-label' ? label : null,
  textContent, getClientRects: () => [1], closest: () => null,
  click() { clicks.push(label || textContent); click(); },
 });
 const confirm = button(null, () => assert.fail('Never submit an official transfer'), 'Confirm (-4pts)');
 const dialog = {
  getClientRects: () => [1],
  querySelectorAll: selector => selector === 'tbody tr'
   ? [[1, wrongReview ? 3 : 17], [2, 16]].map(row => ({
    cells: row.map(id => ({textContent: playerName(id)})),
   }))
   : [confirm],
 };
 class Input {
  getClientRects() { return [1]; }
  closest() { return null; }
  set value(value) { searched = value; }
  dispatchEvent(event) { assert.equal(event.type, 'input'); }
 }
 const input = new Input();
 const document = {
  querySelectorAll(selector) {
   if (selector === '[role="dialog"]') return dialogOpen ? [dialog] : [];
   if (selector === 'input#search') return [input];
   const controls = draft.map(id => button('Remove player ' + playerName(id),
    () => { draft = draft.filter(player => player !== id); }));
   for (const id of plan.incoming) {
    if (searched === playerName(id) && !draft.includes(id))
     controls.push(button('Add player ' + playerName(id), () => draft.push(id)));
   }
   controls.push(button(null, () => { dialogOpen = true; }, 'Make Transfers'));
   return controls;
  },
 };
 const run = vm.runInNewContext(source, {
  window: {chrome: {webview: {postMessage: data => messages.push(structuredClone(data))}}},
  location: {origin, pathname: preparing ? '/transfers' : '/my-team'},
  document, HTMLInputElement: Input, Event, AbortSignal, setTimeout,
  getComputedStyle: () => ({visibility: 'visible'}),
  async fetch(path, options) {
   calls.push(path);
   assert.equal(options.method, undefined, 'Only read requests are permitted');
   const payload = {
    '/api/me/': {player: {entry: reference}},
    '/api/my-team/20/': {picks: current.map(element => ({element}))},
    '/api/bootstrap-static/': {elements, events: [
     {id: nextEvent, is_next: true, deadline_time: '2099-01-01T00:00:00Z'},
    ]},
   }[path];
   assert.ok(payload, path);
   return {ok: true, json: async () => payload};
  },
 });
 await run(plan, preparing);
 return {calls, clicks, messages};
}

(async () => {
 const staged = await fixture();
 assert.deepEqual(staged.clicks,
  ['Remove player Player 1', 'Add player Player 17', 'Remove player Player 2', 'Add player Player 16', 'Make Transfers']);
 assert.deepEqual(staged.messages, [{type:'fpl-transfer-review', status:'prepared', message:'', reset:false}]);
 const invalid = await fixture({wrongReview: true});
 assert.equal(invalid.messages[0].status, 'error');
 assert.equal(invalid.messages[0].reset, true);
 for (const options of [{reference: 33}, {current: updated}, {nextEvent: 11}]) {
  const rejected = await fixture(options);
  assert.deepEqual(rejected.clicks, []);
  assert.equal(rejected.messages[0].status, 'error');
 }
 const unrelated = await fixture({origin: 'https://other.test'});
 assert.deepEqual(unrelated.calls, []);
 const unchanged = await fixture({preparing: false});
 assert.deepEqual(unchanged.messages, []);
 const saved = await fixture({preparing: false, current: updated});
 assert.equal(saved.messages[0].status, 'verified');
 assert.deepEqual(saved.clicks, []);
 console.log('Desktop transfers: draft, manual confirmation, stale account/gameweek, and save verification passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
