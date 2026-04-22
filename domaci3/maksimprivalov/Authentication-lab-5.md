## Lab 5, easy: 2FA simple bypass

### Attack class

Broken authentication state machine is a vulnerability class where an application implements multi-factor authentication but fails to enforce that every factor was successfully completed before granting access to protected resources. After submitting valid first-factor credentials (username + password), the server places the session in a partially-authenticated state and redirects the user to the 2FA verification page. The flaw is that protected pages only check whether a valid session cookie exists, not whether 2FA was actually completed for that session. An attacker who knows valid credentials can skip the 2FA step entirely by navigating directly to a post-login URL, and the server will treat them as fully authenticated.

### Impact

This vulnerability completely negates the protection that 2FA is intended to provide. Any account whose password is known - through phishing, credential stuffing, or a prior data breach - can be taken over instantly without needing access to the victim's phone or authenticator app. Consequences include:

- Full account takeover with no need to compromise the second factor, rendering 2FA worthless as a defence layer.
- Stolen credential databases that would previously be unusable against 2FA-protected accounts become immediately actionable.
- The bypass requires no special tooling - a browser and knowledge of the post-login URL path are sufficient, lowering the bar for exploitation.
- Affected users who enabled 2FA believing it protected them face a false sense of security, which may delay detection of the breach.

### Software weaknesses that enabled the attack

- The server did not track 2FA completion status in the session. After the first factor succeeded it issued a session cookie, but that cookie granted full access to protected endpoints regardless of whether the `/login2` verification step was ever visited or passed.
- Protected pages performed no check that the authenticated session had completed all required authentication steps - they only verified that a session cookie was present and valid.
- The authentication flow relied entirely on client-side navigation (redirect to `/login2`) to enforce 2FA, with no server-side gate that would reject requests to protected resources from sessions still in the partial-auth state.
- No anomaly was logged or alerted when a session transitioned directly from first-factor success to accessing protected pages without ever hitting the 2FA endpoint.

### Countermeasures

#### The server must enforce 2FA completion as a server-side gate, not a client-side redirect:

- Store a `mfa_completed` flag (or equivalent step marker) in the server-side session, set to `false` after first-factor success. Protected endpoints must check this flag and reject or redirect any session where it is not `true`.
- Treat the partially-authenticated session as untrusted: restrict it to the single `/login2` endpoint only, and deny all other requests until 2FA is passed.
- Expire partially-authenticated sessions aggressively (e.g., 5 minutes) so that an attacker cannot indefinitely reuse a stolen first-factor session to probe for bypass paths.

#### Defence in depth:

- Implement step-up authentication checks at the resource level, not just at the redirect level, so that any future addition of new pages automatically inherits the 2FA gate.
- Log and alert on sessions that complete the first factor but never reach the 2FA page - this pattern is a clear signal of bypass attempts.
- Consider binding the fully-authenticated session to a new session ID issued only after 2FA success, invalidating the partial-auth session token entirely.

#### Related surfaces:

- Apply the same completion-state tracking to any multi-step flow: password reset confirmation, email verification, consent screens.
- Audit all protected endpoints to ensure none rely solely on the presence of a session cookie without checking the authentication level associated with that session.

## Solution writeup

Goal: Log in to the victim account carlos, bypassing the 2FA verification step.

- Step 1 - Observe the normal 2FA flow with own credentials
Log in as wiener with the known password. The server redirects to `/login2` (the 2FA page). Enter the verification code and observe that a successful 2FA completion redirects to `/my-profile`. Note this destination URL.

- Step 2 - Begin login as the victim
Log out and start a new login with carlos's credentials. The server accepts the password and redirects the browser to `/login2`, placing the session in a partially-authenticated state.

- Step 3 - Skip 2FA by navigating directly to the protected page
Instead of entering a verification code, manually change the URL in the address bar to `/my-profile`. The server checks only for a valid session cookie, finds one (issued after the first factor), and grants full access without verifying that 2FA was completed.

- Step 4 - Solve the lab
The account page for carlos loads successfully, solving the lab.
