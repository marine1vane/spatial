import hashlib
import hmac
import html
import os
import secrets
import sqlite3
import time
from http import cookies
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

DB_PATH = "spatial.db"
SESSION_COOKIE = "spatial_session"
SECRET_KEY = os.environ.get("SPATIAL_SECRET", "change-this-secret-in-production")

READING_TASKS = [
    ("Letter Explorer", "K", "Match uppercase and lowercase letters."),
    ("CVC Builder", "K-1", "Blend short vowel words into simple words."),
    ("Story Steps", "1-2", "Read short stories and sequence events."),
    ("Meaning Detectives", "2-3", "Use context clues to infer new vocabulary."),
]

MATH_TASKS = [
    ("Counting Garden", "K", "Count objects and compare quantities."),
    ("Addition Rockets", "1", "Practice addition facts within 20."),
    ("Number Bonds Lab", "1-2", "Break numbers into flexible parts."),
    ("Word Problem Quest", "2-3", "Solve one-step and two-step story problems."),
]

sessions = {}


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    conn.commit()
    conn.close()


def password_hash(password: str) -> str:
    return hashlib.sha256((SECRET_KEY + password).encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(password_hash(password), hashed)


def parse_post(environ):
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    body = environ["wsgi.input"].read(size).decode("utf-8")
    parsed = parse_qs(body)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def redirect(location, headers=None):
    out_headers = [("Location", location)]
    if headers:
        out_headers.extend(headers)
    return "302 Found", out_headers, b""


def html_page(title, content, user=None, notice=""):
    auth_links = (
        '<a href="/logout">Logout</a>'
        if user
        else '<a href="/login">Login</a><a href="/register">Register</a>'
    )
    notice_html = f'<p class="notice">{html.escape(notice)}</p>' if notice else ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>{html.escape(title)}</title>
  <link rel='stylesheet' href='/styles.css'>
</head>
<body>
<header>
  <h1>Spatial Academy</h1>
  <p>Starfall-style learning for Kindergarten and primary school</p>
  <nav>
    <a href='/'>Home</a>
    <a href='/tasks'>Learning Tasks</a>
    <a href='/forum'>Parent Forum</a>
    {auth_links}
  </nav>
</header>
<main>
  {notice_html}
  {content}
</main>
</body>
</html>
""".encode("utf-8")


def current_user(environ):
    raw = environ.get("HTTP_COOKIE", "")
    jar = cookies.SimpleCookie()
    jar.load(raw)
    sid = jar.get(SESSION_COOKIE)
    if not sid:
        return None
    uid = sessions.get(sid.value)
    if not uid:
        return None
    conn = db_conn()
    user = conn.execute("SELECT id,email FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return user


def require_user(environ):
    user = current_user(environ)
    if user is None:
        return None, redirect("/login?notice=Please+login+to+access+the+forum")
    return user, None


def home(environ):
    preview = "".join(
        [f"<li><strong>{html.escape(t)}</strong> ({g}) — {html.escape(d)}</li>" for t, g, d in READING_TASKS[:2]]
        + [f"<li><strong>{html.escape(t)}</strong> ({g}) — {html.escape(d)}</li>" for t, g, d in MATH_TASKS[:2]]
    )
    content = f"""
<section class='panel'>
  <h2>Safe learning adventures for early learners</h2>
  <p>Build reading and mathematics confidence through guided tasks and parent support.</p>
</section>
<section class='panel'>
  <h3>Featured Tasks</h3>
  <ul>{preview}</ul>
</section>
"""
    notice = parse_qs(environ.get("QUERY_STRING", "")).get("notice", [""])[0]
    return "200 OK", [("Content-Type", "text/html; charset=utf-8")], html_page("Spatial Academy", content, current_user(environ), notice)


def tasks_page(environ):
    reading = "".join([f"<li><strong>{html.escape(t)}</strong> ({g}) — {html.escape(d)}</li>" for t, g, d in READING_TASKS])
    math = "".join([f"<li><strong>{html.escape(t)}</strong> ({g}) — {html.escape(d)}</li>" for t, g, d in MATH_TASKS])
    content = f"""
<section class='panel columns'>
  <div><h2>Reading Tasks</h2><ul>{reading}</ul></div>
  <div><h2>Math Tasks</h2><ul>{math}</ul></div>
</section>
"""
    return "200 OK", [("Content-Type", "text/html; charset=utf-8")], html_page("Tasks", content, current_user(environ))


def register(environ):
    if environ["REQUEST_METHOD"] == "POST":
        data = parse_post(environ)
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()
        if not email or len(password) < 6:
            return redirect("/register?notice=Use+a+valid+email+and+6%2B+character+password")
        conn = db_conn()
        try:
            conn.execute(
                "INSERT INTO users (email,password_hash,created_at) VALUES (?,?,?)",
                (email, password_hash(password), int(time.time())),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return redirect("/register?notice=Email+already+registered")
        conn.close()
        return redirect("/login?notice=Registration+successful.+Please+login")

    notice = parse_qs(environ.get("QUERY_STRING", "")).get("notice", [""])[0]
    content = """
<section class='panel'>
  <h2>Create account</h2>
  <form method='post' action='/register'>
    <input name='email' type='email' placeholder='Email' required>
    <input name='password' type='password' placeholder='Password (6+ chars)' minlength='6' required>
    <button type='submit'>Register</button>
  </form>
</section>
"""
    return "200 OK", [("Content-Type", "text/html; charset=utf-8")], html_page("Register", content, current_user(environ), notice)


def login(environ):
    if environ["REQUEST_METHOD"] == "POST":
        data = parse_post(environ)
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        conn = db_conn()
        user = conn.execute("SELECT id,email,password_hash FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if not user or not verify_password(password, user["password_hash"]):
            return redirect("/login?notice=Invalid+email+or+password")
        sid = secrets.token_urlsafe(24)
        sessions[sid] = user["id"]
        ck = cookies.SimpleCookie()
        ck[SESSION_COOKIE] = sid
        ck[SESSION_COOKIE]["path"] = "/"
        ck[SESSION_COOKIE]["httponly"] = True
        return redirect("/?notice=Welcome+back", [("Set-Cookie", ck.output(header="").strip())])

    notice = parse_qs(environ.get("QUERY_STRING", "")).get("notice", [""])[0]
    content = """
<section class='panel'>
  <h2>Login</h2>
  <form method='post' action='/login'>
    <input name='email' type='email' placeholder='Email' required>
    <input name='password' type='password' placeholder='Password' required>
    <button type='submit'>Login</button>
  </form>
</section>
"""
    return "200 OK", [("Content-Type", "text/html; charset=utf-8")], html_page("Login", content, current_user(environ), notice)


def logout(environ):
    raw = environ.get("HTTP_COOKIE", "")
    jar = cookies.SimpleCookie()
    jar.load(raw)
    sid = jar.get(SESSION_COOKIE)
    if sid and sid.value in sessions:
        del sessions[sid.value]
    ck = cookies.SimpleCookie()
    ck[SESSION_COOKIE] = ""
    ck[SESSION_COOKIE]["path"] = "/"
    ck[SESSION_COOKIE]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return redirect("/?notice=Logged+out", [("Set-Cookie", ck.output(header="").strip())])


def forum(environ):
    user, auth_redirect = require_user(environ)
    if auth_redirect:
        return auth_redirect

    if environ["REQUEST_METHOD"] == "POST":
        data = parse_post(environ)
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()
        if not title or not content:
            return redirect("/forum?notice=Title+and+message+are+required")
        conn = db_conn()
        conn.execute(
            "INSERT INTO forum_posts (user_id,title,content,created_at) VALUES (?,?,?,?)",
            (user["id"], title, content, int(time.time())),
        )
        conn.commit()
        conn.close()
        return redirect("/forum?notice=Post+published")

    conn = db_conn()
    posts = conn.execute(
        """
        SELECT p.title, p.content, p.created_at, u.email
        FROM forum_posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC
        """
    ).fetchall()
    conn.close()
    posts_html = "".join(
        [
            f"<article class='post'><h4>{html.escape(p['title'])}</h4><p>{html.escape(p['content'])}</p><small>{html.escape(p['email'])}</small></article>"
            for p in posts
        ]
    ) or "<p>No parent discussions yet.</p>"
    notice = parse_qs(environ.get("QUERY_STRING", "")).get("notice", [""])[0]
    content = f"""
<section class='panel'>
  <h2>Parent Discussion Forum</h2>
  <form method='post' action='/forum'>
    <input name='title' type='text' placeholder='Post title' required>
    <textarea name='content' rows='4' placeholder='Message' required></textarea>
    <button type='submit'>Publish</button>
  </form>
</section>
<section class='panel'>
  <h3>Recent Discussions</h3>
  {posts_html}
</section>
"""
    return "200 OK", [("Content-Type", "text/html; charset=utf-8")], html_page("Forum", content, user, notice)


def serve_css():
    with open("styles.css", "rb") as f:
        return "200 OK", [("Content-Type", "text/css; charset=utf-8")], f.read()


def not_found(environ):
    content = "<section class='panel'><h2>Not Found</h2><p>The requested page does not exist.</p></section>"
    return "404 Not Found", [("Content-Type", "text/html; charset=utf-8")], html_page("404", content, current_user(environ))


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    routes = {
        "/": home,
        "/tasks": tasks_page,
        "/register": register,
        "/login": login,
        "/logout": logout,
        "/forum": forum,
        "/styles.css": lambda _env: serve_css(),
    }
    status, headers, body = routes.get(path, not_found)(environ)
    start_response(status, headers)
    return [body]


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    print(f"Spatial Academy running on http://127.0.0.1:{port}")
    with make_server("0.0.0.0", port, app) as httpd:
        httpd.serve_forever()
