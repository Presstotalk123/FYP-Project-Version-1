-- Admin-tunable application settings.
--
-- Key/value rather than a column per toggle: settings are read and written
-- rarely, and adding one should not need a migration. A missing row means
-- "use the code default" in app/services/app_settings.py.

CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(80) NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(updated_by) REFERENCES users (id)
);
