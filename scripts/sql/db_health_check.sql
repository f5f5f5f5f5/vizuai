-- DB health-check for ar_interior schema (post-subscriptions removal)
-- Usage:
-- 1) Cloud SQL Studio: paste and run section by section
-- 2) psql: psql "$DATABASE_URL" -f scripts/sql/db_health_check.sql

-- =====================================================================
-- SECTION A: Read-only integrity checks
-- =====================================================================

-- A1. Current Alembic revision
SELECT version_num FROM alembic_version;

-- A2. Required runtime tables exist
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'users',
    'designs',
    'promocodes',
    'payments',
    'promocode_usages',
    'billing_events',
    'billing_webhook_events'
  )
ORDER BY tablename;

-- A3. Required columns in billing/runtime tables
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'users',
    'payments',
    'promocodes',
    'promocode_usages',
    'billing_events',
    'billing_webhook_events'
  )
ORDER BY table_name, ordinal_position;

-- A4. Foreign key map
SELECT
  tc.table_name,
  kcu.column_name,
  ccu.table_name AS ref_table,
  ccu.column_name AS ref_column,
  tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.table_schema = tc.table_schema
WHERE tc.table_schema = 'public'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN (
    'designs',
    'payments',
    'promocode_usages',
    'billing_events'
  )
ORDER BY tc.table_name, tc.constraint_name;

-- A5. Index map
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'users',
    'designs',
    'promocodes',
    'payments',
    'promocode_usages',
    'billing_events',
    'billing_webhook_events'
  )
ORDER BY tablename, indexname;

-- A6. Quick runtime sanity for latest designs
SELECT
  id,
  mode,
  status,
  selected_image,
  score_render,
  score_fix,
  error_stage,
  pipeline_version,
  created_at
FROM designs
ORDER BY created_at DESC
LIMIT 20;

-- A7. Ensure legacy subscription tables are absent
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('subscriptions', 'subscription_plans', 'user_subscriptions')
ORDER BY tablename;

-- =====================================================================
-- SECTION B: Optional write smoke-check (ROLLBACK at the end)
-- Notes:
-- - Uses latest user from users table
-- - Inserts only into active billing tables, then rolls back
-- =====================================================================

BEGIN;

WITH
u AS (
  SELECT user_id
  FROM users
  ORDER BY created_at DESC
  LIMIT 1
),
seed AS (
  SELECT
    (
      substr(md5(random()::text || clock_timestamp()::text), 1, 8) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 9, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 13, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 17, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 21, 12)
    )::uuid AS promo_id,
    (
      substr(md5(random()::text || clock_timestamp()::text), 1, 8) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 9, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 13, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 17, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 21, 12)
    )::uuid AS pay_id,
    (
      substr(md5(random()::text || clock_timestamp()::text), 1, 8) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 9, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 13, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 17, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 21, 12)
    )::uuid AS usage_id,
    (
      substr(md5(random()::text || clock_timestamp()::text), 1, 8) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 9, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 13, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 17, 4) || '-' ||
      substr(md5(random()::text || clock_timestamp()::text), 21, 12)
    )::uuid AS event_id,
    to_char(clock_timestamp(), 'YYYYMMDDHH24MISS') AS sfx
),
promo AS (
  INSERT INTO promocodes (
    id, code_string, discount_type, discount_amount, code_amount, code_left, max_uses_per_user, is_active, created_at, updated_at
  )
  SELECT
    seed.promo_id,
    'SMOKE_' || seed.sfx,
    'fixed',
    10.00,
    100,
    100,
    1,
    true,
    now(),
    now()
  FROM seed
  RETURNING id
),
pay AS (
  INSERT INTO payments (
    id, user_id, promocode_id, price_original, discount_amount, price_final, currency, status, provider, provider_payment_id, credits_amount, created_at, paid_at
  )
  SELECT
    seed.pay_id,
    u.user_id,
    promo.id,
    99.00,
    10.00,
    89.00,
    'RUB',
    'paid',
    'smoke',
    'smoke_' || seed.sfx,
    1,
    now(),
    now()
  FROM seed, u, promo
  RETURNING id
),
usage_row AS (
  INSERT INTO promocode_usages (
    id, code_id, user_id, payment_id, status, redeemed_at, used_at
  )
  SELECT
    seed.usage_id,
    promo.id,
    u.user_id,
    pay.id,
    'redeemed',
    now(),
    now()
  FROM seed, promo, u, pay
  RETURNING id
)
INSERT INTO billing_events (
  id, provider, event_type, user_id, payment_id, provider_payment_id, currency, credits_amount, reason, created_at
)
SELECT
  seed.event_id,
  'smoke',
  'payment_applied',
  u.user_id,
  pay.id,
  'smoke_' || seed.sfx,
  'RUB',
  1,
  'smoke_write_check',
  now()
FROM seed, u, pay, usage_row;

-- Transaction-local inserted row counters
SELECT
  (SELECT count(*) FROM promocodes WHERE code_string LIKE 'SMOKE_%') AS promos,
  (SELECT count(*) FROM payments WHERE provider = 'smoke') AS smoke_payments,
  (SELECT count(*) FROM promocode_usages WHERE status = 'redeemed') AS redeemed_usages,
  (SELECT count(*) FROM billing_events WHERE provider = 'smoke') AS smoke_billing_events;

ROLLBACK;
