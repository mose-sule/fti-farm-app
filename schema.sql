DROP TABLE IF EXISTS product_history;
DROP TABLE IF EXISTS harvests;
DROP TABLE IF EXISTS activities;
DROP TABLE IF EXISTS soil_tests;
DROP TABLE IF EXISTS crops;
DROP TABLE IF EXISTS fields;
DROP TABLE IF EXISTS farms;

DROP TABLE IF EXISTS market_areas;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS notifications;

CREATE TABLE notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    message TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_read INTEGER DEFAULT 0
);
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE market_areas (
    market_area_id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_name TEXT NOT NULL,
    region TEXT
);
CREATE TABLE farms (
    farm_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    market_area_id INTEGER REFERENCES market_areas(market_area_id),
    farm_name TEXT NOT NULL,
    location TEXT,
    total_area_acres REAL
    latitude REAL,
    longitude REAL,
```//add these anywhere inside the parentheses, e.g. right after `location TEXT,`

**2. Add a weather helper function to `app.py`.** Open it:

```bash
nano app.py
);

CREATE TABLE fields (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    field_name TEXT NOT NULL,
    area_acres REAL,
    soil_type TEXT,
    notes TEXT
);

CREATE TABLE crops (
    crop_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    field_id INTEGER REFERENCES fields(field_id),
    crop_name TEXT NOT NULL,
    variety TEXT,
    planting_date TEXT NOT NULL,
    expected_harvest_date TEXT NOT NULL,
    area_acres REAL,
    status TEXT DEFAULT 'growing'
);

CREATE TABLE soil_tests (
    test_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    field_id INTEGER REFERENCES fields(field_id),
    test_date TEXT NOT NULL,
    soil_type TEXT,
    ph REAL,
    nitrogen REAL,
    phosphorus REAL,
    potassium REAL,
    organic_matter REAL,
    moisture REAL,
    notes TEXT
);

CREATE TABLE activities (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    crop_id INTEGER REFERENCES crops(crop_id),
    activity_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    crop_name TEXT,
    input_used TEXT,
    quantity TEXT,
    notes TEXT
);

CREATE TABLE harvests (
    harvest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    crop_id INTEGER REFERENCES crops(crop_id),
    crop_name TEXT NOT NULL,
    harvest_date TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    quality TEXT,
    notes TEXT
);

CREATE TABLE product_history (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    crop_name TEXT,
    harvest_id INTEGER REFERENCES harvests(harvest_id),
    batch_number TEXT,
    product_date TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    destination TEXT,
    notes TEXT
);
