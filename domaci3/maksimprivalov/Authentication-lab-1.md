## Lab 1, easy: Username enumeration via different responses

### Attack class

Username enumeration is an information disclosure brute-force attack where the application's responses reveal whether a submitted username exists in the system. By observing differences in error messages, HTTP status codes, response lengths, or response timing between login attempts with valid versus invalid usernames, an attacker can build a list of confirmed accounts without ever logging in. This list then serves as the input set for targeted follow-up attacks such as password brute-forcing, credential stuffing, or password spraying.

### Impact

On its own, username enumeration is a low-severity finding - the attacker only learns which accounts exist. However, it is almost always a stepping stone that dramatically increases the success rate of subsequent attacks:

Targeted brute-force becomes feasible because the attacker no longer wastes attempts on non-existent accounts, and rate-limiting protections that block N attempts per username are easier to evade when the attacker knows exactly which usernames to target.
- Credential stuffing attacks using leaked breach databases become more efficient.
- Privacy violations occur when the application's user base is sensitive (e.g., a medical or adult-content platform confirming a specific person is registered).
- Social engineering becomes more credible when the attacker can reference a valid account in a phishing message.

Screenshot from the step when we figured out the account's username and easily guessed the right password after:

![Password](images/lab-1-password.png)

### Software weaknesses that enabled the attack

- The login endpoint returned different error messages for invalid username ("Invalid username") versus invalid password ("Incorrect password"), directly leaking account existence.
- The responses had different lengths, making automated enumeration trivial through Burp Intruder's response length column even if error messages were partially obfuscated.
- No rate limiting was applied to the login endpoint, allowing thousands of enumeration attempts from the same IP.
- The application did not use a constant-time response path - even if the messages were identical, timing differences between "user not found" (fast) and "user found, password check" (slow bcrypt comparison) could be measured.

### Countermeasures

#### Uniform response behavior is the primary defense. All authentication failures must be indistinguishable to an unauthenticated client:

- Return a single generic error message for every failure case - e.g., "Invalid username or password" - regardless of whether the username exists, the password is wrong, or the account is locked.
- Ensure responses have identical HTTP status codes, identical body length, and identical headers across all failure paths. Do not include conditional fields (e.g., "account locked" flags) that vary by case.
- Enforce constant-time processing by running the password-hash comparison (bcrypt/argon2) even when the username does not exist, using a dummy hash. This neutralizes timing side-channels.

#### Rate limiting and monitoring close the remaining gap:

- Apply per-IP and per-account rate limits on /login (e.g., 5 attempts per minute, exponential backoff thereafter).
- Implement CAPTCHA or proof-of-work challenges after a small number of failed attempts.
- Log and alert on enumeration patterns - a single IP submitting hundreds of distinct usernames within minutes is a clear signal.
- Use WAF rules to detect automated tools (consistent User-Agent, request timing, absence of typical browser headers).

#### Defense-in-depth for related surfaces:

- Apply the same uniform-response principle to password reset, registration ("this email is already taken" is the same leak), and account recovery endpoints.
- Enforce strong password policies and encourage 2FA so that even a successfully enumerated + brute-forced password is not sufficient for account takeover.
- Consider account-agnostic authentication flows (e.g., email-based magic links) for high-value accounts where username privacy matters.