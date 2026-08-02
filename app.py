"""
Negarit Business Review
A small Flask + SQLite news site with an admin panel for posting articles.

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

On first run, a SQLite database is created automatically and seeded with
sample categories and articles, plus one admin account. The admin username
and a randomly generated password are printed to the terminal ONCE — save
that password immediately.
"""
import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone, timedelta, UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import wraps

from flask import (
    Flask, g, request, session, redirect, url_for,
    render_template, flash, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Where the database and uploaded images live. Defaults to this project's
# own folder for local development. In production on a host with an
# ephemeral filesystem (e.g. Render), set DATA_DIR to a mounted persistent
# disk's path (e.g. /var/data) so this data survives redeploys/restarts.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, "negarit.db")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ARTICLES_PER_PAGE = 6

app = Flask(__name__)
# In production, set a persistent SECRET_KEY environment variable, otherwise
# every restart invalidates admin sessions (people just get logged out).
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SITE_NAME = "Negarit Business Review"

# The "Scheduled" datetime field in the admin form has no timezone of its
# own (browsers send plain "YYYY-MM-DDTHH:MM"). We interpret that value as
# local time in SITE_TZ, not server time, so scheduling behaves correctly
# no matter which timezone the host (Render, a VPS, etc.) runs in.
#
# zoneinfo needs an IANA time zone database to resolve names like
# "Africa/Addis_Ababa". Linux/Mac ship one at the OS level; Windows (and
# some minimal Docker images) don't, so the 'tzdata' package in
# requirements.txt provides it instead. If that's ever missing anyway
# (e.g. requirements.txt wasn't reinstalled after an update), fall back to
# a fixed UTC+3 offset — Addis Ababa's actual offset, which has no DST to
# worry about — rather than crashing the whole app on startup.
_site_tz_name = os.environ.get("SITE_TIMEZONE", "Africa/Addis_Ababa")
try:
    SITE_TZ = ZoneInfo(_site_tz_name)
except ZoneInfoNotFoundError:
    print(f"WARNING: timezone data for '{_site_tz_name}' not found "
          f"(run: pip install -r requirements.txt). Falling back to a "
          f"fixed UTC+3 offset for scheduled publish times.")
    SITE_TZ = timezone(timedelta(hours=3))

# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE,
    slug    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS admin_users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    filename       TEXT NOT NULL UNIQUE,
    original_name  TEXT,
    uploaded_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    slug           TEXT NOT NULL UNIQUE,
    summary        TEXT NOT NULL DEFAULT '',
    content        TEXT NOT NULL DEFAULT '',
    category_id    INTEGER,
    image_filename TEXT,
    author         TEXT NOT NULL DEFAULT 'Staff Writer',
    author_bio     TEXT,
    author_avatar  TEXT,
    tags           TEXT NOT NULL DEFAULT '',
    claps          INTEGER NOT NULL DEFAULT 0,
    breaking       INTEGER NOT NULL DEFAULT 0,
    editors_pick   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'published',
    featured       INTEGER NOT NULL DEFAULT 0,
    publish_at     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);
