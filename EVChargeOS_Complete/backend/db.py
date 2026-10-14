"""MySQL connection helper for EVChargeOS.

Loads configuration from the project-root .env file, independent of the
current working directory. An empty DB_PASSWORD is allowed for local MySQL
installations configured without a password.
"""
from pathlib import Path
import os
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error as MySQLError

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=False)

def get_connection():
    if not ENV_FILE.exists():
        raise RuntimeError(
            f"Configuration file not found: {ENV_FILE}. "
            "Create .env in the same folder as run.py. See .env.example."
        )

    required = ["DB_HOST", "DB_USER", "DB_NAME"]
    missing = [key for key in required if not os.getenv(key, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing .env settings: " + ", ".join(missing) +
            f". Edit {ENV_FILE} and set these values."
        )

    password = os.getenv("DB_PASSWORD", "")
    if password == "your_mysql_password":
        raise RuntimeError(
            f"DB_PASSWORD is still the example placeholder in {ENV_FILE}. "
            "Replace it with your MySQL password, or leave it blank if your "
            "MySQL account has no password."
        )

    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost").strip(),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root").strip(),
            password=password,
            database=os.getenv("DB_NAME", "evchargeos").strip(),
            autocommit=False,
            connection_timeout=8,
        )
    except (MySQLError, ValueError) as exc:
        raise RuntimeError(
            "Could not connect to MySQL. Check that MySQL Server is running and "
            "DB_HOST, DB_PORT, DB_USER, DB_PASSWORD and DB_NAME in .env are correct. "
            f"Original error: {exc}"
        ) from exc
