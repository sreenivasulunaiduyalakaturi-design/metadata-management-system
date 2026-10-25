"""Metadata Management System - simple base project (Flask + SQLite)."""
import sqlite3
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, flash, jsonify, abort

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["DATABASE"] = "metadata.db"

ASSET_TYPES = ["Dataset", "Table", "File", "Report", "API", "Other"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    asset_type  TEXT NOT NULL DEFAULT 'Other',
    owner       TEXT DEFAULT '',
    source      TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metadata (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    TEXT DEFAULT ''
);
"""


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_tags(raw):
    tags = [t.strip().lower() for t in raw.split(",") if t.strip()]
    return ",".join(dict.fromkeys(tags))  # dedupe, keep order


def read_form():
    """Extract and validate asset data from the submitted form."""
    data = {
        "name": request.form.get("name", "").strip(),
        "description": request.form.get("description", "").strip(),
        "asset_type": request.form.get("asset_type", "Other"),
        "owner": request.form.get("owner", "").strip(),
        "source": request.form.get("source", "").strip(),
        "tags": clean_tags(request.form.get("tags", "")),
    }
    keys = request.form.getlist("meta_key")
    values = request.form.getlist("meta_value")
    data["fields"] = [(k.strip(), v.strip()) for k, v in zip(keys, values) if k.strip()]
    return data


def asset_to_dict(db, row):
    d = dict(row)
    d["tags"] = [t for t in d["tags"].split(",") if t]
    fields = db.execute("SELECT key, value FROM metadata WHERE asset_id = ?", (row["id"],)).fetchall()
    d["custom_fields"] = {f["key"]: f["value"] for f in fields}
    return d


# ---------- web pages ----------
@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    asset_type = request.args.get("type", "").strip()
    tag = request.args.get("tag", "").strip().lower()

    sql = "SELECT DISTINCT a.* FROM assets a LEFT JOIN metadata m ON m.asset_id = a.id WHERE 1=1"
    params = []
    if q:
        like = f"%{q}%"
        sql += " AND (a.name LIKE ? OR a.description LIKE ? OR a.owner LIKE ? OR a.tags LIKE ? OR m.key LIKE ? OR m.value LIKE ?)"
        params += [like] * 6
    if asset_type:
        sql += " AND a.asset_type = ?"
        params.append(asset_type)
    if tag:
        sql += " AND (',' || a.tags || ',') LIKE ?"
        params.append(f"%,{tag},%")
    sql += " ORDER BY a.updated_at DESC"

    assets = [asset_to_dict(db, r) for r in db.execute(sql, params).fetchall()]
    total = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    return render_template("index.html", assets=assets, total=total, q=q,
                           selected_type=asset_type, selected_tag=tag, types=ASSET_TYPES)


@app.route("/asset/<int:asset_id>")
def detail(asset_id):
    db = get_db()
    row = db.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        abort(404)
    return render_template("detail.html", asset=asset_to_dict(db, row))


@app.route("/asset/new", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        data = read_form()
        if not data["name"]:
            flash("Name is required.", "error")
            return render_template("form.html", asset=data, types=ASSET_TYPES, mode="new"), 400
        db = get_db()
        ts = now()
        cur = db.execute(
            "INSERT INTO assets (name, description, asset_type, owner, source, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (data["name"], data["description"], data["asset_type"], data["owner"],
             data["source"], data["tags"], ts, ts))
        db.executemany("INSERT INTO metadata (asset_id, key, value) VALUES (?, ?, ?)",
                       [(cur.lastrowid, k, v) for k, v in data["fields"]])
        db.commit()
        flash("Asset created.", "success")
        return redirect(url_for("detail", asset_id=cur.lastrowid))
    return render_template("form.html", asset={"fields": []}, types=ASSET_TYPES, mode="new")


@app.route("/asset/<int:asset_id>/edit", methods=["GET", "POST"])
def edit(asset_id):
    db = get_db()
    row = db.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        data = read_form()
        if not data["name"]:
            flash("Name is required.", "error")
            data["id"] = asset_id
            return render_template("form.html", asset=data, types=ASSET_TYPES, mode="edit"), 400
        db.execute(
            "UPDATE assets SET name=?, description=?, asset_type=?, owner=?, source=?, tags=?, updated_at=? WHERE id=?",
            (data["name"], data["description"], data["asset_type"], data["owner"],
             data["source"], data["tags"], now(), asset_id))
        db.execute("DELETE FROM metadata WHERE asset_id = ?", (asset_id,))
        db.executemany("INSERT INTO metadata (asset_id, key, value) VALUES (?, ?, ?)",
                       [(asset_id, k, v) for k, v in data["fields"]])
        db.commit()
        flash("Asset updated.", "success")
        return redirect(url_for("detail", asset_id=asset_id))
    d = dict(row)
    fields = db.execute("SELECT key, value FROM metadata WHERE asset_id = ?", (asset_id,)).fetchall()
    d["fields"] = [(f["key"], f["value"]) for f in fields]
    return render_template("form.html", asset=d, types=ASSET_TYPES, mode="edit")


@app.route("/asset/<int:asset_id>/delete", methods=["POST"])
def delete(asset_id):
    db = get_db()
    db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    db.commit()
    flash("Asset deleted.", "success")
    return redirect(url_for("index"))


# ---------- JSON API ----------
@app.route("/api/assets")
def api_list():
    db = get_db()
    rows = db.execute("SELECT * FROM assets ORDER BY id").fetchall()
    return jsonify([asset_to_dict(db, r) for r in rows])


@app.route("/api/assets/<int:asset_id>")
def api_get(asset_id):
    db = get_db()
    row = db.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(asset_to_dict(db, row))


@app.route("/api/assets", methods=["POST"])
def api_create():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    tags = body.get("tags", [])
    tags = clean_tags(",".join(tags) if isinstance(tags, list) else str(tags))
    db, ts = get_db(), now()
    cur = db.execute(
        "INSERT INTO assets (name, description, asset_type, owner, source, tags, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, body.get("description", ""), body.get("asset_type", "Other"),
         body.get("owner", ""), body.get("source", ""), tags, ts, ts))
    for k, v in (body.get("custom_fields") or {}).items():
        db.execute("INSERT INTO metadata (asset_id, key, value) VALUES (?, ?, ?)", (cur.lastrowid, k, str(v)))
    db.commit()
    row = db.execute("SELECT * FROM assets WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(asset_to_dict(db, row)), 201


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def api_delete(asset_id):
    db = get_db()
    cur = db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": asset_id})


@app.errorhandler(404)
def not_found(_):
    return render_template("base.html", content_404=True), 404


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
