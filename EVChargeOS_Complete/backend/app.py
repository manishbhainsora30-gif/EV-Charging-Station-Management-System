import os
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash
from mysql.connector import Error as MySQLError
from dotenv import load_dotenv
from .services import (
    authenticate_user, register_user, register_vehicle, list_stations,
    list_vehicles, create_charging_request, dashboard_stats, list_sessions,
    complete_session, process_waiting_queue, list_pending_requests,
    list_user_requests, approve_request, reject_request,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
TEMPLATE_DIR = PROJECT_ROOT / "frontend" / "templates"
STATIC_DIR = PROJECT_ROOT / "frontend" / "static"
app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)
app.secret_key = os.getenv("SECRET_KEY", "local-development-secret-change-me")

# The database column charging_requests.priority is INTEGER:
# 1 = Emergency, 2 = High, 3 = Normal, 4 = Low.
PRIORITY_MAP = {
    "emergency": 1,
    "high": 2,
    "normal": 3,
    "low": 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
}


def get_priority_value(value):
    """Validate form priority and return the integer stored by MySQL."""
    key = str(value if value is not None else "").strip().lower()
    if key not in PRIORITY_MAP:
        raise ValueError("Select a valid priority.")
    return PRIORITY_MAP[key]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", role="ADMIN"))
        if session.get("user_type") != "ADMIN":
            flash("Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("admin" if session.get("user_type") == "ADMIN" else "dashboard"))
    return render_template("home.html")


@app.route("/user")
def user_portal():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("user_portal.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role", request.form.get("role", "USER")).upper()
    if role not in {"USER", "ADMIN"}:
        role = "USER"
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            user = authenticate_user(email, password, role)
        except MySQLError:
            app.logger.exception("Login database query failed")
            flash("Unable to connect to the database. Check .env and MySQL Server.", "error")
            user = None
        if user:
            session.clear()
            session.update(user_id=user["user_id"], user_type=user["user_type"],
                           name=user["name"], email=user["email"])
            return redirect(url_for("admin" if user["user_type"] == "ADMIN" else "dashboard"))
        if not any(category == "error" for category, _ in session.get("_flashes", [])):
            flash("Invalid email/password, or this account does not belong to the selected portal.", "error")
    return render_template("login.html", role=role)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            register_user(
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("registration_number", ""),
                request.form.get("battery_capacity", ""),
                request.form.get("max_charging_power", ""),
            )
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for("login", role="USER"))
        except ValueError as exc:
            flash(str(exc), "error")
        except MySQLError:
            app.logger.exception("User registration failed")
            flash("Could not create the account. Check your database configuration and try again.", "error")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        stats = dashboard_stats()
        db_error = None
        user_vehicles = list_vehicles(session["user_id"]) if session.get("user_type") == "USER" else []
        user_requests = list_user_requests(session["user_id"]) if session.get("user_type") == "USER" else []
    except MySQLError as exc:
        app.logger.exception("Dashboard database query failed")
        stats = {"vehicles": 0, "requests": 0, "available_connectors": 0, "active_sessions": 0}
        user_vehicles = []
        user_requests = []
        db_error = str(exc)
    return render_template("dashboard.html", stats=stats, name=session.get("name"),
                           db_error=db_error, user_vehicles=user_vehicles,
                           user_requests=user_requests)


@app.route("/vehicles/register", methods=["GET", "POST"])
@login_required
def vehicle_registration():
    if session.get("user_type") != "USER":
        flash("Only user accounts can register vehicles.", "error")
        return redirect(url_for("admin"))
    if request.method == "POST":
        try:
            vehicle_id = register_vehicle(
                session["user_id"], request.form.get("registration_number", ""),
                request.form.get("battery_capacity", ""), request.form.get("max_charging_power", ""),
            )
            flash(f"Vehicle registered successfully (Vehicle ID {vehicle_id}).", "success")
            return redirect(url_for("trip"))
        except ValueError as exc:
            flash(str(exc), "error")
        except MySQLError:
            app.logger.exception("Vehicle registration failed")
            flash("Could not register the vehicle. Check the database and try again.", "error")
    return render_template("vehicle_register.html")


