(() => {
 if (location.origin !== 'https://fantasy.premierleague.com' || window.fplManagerReading) return;
 window.fplManagerReading = true;

 const read = async path => {
  const response = await fetch(path, {
   credentials: 'same-origin', cache: 'no-store', redirect: 'error',
   signal: AbortSignal.timeout(8000),
  });
  return response.ok ? response.json() : null;
 };

 (async () => {
  try {
   const profile = await read('/api/me/');
   const reference = profile?.player?.entry;
   if (!Number.isSafeInteger(reference) || reference < 1) return;

   const team = await read(`/api/my-team/${reference}/`);
   if (!Array.isArray(team?.picks) || team.picks.length !== 15) return;
   const salePrices = {};
   for (const {element, selling_price} of team.picks) {
    if (!Number.isSafeInteger(element) || element < 1 || element in salePrices ||
        !Number.isSafeInteger(selling_price) || selling_price < 1) return;
    salePrices[element] = selling_price;
   }

   const {bank, limit, made} = team.transfers ?? {};
   const free = Number.isInteger(limit) && limit >= 0 && limit <= 5 &&
       Number.isInteger(made) && made >= 0 ? Math.max(0, limit - made) : null;
   window.chrome.webview.postMessage({
    type: 'fpl-account',
    reference,
    sale_prices: salePrices,
    bank: Number.isInteger(bank) && bank >= 0 ? bank : null,
    free_transfers: free,
   });
  } catch {
   // The runner retries while the official account is signing in.
  } finally {
   window.fplManagerReading = false;
  }
 })();
})();
