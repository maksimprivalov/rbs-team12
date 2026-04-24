## Lab 3, medium: CSRF where token validation depends on token being present

### Attack class

Same attack class as Lab 1. Cross-Site Request Forgery (CSRF) is an attack that tricks an authenticated user's browser into sending an unintended state-changing request to a web application. Because browsers automatically attach session cookies to every request destined for the origin that issued them, a malicious page hosted on a different domain can silently trigger actions on behalf of the victim without their knowledge or consent.

In this variant the application does issue a CSRF token and validates it when present - but the validation is conditional: if the `csrf` parameter is absent from the request entirely, the server skips the check and processes the action anyway. An attacker simply omits the field from the forged form rather than trying to guess or steal a valid token.

### Impact

Same impact as Labs 1 and 2. A successful CSRF attack lets an attacker perform any action the victim is authorized to perform:

- Account takeover through email or password change (as in this lab).
- Unauthorized fund transfers or purchases if the target is a banking or e-commerce application.
- Privilege escalation when an administrator visits the malicious page - the attacker inherits admin-level permissions for that forged request.
- Data exfiltration or deletion if state-changing endpoints also return sensitive data in the response.

The severity is directly proportional to the victim's privilege level and the sensitivity of available actions.

### Software weaknesses that enabled the attack

- The CSRF token validation was conditional on the token's presence in the request. The server checked `if csrf_token is not None: validate(csrf_token)` but took no action when the parameter was missing entirely, treating its absence as a valid state.
- The guard never enforced that a token must exist - only that an existing token must be correct. These are two distinct checks and the second alone is insufficient.
- The session cookie lacked the `SameSite` attribute, so the browser attached it to cross-site POST requests submitted by an auto-submitting HTML form on an attacker-controlled page.
- No `Origin` or `Referer` validation was performed as a fallback, leaving the server with no signal that the request originated from a different domain.

### Countermeasures

#### Token presence must be a hard requirement:

- Treat a missing CSRF token as a validation failure, not as a case to skip. The check must be: `if csrf_token is None or not validate(csrf_token): reject()`.
- Reject the request with `403 Forbidden` whenever the token is absent, empty, or invalid - never silently proceed.
- Use a framework-level CSRF middleware that enforces token presence by default for all state-changing methods (POST, PUT, PATCH, DELETE), so individual handlers cannot accidentally bypass it by omitting the check.

#### SameSite cookie attribute blocks the browser-level vector:

- Set `SameSite=Strict` on session cookies so the browser never attaches them to cross-site requests.
- Where `Strict` breaks legitimate cross-site navigations, use `SameSite=Lax` as the minimum - it blocks cross-site form POSTs while allowing top-level navigations.
- Pair `SameSite` with `Secure` and `HttpOnly` to reduce the attack surface further.

#### Defense-in-depth for sensitive endpoints:

- Validate the `Origin` and `Referer` headers server-side as a secondary check. Reject requests whose origin does not match the expected application domain.
- Require re-authentication (password confirmation) for high-impact actions such as email or password changes, even for already-authenticated sessions.
- Run automated tests that submit state-changing requests without a CSRF token and assert a `403` response - this class of misconfiguration is trivially detectable with a single negative test case.

## Solution writeup

Goal: Use the exploit server to craft a page that, when visited by the victim, forges a POST request to change their email address - bypassing CSRF protection by simply omitting the token from the request body.

- Step 1 - Analyze the email-change request
Log in with the provided credentials and change your email address while Burp Proxy is intercepting. Locate the resulting `POST /my-account/change-email` request. The body includes both `email` and `csrf` parameters.

- Step 2 - Discover the presence-based bypass
Send the captured request to Repeater. Remove the `csrf` parameter from the request body entirely (do not send an empty value - remove the field). Send the request - the server responds with `302 Found` and processes the email change, confirming that the validation only runs when the token is present and is silently skipped when it is absent.

- Step 3 - Craft the CSRF exploit page
On the exploit server, write an HTML page with a POST form that auto-submits without a `csrf` field:

```html
<form method="POST" action="https://<lab-id>.web-security-academy.net/my-account/change-email">
    <input type="hidden" name="email" value="attacker@web-security-academy.net">
    <input type="submit" value="Submit request"/>
</form>
<script>
    document.forms[0].submit();
</script>
```

The `csrf` hidden field is intentionally absent. The browser will attach the victim's session cookie automatically.

- Step 4 - Deliver the exploit to the victim
Click **Store**, then **Deliver exploit to victim**. The victim's browser loads the page, the form auto-submits with their session cookie attached and no token in the body, and the application changes their email address.

Screenshot of the exploit payload on the exploit server before delivery:

![CSRF exploit form without token on the exploit server](images/csrf-lab-3-request.png)

- Step 5 - Confirm the lab is solved
The application processes the forged request and updates the victim's email, solving the lab.
