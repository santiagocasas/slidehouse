// Thin wrapper around the local JSON API.

export async function api(url, data) {
  let response;
  try {
    response = await fetch(url, data
      ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)}
      : {cache: 'no-store'});
  } catch (_) {
    throw new Error('Cannot reach the SlideHouse server — run "slidehouse" in your slides folder, then click Reload.');
  }
  let result;
  try {
    result = await response.json();
  } catch (_) {
    throw new Error(`The server returned an invalid response (${response.status})`);
  }
  if (!response.ok) throw new Error(result.error || response.statusText);
  return result;
}
