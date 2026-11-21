# Google OAuth, Gmail, and master account setup

Use this guide to configure the private account and email credentials. For the selected GitHub-to-EC2 deployment with direct Uvicorn HTTPS on port 443, follow the [native deployment guide](ec2-native-deployment.md).

## 1. Google sign-up and sign-in credentials

1. Sign in as `chewang1705@gmail.com` at [Google Cloud Console](https://console.cloud.google.com/).
2. Open the project picker and create a project such as **Launchpad Radar**.
3. Open **Google Auth Platform**. If prompted, select **Get started**.
4. In **Branding**, set the app name to **Launchpad Radar**, support email and developer contact to your email, and authorized domain to `shivam-tripathi.com`. Complete any ownership verification Google requests. Use real homepage/privacy URLs if you later publish those fields; do not enter nonexistent pages.
5. In **Audience**, choose **External** for users outside a Google Workspace organization. During testing, add `chewang1705@gmail.com` and other testers. Before opening registration to everyone, use Google's publish-to-production process and complete any requested verification.
6. In **Data Access**, configure only basic OpenID profile/email scopes (`openid`, `email`, `profile`). The app does not request Gmail access through login.
7. In **Clients**, choose **Create client → Web application**. Name it **Launchpad web**.
8. Add these **Authorized redirect URIs**, with exactly the same capitalization, scheme, port and path:

   ```text
   https://radar.shivam-tripathi.com/api/auth/google/callback
   http://localhost:8000/api/auth/google/callback
   http://localhost:5173/api/auth/google/callback
   ```

   JavaScript origins are unnecessary for this server-side flow. If you add them, use origins only, such as `https://radar.shivam-tripathi.com` (no callback path).
9. Select **Create**. Copy the client ID and client secret immediately into the private project-root `.env`:

   ```dotenv
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```

10. For production, keep `APP_URL=https://radar.shivam-tripathi.com`. The local development script overrides this with `http://localhost:5173`. A direct local backend launch should override it with `http://localhost:8000`.

The first successful Google sign-in creates a regular account; later sign-ins reuse its Google subject ID. It does not promote accounts by email address. The master account has its own username/password login, even when it uses the same email address.

References: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server), [create OAuth clients](https://support.google.com/cloud/answer/15549257).

## 2. Gmail sending credentials

1. Open [Google Account security](https://myaccount.google.com/security), signed in as `chewang1705@gmail.com`.
2. Enable **2-Step Verification** and complete its setup.
3. Open [App passwords](https://myaccount.google.com/apppasswords). Reauthenticate if asked.
4. Name the app **Launchpad job alerts** and select **Create**.
5. Copy the generated app password to `.env`:

   ```dotenv
   GMAIL_ADDRESS=chewang1705@gmail.com
   GMAIL_APP_PASSWORD=your-16-character-app-password
   ```

6. Keep this separate from your normal Google password. Do not put it in frontend code or commit it. Restart/recreate the app after changing environment credentials.

The sender uses authenticated TLS to `smtp.gmail.com:465`; no Gmail API enablement is necessary. If App passwords is unavailable, check Google's listed restrictions for organization accounts, Advanced Protection, and security-key-only 2-Step Verification. Gmail usage limits apply; this is intended for a small user base. See [Google app-password instructions](https://support.google.com/accounts/answer/185833).

New Google accounts are subscribed to six-hourly alerts, as disclosed on the sign-in page. Each recipient receives an individual digest with titles, companies, locations, and original employer links. **My account & emails** lets them unsubscribe, choose daily delivery, or set keyword/location filters. Only live, active jobs first discovered after that account joined are eligible. No new matches means no email. Digests contain up to 100 jobs; additional unsent matches stay eligible for later digests. The master account starts with alerts off to avoid duplicate messages when the operator also signs in with Google.

After collections finish, the mail scheduler checks eligibility every minute. Successful deliveries are recorded per user/job. Failures retain the jobs and retry after 15 minutes. SQLite delivery tracking prevents routine repeats, but SMTP cannot guarantee exactly-once delivery: a crash after Gmail accepts a message but before the database records it can cause a duplicate.

## 3. Master account

From the project root, after installing backend dependencies:

```bash
.venv/bin/python scripts/setup_accounts.py
```

This creates `.env` and `master-credentials.txt` with owner-only permissions. It generates a random password and stores only its scrypt hash in `.env`. It preserves an existing configured hash. Both private files are excluded from Git.

The initial username is `radar-master`. Open `master-credentials.txt` locally for its password, then put it in a password manager. The backend creates the master account on its first startup. Existing pre-account bookmarks are copied to that account only. The original legacy bookmarks table remains for migration preservation and is no longer used by the API.

The master can list accounts, view account email/status/alert activity and save counts, disable/enable users, and manage company sources. Disabling a user immediately invalidates existing sessions. The master cannot disable itself through the dashboard. Change the master username/password in **My account & emails → Master credentials**; this also revokes its other sessions. Startup never replaces an existing master password with the bootstrap value from `.env`.

