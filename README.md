# Negarit Business News

A Flask + SQLite news site with an admin panel for posting articles.
Server-rendered HTML/CSS (Jinja2 templates), no JS framework, single SQLite
file for storage.

## Project status

**Sprint 1 — Admin fixes:** done (login, session management, logout, password change).
**Sprint 2 — CMS:** done (dashboard stats, full article CRUD, scheduled
publishing, drafts/published, image upload + media library).
**Sprint 3 — Site enhancements:** not started (featured section is already
in from Sprint 2's base; ticker, search, most-read, newsletter signup still
open).
**Sprint 4 — Production readiness:** in progress (Render deploy guide below,
including the persistent-storage setup it needs; domain/HTTPS covered in
the same walkthrough; SEO and analytics still open).

## Project structure

```
negarit-business-news/
├── app.py                        # routes, DB helpers, auth, CRUD, scheduling
├── requirements.txt
├── Procfile                      # for Render/Railway/Heroku-style hosts
├── static/css/style.css
├── uploads/                       # images land here (auto-created; gitignored)
├── negarit.db                     # created automatically on first run (not in git)
├── templates/
│   ├── base.html                  # masthead, nav, admin subnav, footer
│   ├── index.html                 # homepage (featured + latest)
│   ├── category.html              # section listing, paginated
│   ├── article.html                # single article + related stories
│   ├── about.html / contact.html   # static pages — edit the placeholder copy
│   ├── 404.html
│   └── admin/                      # login, dashboard, article form,
│                                    # media library, change password
```

`DB_PATH` and `UPLOAD_FOLDER` both live under `DATA_DIR` (defaults to this
project folder). In production on a host with an ephemeral filesystem,
point `DATA_DIR` at a persistent disk instead — see Deploying below.

## Run it locally

```bash
cd negarit-business-news
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**.

The **first time** you run it, `negarit.db` is created automatically and
seeded with 5 sections and 6 sample articles (fictional companies — replace
or delete them from the dashboard). The terminal will print something like:

```
============================================================
  Negarit Business News — first-time setup complete
  Admin login URL : /admin/login
  Admin username  : admin
  Admin password  : Xk9pQ2mZnR8
  This password is shown ONCE. Save it now, then change it
  from the admin dashboard after logging in.
============================================================
```

**Copy that password immediately** — it's random per install and only
printed once. Log in at `/admin/login`, and change it right away from
**Change Password** in the admin bar.

If you ever lose it and have terminal/DB access, you can reset it directly:

```bash
python3 -c "
import sqlite3
from werkzeug.security import generate_password_hash
conn = sqlite3.connect('negarit.db')
conn.execute('UPDATE admin_users SET password_hash=? WHERE username=?',
             (generate_password_hash('a-new-password'), 'admin'))
conn.commit()
"
```

If you already have a `negarit.db` from before this update, just run the
app — it adds the new columns/tables it needs automatically on startup, no
data loss.

## How content works

- **Sections** (Markets, Economy, Companies, Technology, Policy) are seeded
  once in `app.py` (`DEFAULT_CATEGORIES`). There's no "manage sections" admin
  screen yet — add/rename/remove rows in the `categories` table directly, or
  ask to have that screen built if you want it (would fit well in Sprint 3).
- **Articles** have a title, summary (used on cards), content, section,
  byline, optional image, and a status: **Published**, **Scheduled**, or
  **Draft**.
- **Draft** articles are only visible to you (while logged in) at their
  article URL, so you can preview before publishing.
- **Scheduled** articles go live automatically once their publish time
  passes — no need to come back and click publish. Under the hood, this is
  checked on each incoming request rather than a background cron job, which
  keeps hosting simple; the trade-off is an article won't flip to published
  until the *next* visit to the site after its time passes (in practice,
  within seconds on anything but a completely idle site). The time you pick
  is interpreted in the `SITE_TIMEZONE` (see below), not the server's clock.
- **Featured** marks the single article shown in the homepage hero. Marking
  a new one automatically un-features the previous one — only one at a time.
- **Media Library** (admin bar → Media Library) holds every uploaded image
  in one place. Upload there directly, or upload from the article form —
  either way it lands in the library and can be reused across articles.
  Deleting an article never deletes its image (it might be reused
  elsewhere); delete unused images from the library itself, where it's
  blocked if anything still references them.
- The content field accepts basic HTML (`<p>`, `<strong>`, `<em>`,
  `<a href="">`, `<h3>`) so you can format articles without a rich-text
  editor. It renders as-is, so keep the admin password private.

## Configuration

Set these as environment variables in production (a `.env` file works
locally too if you use `python-dotenv`, not included by default):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies. **Set this in production** — without it, a new random key is generated on every restart, which logs every admin session out each time the process restarts. | random per-process |
| `SITE_TIMEZONE` | Timezone used to interpret "Scheduled" publish times you type into the admin form. | `Africa/Addis_Ababa` |
| `DATA_DIR` | Folder holding `negarit.db` and `uploads/`. Point this at a persistent disk in production (see Deploying) — otherwise your data is wiped on every redeploy/restart. | this project's folder |

## Customizing

- **Colors/fonts**: all design tokens are CSS variables at the top of
  `static/css/style.css` (`:root { --ink-navy, --brand-blue,
  --herald-orange, ... }`). Change them there and the whole site updates.
- **About/Contact copy**: currently placeholder text — edit directly in
  `templates/about.html` and `templates/contact.html`.
- **Site name**: `SITE_NAME` near the top of `app.py`.

## Deploying (Render)

This section assumes Render specifically, since that's the target in the
Sprint 4 plan. **Read this before you deploy** — the persistence step
(step 4) isn't optional; skipping it means your articles and images get
wiped the first time the service redeploys or goes idle.

**Cost**: Render's free tier looks tempting but doesn't actually work for
this app — free web services spin down after 15 minutes idle, and Render
wipes the local filesystem (your database + uploaded images) on *every*
spin-down, not just on redeploys. Render's free PostgreSQL is a 30-day
trial, not a permanent free option, so it doesn't avoid the cost either —
it would just delay it while adding a real database migration. The
practical setup is a **Starter web service ($7/mo) + a small persistent
disk (~$0.25/mo for 1GB)** ≈ **$7.25/month total**, on Render's free Hobby
workspace tier (no extra per-seat fees for a solo project). Always-on, no
data loss, keeps this exact codebase.

### 1. Push the code to GitHub
Skip this if it's already there.
```bash
# from inside negarit-business-news/
git remote add origin <your-new-empty-github-repo-url>
git push -u origin main
```
(Create the empty repo on GitHub first — don't initialize it with a
README/license, since this folder already has its own git history.)

### 2. Create the Render Web Service
1. Sign up / log in at [render.com](https://render.com) and connect your GitHub account.
2. **New +** → **Web Service** → select the `negarit-business-news` repo.
3. Render should auto-detect Python. Set:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (this matches the included `Procfile`)
4. **Instance Type**: choose **Starter** ($7/mo) — not Free, per the cost note above.

### 3. Set environment variables
In the service's **Environment** tab, add:
| Key | Value |
|---|---|
| `SECRET_KEY` | a random string — generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `DATA_DIR` | `/var/data` |
| `SITE_TIMEZONE` | `Africa/Addis_Ababa` (optional — this is already the default) |

### 4. Add the persistent disk
Still on the service creation/settings page, under **Disks**:
- **Mount Path**: `/var/data` (must match `DATA_DIR` above exactly)
- **Size**: 1 GB is plenty to start (articles + a good number of images)

This is the step that actually prevents data loss — `DATA_DIR=/var/data`
without a disk mounted there does nothing.

### 5. Deploy and get your admin password
Click **Create Web Service**. Watch the **Logs** tab for the first-run
banner — it only prints once, so copy the password from there:
```
Admin login URL : /admin/login
Admin username  : admin
Admin password  : <random>
```
Your site is live at `https://your-service-name.onrender.com`. Log in and
change that password immediately from the admin bar.

