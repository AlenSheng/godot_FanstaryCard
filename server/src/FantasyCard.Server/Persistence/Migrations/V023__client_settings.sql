CREATE TABLE client_settings (
    id integer PRIMARY KEY CHECK (id = 1),
    local_login_enabled boolean NOT NULL DEFAULT false,
    announcement_title varchar(120) NOT NULL DEFAULT '',
    announcement_body varchar(6000) NOT NULL DEFAULT '',
    version bigint NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO client_settings(id, local_login_enabled)
VALUES (1, true);
