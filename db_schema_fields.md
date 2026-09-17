# DB Schema Fields

Этот файл фиксирует текущий baseline схемы БД.

Важно:
- web-first модель живёт вокруг `accounts`, `jobs`, `drafts`, `payments`, `billing_events`;
- legacy Telegram-модель всё ещё живёт вокруг `users`;
- часть таблиц обслуживает обе модели одновременно;
- если код и этот файл расходятся, приоритет у моделей в `models/` и свежих Alembic migration files.

## 1. Основные принципы

- `accounts` — web-аккаунты и их профили.
- `users` — legacy Telegram users.
- `designs` — общий результатовый артефакт и для web, и для legacy flows.
- баланс web не хранится одной колонкой в `accounts`; он считается из `payments` и `billing_events`.
- `design_projects` и отдельный PDF service больше не являются active runtime path.

## 2. Web account / auth tables

### `accounts`
- `id` UUID PK
- `status`
- `display_name`
- `primary_email`
- `primary_phone`
- `avatar_url`
- `marketing_opt_in`
- `locale`
- `timezone`
- `created_at`
- `updated_at`
- `last_seen_at`

### `account_identities`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `provider`
- `provider_user_id`
- `provider_email`
- `provider_phone`
- `is_primary`
- `is_verified`
- `created_at`
- `updated_at`

Unique:
- `(provider, provider_user_id)`