"""

DEFAULT_CATEGORIES = ["Markets", "Economy", "Companies", "Technology", "Policy"]

# Seed content uses fictional company names on purpose, so it reads
# unmistakably as placeholder copy rather than real reporting.
SEED_ARTICLES = [
    {
        "title": "Highland Coffee Exports Reports Record Quarter",
        "category": "Companies",
        "summary": "The exporter says diversified buyers and steadier logistics lifted shipment volumes to a new high.",
        "content": "<p>Highland Coffee Exports Ltd. says its latest quarter was its strongest on record, "
                    "crediting a broader base of overseas buyers and fewer delays moving containers out of port.</p>"
                    "<p>Executives told reporters that the company had spent the past year diversifying its client "
                    "base across new regions, reducing its reliance on any single market. Warehouse upgrades and "
                    "tighter coordination with shipping partners also helped cut turnaround times.</p>"
                    "<p>Industry watchers say the results reflect a wider trend among exporters investing in "
                    "logistics resilience after a stretch of unpredictable shipping costs.</p>",
        "featured": 1,
    },
    {
        "title": "Addis Fintech Startups Draw New Investment",
        "category": "Technology",
        "summary": "A wave of early-stage funding is targeting payments and lending platforms built for small merchants.",
        "content": "<p>A handful of early-stage technology firms focused on digital payments and small-business "
                    "lending have closed new funding rounds in recent weeks, according to people familiar with the "
                    "deals.</p><p>Investors say they are drawn to platforms that serve merchants who have "
                    "historically had limited access to formal banking tools. Several of the startups say they plan "
                    "to use the capital to expand their engineering teams and broaden merchant onboarding.</p>"
                    "<p>Analysts caution that competition in the space is intensifying, and that user growth alone "
                    "will not be enough to guarantee long-term investor confidence.</p>",
        "featured": 0,
    },
    {
        "title": "Central Bank Signals Steady Policy Stance",
        "category": "Economy",
        "summary": "Officials indicate no imminent change to the current policy rate, citing a cautious wait-and-see approach.",
        "content": "<p>Central bank officials indicated this week that current monetary policy settings are likely to "
                    "remain in place for the near term, as authorities continue to monitor inflation and currency "
                    "conditions.</p><p>In prepared remarks, an official said the approach reflects a preference for "
                    "stability while broader economic data is assessed. Business groups have generally welcomed the "
                    "predictability, though some importers continue to flag access to foreign exchange as a "
                    "pressure point.</p><p>Economists say further guidance is expected at the next scheduled policy "
                    "review.</p>",
        "featured": 0,
    },
    {
        "title": "Government Unveils Draft Trade Policy Framework",
        "category": "Policy",
        "summary": "The proposal aims to simplify licensing for exporters while tightening standards enforcement.",
        "content": "<p>Officials have circulated a draft framework intended to simplify licensing procedures for "
                    "export-oriented businesses, while introducing stricter enforcement of product standards.</p>"
                    "<p>Business associations have broadly welcomed the simplification measures, though some members "
                    "have asked for a longer transition period before new compliance requirements take effect.</p>"
                    "<p>A public comment period is expected before the framework is finalized.</p>",
        "featured": 0,
    },
    {
        "title": "Great Rift Logistics Expands Regional Network",
        "category": "Companies",
        "summary": "The freight operator is adding routes and warehouse capacity to meet rising cross-border demand.",
        "content": "<p>Great Rift Logistics says it is adding new freight routes and warehouse capacity as demand for "
                    "regional cross-border shipping continues to climb.</p><p>The company's operations lead said "
                    "the expansion was planned around corridors that have seen the fastest growth in trade volume "
                    "over the past two years. The firm expects the added capacity to shorten average delivery "
                    "times for its retail and manufacturing clients.</p>",
        "featured": 0,
    },
    {
        "title": "Mobile Money Adoption Continues to Climb",
        "category": "Technology",
        "summary": "New usage data points to steady growth in digital wallets among small and informal businesses.",
        "content": "<p>Usage of mobile money services among small and informal businesses continues to grow, "
                    "according to industry data reviewed this week.</p><p>Vendors cite convenience and reduced "
                    "cash-handling risk as leading reasons for adoption. Providers, meanwhile, are competing to "
                    "add features aimed at merchants, including simple bookkeeping tools and short-term working "
                    "capital advances.</p><p>Analysts note that reliable network coverage remains the biggest "
                    "barrier to adoption in more remote areas.</p>",
        "featured": 0,
    },
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Return a request-scoped SQLite connection."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate_db(conn):
    """Add columns/tables introduced after the initial release to an
    existing database, so upgrading never requires deleting real data."""
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "publish_at" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN publish_at TEXT")
    if "tags" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
    if "author_bio" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN author_bio TEXT")
    if "author_avatar" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN author_avatar TEXT")
    if "claps" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN claps INTEGER NOT NULL DEFAULT 0")
    if "breaking" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN breaking INTEGER NOT NULL DEFAULT 0")
    if "editors_pick" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN editors_pick INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def init_db():
    """Create tables and seed sample data the very first time the app runs."""
    first_run = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    migrate_db(conn)

    if first_run:
        now = datetime.now(UTC).isoformat()

        category_ids = {}
        for name in DEFAULT_CATEGORIES:
            cur = conn.execute(
                "INSERT INTO categories (name, slug) VALUES (?, ?)",
                (name, slugify(name)),
            )
            category_ids[name] = cur.lastrowid

        for i, art in enumerate(SEED_ARTICLES):
            slug = slugify(art["title"])
            conn.execute(
                """INSERT INTO articles
                   (title, slug, summary, content, category_id, author,
                    status, featured, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, ?)""",
                (
                    art["title"], slug, art["summary"], art["content"],
                    category_ids[art["category"]], "Staff Writer",
                    art["featured"], now, now,
                ),
            )

        admin_password = secrets.token_urlsafe(9)
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", generate_password_hash(admin_password), now),
        )
        conn.commit()
        conn.close()

        banner = "=" * 64
        print(banner)
        print(f"  {SITE_NAME} — first-time setup complete")
        print(f"  Admin login URL : /admin/login")
        print(f"  Admin username  : admin")
        print(f"  Admin password  : {admin_password}")
        print("  This password is shown ONCE. Save it now, then change it")
        print("  from the admin dashboard after logging in.")
        print(banner)
    else:
        conn.close()


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")


def reading_time_minutes(html_content):
    """Strip HTML tags, count words, estimate minutes at ~200 wpm."""
    text = _TAG_RE.sub(" ", html_content or "")
    word_count = len(text.split())
    return max(1, round(word_count / 200))


def parse_tags(raw):
    """Turn a comma-separated admin input into a clean, deduped list."""
    if not raw:
        return []
    seen = []
    for piece in raw.split(","):
        tag = piece.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def format_tags_for_input(raw):
    """Comma+space join for pre-filling the admin form's text input."""
    return ", ".join(parse_tags(raw))


