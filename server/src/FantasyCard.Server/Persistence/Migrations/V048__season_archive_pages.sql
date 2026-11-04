ALTER TABLE equipments DROP CONSTRAINT equipments_location_check;
ALTER TABLE equipments ADD CONSTRAINT equipments_location_check CHECK(location IN
    ('Inventory','Equipped','MarketListed','MarketReturnPending','PreparationLocked','InMatchEquipped','InMatchBackpack',
     'RelicPile','EnhanceMaterialConsumed','Recycled','SeasonArchive'));

-- Collection storage has no active-season warehouse slot limit. Original item
-- identity, enhancement and provenance remain on equipments, without a remint.
CREATE TABLE season_archive_loadouts (
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    hero_class smallint NOT NULL CHECK(hero_class BETWEEN 1 AND 3),
    head_id uuid REFERENCES equipments(instance_id),
    hands_id uuid REFERENCES equipments(instance_id),
    chest_id uuid REFERENCES equipments(instance_id),
    legs_id uuid REFERENCES equipments(instance_id),
    feet_id uuid REFERENCES equipments(instance_id),
    original_version bigint NOT NULL CHECK(original_version > 0),
    archived_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,season_id,hero_class),
    FOREIGN KEY(player_id,season_id) REFERENCES player_season_state(player_id,season_id)
);

CREATE TABLE season_archive_items (
    player_id uuid NOT NULL,
    season_id varchar(80) NOT NULL,
    item_id uuid NOT NULL REFERENCES equipments(instance_id),
    job_id uuid NOT NULL REFERENCES season_archive_jobs(job_id),
    from_location varchar(32) NOT NULL,
    to_location varchar(32) NOT NULL,
    archived_at timestamptz NOT NULL,
    PRIMARY KEY(player_id,season_id,item_id),
    FOREIGN KEY(player_id,season_id) REFERENCES player_season_state(player_id,season_id)
);
