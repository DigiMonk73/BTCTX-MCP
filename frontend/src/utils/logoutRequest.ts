// The Header's Logout, asked for once (#583's re-check). /logout logs out
// only for the request this page made: the POST would come from BitcoinTX's
// own page, so the server's cross-site refusal can't stop a link from
// another site, and a typed address, a reload or a Back or Forward onto
// /logout carry no request still waiting. Kept in memory, which no other
// site and no history entry can reach.

let issued = 0;
let waiting: number | null = null;

/** A new request to log out: the token the navigation to /logout carries. */
export function requestLogout(): number {
  issued += 1;
  waiting = issued;
  return waiting;
}

/** Whether `token` is the request still waiting; it can be used only once. */
export function takeLogoutRequest(token: unknown): boolean {
  if (token === null || token !== waiting) return false;
  waiting = null;
  return true;
}
