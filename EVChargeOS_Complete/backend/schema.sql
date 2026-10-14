CREATE DATABASE IF NOT EXISTS evchargeos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE evchargeos;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL UNIQUE,
  user_type ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  password_hash VARCHAR(255) NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
  vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  registration_number VARCHAR(50) NOT NULL UNIQUE,
  battery_capacity DECIMAL(8,2) NOT NULL,
  max_charging_power DECIMAL(8,2) NOT NULL,
  CONSTRAINT fk_vehicle_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS charging_stations (
  station_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  location VARCHAR(255) NOT NULL,
  total_connectors INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS connectors (
  connector_id INT AUTO_INCREMENT PRIMARY KEY,
  station_id INT NOT NULL,
  connector_type VARCHAR(50) NOT NULL DEFAULT 'Type 2',
  max_power_kw DECIMAL(8,2) NOT NULL,
  status ENUM('AVAILABLE','OCCUPIED','MAINTENANCE') NOT NULL DEFAULT 'AVAILABLE',
  CONSTRAINT fk_connector_station FOREIGN KEY (station_id) REFERENCES charging_stations(station_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS charging_requests (
  request_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  vehicle_id INT NOT NULL,
  station_id INT NOT NULL,
  required_power DECIMAL(8,2) NOT NULL,
  priority INT NOT NULL DEFAULT 3,
  status ENUM('WAITING','ALLOCATED','CHARGING','COMPLETED','CANCELLED') NOT NULL DEFAULT 'WAITING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  required_power_kw DECIMAL(8,2) NOT NULL,
  approval_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  distance_to_station_km DECIMAL(8,2) NULL,
  battery_level_percent TINYINT UNSIGNED NULL,
  CONSTRAINT fk_request_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_request_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
  CONSTRAINT fk_request_station FOREIGN KEY (station_id) REFERENCES charging_stations(station_id)
);
CREATE TABLE IF NOT EXISTS charging_sessions (
  session_id INT AUTO_INCREMENT PRIMARY KEY,
  request_id INT NOT NULL,
  connector_id INT NOT NULL,
  start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  end_time DATETIME NULL,
  energy_consumed DECIMAL(10,2) NOT NULL DEFAULT 0,
  energy_consumed_kwh DECIMAL(10,2) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  CONSTRAINT fk_session_request FOREIGN KEY (request_id) REFERENCES charging_requests(request_id),
  CONSTRAINT fk_session_connector FOREIGN KEY (connector_id) REFERENCES connectors(connector_id)
);
CREATE TABLE IF NOT EXISTS reservations (
  reservation_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  station_id INT NOT NULL,
  connector_id INT NULL,
  reservation_time DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  CONSTRAINT fk_reservation_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_reservation_station FOREIGN KEY (station_id) REFERENCES charging_stations(station_id),
  CONSTRAINT fk_reservation_connector FOREIGN KEY (connector_id) REFERENCES connectors(connector_id)
);
