CREATE TABLE IF NOT EXISTS csfloat_sales
(
    -- Primary identifiers
    id               String,
    sold_at          DateTime64(6, 'UTC'),

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
    rarity           UInt8,
    wear_name        LowCardinality(String),

    -- Stickers: typed array; query sub-fields with arrayMap + tupleElement
    stickers Array(Tuple(
        sticker_id UInt32,
        slot       UInt8,
        name       String,
        ref_price  Int32,
        ref_qty    UInt32
    )) DEFAULT [],

    -- Charm: at most one per item; flattened to nullable scalar columns
    keychain_id      Nullable(UInt32),
    keychain_pattern Nullable(UInt32),
    keychain_name    Nullable(String),
    keychain_ref_price Nullable(Int32),

    -- Fade (only populated for Fade-finish skins; NULL otherwise)
    fade_pct         Nullable(Float32),
    fade_rank        Nullable(UInt32),
    fade_type        LowCardinality(Nullable(String)),

    -- Blue gem (Case Hardened only; exact sub-fields TBD until a live CH item
    -- is fetched — stored as JSON string until schema is confirmed)
    blue_gem         Nullable(String),

    -- CSFloat Float Appraiser reference block
    ref_base_price      Int32,
    ref_float_factor    Float32,
    ref_predicted_price Int32,
    ref_quantity        UInt32,
    ref_keychain_price  Int32 DEFAULT 0,

    -- Ingestion metadata
    _ingested_at     DateTime64(3, 'UTC'),
    _snapshot_date   Date
)
ENGINE = ReplacingMergeTree(_ingested_at)
PARTITION BY toYYYYMM(sold_at)
ORDER BY (market_hash_name, paint_index, id);
