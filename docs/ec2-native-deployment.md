# Direct EC2 deployment: Uvicorn on port 443

This is the selected deployment for the Amazon Linux 2023 x86_64 t3.micro. Uvicorn serves React and FastAPI over HTTPS on TCP 443 using the exported ACM certificate. A systemd service runs one application process, restarts it on failure, and starts it after reboots. Source is pulled from GitHub, the frontend is built during deployment, and the private `.env` is created manually on EC2.

The existing SSH alias `ec2` can be used to connect from the Mac. Commands below are run by the operator; no automated remote SSH execution is required. All commands below are single lines; paste each line separately and stop if a command reports an error.

## 1. EC2: clone the application from GitHub

Run these commands yourself in your EC2 terminal. The main-branch instructions apply after the pull request has been merged:

```bash
sudo dnf install -y git nodejs22 nodejs22-npm
cd ~
git clone https://github.com/shivam261/junior-job-radar.git
cd ~/junior-job-radar
npm-22 ci --prefix frontend
npm-22 run build --prefix frontend
```

The frontend build runs once during deployment. Node is not a running application service. The installer then serves the compiled frontend through the same Uvicorn process as the API. The checkout and frontend dependencies occupy disk space; they do not stay active in memory after the build exits. On a t3.micro, a build can still exhaust available RAM; if it exits with an out-of-memory error, stop and resolve that before installing. A locally built bundle remains an optional fallback, documented below.

## 2. EC2: create the private .env using cat

In the cloned project directory:

```bash
umask 077
cat > .env
```

Paste your configured environment values, then press **Ctrl+D** on a new line to finish. `cat` reads the contents directly, rather than sending each secret as a shell command. Use the values from your existing private `.env`, including `MASTER_USERNAME` and `MASTER_PASSWORD_HASH` generated earlier. The Google/Gmail values and master hash must be your real server-side values; do not use placeholder passwords.

These are the required configuration keys (the following block is an example to fill, not a shell command):

```dotenv
APP_URL=https://radar.shivam-tripathi.com
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
GMAIL_ADDRESS=YOUR_GMAIL_SENDER
GMAIL_APP_PASSWORD=YOUR_GMAIL_APP_PASSWORD
MASTER_EMAIL=YOUR_EMAIL
MASTER_USERNAME=radar-master
MASTER_PASSWORD_HASH='YOUR_GENERATED_SCRYPT_HASH'
AUTO_REFRESH=true
REFRESH_ON_STARTUP=true
REFRESH_INTERVAL_SECONDS=21600
```

Confirm permissions without printing the configuration:

```bash
chmod 600 .env
ls -l .env
```

`.env` is git-ignored and must never be committed. `master-credentials.txt` contains the matching original master password on the machine where you ran `scripts/setup_accounts.py`. If you have not generated it yet, follow README's local setup, run that script, and copy the generated hash into the EC2 `.env`. The existing private credential file is not uploaded or published.

## 3. EC2: confirm the certificate files

The installer expects your original ACM exports in `/home/ec2-user/launchpad-certs/`:

```text
certificate.pem
certificate_chain.pem
private_key.pem
```

Check filenames and permissions:

```bash
ls -lh ~/launchpad-certs
chmod 600 ~/launchpad-certs/*.pem
```

The installer verifies the domain, trust chain, expiry, and matching private key. It reads the original encrypted `private_key.pem` directly; enter the ACM export passphrase when prompted. Previously prepared `fullchain.pem` and `server-key.pem` in that folder can remain there.

## 4. EC2: install and start the application

```bash
cd ~/junior-job-radar
sudo bash deploy/install-native.sh
```

The installer installs Python 3.12 and backend dependencies, validates the certificate, installs the code, and starts `launchpad.service`. Enter the **ACM export passphrase** if OpenSSL asks for it. The passphrase is not printed or stored by the installer. If a different application already uses port 443, the installer stops with an explanation rather than stopping that application.

The app runs as the dedicated Linux user `launchpad`, with the capability to bind port 443. It has these server paths:

| Path | Purpose |
| --- | --- |
| `/opt/launchpad` | Application and Python virtual environment |
| `/etc/launchpad/launchpad.env` | Root-readable server environment configuration |
| `/etc/launchpad/tls/fullchain.pem` | Certificate and certificate chain |
| `/etc/launchpad/tls/server-key.pem` | Private key, readable only by root and the app group |
| `/var/lib/launchpad/jobs.sqlite3` | Persistent jobs, accounts, bookmarks and mail history |
| `/etc/systemd/system/launchpad.service` | Service definition |

