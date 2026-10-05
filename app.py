import os
import secrets
import string
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

database_url = os.environ.get("DATABASE_URL", "sqlite:///keys.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class LicenseKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    device_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)


def now():
    return datetime.now(timezone.utc)


def make_key():
    alphabet = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(alphabet) for _ in range(6)) for _ in range(3)]
    return "VIP-" + "-".join(parts)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


def api_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.environ.get("ADMIN_API_TOKEN")
        supplied = request.headers.get("X-Admin-Token")
        if not expected or not supplied or not secrets.compare_digest(supplied, expected):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session["admin_id"] = admin.id
            return redirect(url_for("admin_dashboard"))
        flash("بيانات الدخول غير صحيحة", "error")
    return render_template("login.html")


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    keys = LicenseKey.query.order_by(LicenseKey.created_at.desc()).all()
    return render_template("dashboard.html", keys=keys, current_time=now())


@app.post("/admin/keys/create")
@admin_required
def admin_create_key():
    try:
        days = int(request.form.get("days", "30"))
    except ValueError:
        days = 30
    days = max(1, min(days, 3650))
    key = LicenseKey(
        key=make_key(),
        active=True,
        expires_at=now() + timedelta(days=days)
    )
    db.session.add(key)
    db.session.commit()
    flash(f"تم إنشاء المفتاح: {key.key}", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/keys/<int:key_id>/toggle")
@admin_required
def toggle_key(key_id):
    item = db.get_or_404(LicenseKey, key_id)
    item.active = not item.active
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/keys/<int:key_id>/extend")
@admin_required
def extend_key(key_id):
    item = db.get_or_404(LicenseKey, key_id)
    try:
        days = int(request.form.get("days", "30"))
    except ValueError:
        days = 30
    days = max(1, min(days, 3650))
    base = item.expires_at if item.expires_at > now() else now()
    item.expires_at = base + timedelta(days=days)
    item.active = True
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.delete("/admin/keys/<int:key_id>")
@admin_required
def delete_key(key_id):
    item = db.get_or_404(LicenseKey, key_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    supplied_key = str(data.get("key", "")).strip().upper()
    device_id = str(data.get("device_id", "")).strip()[:255]

    if not supplied_key:
        return jsonify({"ok": False, "valid": False, "error": "missing_key"}), 400

    item = LicenseKey.query.filter_by(key=supplied_key).first()
    if not item:
        return jsonify({"ok": True, "valid": False, "error": "invalid_key"}), 200

    if not item.active:
        return jsonify({"ok": True, "valid": False, "error": "disabled"}), 200

    if item.expires_at <= now():
        return jsonify({"ok": True, "valid": False, "error": "expired"}), 200

    # Optional one-device binding. The first successful device claims the key.
    if device_id:
        if item.device_id and item.device_id != device_id:
            return jsonify({"ok": True, "valid": False, "error": "device_mismatch"}), 200
        if not item.device_id:
            item.device_id = device_id

    item.last_used_at = now()
    db.session.commit()

    # This token is an application-session token. Store it server-side if you need
    # revocation; this starter keeps the response simple.
    token = secrets.token_urlsafe(32)
    return jsonify({
        "ok": True,
        "valid": True,
        "token": token,
        "expires_at": item.expires_at.isoformat()
    })


@app.post("/api/admin/keys")
@api_admin_required
def api_admin_create_key():
    data = request.get_json(silent=True) or {}
    try:
        days = int(data.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 3650))

    item = LicenseKey(
        key=make_key(),
        active=True,
        expires_at=now() + timedelta(days=days)
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({
        "ok": True,
        "key": item.key,
        "expires_at": item.expires_at.isoformat()
    }), 201


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "license-api"})


def init_db():
    with app.app_context():
        db.create_all()
        if Admin.query.count() == 0:
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD")
            if not password:
                password = secrets.token_urlsafe(12)
                print(f"\nGenerated ADMIN password: {password}\n")
            db.session.add(Admin(
                username=username,
                password_hash=generate_password_hash(password)
            ))
            db.session.commit()


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
