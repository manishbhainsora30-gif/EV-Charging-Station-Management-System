# EVChargeOS — complete Flask + MySQL project

Features: user registration/login, vehicle management, charging requests, manual distance and battery-level input, admin approval/rejection, compatible connector allocation, priority queue scheduling, session completion, and connector release.

## Requirements
- Python 3.10+
- MySQL Server

## Windows setup (VS Code terminal / PowerShell)
1. Extract this ZIP.
2. Open the extracted `EVChargeOS_Complete` folder in VS Code.
3. Create and activate a virtual environment (optional but recommended):
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env` and set `DB_USER` and `DB_PASSWORD` to your MySQL credentials. Keep `DB_NAME=evchargeos`.
6. Create tables and demo stations/admin account:
   ```powershell
   python -m backend.setup_db
   ```
7. Run the app:
   ```powershell
   python run.py
   ```
8. Open `http://127.0.0.1:5000`.

Demo administrator created only if no admin account exists:
- Email: `admin@evchargeos.local`
- Password: `Admin@12345`

Change the demo password before using this outside a local academic demo. Public registration can only create USER accounts; create additional admins directly in MySQL or through a secured admin-only workflow.

## User workflow
Register/login → register a vehicle → submit charging request with station, vehicle, required power, distance to station, battery percentage and priority → wait for admin approval.

## Admin workflow
Login as admin → review request details → approve/reject. Approval tries to allocate an available compatible connector at the selected station. If none is available, the request remains approved and waiting. Use Process approved queue to retry. Complete active sessions by entering consumed kWh; the connector is then released.

## Database notes
- Fresh install: `python -m backend.setup_db` creates the schema and demo stations/connectors.
- Existing database: first back up the database, then run `backend/sql/add_distance_battery_columns.sql` once in MySQL if the two new columns do not exist. Do not run the ALTER script repeatedly.
- This project does not calculate distance automatically; the user enters distance manually.

## OS + DBMS concepts
- OS: priority scheduling, shared connector resource allocation, synchronization via MySQL row locks and transactions.
- DBMS: relational schema, primary/foreign keys, transactions, queue records, sessions and normalized data.


### Configuration troubleshooting

- The `.env` file must be in the `EVChargeOS_Complete` root folder, beside `run.py`.
- This ZIP includes a starter `.env`; edit its `DB_PASSWORD` value before running setup if your MySQL root account has a password.
- If MySQL reports `Access denied`, the username/password are incorrect or the server uses a different account.
- If MySQL reports `Unknown database`, run `python -m backend.setup_db` after correcting `.env`.
- Start the app from this folder with `python run.py`.