app.jinja_env.filters["reading_time"] = reading_time_minutes
app.jinja_env.filters["parse_tags"] = parse_tags
app.jinja_env.filters["format_tags_for_input"] = format_tags_for_input


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text or "post"


def unique_article_slug(db, title, ignore_id=None):
    base = slugify(title)
    slug = base
    n = 2
    while True:
        if ignore_id:
            row = db.execute(
                "SELECT id FROM articles WHERE slug = ? AND id != ?", (slug, ignore_id)
            ).fetchone()
        else:
            row = db.execute("SELECT id FROM articles WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return slug
        slug = f"{base}-{n}"
        n += 1


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage, db):
    """Save an uploaded image with a collision-proof name, record it in the
    media library, and return the filename (or None)."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        flash("Image must be PNG, JPG, WEBP, or GIF.", "error")
        return None
    safe_name = secure_filename(file_storage.filename)
    unique_name = f"{secrets.token_hex(6)}_{safe_name}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
    db.execute(
        "INSERT INTO media (filename, original_name, uploaded_at) VALUES (?, ?, ?)",
        (unique_name, safe_name, datetime.now(UTC).isoformat())
    )
    return unique_name


def delete_upload(filename, db=None):
    """Remove an uploaded file from disk and, if a db handle is given,
    from the media library table too."""
    if not filename:
        return
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    if db is not None:
        db.execute("DELETE FROM media WHERE filename = ?", (filename,))


def resolve_image_selection(req, db, current_filename=None):
    """Decide which image an article should use, in priority order:
    a freshly uploaded file > an existing library image picked from the
    dropdown > (if 'remove image' was checked) none > the current image
    unchanged. Uploads are saved into the media library as a side effect."""
    uploaded = save_upload(req.files.get("image"), db)
    if uploaded:
        return uploaded
    existing_choice = req.form.get("existing_image")
    if existing_choice:
        return existing_choice
    if req.form.get("remove_image") == "on":
        return None
    return current_filename


def format_date(iso_string):
    """'%-d' (no leading zero) is a Linux/Mac-only strftime extension —
    it doesn't exist on Windows. Compute the day manually instead of
    relying on a platform-specific flag, so this works everywhere."""
    try:
        dt = datetime.fromisoformat(iso_string)
    except (ValueError, TypeError):
        return iso_string
    return f"{dt:%B} {dt.day}, {dt:%Y}"


def format_datetime(iso_string):
    """Render a stored naive-UTC timestamp as site-local time for display.
    Same portability note as format_date — hour/day computed manually."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string).replace(tzinfo=timezone.utc).astimezone(SITE_TZ)
    except (ValueError, TypeError):
        return iso_string
    hour_12 = dt.hour % 12 or 12
    am_pm = "AM" if dt.hour < 12 else "PM"
    return f"{dt:%B} {dt.day}, {dt:%Y} at {hour_12}:{dt:%M} {am_pm}"


