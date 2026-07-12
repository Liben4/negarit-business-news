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
**Sprint 4 — Production readiness:** not started (Render deploy, domain,
HTTPS, SEO, analytics).

## Project structure

```
negarit-business-news/
├── app.py                        # routes, DB helpers, auth, CRUD, scheduling
├── requirements.txt
├── Procfile                      # for Render/Railway/Heroku-style hosts
├── static/
│   ├── css/style.css
│   └── uploads/                  # images land here (auto-created)
├── templates/
│   ├── base.html                  # masthead, nav, admin subnav, footer
│   ├── index.html                 # homepage (featured + latest)
│   ├── category.html              # section listing, paginated
│   ├── article.html                # single article + related stories
│   ├── about.html / contact.html   # static pages — edit the placeholder copy
│   ├── 404.html
│   └── admin/                      # login, dashboard, article form,
│                                    # media library, change password
└── negarit.db                      # created automatically on first run (not in git)
```

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

## Customizing

- **Colors/fonts**: all design tokens are CSS variables at the top of
  `static/css/style.css` (`:root { --ink-navy, --brand-blue,
  --herald-orange, ... }`). Change them there and the whole site updates.
- **About/Contact copy**: currently placeholder text — edit directly in
  `templates/about.html` and `templates/contact.html`.
- **Site name**: `SITE_NAME` near the top of `app.py`.

## Deploying

Any host that can run a Python/WSGI app works. Two common paths (Sprint 4
will walk through the Render path specifically when we get there):

### Option A — PaaS (Render, Railway, PythonAnywhere)
The included `Procfile` (`web: gunicorn app:app`) is ready for
Render/Railway-style platforms: push the repo to GitHub, connect it, set
the `SECRET_KEY` (and optionally `SITE_TIMEZONE`) environment variable, and
deploy. PythonAnywhere doesn't use a Procfile — instead point its "Manual
configuration (WSGI)" setup at `app.app` following their Flask quickstart.

### Option B — Your own VPS (Ubuntu + gunicorn + nginx)
```bash
# on the server
sudo apt update && sudo apt install python3-venv nginx
cd /var/www && git clone <your-repo-url> negarit-business-news
cd negarit-business-news
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# run with gunicorn (add a systemd service to keep it alive on reboot)
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```
Then point nginx at `127.0.0.1:8000` as a reverse proxy, and get an SSL
certificate (e.g. `certbot --nginx`) so the admin login isn't sent over
plain HTTP.

### Before going live, either way
1. Set a persistent **`SECRET_KEY`** (see Configuration above).
   ```bash
   export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
   ```
2. Log in and change the default admin password if you haven't already.
3. Serve over **HTTPS** — the admin login form sends a password over the
   wire, so plain HTTP exposes it.
4. Back up `negarit.db` periodically — it's the entire database (one file,
   easy to copy/cron) — and `static/uploads/` for the media library.
5. Don't commit `negarit.db` or `static/uploads/*` to git (already handled
   by `.gitignore`) — each environment should generate its own DB and admin
   password rather than sharing one.

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
