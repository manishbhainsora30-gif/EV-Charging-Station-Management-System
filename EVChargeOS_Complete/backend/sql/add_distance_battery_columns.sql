USE evchargeos;
ALTER TABLE charging_requests ADD COLUMN distance_to_station_km DECIMAL(8,2) NULL;
ALTER TABLE charging_requests ADD COLUMN battery_level_percent TINYINT UNSIGNED NULL;