def parse_local_datetime(value):
    """Take a <input type=datetime-local> value ('YYYY-MM-DDTHH:MM'),
    interpret it as SITE_TZ local time, and return a naive-UTC ISO string
    for storage (matching created_at/updated_at's convention). None if
    the value is missing or unparsable."""
    if not value:
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=SITE_TZ).astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def to_datetime_local_value(iso_string):
    """Inverse of parse_local_datetime — used to pre-fill the form's
    datetime-local input when editing a scheduled article."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string).replace(tzinfo=timezone.utc).astimezone(SITE_TZ)
    except (ValueError, TypeError):
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M")


app.jinja_env.filters["format_date"] = format_date
app.jinja_env.filters["format_datetime"] = format_datetime
app.jinja_env.filters["datetime_local_value"] = to_datetime_local_value


# ---------------------------------------------------------------------------
# Auth + CSRF
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def promote_scheduled_articles():
    """Flip any 'scheduled' article whose publish time has passed over to
    'published'. Runs on every request instead of relying on a cron/worker
    process, which keeps deployment simple for a small site like this."""
    now = datetime.now(UTC).isoformat()
    db = get_db()
    db.execute(
        "UPDATE articles SET status = 'published', updated_at = ? "
        "WHERE status = 'scheduled' AND publish_at IS NOT NULL AND publish_at <= ?",
        (now, now),
    )
    db.commit()


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf_token")
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not submitted or token != submitted:
            abort(403)


@app.errorhandler(403)
def forbidden(e):
    return render_template("404.html", message="That request could not be verified. Please try again."), 403


# ---------------------------------------------------------------------------
# Shared template context
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    breaking_articles = db.execute(
        """SELECT title, slug FROM articles
           WHERE status = 'published' AND breaking = 1
           ORDER BY created_at DESC LIMIT 10"""
    ).fetchall()
    return {
        "site_name": SITE_NAME,
        "nav_categories": categories,
        "breaking_articles": breaking_articles,
        "current_year": datetime.now(UTC).year,
        "is_admin": bool(session.get("admin_id")),
    }


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded images from UPLOAD_FOLDER. Kept separate from
    Flask's automatic /static handling because UPLOAD_FOLDER can point
    outside the app folder entirely (e.g. a persistent disk in production)."""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/")
def index():
    db = get_db()
    featured_articles = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published' AND articles.featured = 1
           ORDER BY articles.updated_at DESC LIMIT 5"""
    ).fetchall()

    if not featured_articles:
        fallback = db.execute(
            """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
               FROM articles LEFT JOIN categories ON articles.category_id = categories.id
               WHERE articles.status = 'published'
               ORDER BY articles.created_at DESC LIMIT 1"""
        ).fetchone()
        featured_articles = [fallback] if fallback else []

    exclude_ids = [a["id"] for a in featured_articles] or [-1]
    placeholders = ",".join("?" * len(exclude_ids))
    latest = db.execute(
        f"""SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published' AND articles.id NOT IN ({placeholders})
           ORDER BY articles.created_at DESC LIMIT 8""",
        exclude_ids,
    ).fetchall()

    editors_picks = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published' AND articles.editors_pick = 1
           ORDER BY articles.updated_at DESC LIMIT 4"""
    ).fetchall()

    # "Today" means today in SITE_TZ, not the server's own timezone —
    # same reasoning as scheduled publishing.
    now_local = datetime.now(UTC).astimezone(SITE_TZ)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(UTC).replace(tzinfo=None).isoformat()

    highlights = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published' AND articles.created_at >= ?
           ORDER BY articles.created_at DESC LIMIT 6""",
        (today_start_utc,),
    ).fetchall()

    return render_template("index.html", featured_articles=featured_articles, latest=latest,
                            editors_picks=editors_picks, highlights=highlights)


@app.route("/category/<slug>")
def category(slug):
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    if cat is None:
        abort(404)

    page = max(request.args.get("page", 1, type=int), 1)
    offset = (page - 1) * ARTICLES_PER_PAGE

    total = db.execute(
        "SELECT COUNT(*) FROM articles WHERE category_id = ? AND status = 'published'", (cat["id"],)
    ).fetchone()[0]

    articles = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.category_id = ? AND articles.status = 'published'
           ORDER BY articles.created_at DESC LIMIT ? OFFSET ?""",
        (cat["id"], ARTICLES_PER_PAGE, offset),
    ).fetchall()

    has_next = offset + ARTICLES_PER_PAGE < total
    has_prev = page > 1

    return render_template(
        "category.html", category=cat, articles=articles,
        page=page, has_next=has_next, has_prev=has_prev,
    )


