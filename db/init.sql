-- =========================================
-- TFT Match Insight & Win Predictor Schema
-- =========================================

-- Summoner / Player registry
CREATE TABLE IF NOT EXISTS summoners (
    puuid          VARCHAR(100) PRIMARY KEY,
    summoner_name  VARCHAR(100),
    summoner_id    VARCHAR(100),
    region         VARCHAR(20),
    fetched_at     TIMESTAMP DEFAULT NOW()
);

-- One row per TFT match
CREATE TABLE IF NOT EXISTS matches (
    match_id          VARCHAR(50) PRIMARY KEY,
    game_datetime     TIMESTAMP NOT NULL,
    game_length       FLOAT,
    tft_set_number    INT,
    tft_set_core_name VARCHAR(50),
    queue_id          INT,
    created_at        TIMESTAMP DEFAULT NOW()
);

-- One row per player per match (8 players per match)
CREATE TABLE IF NOT EXISTS participants (
    id                        SERIAL PRIMARY KEY,
    match_id                  VARCHAR(50) REFERENCES matches(match_id) ON DELETE CASCADE,
    puuid                     VARCHAR(100),
    placement                 INT NOT NULL,          -- 1 = 1st, 8 = last
    level                     INT,
    last_round                INT,
    time_eliminated           FLOAT,
    total_damage_to_players   FLOAT,
    players_eliminated        INT,
    gold_left                 INT,
    augments                  TEXT[],
    partner_group_id          INT,
    UNIQUE (match_id, puuid)
);

-- Units on the board
CREATE TABLE IF NOT EXISTS units (
    id              SERIAL PRIMARY KEY,
    participant_id  INT REFERENCES participants(id) ON DELETE CASCADE,
    character_id    VARCHAR(80),
    rarity          INT,
    tier            INT,
    items           TEXT[]
);

-- Active traits
CREATE TABLE IF NOT EXISTS traits (
    id              SERIAL PRIMARY KEY,
    participant_id  INT REFERENCES participants(id) ON DELETE CASCADE,
    name            VARCHAR(80),
    num_units       INT,
    style           INT,    -- 0=inactive, 1=bronze, 2=silver, 3=gold, 4=prismatic
    tier_current    INT,
    tier_total      INT
);

-- Track which matches we've already fetched per summoner
CREATE TABLE IF NOT EXISTS fetch_log (
    id          SERIAL PRIMARY KEY,
    puuid       VARCHAR(100),
    match_id    VARCHAR(50),
    fetched_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (puuid, match_id)
);

-- =========================================
-- Indexes for query performance
-- =========================================
CREATE INDEX IF NOT EXISTS idx_participants_puuid    ON participants(puuid);
CREATE INDEX IF NOT EXISTS idx_participants_match    ON participants(match_id);
CREATE INDEX IF NOT EXISTS idx_participants_placement ON participants(placement);
CREATE INDEX IF NOT EXISTS idx_units_participant     ON units(participant_id);
CREATE INDEX IF NOT EXISTS idx_traits_participant    ON traits(participant_id);
CREATE INDEX IF NOT EXISTS idx_matches_datetime      ON matches(game_datetime);
CREATE INDEX IF NOT EXISTS idx_fetch_log_puuid       ON fetch_log(puuid);