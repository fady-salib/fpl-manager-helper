async (plan, preparing) => {
 if (location.origin !== 'https://fantasy.premierleague.com' || window.fplManagerReviewing) return;
 const validIds = (ids, length) => Array.isArray(ids) && ids.length === length &&
  ids.every(id => Number.isSafeInteger(id) && id > 0) && new Set(ids).size === ids.length;
 const count = plan.incoming?.length;
 if (!Number.isSafeInteger(plan.reference) || plan.reference < 1 || !Number.isSafeInteger(plan.event) ||
     count < 1 || count > 4 || !validIds(plan.owned, 15) || !validIds(plan.incoming, count) ||
     !validIds(plan.outgoing, count) || plan.incoming.some(id => plan.owned.includes(id)) ||
     plan.outgoing.some(id => !plan.owned.includes(id))) return;
 if (preparing && location.pathname !== '/transfers') return;

 window.fplManagerReviewing = true;
 let edited = false;
 const send = (status, message) => window.chrome.webview.postMessage({
  type: 'fpl-transfer-review', status, message, reset: edited && status === 'error',
 });
 const read = async path => {
  const response = await fetch(path, {
   credentials: 'same-origin', cache: 'no-store', redirect: 'error',
   signal: AbortSignal.timeout(8000),
  });
  return response.ok ? response.json() : null;
 };
 const sameIds = (actual, expected) => validIds(actual, expected.length) &&
  expected.every(id => actual.includes(id));
 const expected = [...plan.owned.filter(id => !plan.outgoing.includes(id)), ...plan.incoming];
 const text = value => String(value || '').normalize('NFC').trim().replace(/\s+/g, ' ');
 const visible = element => element.getClientRects().length && getComputedStyle(element).visibility === 'visible';
 const enabled = element => !element.disabled && element.getAttribute('aria-disabled') !== 'true' &&
  !element.closest('[inert], [aria-hidden="true"]');
 const buttons = (root = document) => Array.from(root.querySelectorAll('button, [role="button"]')).filter(visible);
 const named = (label, root) => buttons(root).filter(button =>
  text(button.getAttribute('aria-label') || button.textContent) === label && enabled(button));
 const uniquely = list => list.length === 1 ? list[0] : null;
 const managerSquad = () => buttons().filter(button => {
  const table = button.closest('table');
  return (!table || table.getAttribute('aria-label') === 'Transfers List') &&
   /^Remove player /.test(button.getAttribute('aria-label') || '');
 });
 const inSquad = name => uniquely(managerSquad().filter(button =>
  text(button.getAttribute('aria-label')) === 'Remove player ' + name && enabled(button)));
 const search = () => uniquely(Array.from(document.querySelectorAll('input#search')).filter(visible));
 const waitFor = async (find, message, timeout = 4000) => {
  const until = Date.now() + timeout;
  do {
   const node = find();
   if (node) return node;
   await new Promise(resolve => setTimeout(resolve, 100));
  } while (Date.now() < until);
  throw Error(message);
 };

 try {
  const profile = await read('/api/me/');
  const reference = profile?.player?.entry;
  if (!Number.isSafeInteger(reference)) return;
  if (reference !== plan.reference) {
   send('error', 'This FPL window is signed in to a different account.');
   return;
  }
  const team = await read(`/api/my-team/${reference}/`);
  const roster = team?.picks?.map(pick => pick.element);
  if (!Array.isArray(roster)) return;
  if (!preparing) {
   if (sameIds(roster, expected)) send('verified', '');
   return;
  }
  if (!sameIds(roster, plan.owned)) {
   send('error', 'Your FPL squad changed. Sync with FPL and recalculate the recommendation.');
   return;
  }
  const data = await read('/api/bootstrap-static/');
  if (!Array.isArray(data?.events) || !Array.isArray(data.elements)) return;
  const event = data.events.find(item => item.is_next === true);
  if (event?.id !== plan.event || Date.parse(event.deadline_time) <= Date.now()) {
   send('error', 'The FPL gameweek changed. Refresh local data and recalculate the recommendation.');
   return;
  }
  if (team.chips?.some(chip => ['active', 'pending'].includes(chip.status_for_entry) &&
      ['wildcard', 'freehit'].includes(chip.name))) {
   send('error', 'A transfer chip is active. Review those moves in the official FPL window.');
   return;
  }

  const players = new Map(data.elements.map(player => [player.id, player]));
  const original = plan.owned.map(id => text(players.get(id)?.web_name));
  const result = expected.map(id => text(players.get(id)?.web_name));
  const changedNames = [...plan.outgoing, ...plan.incoming].map(id => text(players.get(id)?.web_name));
  if (![original, result].every(names => names.every(Boolean) && new Set(names).size === names.length) ||
      changedNames.some(name => data.elements.filter(player => text(player.web_name) === name).length !== 1)) {
   send('error', 'FPL uses an ambiguous player name. Select the recommended moves in the official window.');
   return;
  }
  const pairs = [];
  const incoming = plan.incoming.map(id => players.get(id));
  for (const id of plan.outgoing) {
   const player = players.get(id);
   const index = incoming.findIndex(item => item.element_type === player.element_type);
   if (index < 0) throw Error('The recommended players no longer match FPL positions.');
   pairs.push([player, incoming.splice(index, 1)[0]]);
  }

  await waitFor(() => managerSquad().length === 15 && original.every(inSquad), 'The official squad controls did not match the recommendation.', 6500);
  for (const [out, next] of pairs) {
   const outName = text(out.web_name), inName = text(next.web_name);
   const remove = await waitFor(() => inSquad(outName), `Could not find ${outName} in the FPL squad.`);
   edited = true;
   remove.click();
   await waitFor(() => !inSquad(outName), `FPL did not remove ${outName} from the draft.`);
   if (!search()) {
    const position = data.element_types?.find(item => item.id === next.element_type)?.singular_name;
    const select = uniquely(named('Select ' + position));
    if (select) select.click();
   }
   const input = await waitFor(search, 'The official player search could not be opened.');
   Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, inName);
   input.dispatchEvent(new Event('input', {bubbles: true}));
   const add = await waitFor(() => uniquely(named('Add player ' + inName)),
    `FPL did not offer ${inName} as an eligible replacement.`);
   add.click();
   const sheet = input.closest('[role="dialog"]');
   if (sheet && visible(sheet)) {
    const close = uniquely(named('Close', sheet));
    if (close) close.click();
   }
   await waitFor(() => inSquad(inName), `FPL did not add ${inName} to the draft.`);
  }

  await waitFor(() => managerSquad().length === 15 && result.every(inSquad),
   'The staged FPL squad did not match the recommendation.');
  const review = await waitFor(() => uniquely(named('Make Transfers')),
   'FPL did not enable transfer review for this draft.');
  review.click();
  const getReview = () => Array.from(document.querySelectorAll('[role="dialog"]')).find(dialog =>
   visible(dialog) && buttons(dialog).some(button => /^Confirm\b/.test(text(button.textContent))));
  const dialog = await waitFor(getReview, 'FPL did not show the official confirmation dialog.');
  const rows = Array.from(dialog.querySelectorAll('tbody tr'));
  const reviewedOut = rows.map(row => text(row.cells[0]?.textContent)).sort();
  const reviewedIn = rows.map(row => text(row.cells[1]?.textContent)).sort();
  const expectedNames = ids => ids.map(id => text(players.get(id)?.web_name)).sort();
  if (rows.length !== count || !expectedNames(plan.outgoing).every((name, i) => name === reviewedOut[i]) ||
      !expectedNames(plan.incoming).every((name, i) => name === reviewedIn[i])) {
   throw Error('The official confirmation did not contain the recommended moves.');
  }
  send('prepared', '');
 } catch (error) {
  if (edited) send('error', error.message);
  else if (error instanceof Error && error.name === 'Error') send('error', error.message);
 } finally {
  window.fplManagerReviewing = false;
 }
}