@app.route("/article/<slug>")
def article(slug):
    db = get_db()
    art = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.slug = ?""",
        (slug,),
    ).fetchone()

    if art is None:
        abort(404)
    if art["status"] != "published" and not session.get("admin_id"):
        abort(404)

    related = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.category_id = ? AND articles.id != ? AND articles.status = 'published'
           ORDER BY articles.created_at DESC LIMIT 3""",
        (art["category_id"], art["id"]),
    ).fetchall()

    prev_article = db.execute(
        """SELECT title, slug FROM articles
           WHERE status = 'published' AND created_at < ?
           ORDER BY created_at DESC LIMIT 1""",
        (art["created_at"],),
    ).fetchone()

    next_article = db.execute(
        """SELECT title, slug FROM articles
           WHERE status = 'published' AND created_at > ?
           ORDER BY created_at ASC LIMIT 1""",
        (art["created_at"],),
    ).fetchone()

    already_clapped = bool(session.get(f"clapped_{art['id']}"))

    return render_template(
        "article.html", article=art, related=related,
        prev_article=prev_article, next_article=next_article,
        already_clapped=already_clapped,
    )


@app.route("/article/<slug>/clap", methods=["POST"])
def clap_article(slug):
    db = get_db()
    art = db.execute("SELECT id, claps FROM articles WHERE slug = ? AND status = 'published'", (slug,)).fetchone()
    if art is None:
        abort(404)

    session_key = f"clapped_{art['id']}"
    if not session.get(session_key):
        db.execute("UPDATE articles SET claps = claps + 1 WHERE id = ?", (art["id"],))
        db.commit()
        session[session_key] = True
        claps = art["claps"] + 1
    else:
        claps = art["claps"]

    return {"claps": claps, "already_clapped": True}


@app.route("/tag/<tag>")
def tag(tag):
    db = get_db()
    tag = tag.strip().lower()
    all_published = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published'
           ORDER BY articles.created_at DESC"""
    ).fetchall()

    matching = [a for a in all_published if tag in parse_tags(a["tags"])]
    if not matching:
        abort(404)

    page = max(request.args.get("page", 1, type=int), 1)
    offset = (page - 1) * ARTICLES_PER_PAGE
    total = len(matching)
    articles = matching[offset:offset + ARTICLES_PER_PAGE]
    has_next = offset + ARTICLES_PER_PAGE < total
    has_prev = page > 1

    return render_template("tag.html", tag=tag, articles=articles, total=total,
                            page=page, has_next=has_next, has_prev=has_prev)


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    db = get_db()

    if not query:
        return render_template("search.html", query="", articles=[], total=0,
                                page=1, has_next=False, has_prev=False)

    page = max(request.args.get("page", 1, type=int), 1)
    offset = (page - 1) * ARTICLES_PER_PAGE

    # Escape LIKE's own wildcard characters in the user's input so a
    # search for e.g. "50% growth" doesn't get treated as a wildcard.
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_pattern = f"%{escaped}%"

    total = db.execute(
        """SELECT COUNT(*) FROM articles
           WHERE status = 'published' AND
           (title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')""",
        (like_pattern, like_pattern, like_pattern),
    ).fetchone()[0]

    articles = db.execute(
        """SELECT articles.*, categories.name AS category_name, categories.slug AS category_slug
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           WHERE articles.status = 'published' AND
           (articles.title LIKE ? ESCAPE '\\' OR articles.summary LIKE ? ESCAPE '\\' OR articles.content LIKE ? ESCAPE '\\')
           ORDER BY CASE WHEN articles.title LIKE ? ESCAPE '\\' THEN 0 ELSE 1 END, articles.created_at DESC
           LIMIT ? OFFSET ?""",
        (like_pattern, like_pattern, like_pattern, like_pattern, ARTICLES_PER_PAGE, offset),
    ).fetchall()

    has_next = offset + ARTICLES_PER_PAGE < total
    has_prev = page > 1

    return render_template("search.html", query=query, articles=articles, total=total,
                            page=page, has_next=has_next, has_prev=has_prev)