### 6. Connect your custom domain
In the service's **Settings** → **Custom Domains**:
1. Click **Add Custom Domain**, enter your domain.
2. Render shows you a DNS record to add (an `A`/`ANAME` record for a root
   domain like `negarit.com`, or a `CNAME` for a subdomain like
   `www.negarit.com`) — add it at wherever you bought the domain
   (Namecheap, GoDaddy, Cloudflare, etc.).
3. Back in Render, click **Verify**. DNS can take a few minutes to
   propagate — if verification fails immediately, wait and retry.
4. Once verified, Render automatically issues a **free TLS certificate**
   for the domain — no separate HTTPS setup needed, and no cost.

### Redeploying after future changes
Render auto-deploys on every push to `main` by default. Your normal
feature-branch workflow (branch → test → merge to main) continues to work
exactly as before — merging to `main` is what triggers the live update.

### Alternative: your own VPS (Ubuntu + gunicorn + nginx)
If you'd rather not use Render at all:
```bash
sudo apt update && sudo apt install python3-venv nginx
cd /var/www && git clone <your-repo-url> negarit-business-news
cd negarit-business-news
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATA_DIR=/var/www/negarit-business-news   # or anywhere with disk space
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app   # add a systemd service to keep it alive on reboot
```
Point nginx at `127.0.0.1:8000` as a reverse proxy, then `certbot --nginx`
for a free SSL certificate. A VPS's disk is persistent by default, so
there's no Render-style disk-mounting step — just make sure `DATA_DIR`
points somewhere with actual disk space.

### Before going live, either way
1. Set a persistent **`SECRET_KEY`** (see Configuration above) — done in
   step 3 if you followed the Render walkthrough.
2. Log in and change the default admin password if you haven't already.
3. Confirm you're on **HTTPS** — the admin login form sends a password
   over the wire.
4. Back up `negarit.db` and `uploads/` periodically regardless of host —
   Render snapshots the persistent disk daily, but a second backup never hurts.

## Troubleshooting

**`ModuleNotFoundError: No module named 'tzdata'` / `ZoneInfoNotFoundError`
on Windows** — Windows has no OS-level IANA time zone database (Linux/Mac
do), which `zoneinfo` needs to resolve `SITE_TIMEZONE`. Fixed as of this
version via the `tzdata` package in `requirements.txt` — if you still hit
this, run `pip install -r requirements.txt` again (or `pip install
tzdata` directly) and restart the app.

## Development workflow

This repo now uses git, with one feature branch per change, merged into
`main` with `--no-ff` so each feature's history stays intact and revertable
as a unit:

```bash
git checkout -b feature/short-name
# ...make changes, test...
git commit -m "Add thing — short description of what and why"
git checkout main
git merge --no-ff feature/short-name
```

To roll back a feature that turns out to be broken: `git log --oneline
--graph` to find its merge commit, then `git revert -m 1 <merge-commit>`.

The local repo has no remote configured yet. To push it to your own GitHub:
```bash
git remote add origin <your-repo-url>
git push -u origin main
```

## Possible next steps

Sprint 3 (featured section is already done): breaking news ticker, search,
most-read articles (needs view tracking), newsletter signup (needs an email
provider — Mailchimp/ConvertKit/etc. — since sending real email isn't
configured here). Sprint 4: Render deployment, custom domain, HTTPS, SEO
(meta tags, sitemap.xml, robots.txt), Google Analytics/Search Console.
Also open: category management UI, a rich-text/WYSIWYG editor for article
content, image resizing on upload.