The installer sets `APP_URL=https://radar.shivam-tripathi.com` and the persistent database path in the installed server environment. It leaves your Google/Gmail credentials intact. The app's six-hour collection and mail schedulers run inside this single process; no separate cron job is needed. The first EC2 installation starts with a fresh database and collects live jobs.

At the end, the installer checks HTTPS locally with the domain name, even if public DNS is not ready. A successful check prints `Launchpad is serving HTTPS on TCP 443.`

## 5. DNS, network and Google callback

In the DNS provider for `shivam-tripathi.com`, set the A record named `radar` to the instance's public IPv4 address. Use an Elastic IP if you want the address to remain stable through stops/starts. Keep the separate ACM validation CNAME in place.

Allow inbound HTTPS TCP 443 in the EC2 security group for the intended users (typically `0.0.0.0/0` for this public app). Restrict SSH TCP 22 to your IP. This direct ACM setup does not require opening TCP 8000 or TCP 80. Open the site using `https://`; no HTTP redirect service is installed. Leave outbound access available for Google OAuth, Gmail TLS on TCP 465, DNS and employer feeds.

The Google OAuth web client must list this exact redirect URI:

```text
https://radar.shivam-tripathi.com/api/auth/google/callback
```

## 6. Check the result

On EC2:

```bash
sudo systemctl status launchpad --no-pager
curl -fsS --resolve radar.shivam-tripathi.com:443:127.0.0.1 https://radar.shivam-tripathi.com/api/health
```

On the Mac, after DNS is ready:

```bash
curl -fsS https://radar.shivam-tripathi.com/api/health
```

The health endpoint should return `{"status":"ok"}`. Open `https://radar.shivam-tripathi.com`, test Google sign-in and a private bookmark, then test the master login from the credentials file on the Mac. New Google accounts have six-hourly job emails enabled and can adjust or disable them in their account settings.

For a failed startup, read the service logs on EC2:

```bash
sudo journalctl -u launchpad -n 80 --no-pager
```

To restart after editing the installed environment:

```bash
sudo nano /etc/launchpad/launchpad.env
sudo systemctl restart launchpad
```

## Updates, backups and renewed certificates

For code updates, pull the merged source, rebuild the frontend, then rerun the installer:

```bash
cd ~/junior-job-radar
git pull --ff-only origin main
npm-22 ci --prefix frontend
npm-22 run build --prefix frontend
sudo bash deploy/install-native.sh
```

 The installer stops the existing Launchpad service during updates and creates a database backup in `/var/lib/launchpad/backups` before replacing code. The persistent database is retained. Keep a protected backup outside the instance as well. The git-ignored `.env` in the EC2 checkout is the deployment source. If you edit `/etc/launchpad/launchpad.env` directly, synchronize the intended changes to that checkout `.env` before redeploying so they are retained.

ACM renewal does not install renewed files onto EC2 automatically. After exporting a renewed certificate and copying the new three exports into `~/launchpad-certs`, run on EC2:

```bash
sudo bash ~/junior-job-radar/deploy/install-tls.sh ~/launchpad-certs
sudo systemctl restart launchpad
```

Verify the live expiry after restarting:

```bash
openssl s_client -connect radar.shivam-tripathi.com:443 -servername radar.shivam-tripathi.com </dev/null 2>/dev/null | openssl x509 -noout -dates
```

Renewal export/deployment is a manual procedure in this setup; automatic ACM export requires separately configuring a restricted AWS instance role, the certificate ARN/region, and a renewal deployment job. Certificate renewal automation has not been installed by these scripts.

References: [AL2023 Node.js versions](https://docs.aws.amazon.com/linux/al2023/ug/nodejs.html), [AL2023 Python versions](https://docs.aws.amazon.com/linux/al2023/ug/python.html), [Uvicorn HTTPS options](https://uvicorn.dev/settings/), [systemd capabilities and execution settings](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html), [ACM exportable certificates](https://docs.aws.amazon.com/acm/latest/userguide/acm-exportable-certificates.html).


## Optional: deploy a frontend built on the Mac

If you prefer to build away from the small EC2 instance, `scripts/package_native.py` builds React locally and packages the backend, pinned requirements, built frontend and deployment scripts into `dist/launchpad-native.tar.gz`. It excludes credentials, certificates and data. Extract that archive into a private directory on EC2, create `.env` there with `cat` as above, then run the included `deploy/install-native.sh`. The GitHub workflow above is the selected default.
