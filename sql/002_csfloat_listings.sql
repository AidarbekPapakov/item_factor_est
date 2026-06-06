-- Placeholder: /listings endpoint requires session-based auth (not API key).
-- Table is created now so it's available when listings ingestion is potenitally added later.
CREATE TABLE IF NOT EXISTS csfloat_listings
(
    listing_id       String,
    _snapshot_date   Date,

    -- Price comes in cents, thus integer type is chosen
    price            Int32,

    -- Item identity
    market_hash_name String,
    def_index        UInt16,
    paint_index      UInt16,
    paint_seed       UInt32,
    float_value      Float32,
    is_stattrak      Bool,
    is_souvenir      Bool,
    wear_name        LowCardinality(String),

    -- Applied items
    stickers         String DEFAULT '[]',
    keychains        String DEFAULT '[]',

    -- Steam market reference price (cents)
    scm_price        Int32 DEFAULT 0,

    -- Ingestion metadata
    _ingested_at     DateTime64(3, 'UTC')
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(_snapshot_date)
ORDER BY (_snapshot_date, market_hash_name, listing_id);
