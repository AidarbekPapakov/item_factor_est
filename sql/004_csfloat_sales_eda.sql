SELECT
    id,
    sold_at,
    price,
    ref_base_price,
    ref_predicted_price,
    market_hash_name,
    wear_name,
    is_stattrak,
    is_souvenir,
    float_value,
    length(stickers) AS n_stickers,
    _snapshot_date
FROM default.csfloat_sales FINAL