### `account_sessions`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `session_token_hash`
- `refresh_token_hash`
- `status`
- `user_agent`
- `ip_address`
- `device_meta_json`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`

### `account_magic_link_tokens`
- `id` UUID PK
- `account_id` FK -> `accounts.id`, nullable
- `email`
- `token_hash`
- `status`
- `redirect_path`
- `created_at`
- `expires_at`
- `used_at`
- `sent_at`

### `account_flow_events`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `event_type`
- `screen_key`
- `action_key`
- `source`
- `meta_json`
- `created_at`

### `public_site_events`
- `id` UUID PK
- `anon_id`
- `event_type`
- `screen_key`
- `action_key`
- `source`
- `path`
- `referrer`
- `meta_json`
- `created_at`

### `web_acquisition_attributions`
- `id` UUID PK
- `anon_id` unique
- `account_id` FK -> `accounts.id`, nullable
- `first_utm_source`
- `first_utm_medium`
- `first_utm_campaign`
- `first_utm_content`
- `first_utm_term`
- `first_landing_host`
- `first_landing_path`
- `first_referrer`
- `first_seen_at`
- `last_seen_at`
- `linked_at`
- `created_at`
- `updated_at`

## 3. Uploads / drafts

### `uploaded_files`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `purpose`
- `filename`
- `content_type`
- `size_bytes`
- `storage_key`
- `file_url`
- `status`
- `created_at`

Примечание:
- это канонический web-first слой пользовательских загрузок;
- lifecycle retention для user-facing contract сейчас ориентирован именно на долгоживущие `uploads/`.

### `upload_intents`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `purpose`
- `filename`
- `content_type`
- `size_bytes`
- `storage_key`
- `status`
- `expires_at`
- `completed_at`
- `file_id` FK -> `uploaded_files.id`, nullable
- `created_at`

### `design_drafts`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `source_file_id` FK -> `uploaded_files.id`, nullable
- `style_reference_file_id` FK -> `uploaded_files.id`, nullable
- `source_image_url`
- `prepared_image_url`
- `style_reference_image_url`
- `style_reference_enabled`
- `user_request`
- `settings_json`
- `estimated_units`
- `status`
- `created_at`
- `updated_at`

### `furniture_search_drafts`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `source_file_id` FK -> `uploaded_files.id`, nullable
- `source_image_url`
- `prepared_image_url`
- `user_request`
- `settings_json`
- `estimated_units`
- `status`
- `created_at`
- `updated_at`

## 4. Jobs / artifacts

### `jobs`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `job_type`
- `status`
- `draft_id`
- `draft_type`
- `result_ref_type`
- `result_ref_id`
- `error_code`
- `error_message`
- `error_stage`
- `units_reserved`
- `units_final`
- `provider_meta_json`
- `progress_meta_json`
- `created_at`
- `started_at`
- `ended_at`

### `designs`
- `id` UUID PK
- `user_id` FK -> `users.user_id`, nullable
- `account_id` FK -> `accounts.id`, nullable
- `original_image_url`
- `prepared_image_url`
- `render_image_url`
- `fix_image_url`
- `final_image_url`
- `style_reference_image_url`
- `style_reference_used`
- `style_reference_status`
- `selected_image`
- `user_request`
- `status`
- `error_message`
- `error_stage`
- `created_at`
- `ended_at`
- `duration_seconds`
- `cost_usd`
- `score_render`
- `score_fix`
- `providers_json`
- `debug_json`
- `pipeline_version`
- `mode`
- `units_spent`
- `job_id` FK -> `jobs.id`, nullable
- `draft_id` FK -> `design_drafts.id`, nullable
- `metadata` JSON (`metadata_json` в ORM)

Примечание:
- `designs` остаётся общей таблицей результатов для web и legacy bot flows.
- design result reuse/edit/download semantics завязаны не только на DB row, но и на доступность связанных storage objects в GCS.

## 5. Billing / payments / promo

### `checkout_sessions`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `provider`
- `status`
- `credits_amount`
- `currency`
- `amount_original`
- `discount_amount`
- `amount_final`
- `provider_checkout_id`
- `metadata_json`
- `created_at`
- `updated_at`
- `completed_at`
- `expires_at`

### `payments`
- `id` UUID PK
- `user_id` FK -> `users.user_id`, nullable
- `account_id` FK -> `accounts.id`, nullable
- `checkout_session_id` FK -> `checkout_sessions.id`, nullable
- `promocode_id` FK -> `promocodes.id`, nullable
- `price_original`
- `discount_amount`
- `price_final`
- `currency`
- `status`
- `provider`
- `provider_payment_id`
- `telegram_payment_charge_id`
- `credits_amount`
- `refund_reason`
- `created_at`
- `paid_at`
- `refunded_at`

### `billing_events`
- `id` UUID PK
- `provider`
- `event_type`
- `user_id` FK -> `users.user_id`, nullable
- `account_id` FK -> `accounts.id`, nullable
- `payment_id` FK -> `payments.id`, nullable
- `provider_payment_id`
- `telegram_payment_charge_id`
- `currency`
- `stars_amount`
- `provider_amount`
- `credits_amount`
- `reason`
- `meta_json`
- `created_at`

### `billing_webhook_events`
- `id` UUID PK
- `provider`
- `event_type`
- `idempotency_key`
- `status`
- `attempts`
- `order_id`
- `provider_payment_id`
- `payload_json`
- `last_error`
- `first_seen_at`
- `last_seen_at`
- `processed_at`
- `created_at`
- `updated_at`

Unique:
- `(provider, idempotency_key)`

### `promocodes`
- `id` UUID PK
- `code_string`
- `discount_type`
- `discount_amount`
- `code_amount`
- `code_left`
- `max_uses_per_user`
- `is_new_users_only`
- `starts_at`
- `ends_at`
- `is_active`
- `created_at`
- `updated_at`

### `promocode_usages`
- `id` UUID PK
- `code_id` FK -> `promocodes.id`
- `user_id` FK -> `users.user_id`, nullable
- `account_id` FK -> `accounts.id`, nullable
- `payment_id` FK -> `payments.id`, nullable
- `status`
- `reserved_at`
- `expires_at`
- `released_at`
- `redeemed_at`
- `release_reason`
- `credits_amount`
- `price_original`
- `discount_amount`
- `price_final`
- `used_at`

## 6. Idempotency / API support

### `api_idempotency_keys`
- `id` UUID PK
- `account_id` FK -> `accounts.id`
- `scope`
- `idempotency_key`
- `request_hash`
- `status`
- `response_status`
- `response_body`
- `created_at`
- `completed_at`

Unique:
- `(account_id, scope, idempotency_key)`

## 7. Legacy Telegram tables

### `users`
- `user_id` bigint PK
- `username`
- `first_name`
- `last_name`
- `is_active`
- `credits_status`
- `usage_left`
- `usage_count`
- `acquisition_source`
- `acquisition_recorded_at`
- `last_screen_key`
- `last_screen_at`
- `last_request_at`
- `created_at`
- `updated_at`

Примечание:
- `usage_left` — legacy Telegram balance field;
- для web balance source of truth уже другой: `payments`/`billing_events`.

### `user_flow_events`
- `id` UUID PK
- `user_id` FK -> `users.user_id`
- `event_type`
- `screen_key`
- `action_key`
- `source`
- `meta_json`
- `created_at`

## 8. Что уже не считать active schema path

В активном runtime больше не использовать как текущую product-модель:
- `design_projects` / `DesignProject` layer
- отдельный PDF service schema path

Если такие таблицы ещё физически остаются в прод-БД:
- это не означает, что код их ещё использует;
- перед удалением нужен отдельный schema cleanup rollout с migration plan.
