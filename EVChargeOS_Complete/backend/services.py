from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError
from .db import get_connection
from .scheduler import choose_connector


def authenticate_user(email, password, expected_role=None):
    """Authenticate against MySQL. Upgrade legacy plaintext demo passwords on login."""
    email = (email or "").strip().lower()
    if expected_role is not None:
        expected_role = str(expected_role).strip().upper()
        if expected_role not in {"USER", "ADMIN"}:
            return None
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT user_id, name, email, password_hash, user_type FROM users WHERE email=%s LIMIT 1",
            (email,),
        )
        user = cur.fetchone()
        if not user or (expected_role is not None and user["user_type"] != expected_role):
            return None
        stored = user.get("password_hash") or ""
        valid = False
        # Older versions seeded demo passwords as plain text. Accept them once and
        # replace with a secure Werkzeug hash so existing installations keep working.
        if stored.startswith(("scrypt:", "pbkdf2:")):
            try:
                valid = check_password_hash(stored, password)
            except (ValueError, TypeError):
                valid = False
        else:
            valid = (stored == password)
            if valid:
                cur.execute(
                    "UPDATE users SET password_hash=%s WHERE user_id=%s",
                    (generate_password_hash(password), user["user_id"]),
                )
                conn.commit()
        if not valid:
            return None
        return {"user_id": user["user_id"], "name": user["name"],
                "email": user["email"], "user_type": user["user_type"]}
    finally:
        conn.close()