@app.route("/trip", methods=["GET", "POST"])
@login_required
def trip():
    if session.get("user_type") != "USER":
        flash("Charging requests are available through the user portal.", "error")
        return redirect(url_for("admin"))
    try:
        stations = list_stations()
        vehicles = list_vehicles(session["user_id"])
    except MySQLError as exc:
        app.logger.exception("Charging form database query failed")
        stations, vehicles = [], []
        flash(f"Database error: {exc}. Check .env and run python -m backend.setup_db.", "error")
    if request.method == "POST" and stations and vehicles:
        try:
            vehicle_id = int(request.form.get("vehicle_id", ""))
            station_id = int(request.form.get("station_id", ""))
            power = request.form.get("required_power_kw", "")
            # HTML may send a label (e.g. "Normal") or numeric value (e.g. "3").
            # Always convert it before calling the database service.
            priority = get_priority_value(request.form.get("priority", "Normal"))
            distance = request.form.get("distance_to_station_km", "")
            battery_level = request.form.get("battery_level_percent", "")
            request_id = create_charging_request(
                session["user_id"], vehicle_id, station_id, power, priority,
                distance_to_station_km=distance,
                battery_level_percent=battery_level,
            )
            flash(
                f"Request #{request_id} submitted successfully and sent to the administrator for approval.",
                "success",
            )
            return redirect(url_for("trip"))
        except ValueError as exc:
            flash(str(exc), "error")
        except MySQLError as exc:
            app.logger.exception("Charging request insert failed")
            flash(f"Database error: {exc}. Check table structure and foreign keys.", "error")
    return render_template("trip.html", stations=stations, vehicles=vehicles)


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        try:
            complete_session(request.form.get("session_id", ""), request.form.get("energy_consumed_kwh", ""))
            flash("Session completed and connector released.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        except MySQLError as exc:
            app.logger.exception("Completing session failed")
            flash(f"Database error: {exc}", "error")
        return redirect(url_for("admin"))
    try:
        sessions = list_sessions()
        pending_requests = list_pending_requests()
    except MySQLError as exc:
        app.logger.exception("Admin sessions or requests query failed")
        sessions, pending_requests = [], []
        flash(f"Database error: {exc}. Run python -m backend.setup_db.", "error")
    return render_template("admin.html", sessions=sessions,
                           pending_requests=pending_requests)


@app.route("/admin/requests/<int:request_id>/approve", methods=["POST"])
@admin_required
def admin_approve_request(request_id):
    try:
        allocated = approve_request(request_id)
        if allocated:
            flash(f"Request #{request_id} approved and a connector was allocated; charging session started.", "success")
        else:
            flash(f"Request #{request_id} approved. It remains in the waiting queue until a compatible connector is available.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except MySQLError as exc:
        app.logger.exception("Approving request failed")
        flash(f"Database error while approving request: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/admin/requests/<int:request_id>/reject", methods=["POST"])
@admin_required
def admin_reject_request(request_id):
    try:
        reject_request(request_id)
        flash(f"Request #{request_id} rejected. No connector was allocated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except MySQLError as exc:
        app.logger.exception("Rejecting request failed")
        flash(f"Database error while rejecting request: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/admin/process-queue", methods=["POST"])
@admin_required
def process_queue():
    try:
        allocated = process_waiting_queue()
        flash(f"Queue processed: {allocated} request(s) allocated.", "success")
    except MySQLError as exc:
        app.logger.exception("Queue processing failed")
        flash(f"Database error: {exc}", "error")
    return redirect(url_for("admin"))


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500,
                           message="Unexpected server error. Check the VS Code terminal for details."), 500