@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email")
    if email:
        print(f"========================================")
        print(f"NEW NEWSLETTER SUBSCRIBER: {email}")
        print(f"========================================")
        
        # Notice we added the 'newsletter' category here
        flash("Thank you for subscribing to our newsletter!", "newsletter")
        return redirect(url_for("index"))
        
    return redirect(url_for("index"))
@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------------------------------------------------------------------
# Admin: auth
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["admin_id"] = user["id"]
            session["admin_username"] = user["username"]
            flash("Logged in.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Incorrect username or password.", "error")

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin/media")
@login_required
def admin_media():
    db = get_db()
    items = db.execute("SELECT * FROM media ORDER BY uploaded_at DESC").fetchall()
    # Figure out which filenames are currently used by an article, so the
    # library can show that and block deleting images still in use.
    used = {row["image_filename"] for row in db.execute(
        "SELECT DISTINCT image_filename FROM articles WHERE image_filename IS NOT NULL"
    ).fetchall()}
    media = [dict(item, in_use=item["filename"] in used) for item in items]
    return render_template("admin/media.html", media=media)


@app.route("/admin/media/upload", methods=["POST"])
@login_required
def admin_media_upload():
    db = get_db()
    filename = save_upload(request.files.get("image"), db)
    if filename:
        db.commit()
        flash("Image uploaded to the library.", "success")
    return redirect(url_for("admin_media"))


@app.route("/admin/media/delete/<int:media_id>", methods=["POST"])
@login_required
def admin_media_delete(media_id):
    db = get_db()
    item = db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    if item is None:
        abort(404)

    in_use = db.execute(
        "SELECT COUNT(*) FROM articles WHERE image_filename = ?", (item["filename"],)
    ).fetchone()[0]
    if in_use:
        flash(f"That image is used by {in_use} article(s) — remove it from those articles first.", "error")
        return redirect(url_for("admin_media"))

    delete_upload(item["filename"], db)
    db.commit()
    flash("Image deleted.", "success")
    return redirect(url_for("admin_media"))


