from pathlib import Path
import os
from dotenv import load_dotenv
import mysql.connector
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

def main():
    cfg = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3306")),
               user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""))
    db_name = os.getenv("DB_NAME", "evchargeos")
    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit(); cur.close(); conn.close()
    conn = mysql.connector.connect(**cfg, database=db_name)
    cur = conn.cursor()
    schema = (ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")
    for statement in schema.split(';'):
        statement = statement.strip()
        if statement and not statement.upper().startswith('CREATE DATABASE') and not statement.upper().startswith('USE '):
            cur.execute(statement)
    # Seed stations and connectors only when no stations exist.
    cur.execute("SELECT COUNT(*) FROM charging_stations")
    if cur.fetchone()[0] == 0:
        stations = [
            ("Dehradun Central Charging Station", "Dehradun", 2),
            ("ISBT EV Charging Station", "ISBT, Dehradun", 2),
            ("Rajpur Road Charging Station", "Rajpur Road, Dehradun", 2),
            ("EVChargeOS Demo Station", "Demo Location, Dehradun", 3),
        ]
        for name, location, count in stations:
            cur.execute("INSERT INTO charging_stations(name, location, total_connectors) VALUES (%s,%s,%s)", (name, location, count))
            station_id = cur.lastrowid
            for i in range(count):
                power = [7.4, 22, 30][i % 3]
                cur.execute("INSERT INTO connectors(station_id, connector_type, max_power_kw, status) VALUES (%s,%s,%s,'AVAILABLE')", (station_id, 'Type 2', power))
    # Create a demo admin only if no admin exists. Change password after first login.
    cur.execute("SELECT user_id FROM users WHERE user_type='ADMIN' LIMIT 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO users(name,email,user_type,password_hash) VALUES (%s,%s,'ADMIN',%s)",
                    ('EVChargeOS Admin', 'admin@evchargeos.local', generate_password_hash('Admin@12345')))
    conn.commit(); cur.close(); conn.close()
    print("EVChargeOS database setup complete.")
    print("Demo admin: admin@evchargeos.local / Admin@12345 (change this password after setup).")

if __name__ == '__main__':
    main()