def register_user(name, email, password, registration_number=None, battery_capacity=None, max_charging_power=None):
    """Create a USER account and, when supplied, save its first vehicle atomically.

    Public registration always creates a USER; it can never create an ADMIN.
    Vehicle details are inserted in the same transaction so users do not end up
    with an account but a missing vehicle if registration fails halfway through.
    """
    name = (name or "").strip()
    email = (email or "").strip().lower()
    password = password or ""
    registration_number = (registration_number or "").strip().upper()
    vehicle_details_supplied = any(
        value not in (None, "")
        for value in (registration_number, battery_capacity, max_charging_power)
    )

    if len(name) < 2 or len(name) > 100:
        raise ValueError("Name must be between 2 and 100 characters.")
    if not email or "@" not in email or len(email) > 150:
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    battery = power = None
    if vehicle_details_supplied:
        if not registration_number or len(registration_number) > 50:
            raise ValueError("Enter a valid vehicle registration number.")
        try:
            battery = float(battery_capacity)
            power = float(max_charging_power)
        except (TypeError, ValueError):
            raise ValueError("Enter the battery capacity and maximum charging power.")
        if battery <= 0 or battery > 2000:
            raise ValueError("Battery capacity must be greater than 0 and no more than 2000 kWh.")
        if power <= 0 or power > 500:
            raise ValueError("Maximum charging power must be greater than 0 and no more than 500 kW.")

    conn = get_connection()
    try:
        conn.start_transaction()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash, user_type) VALUES (%s, %s, %s, 'USER')",
            (name, email, generate_password_hash(password)),
        )
        user_id = cur.lastrowid
        if vehicle_details_supplied:
            cur.execute("""INSERT INTO vehicles
                (user_id, registration_number, battery_capacity, max_charging_power)
                VALUES (%s, %s, %s, %s)""",
                (user_id, registration_number, battery, power))
        conn.commit()
        return user_id
    except IntegrityError as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            message = ("An account with this email already exists. Please log in."
                       if "email" in str(exc).lower() else
                       "That vehicle registration number is already registered.")
            raise ValueError(message) from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def register_vehicle(user_id, registration_number, battery_capacity, max_charging_power):
    """Register a vehicle for the currently authenticated user."""
    registration_number = (registration_number or "").strip().upper()
    try:
        battery = float(battery_capacity)
        power = float(max_charging_power)
    except (TypeError, ValueError):
        raise ValueError("Enter valid battery capacity and maximum charging power.")
    if not registration_number or len(registration_number) > 50:
        raise ValueError("Enter a valid vehicle registration number.")
    if battery <= 0 or battery > 2000:
        raise ValueError("Battery capacity must be greater than 0 and no more than 2000 kWh.")
    if power <= 0 or power > 500:
        raise ValueError("Maximum charging power must be greater than 0 and no more than 500 kW.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO vehicles
            (user_id, registration_number, battery_capacity, max_charging_power)
            VALUES (%s, %s, %s, %s)""", (user_id, registration_number, battery, power))
        conn.commit()
        return cur.lastrowid
    except IntegrityError as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            raise ValueError("That vehicle registration number is already registered.") from exc
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_stations():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT station_id, name, location FROM charging_stations ORDER BY station_id")
        return cur.fetchall()
    finally:
        conn.close()

def list_vehicles(user_id=None):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        sql = """SELECT vehicle_id, user_id, registration_number, battery_capacity,
                        max_charging_power FROM vehicles"""
        params = ()
        if user_id is not None:
            sql += " WHERE user_id=%s"
            params = (user_id,)
        sql += " ORDER BY vehicle_id"
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()

def dashboard_stats():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        queries = {
            "vehicles": "SELECT COUNT(*) AS n FROM vehicles",
            "requests": "SELECT COUNT(*) AS n FROM charging_requests",
            "available_connectors": "SELECT COUNT(*) AS n FROM connectors WHERE status='AVAILABLE'",
            "active_sessions": "SELECT COUNT(*) AS n FROM charging_sessions WHERE status='ACTIVE'",
        }
        result = {}
        for key, sql in queries.items():
            cur.execute(sql)
            result[key] = cur.fetchone()["n"]
        return result
    finally:
        conn.close()

def _priority_rank(priority):
    """Normalize priority labels and ranks to the integer database format."""
    mapping = {
        "emergency": 1, "high": 2, "normal": 3, "low": 4,
        "1": 1, "2": 2, "3": 3, "4": 4,
    }
    key = str(priority if priority is not None else "").strip().lower()
    if key not in mapping:
        raise ValueError("Select a valid priority.")
    return mapping[key]


def create_charging_request(user_id, vehicle_id, station_id, required_power_kw, priority,
                            distance_to_station_km, battery_level_percent):
    try:
        power = float(required_power_kw)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid charging power.")
    if power <= 0 or power > 500:
        raise ValueError("Charging power must be greater than 0 and no more than 500 kW.")
    # The current EVChargeOS MySQL schema stores priority as an INTEGER.
    # Accept both form labels and already-converted integer/string ranks.
    priority = _priority_rank(priority)
    try:
        distance = float(distance_to_station_km)
        battery = int(battery_level_percent)
    except (TypeError, ValueError):
        raise ValueError("Enter the distance to the station and battery percentage.")
    if distance < 0 or distance > 10000:
        raise ValueError("Distance must be between 0 and 10000 km.")
    if battery < 0 or battery > 100:
        raise ValueError("Battery level must be between 0 and 100 percent.")

    conn = get_connection()
    request_id = None
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
        if not cur.fetchone():
            raise ValueError("User account was not found. Please log in again.")
        cur.execute("""
            SELECT vehicle_id, user_id, max_charging_power
            FROM vehicles WHERE vehicle_id=%s
        """, (vehicle_id,))
        vehicle = cur.fetchone()
        if not vehicle or int(vehicle["user_id"]) != int(user_id):
            raise ValueError("Select a vehicle registered to your account.")
        cur.execute("SELECT station_id FROM charging_stations WHERE station_id=%s", (station_id,))
        if not cur.fetchone():
            raise ValueError("Select a valid charging station.")
        if vehicle["max_charging_power"] is not None and power > float(vehicle["max_charging_power"]):
            raise ValueError("Requested power exceeds the vehicle's maximum charging power.")
        cur.execute("""
            INSERT INTO charging_requests
                (user_id, vehicle_id, station_id, required_power, required_power_kw,
                 priority, status, approval_status, distance_to_station_km,
                 battery_level_percent, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'WAITING', 'PENDING', %s, %s, NOW())
        """, (user_id, vehicle_id, station_id, power, power, priority, distance, battery))
        request_id = cur.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Requests must be reviewed by an administrator before they can be allocated.
    return request_id

def allocate_request(request_id):
    conn = get_connection()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT request_id, station_id, required_power_kw, status, approval_status
            FROM charging_requests WHERE request_id=%s FOR UPDATE
        """, (request_id,))
        req = cur.fetchone()
        if not req or req["status"] != "WAITING" or req["approval_status"] != "APPROVED":
            conn.commit()
            return False
        cur.execute("""
            SELECT connector_id, station_id, max_power_kw, status
            FROM connectors
            WHERE station_id=%s AND status='AVAILABLE'
            ORDER BY max_power_kw FOR UPDATE
        """, (req["station_id"],))
        connector = choose_connector(cur.fetchall(), float(req["required_power_kw"]))
        if not connector:
            conn.commit()
            return False
        cur.execute("UPDATE connectors SET status='OCCUPIED' WHERE connector_id=%s AND status='AVAILABLE'",
                    (connector["connector_id"],))
        if cur.rowcount != 1:
            conn.rollback()
            return False
        cur.execute("UPDATE charging_requests SET status='ALLOCATED' WHERE request_id=%s",
                    (request_id,))
        cur.execute("""
            INSERT INTO charging_sessions
                (request_id, connector_id, status, start_time, energy_consumed_kwh)
            VALUES (%s, %s, 'ACTIVE', NOW(), 0)
        """, (request_id, connector["connector_id"]))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def process_waiting_queue():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT request_id FROM charging_requests
            WHERE status='WAITING' AND approval_status='APPROVED'
            ORDER BY priority ASC, created_at ASC, request_id ASC
        """)
        ids = [row["request_id"] for row in cur.fetchall()]
    finally:
        conn.close()
    return sum(1 for request_id in ids if allocate_request(request_id))

def list_pending_requests():
    """List requests awaiting administrator approval, with user and resource details."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT cr.request_id, cr.user_id, u.name AS user_name, u.email,
                   cr.vehicle_id, v.registration_number, cr.station_id,
                   st.name AS station_name, st.location AS station_location,
                   cr.required_power_kw, cr.priority, cr.status,
                   cr.approval_status, cr.distance_to_station_km,
                   cr.battery_level_percent, cr.created_at
            FROM charging_requests cr
            JOIN users u ON u.user_id = cr.user_id
            JOIN vehicles v ON v.vehicle_id = cr.vehicle_id
            JOIN charging_stations st ON st.station_id = cr.station_id
            WHERE cr.approval_status = 'PENDING'
            ORDER BY cr.priority ASC, cr.created_at ASC, cr.request_id ASC
        """)
        return cur.fetchall()
    finally:
        conn.close()


def list_user_requests(user_id):
    """List a user's own charging requests and their approval/allocation state."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT cr.request_id, cr.required_power_kw, cr.priority, cr.status,
                   cr.approval_status, cr.distance_to_station_km,
                   cr.battery_level_percent, cr.created_at, st.name AS station_name,
                   v.registration_number,
                   (SELECT cs.session_id FROM charging_sessions cs
                    WHERE cs.request_id = cr.request_id ORDER BY cs.session_id DESC LIMIT 1) AS session_id,
                   (SELECT cs.connector_id FROM charging_sessions cs
                    WHERE cs.request_id = cr.request_id ORDER BY cs.session_id DESC LIMIT 1) AS connector_id
            FROM charging_requests cr
            JOIN charging_stations st ON st.station_id = cr.station_id
            JOIN vehicles v ON v.vehicle_id = cr.vehicle_id
            WHERE cr.user_id = %s
            ORDER BY cr.created_at DESC, cr.request_id DESC
        """, (user_id,))
        return cur.fetchall()
    finally:
        conn.close()


def approve_request(request_id):
    """Approve a pending request, then attempt allocation through the scheduler."""
    try:
        rid = int(request_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid request ID.")
    if rid <= 0:
        raise ValueError("Invalid request ID.")

    conn = get_connection()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT request_id, status, approval_status
                       FROM charging_requests WHERE request_id=%s FOR UPDATE""", (rid,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Charging request not found.")
        if row["approval_status"] != "PENDING":
            raise ValueError("This request has already been reviewed.")
        cur.execute("""UPDATE charging_requests SET approval_status='APPROVED', status='WAITING'
                       WHERE request_id=%s AND approval_status='PENDING'""", (rid,))
        if cur.rowcount != 1:
            raise ValueError("The request could not be approved. Refresh and try again.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # If no compatible connector is free, it stays WAITING but approved.
    allocated = allocate_request(rid)
    return allocated


def reject_request(request_id):
    """Reject a pending request without allocating a connector."""
    try:
        rid = int(request_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid request ID.")
    if rid <= 0:
        raise ValueError("Invalid request ID.")
    conn = get_connection()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT request_id, approval_status FROM charging_requests
                       WHERE request_id=%s FOR UPDATE""", (rid,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Charging request not found.")
        if row["approval_status"] != "PENDING":
            raise ValueError("This request has already been reviewed.")
        cur.execute("""UPDATE charging_requests SET approval_status='REJECTED'
                       WHERE request_id=%s AND approval_status='PENDING'""", (rid,))
        if cur.rowcount != 1:
            raise ValueError("The request could not be rejected. Refresh and try again.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_sessions():
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT session_id, request_id, connector_id, status, start_time,
                   end_time, energy_consumed_kwh
            FROM charging_sessions ORDER BY session_id DESC LIMIT 100
        """)
        return cur.fetchall()
    finally:
        conn.close()

def complete_session(session_id, energy_kwh):
    try:
        energy = float(energy_kwh)
        sid = int(session_id)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid session ID and energy value.")
    if sid <= 0 or energy < 0:
        raise ValueError("Session ID must be positive and energy cannot be negative.")
    conn = get_connection()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT session_id, request_id, connector_id, status
            FROM charging_sessions WHERE session_id=%s FOR UPDATE
        """, (sid,))
        s = cur.fetchone()
        if not s:
            raise ValueError("Charging session not found.")
        if s["status"] != "ACTIVE":
            raise ValueError("This session is not active.")
        cur.execute("""
            UPDATE charging_sessions SET status='COMPLETED', end_time=NOW(),
                energy_consumed_kwh=%s WHERE session_id=%s
        """, (energy, sid))
        cur.execute("UPDATE connectors SET status='AVAILABLE' WHERE connector_id=%s",
                    (s["connector_id"],))
        cur.execute("UPDATE charging_requests SET status='COMPLETED' WHERE request_id=%s",
                    (s["request_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    process_waiting_queue()