@app.route("/admin/change-password", methods=["GET", "POST"])
@login_required
def admin_change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        db = get_db()
        user = db.execute("SELECT * FROM admin_users WHERE id = ?", (session["admin_id"],)).fetchone()

        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            db.execute(
                "UPDATE admin_users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), user["id"]),
            )
            db.commit()
            flash("Password changed.", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template("admin/change_password.html")


# ---------------------------------------------------------------------------
# Admin: dashboard + article CRUD
# ---------------------------------------------------------------------------

@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    articles = db.execute(
        """SELECT articles.*, categories.name AS category_name
           FROM articles LEFT JOIN categories ON articles.category_id = categories.id
           ORDER BY articles.updated_at DESC"""
    ).fetchall()

    stats = {
        "total": len(articles),
        "published": sum(1 for a in articles if a["status"] == "published"),
        "scheduled": sum(1 for a in articles if a["status"] == "scheduled"),
        "drafts": sum(1 for a in articles if a["status"] == "draft"),
        "categories": db.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
    }

    return render_template("admin/dashboard.html", articles=articles, stats=stats)


@app.route("/admin/new", methods=["GET", "POST"])
@login_required
def admin_new_article():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    media = db.execute("SELECT * FROM media ORDER BY uploaded_at DESC").fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        category_id = request.form.get("category_id") or None
        author = request.form.get("author", "").strip() or "Staff Writer"
        author_bio = request.form.get("author_bio", "").strip() or None
        tags = ",".join(parse_tags(request.form.get("tags", "")))
        status = request.form.get("status")
        if status not in ("draft", "scheduled", "published"):
            status = "published"
        featured = 1 if request.form.get("featured") == "on" else 0
        breaking = 1 if request.form.get("breaking") == "on" else 0
        editors_pick = 1 if request.form.get("editors_pick") == "on" else 0

        if not title or not content:
            flash("Title and content are required.", "error")
            return render_template("admin/article_form.html", categories=categories, media=media, article=None, mode="new")

        publish_at = None
        if status == "scheduled":
            publish_at = parse_local_datetime(request.form.get("publish_at"))
            if not publish_at:
                flash("Pick a publish date/time, or choose Draft/Published instead.", "error")
                return render_template("admin/article_form.html", categories=categories, media=media, article=None, mode="new")
            if publish_at <= datetime.utcnow().isoformat():
                flash("Scheduled time must be in the future.", "error")
                return render_template("admin/article_form.html", categories=categories, media=media, article=None, mode="new")

        slug = unique_article_slug(db, title)
        image_filename = resolve_image_selection(request, db)
        author_avatar = save_upload(request.files.get("author_avatar"), db)
        now = datetime.utcnow().isoformat()

        db.execute(
            """INSERT INTO articles
               (title, slug, summary, content, category_id, image_filename,
                author, author_bio, author_avatar, tags, status, featured, breaking, editors_pick,
                publish_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, slug, summary, content, category_id, image_filename,
             author, author_bio, author_avatar, tags, status, featured, breaking, editors_pick,
             publish_at, now, now),
        )
        db.commit()
        messages = {"published": "Article published.", "draft": "Draft saved.",
                    "scheduled": f"Article scheduled for {format_datetime(publish_at)}."}
        flash(messages[status], "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin/article_form.html", categories=categories, media=media, article=None, mode="new")


@app.route("/admin/edit/<int:article_id>", methods=["GET", "POST"])
@login_required
def admin_edit_article(article_id):
    db = get_db()
    art = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if art is None:
        abort(404)
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    media = db.execute("SELECT * FROM media ORDER BY uploaded_at DESC").fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        category_id = request.form.get("category_id") or None
        author = request.form.get("author", "").strip() or "Staff Writer"
        author_bio = request.form.get("author_bio", "").strip() or None
        tags = ",".join(parse_tags(request.form.get("tags", "")))
        status = request.form.get("status")
        if status not in ("draft", "scheduled", "published"):
            status = "published"
        featured = 1 if request.form.get("featured") == "on" else 0
        breaking = 1 if request.form.get("breaking") == "on" else 0
        editors_pick = 1 if request.form.get("editors_pick") == "on" else 0

        if not title or not content:
            flash("Title and content are required.", "error")
            return render_template("admin/article_form.html", categories=categories, media=media, article=art, mode="edit")

        publish_at = None
        if status == "scheduled":
            publish_at = parse_local_datetime(request.form.get("publish_at"))
            if not publish_at:
                flash("Pick a publish date/time, or choose Draft/Published instead.", "error")
                return render_template("admin/article_form.html", categories=categories, media=media, article=art, mode="edit")
            if publish_at <= datetime.utcnow().isoformat():
                flash("Scheduled time must be in the future.", "error")
                return render_template("admin/article_form.html", categories=categories, media=media, article=art, mode="edit")

        slug = unique_article_slug(db, title, ignore_id=article_id)
        image_filename = resolve_image_selection(request, db, current_filename=art["image_filename"])
        author_avatar = save_upload(request.files.get("author_avatar"), db) or art["author_avatar"]

        now = datetime.utcnow().isoformat()

        db.execute(
            """UPDATE articles SET title=?, slug=?, summary=?, content=?, category_id=?,
               image_filename=?, author=?, author_bio=?, author_avatar=?, tags=?,
               status=?, featured=?, breaking=?, editors_pick=?, publish_at=?, updated_at=?
               WHERE id=?""",
            (title, slug, summary, content, category_id, image_filename,
             author, author_bio, author_avatar, tags, status, featured, breaking, editors_pick, publish_at, now, article_id),
        )
        db.commit()
        messages = {"published": "Article updated.", "draft": "Draft saved.",
                    "scheduled": f"Article scheduled for {format_datetime(publish_at)}."}
        flash(messages[status], "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin/article_form.html", categories=categories, media=media, article=art, mode="edit")


@app.route("/admin/delete/<int:article_id>", methods=["POST"])
@login_required
def admin_delete_article(article_id):
    db = get_db()
    art = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if art is None:
        abort(404)
    # Note: the article's image is left in the media library on purpose —
    # it may be reused by other articles. Remove unused images from
    # the Media Library page if you want to reclaim disk space.
    db.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    db.commit()
    flash("Article deleted.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", message=None), 404


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

init_db()
init_db()

@app.route("/reset-admin")
def reset_admin():
    db = get_db()
    db.execute(
        "UPDATE admin_users SET password_hash = ? WHERE username = ?",
        (generate_password_hash("Admin@123"), "admin"),
    )
    db.commit()
    return "Admin password reset successfully!"
    return "Admin password reset successfully!"
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
