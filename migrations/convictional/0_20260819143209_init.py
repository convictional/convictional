from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient | None = None) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "organization" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "name" VARCHAR(255),
    "domain" VARCHAR(255) UNIQUE,
    "oidc_token" VARCHAR(255),
    "system_prompt" TEXT,
    "integrations" JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_organizatio_deleted_09e1f5" ON "organization" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_organizatio_domain_03ea98" ON "organization" ("domain");
CREATE TABLE IF NOT EXISTS "content" (
    "tags" JSONB NOT NULL,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "category" VARCHAR(255) NOT NULL,
    "source_id" TEXT NOT NULL,
    "source_url" TEXT NOT NULL,
    "content_type" VARCHAR(255) NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "allowed_user_ids" JSONB NOT NULL,
    "title" TEXT NOT NULL,
    "title_normalized" TEXT NOT NULL,
    "author" TEXT,
    "author_normalized" TEXT,
    "preview_content" TEXT,
    "preview_content_normalized" TEXT,
    "index_content" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "embedding" vector(1536) NOT NULL DEFAULT '[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]',
    "text_search" TSVECTOR,
    "last_indexed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lookup_key" TEXT,
    "lookup_priority" INT NOT NULL DEFAULT 0,
    "is_ai_excluded" BOOL NOT NULL DEFAULT False,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_content_organiz_45a37b" UNIQUE ("organization_id", "source_id")
);
CREATE INDEX IF NOT EXISTS "idx_content_text_se_a0edfa" ON "content" USING GIN ("text_search") WITH (fastupdate=off);
CREATE INDEX IF NOT EXISTS "idx_content_allowed_fb56eb" ON "content" USING GIN ("allowed_user_ids");
CREATE INDEX IF NOT EXISTS "idx_content_source__cc39d4" ON "content" ("source_id");
CREATE INDEX IF NOT EXISTS "idx_content_organiz_3fcc76" ON "content" ("organization_id", "sharing");
CREATE INDEX IF NOT EXISTS "idx_content_organiz_45a37b" ON "content" ("organization_id", "source_id" text_pattern_ops);
CREATE INDEX IF NOT EXISTS "idx_content_author__634336" ON "content" USING GIN ("author_normalized" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_content_embeddi_d59ccd" ON "content" USING HNSW ("embedding" vector_cosine_ops) WITH (m = 16, ef_construction = 64);
COMMENT ON COLUMN "content"."category" IS 'DOCUMENT: document\nACTIVITY: activity\nPERSON: person';
COMMENT ON COLUMN "content"."content_type" IS 'MEETING: meeting\nMEETING_TRANSCRIPT: meeting_transcript\nPOST: post\nPOST_COMMENT: post_comment\nGOAL_COMMENT: goal_comment\nUSER: user\nEMAIL_CONTACT: email_contact\nDOCUMENT: document\nGOAL: goal\nDECISION: decision\nFILE: file\nEMAIL_THREAD: email_thread\nSLACK_MESSAGE: slack_message\nCHAT: chat\nCHAT_HISTORY: chat_history';
COMMENT ON COLUMN "content"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
COMMENT ON COLUMN "content"."title" IS 'protected_column';
COMMENT ON COLUMN "content"."title_normalized" IS 'protected_column';
COMMENT ON COLUMN "content"."preview_content" IS 'protected_column';
COMMENT ON COLUMN "content"."preview_content_normalized" IS 'protected_column';
COMMENT ON COLUMN "content"."index_content" IS 'protected_column';
COMMENT ON COLUMN "content"."text_search" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "group" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "name" TEXT NOT NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_group_deleted_10126a" ON "group" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_group_organiz_15f4b4" ON "group" ("organization_id");
CREATE TABLE IF NOT EXISTS "filereference" (
    "id" UUID NOT NULL PRIMARY KEY,
    "key" VARCHAR(500) NOT NULL,
    "filename" VARCHAR(500) NOT NULL,
    "content_type" VARCHAR(100) NOT NULL,
    "metadata" JSONB,
    "byte_size" BIGINT NOT NULL DEFAULT 0,
    "checksum" VARCHAR(255) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "user" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "email" VARCHAR(255) NOT NULL UNIQUE,
    "has_verified_email" BOOL NOT NULL DEFAULT False,
    "name" VARCHAR(255),
    "oauth_picture" VARCHAR(2048),
    "last_logged_in_at" TIMESTAMPTZ,
    "last_seen_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_logout_at" TIMESTAMPTZ,
    "bio" TEXT,
    "signup_reason" TEXT,
    "time_zone" VARCHAR(255),
    "push_working_hours_start" TIME,
    "push_working_hours_end" TIME,
    "is_admin" BOOL NOT NULL DEFAULT False,
    "integrations" JSONB NOT NULL,
    "onboarding_mailbox_sync_started_at" TIMESTAMPTZ,
    "onboarding_mailbox_sync_completed_at" TIMESTAMPTZ,
    "avatar_file_id" UUID REFERENCES "filereference" ("id") ON DELETE SET NULL,
    "invited_by_id" UUID REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_user_deleted_80297f" ON "user" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_user_email_1b4f1c" ON "user" ("email");
CREATE INDEX IF NOT EXISTS "idx_user_organiz_cc3490" ON "user" ("organization_id");
CREATE TABLE IF NOT EXISTS "groupmember" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "group_id" UUID NOT NULL REFERENCES "group" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_groupmember_group_i_b5027e" UNIQUE ("group_id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_groupmember_group_i_b5027e" ON "groupmember" ("group_id", "user_id");
CREATE TABLE IF NOT EXISTS "meetingcollection" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_meetingcoll_organiz_ec5893" ON "meetingcollection" ("organization_id");
CREATE TABLE IF NOT EXISTS "workspace" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "resource_gid" VARCHAR(500) NOT NULL UNIQUE,
    "sharing" VARCHAR(12) NOT NULL DEFAULT 'private',
    "assignee_id" UUID REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "workspace"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "collaborator" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(255) NOT NULL DEFAULT 'approved',
    "added_by_id" UUID REFERENCES "user" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_collaborato_workspa_b06c3e" UNIQUE ("workspace_id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_collaborato_workspa_b06c3e" ON "collaborator" ("workspace_id", "user_id");
CREATE INDEX IF NOT EXISTS "idx_collaborato_user_id_f15399" ON "collaborator" ("user_id", "workspace_id");
COMMENT ON COLUMN "collaborator"."status" IS 'PENDING: pending\nAPPROVED: approved';
CREATE TABLE IF NOT EXISTS "event" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "recordable_id" UUID NOT NULL,
    "recordable_type" VARCHAR(500) NOT NULL,
    "action" VARCHAR(255) NOT NULL,
    "details" JSONB NOT NULL,
    "creator_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_event_recorda_290e26" ON "event" ("recordable_type", "recordable_id");
CREATE INDEX IF NOT EXISTS "idx_event_workspa_87f974" ON "event" ("workspace_id", "created_at");
COMMENT ON COLUMN "event"."action" IS 'POST_CREATED: post_created\nPOST_ANNOUNCED: post_announced\nPOST_COMMENTED: post_commented\nPOST_PINNED: post_pinned\nPOST_DECIDED: post_decided\nADDED_COLLABORATOR: added_collaborator\nREMOVED_COLLABORATOR: removed_collaborator\nREQUESTED_COLLABORATOR_ACCESS: requested_collaborator_access\nCOMMENTED: commented\nEMAIL_THREAD_COMMENT_EDITED: email_thread_comment_edited\nEMAIL_THREAD_COMMENT_DELETED: email_thread_comment_deleted\nDRAFT_SCHEDULED: draft_scheduled\nDRAFT_UNSCHEDULED: draft_unscheduled\nGOAL_CREATED: goal_created\nGOAL_UPDATED: goal_updated\nGOAL_CLOSED: goal_closed\nGOAL_REACTIVATED: goal_reactivated\nGOAL_ACTIVATED: goal_activated\nGOAL_COMPLETED: goal_completed\nGOAL_DELETED: goal_deleted\nGOAL_COMMENTED: goal_commented\nGOAL_UPDATE_POSTED: goal_update_posted\nGOAL_UPDATE_REQUESTED: goal_update_requested\nMEETING_UPDATED: meeting_updated\nMEETING_DELETED: meeting_deleted\nMEETING_PROCESSED: meeting_processed\nMEETING_AGENDA_UPDATED: meeting_agenda_updated\nDOCUMENT_COMMENTED: document_commented\nUPDATED_SHARING: updated_sharing\nASSIGNED: assigned\nUNASSIGNED: unassigned\nDECIDED: decided\nCHAT_MESSAGE_CREATED: chat_message_created\nCHAT_MESSAGE_EDITED: chat_message_edited\nCHAT_MESSAGE_DELETED: chat_message_deleted\nCHAT_COLLABORATOR_ADDED: chat_collaborator_added\nCHAT_COLLABORATOR_REMOVED: chat_collaborator_removed\nCHAT_RENAMED: chat_renamed';
CREATE TABLE IF NOT EXISTS "goal" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "position" INT NOT NULL DEFAULT 0,
    "closed_at" TIMESTAMPTZ,
    "completed_at" TIMESTAMPTZ,
    "deleted_at" TIMESTAMPTZ,
    "title" TEXT,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'organization',
    "description" TEXT NOT NULL,
    "target_date" DATE,
    "start_date" DATE,
    "activated_at" TIMESTAMPTZ,
    "status" VARCHAR(255) NOT NULL DEFAULT 'on_track',
    "progress" DOUBLE PRECISION,
    "planning_list_name" TEXT,
    "extras" JSONB NOT NULL,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "group_id" UUID REFERENCES "group" ("id") ON DELETE SET NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "owner_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL,
    "parent_id" UUID REFERENCES "goal" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION
);
CREATE INDEX IF NOT EXISTS "idx_goal_deleted_9091a4" ON "goal" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_goal_organiz_70db37" ON "goal" ("organization_id");
CREATE INDEX IF NOT EXISTS "idx_goal_parent__c43481" ON "goal" ("parent_id");
CREATE INDEX IF NOT EXISTS "idx_goal_organiz_471e7d" ON "goal" ("organization_id", "activated_at");
CREATE INDEX IF NOT EXISTS "idx_goal_organiz_d14805" ON "goal" ("organization_id", "closed_at");
CREATE INDEX IF NOT EXISTS "idx_goal_organiz_a05047" ON "goal" ("organization_id", "parent_id", "activated_at", "closed_at");
COMMENT ON COLUMN "goal"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
COMMENT ON COLUMN "goal"."status" IS 'ON_TRACK: on_track\nAT_RISK: at_risk\nOFF_TRACK: off_track';
CREATE TABLE IF NOT EXISTS "goalalignment" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content_indexed_at" TIMESTAMPTZ NOT NULL,
    "signal" VARCHAR(255) NOT NULL,
    "alignment_score" DOUBLE PRECISION NOT NULL,
    "description" TEXT NOT NULL,
    "content_id" UUID NOT NULL REFERENCES "content" ("id") ON DELETE CASCADE,
    "created_by_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL,
    "goal_id" UUID NOT NULL REFERENCES "goal" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "pinned_by_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_goalalignme_content_6189ea" UNIQUE ("content_id", "goal_id", "content_indexed_at")
);
CREATE INDEX IF NOT EXISTS "idx_goalalignme_deleted_55732a" ON "goalalignment" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_goalalignme_goal_id_487e3b" ON "goalalignment" ("goal_id");
CREATE INDEX IF NOT EXISTS "idx_goalalignme_organiz_58e5f9" ON "goalalignment" ("organization_id");
CREATE INDEX IF NOT EXISTS "idx_goalalignme_organiz_dd7889" ON "goalalignment" ("organization_id", "goal_id");
COMMENT ON COLUMN "goalalignment"."signal" IS 'STRONG: strong\nMEDIUM: medium\nWEAK: weak';
CREATE TABLE IF NOT EXISTS "goalupdate" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "closed_at" TIMESTAMPTZ,
    "completed_at" TIMESTAMPTZ,
    "status" VARCHAR(255) NOT NULL,
    "progress" DOUBLE PRECISION,
    "question_text" TEXT NOT NULL,
    "answer_text" TEXT,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "goal_id" UUID NOT NULL REFERENCES "goal" ("id") ON DELETE CASCADE,
    "requested_by_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_goalupdate_goal_id_b26ab5" ON "goalupdate" ("goal_id");
CREATE INDEX IF NOT EXISTS "idx_goalupdate_creator_2279a4" ON "goalupdate" ("creator_id");
CREATE INDEX IF NOT EXISTS "idx_goalupdate_request_cc234e" ON "goalupdate" ("requested_by_id");
COMMENT ON COLUMN "goalupdate"."status" IS 'ON_TRACK: on_track\nAT_RISK: at_risk\nOFF_TRACK: off_track';
CREATE TABLE IF NOT EXISTS "mailboxentry" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "preview" TEXT NOT NULL,
    "last_comment" TEXT,
    "is_shared" BOOL NOT NULL DEFAULT False,
    "last_activity_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "labels" JSONB NOT NULL,
    "resource_gid" VARCHAR(500) NOT NULL,
    "snoozed_until" TIMESTAMPTZ,
    "workspace_attachment_count" INT NOT NULL DEFAULT 0,
    "is_preview_comment" BOOL NOT NULL DEFAULT False,
    "is_ai_excluded" BOOL NOT NULL DEFAULT False,
    "read_at" TIMESTAMPTZ,
    "assignee_id" UUID REFERENCES "user" ("id") ON DELETE CASCADE,
    "last_comment_author_id" UUID REFERENCES "user" ("id") ON DELETE CASCADE,
    "last_event_id" UUID REFERENCES "event" ("id") ON DELETE SET NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "owner_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_mailboxentr_resourc_f308a4" UNIQUE ("resource_gid", "owner_id")
);
CREATE INDEX IF NOT EXISTS "idx_mailboxentr_deleted_5a8d5c" ON "mailboxentry" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_mailboxentr_owner_i_8af666" ON "mailboxentry" ("owner_id", "last_activity_at");
CREATE INDEX IF NOT EXISTS "idx_mailboxentr_labels_e5fed7" ON "mailboxentry" USING GIN ("labels");
COMMENT ON COLUMN "mailboxentry"."title" IS 'protected_column';
COMMENT ON COLUMN "mailboxentry"."preview" IS 'protected_column';
COMMENT ON COLUMN "mailboxentry"."last_comment" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "meeting" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "scheduled_at" TIMESTAMPTZ,
    "scheduled_end_at" TIMESTAMPTZ,
    "summary" TEXT,
    "organizer" JSONB,
    "attendees" JSONB NOT NULL,
    "transcript" TEXT,
    "processed_transcript" JSONB,
    "chat_messages" JSONB NOT NULL,
    "ical_uid" TEXT,
    "provider_meeting_id" TEXT,
    "count_occurrences" INT NOT NULL DEFAULT 1,
    "conferencing_url" TEXT,
    "agenda" TEXT,
    "manually_created_at" TIMESTAMPTZ,
    "did_recording_fail" BOOL NOT NULL DEFAULT False,
    "collection_auto_assigned" BOOL NOT NULL DEFAULT False,
    "collection_id" UUID REFERENCES "meetingcollection" ("id") ON DELETE SET NULL,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "recording_id" UUID REFERENCES "filereference" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION
);
CREATE INDEX IF NOT EXISTS "idx_meeting_deleted_5eddf8" ON "meeting" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_meeting_schedul_851d84" ON "meeting" ("scheduled_at");
CREATE INDEX IF NOT EXISTS "idx_meeting_provide_28c72f" ON "meeting" ("provider_meeting_id", "scheduled_at") WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS "idx_meeting_organiz_ce5d78" ON "meeting" ("organization_id", "sharing", "creator_id") WHERE deleted_at IS NULL;
COMMENT ON COLUMN "meeting"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "attachment" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "summary" TEXT,
    "comment_gid" VARCHAR(500),
    "claim_id" UUID,
    "file_id" UUID NOT NULL REFERENCES "filereference" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "workspace_id" UUID REFERENCES "workspace" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_attachment_workspa_0e2fca" ON "attachment" ("workspace_id");
CREATE INDEX IF NOT EXISTS "idx_attachment_comment_ebd41a" ON "attachment" ("comment_gid", "claim_id", "created_at");
CREATE TABLE IF NOT EXISTS "decision" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "comment_gid" VARCHAR(500) NOT NULL UNIQUE,
    "decided_at" TIMESTAMPTZ NOT NULL,
    "decided_by_id" UUID REFERENCES "user" ("id") ON DELETE SET NULL,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_decision_workspa_02ffa2" ON "decision" ("workspace_id", "decided_at");
CREATE TABLE IF NOT EXISTS "post" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'organization',
    "is_announcement" BOOL NOT NULL DEFAULT False,
    "pinned_at" TIMESTAMPTZ,
    "published_at" TIMESTAMPTZ,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "group_id" UUID REFERENCES "group" ("id") ON DELETE SET NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION
);
CREATE INDEX IF NOT EXISTS "idx_post_deleted_1b7832" ON "post" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_post_organiz_d14aec" ON "post" ("organization_id", "published_at");
COMMENT ON COLUMN "post"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "postgroupmute" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "group_id" UUID NOT NULL REFERENCES "group" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_postgroupmu_user_id_64edaf" UNIQUE ("user_id", "group_id")
);
CREATE TABLE IF NOT EXISTS "document" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION
);
CREATE INDEX IF NOT EXISTS "idx_document_deleted_b64b7d" ON "document" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_document_organiz_6b8066" ON "document" ("organization_id");
COMMENT ON COLUMN "document"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "emailcontact" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "external_contact_id" TEXT,
    "email" TEXT NOT NULL,
    "name" TEXT,
    "photo_url" TEXT,
    "last_synced_at" TIMESTAMPTZ,
    "last_interacted_at" TIMESTAMPTZ,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_emailcontac_email_8f960e" UNIQUE ("email", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_emailcontac_email_7c6254" ON "emailcontact" ("email");
CREATE INDEX IF NOT EXISTS "idx_emailcontac_user_id_582424" ON "emailcontact" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_emailcontac_user_id_e183d4" ON "emailcontact" ("user_id", "name", "email");
CREATE INDEX IF NOT EXISTS "idx_emailcontac_user_id_3053a1" ON "emailcontact" ("user_id", "last_interacted_at");
CREATE INDEX IF NOT EXISTS "idx_emailcontact_name_gin" ON "emailcontact" USING GIN ("name" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_emailcontact_email_gin" ON "emailcontact" USING GIN ("email" gin_trgm_ops);
CREATE TABLE IF NOT EXISTS "emailthread" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "labels" JSONB NOT NULL,
    "deleted_at" TIMESTAMPTZ,
    "title" TEXT NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "external_thread_id" TEXT,
    "is_decrypted" BOOL NOT NULL DEFAULT True,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION,
    CONSTRAINT "uid_emailthread_externa_41d9ba" UNIQUE ("external_thread_id", "creator_id")
);
CREATE INDEX IF NOT EXISTS "idx_emailthread_deleted_dce56b" ON "emailthread" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_emailthread_is_decr_38c988" ON "emailthread" ("is_decrypted");
COMMENT ON COLUMN "emailthread"."title" IS 'protected_column';
COMMENT ON COLUMN "emailthread"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "mailboxview" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "view_request" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "layout" VARCHAR(16) NOT NULL DEFAULT 'grouped',
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_mailboxview_user_id_6646d3" ON "mailboxview" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_mailboxview_organiz_102fea" ON "mailboxview" ("organization_id");
COMMENT ON COLUMN "mailboxview"."layout" IS 'GROUPED: grouped\nRANKED: ranked';
CREATE TABLE IF NOT EXISTS "emailmessage" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "labels" JSONB NOT NULL,
    "deleted_at" TIMESTAMPTZ,
    "external_message_id" TEXT,
    "external_thread_id" TEXT,
    "external_history_id" TEXT,
    "message_id" TEXT,
    "message_type" VARCHAR(255) NOT NULL,
    "subject" TEXT,
    "sender" TEXT,
    "to" JSONB NOT NULL,
    "cc" JSONB NOT NULL,
    "bcc" JSONB NOT NULL,
    "body_plain" TEXT,
    "body_html" TEXT,
    "body_markdown" TEXT,
    "headers_list" JSONB,
    "preview" TEXT,
    "received_at" TIMESTAMPTZ,
    "sent_at" TIMESTAMPTZ,
    "sent_from_convictional_at" TIMESTAMPTZ,
    "scheduled_for" TIMESTAMPTZ,
    "scheduled_send_job_id" UUID,
    "in_reply_to_id" UUID REFERENCES "emailmessage" ("id") ON DELETE SET NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "raw_data_file_id" UUID REFERENCES "filereference" ("id") ON DELETE CASCADE,
    "thread_id" UUID NOT NULL REFERENCES "emailthread" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_emailmessag_externa_ff34a7" UNIQUE ("external_message_id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_emailmessag_deleted_1d7d8b" ON "emailmessage" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_message_5a47cf" ON "emailmessage" ("message_id", "user_id");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_externa_aec3e6" ON "emailmessage" ("external_message_id", "message_id", "deleted_at", "user_id", "received_at", "created_at");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_thread__05c579" ON "emailmessage" ("thread_id", "message_type");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_externa_8cf762" ON "emailmessage" ("external_thread_id");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_receive_1a0849" ON "emailmessage" ("received_at", "created_at");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_organiz_43a03f" ON "emailmessage" ("organization_id");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_deleted_261fc6" ON "emailmessage" ("deleted_at", "user_id", "message_type", "received_at");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_user_id_2667a7" ON "emailmessage" ("user_id", "message_type", "received_at") WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS "idx_emailmessag_in_repl_4a6ee9" ON "emailmessage" ("in_reply_to_id");
CREATE INDEX IF NOT EXISTS "idx_emailmessag_schedul_0373b0" ON "emailmessage" ("scheduled_for") WHERE scheduled_for IS NOT NULL;
COMMENT ON COLUMN "emailmessage"."message_type" IS 'RECEIVED: received\nSENT: sent\nDRAFT: draft\nSENDING: sending';
COMMENT ON COLUMN "emailmessage"."subject" IS 'protected_column';
COMMENT ON COLUMN "emailmessage"."body_plain" IS 'protected_column';
COMMENT ON COLUMN "emailmessage"."body_html" IS 'protected_column';
COMMENT ON COLUMN "emailmessage"."body_markdown" IS 'protected_column';
COMMENT ON COLUMN "emailmessage"."headers_list" IS 'protected_column';
COMMENT ON COLUMN "emailmessage"."preview" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "emailattachment" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "external_attachment_id" TEXT,
    "content_id" TEXT,
    "is_inline" BOOL NOT NULL DEFAULT False,
    "is_referenced_in_html" BOOL NOT NULL DEFAULT False,
    "email_message_id" UUID NOT NULL REFERENCES "emailmessage" ("id") ON DELETE CASCADE,
    "file_id" UUID NOT NULL REFERENCES "filereference" ("id") ON DELETE CASCADE,
    "thread_id" UUID NOT NULL REFERENCES "emailthread" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_emailattach_externa_a472b8" UNIQUE ("external_attachment_id", "email_message_id")
);
CREATE INDEX IF NOT EXISTS "idx_emailattach_thread__83408a" ON "emailattachment" ("thread_id");
CREATE INDEX IF NOT EXISTS "idx_emailattach_email_m_b87ef0" ON "emailattachment" ("email_message_id");
CREATE INDEX IF NOT EXISTS "idx_emailattach_thread__5c0134" ON "emailattachment" ("thread_id", "email_message_id");
CREATE TABLE IF NOT EXISTS "quicklink" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "label" TEXT NOT NULL,
    "url" TEXT,
    "open_in_new_tab" BOOL NOT NULL DEFAULT False,
    "owner_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "scheduledresearch" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "prompt" TEXT NOT NULL,
    "topic_prompt" TEXT,
    "formatting_prompt" TEXT,
    "preparation_failed_at" TIMESTAMPTZ,
    "schedule_cron" VARCHAR(255) NOT NULL,
    "sources" JSONB NOT NULL,
    "last_delivered_at" TIMESTAMPTZ,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_scheduledre_deleted_eefa13" ON "scheduledresearch" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_scheduledre_creator_9eb24c" ON "scheduledresearch" ("creator_id");
CREATE TABLE IF NOT EXISTS "contentlookup" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "source_id" TEXT NOT NULL,
    "source_url" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "title_normalized" TEXT NOT NULL,
    "author" TEXT,
    "author_normalized" TEXT,
    "preview_content_normalized" TEXT,
    "content_type" VARCHAR(255) NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "allowed_user_ids" JSONB NOT NULL,
    "metadata" JSONB NOT NULL,
    "lookup_key" TEXT,
    "lookup_priority" INT NOT NULL DEFAULT 0,
    -- The model declares this generated=True; the expression lives here because the ORM
    -- cannot express generated-column DDL.
    "lookup_search" TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('english', COALESCE(title_normalized, '')), 'A') || setweight(to_tsvector('english', COALESCE(author_normalized, '')), 'B') || setweight(to_tsvector('english', left(COALESCE(preview_content_normalized, ''), 1000)), 'C')) STORED,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "content_id" UUID NOT NULL UNIQUE REFERENCES "content" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_contentlook_lookup__835526" ON "contentlookup" USING GIN ("lookup_search") WITH (fastupdate=off);
CREATE INDEX IF NOT EXISTS "idx_contentlook_allowed_bc3a26" ON "contentlookup" USING GIN ("allowed_user_ids");
CREATE INDEX IF NOT EXISTS "idx_contentlook_author__1043d7" ON "contentlookup" USING GIN ("author_normalized" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_contentlook_organiz_9b244b" ON "contentlookup" ("organization_id", "sharing");
COMMENT ON COLUMN "contentlookup"."title" IS 'protected_column';
COMMENT ON COLUMN "contentlookup"."title_normalized" IS 'protected_column';
COMMENT ON COLUMN "contentlookup"."preview_content_normalized" IS 'protected_column';
COMMENT ON COLUMN "contentlookup"."content_type" IS 'MEETING: meeting\nMEETING_TRANSCRIPT: meeting_transcript\nPOST: post\nPOST_COMMENT: post_comment\nGOAL_COMMENT: goal_comment\nUSER: user\nEMAIL_CONTACT: email_contact\nDOCUMENT: document\nGOAL: goal\nDECISION: decision\nFILE: file\nEMAIL_THREAD: email_thread\nSLACK_MESSAGE: slack_message\nCHAT: chat\nCHAT_HISTORY: chat_history';
COMMENT ON COLUMN "contentlookup"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
COMMENT ON COLUMN "contentlookup"."lookup_search" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "lookupsearchmetric" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "query" TEXT NOT NULL,
    "result_count" INT NOT NULL DEFAULT 0,
    "result_ids" JSONB NOT NULL,
    "clicked_content_id" UUID,
    "clicked_position" INT,
    "filter_author_gid" TEXT,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "linkpreview" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "url" TEXT NOT NULL,
    "url_hash" VARCHAR(64) NOT NULL UNIQUE,
    "status" VARCHAR(255) NOT NULL DEFAULT 'failed',
    "type" VARCHAR(255) NOT NULL DEFAULT 'link',
    "title" TEXT,
    "description" TEXT,
    "image_url" TEXT,
    "site_name" TEXT,
    "oembed_html" TEXT,
    "fetched_at" TIMESTAMPTZ,
    "expires_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_linkpreview_url_has_24aa82" ON "linkpreview" ("url_hash");
COMMENT ON COLUMN "linkpreview"."status" IS 'READY: ready\nFAILED: failed';
COMMENT ON COLUMN "linkpreview"."type" IS 'LINK: link\nVIDEO: video';
CREATE TABLE IF NOT EXISTS "goalcomment" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "closed_at" TIMESTAMPTZ,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "goal_id" UUID NOT NULL REFERENCES "goal" ("id") ON DELETE CASCADE,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "parent_id" UUID REFERENCES "goalcomment" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_goalcomment_deleted_e921df" ON "goalcomment" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_goalcomment_goal_id_35a502" ON "goalcomment" ("goal_id");
COMMENT ON COLUMN "goalcomment"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "postcomment" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "parent_id" UUID REFERENCES "postcomment" ("id") ON DELETE CASCADE,
    "post_id" UUID NOT NULL REFERENCES "post" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_postcomment_deleted_d799a8" ON "postcomment" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_postcomment_post_id_7756f8" ON "postcomment" ("post_id");
COMMENT ON COLUMN "postcomment"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "postdraftcomment" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "comment_mark_id" VARCHAR(36) NOT NULL,
    "quoted_text" TEXT NOT NULL,
    "resolved_at" TIMESTAMPTZ,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "post_id" UUID NOT NULL REFERENCES "post" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_postdraftco_post_id_7b710d" ON "postdraftcomment" ("post_id");
COMMENT ON COLUMN "postdraftcomment"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "documentcomment" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "comment_mark_id" VARCHAR(36) NOT NULL,
    "quoted_text" TEXT NOT NULL,
    "resolved_at" TIMESTAMPTZ,
    "document_id" UUID NOT NULL REFERENCES "document" ("id") ON DELETE CASCADE,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_documentcom_documen_9a0034" ON "documentcomment" ("document_id");
COMMENT ON COLUMN "documentcomment"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "emailthreadcomment" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "email_thread_id" UUID NOT NULL REFERENCES "emailthread" ("id") ON DELETE CASCADE,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "reply_to_id" UUID REFERENCES "emailthreadcomment" ("id") ON DELETE SET NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_emailthread_deleted_02d7eb" ON "emailthreadcomment" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_emailthread_email_t_e4234d" ON "emailthreadcomment" ("email_thread_id");
CREATE INDEX IF NOT EXISTS "idx_emailthread_reply_t_bd7b36" ON "emailthreadcomment" ("reply_to_id");
COMMENT ON COLUMN "emailthreadcomment"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "mention" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "recordable_gid" VARCHAR(500) NOT NULL,
    "content" TEXT NOT NULL,
    "delivered_at" TIMESTAMPTZ,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "event_id" UUID REFERENCES "event" ("id") ON DELETE SET NULL,
    "mentioned_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_mention_workspa_756cef" ON "mention" ("workspace_id");
CREATE TABLE IF NOT EXISTS "pushsubscription" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "endpoint" TEXT NOT NULL,
    "protocol" VARCHAR(16) NOT NULL DEFAULT 'web_push',
    "p256dh_key" TEXT,
    "auth_key" TEXT,
    "user_agent" TEXT,
    "platform" TEXT,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_pushsubscri_deleted_5fc863" ON "pushsubscription" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_pushsubscri_user_id_ff9a40" ON "pushsubscription" ("user_id");
COMMENT ON COLUMN "pushsubscription"."protocol" IS 'WEB_PUSH: web_push\nAPNS: apns';
COMMENT ON COLUMN "pushsubscription"."auth_key" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "notification" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "channel" VARCHAR(5) NOT NULL DEFAULT 'email',
    "device_label_snapshot" TEXT,
    "delivered_at" TIMESTAMPTZ,
    "device_id" UUID REFERENCES "pushsubscription" ("id") ON DELETE SET NULL,
    "event_id" UUID NOT NULL REFERENCES "event" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_notificatio_event_i_f5db13" UNIQUE ("event_id", "user_id", "channel", "device_id")
);
CREATE INDEX IF NOT EXISTS "idx_notificatio_device__497d0c" ON "notification" ("device_id");
CREATE INDEX IF NOT EXISTS "idx_notificatio_user_id_fe0336" ON "notification" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_notificatio_deliver_537f4d" ON "notification" ("delivered_at");
COMMENT ON COLUMN "notification"."channel" IS 'EMAIL: email\nPUSH: push';
CREATE TABLE IF NOT EXISTS "subscription" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "level" VARCHAR(13) NOT NULL DEFAULT 'relevant_only',
    "subscriber_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_subscriptio_subscri_223ccb" UNIQUE ("subscriber_id", "workspace_id")
);
CREATE INDEX IF NOT EXISTS "idx_subscriptio_workspa_e2f512" ON "subscription" ("workspace_id", "subscriber_id");
COMMENT ON COLUMN "subscription"."level" IS 'ALL: all\nBROADCASTS: broadcasts\nRELEVANT_ONLY: relevant_only';
CREATE TABLE IF NOT EXISTS "subscriptionpreference" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "default_level" VARCHAR(13) NOT NULL DEFAULT 'relevant_only',
    "resource_type" VARCHAR(255) NOT NULL,
    "subscriber_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_subscriptio_subscri_69e909" UNIQUE ("subscriber_id", "resource_type")
);
CREATE INDEX IF NOT EXISTS "idx_subscriptio_subscri_69e909" ON "subscriptionpreference" ("subscriber_id", "resource_type");
COMMENT ON COLUMN "subscriptionpreference"."default_level" IS 'ALL: all\nBROADCASTS: broadcasts\nRELEVANT_ONLY: relevant_only';
CREATE TABLE IF NOT EXISTS "visit" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "last_visit_at" TIMESTAMPTZ,
    "last_event_id" UUID REFERENCES "event" ("id") ON DELETE SET NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL REFERENCES "workspace" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_visit_user_id_2d9f49" UNIQUE ("user_id", "workspace_id")
);
COMMENT ON TABLE "visit" IS 'The single per-(user, workspace) read-state primitive.';
CREATE TABLE IF NOT EXISTS "livedocumentupdate" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "topic_name" VARCHAR(500) NOT NULL,
    "update_data" BYTEA NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_livedocumen_topic_n_522339" ON "livedocumentupdate" ("topic_name");
CREATE INDEX IF NOT EXISTS "idx_livedocumen_topic_n_f2ae71" ON "livedocumentupdate" ("topic_name", "created_at");
CREATE TABLE IF NOT EXISTS "chat" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "last_message_at" TIMESTAMPTZ,
    "collaborators_hash" VARCHAR(64),
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "group_id" UUID REFERENCES "group" ("id") ON DELETE CASCADE,
    "last_message_id" UUID,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE,
    "workspace_id" UUID NOT NULL UNIQUE REFERENCES "workspace" ("id") ON DELETE NO ACTION,
    CONSTRAINT "uid_chat_group_i_1826ff" UNIQUE ("group_id")
);
CREATE INDEX IF NOT EXISTS "idx_chat_deleted_a3e46b" ON "chat" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_chat_organiz_f496b6" ON "chat" ("organization_id");
CREATE INDEX IF NOT EXISTS "idx_chat_organiz_40a1d2" ON "chat" ("organization_id", "last_message_at");
COMMENT ON COLUMN "chat"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
CREATE TABLE IF NOT EXISTS "chatmessage" (
    "deleted_at" TIMESTAMPTZ,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content" TEXT NOT NULL,
    "reactions" JSONB NOT NULL,
    "chat_id" UUID NOT NULL REFERENCES "chat" ("id") ON DELETE CASCADE,
    "link_preview_id" UUID REFERENCES "linkpreview" ("id") ON DELETE SET NULL,
    "reply_to_id" UUID REFERENCES "chatmessage" ("id") ON DELETE SET NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_chatmessage_deleted_fbc0ee" ON "chatmessage" ("deleted_at");
CREATE INDEX IF NOT EXISTS "idx_chatmessage_chat_id_3e405a" ON "chatmessage" ("chat_id", "created_at");
COMMENT ON COLUMN "chatmessage"."content" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "emailalias" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "address" VARCHAR(255) NOT NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_emailalias_address_7ad402" UNIQUE ("address", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_emailalias_address_c3a446" ON "emailalias" ("address");
CREATE INDEX IF NOT EXISTS "idx_emailalias_user_id_f379e3" ON "emailalias" ("user_id");
CREATE TABLE IF NOT EXISTS "oauthtoken" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "provider" VARCHAR(255) NOT NULL,
    "client_id" VARCHAR(255),
    "access_token" TEXT NOT NULL,
    "refresh_token" TEXT,
    "scope" TEXT NOT NULL,
    "expires_at" TIMESTAMPTZ,
    "is_decrypted" BOOL NOT NULL DEFAULT True,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_oauthtoken_user_id_4a1894" ON "oauthtoken" ("user_id", "provider", "client_id");
CREATE INDEX IF NOT EXISTS "idx_oauthtoken_is_decr_fb52d6" ON "oauthtoken" ("is_decrypted");
COMMENT ON COLUMN "oauthtoken"."provider" IS 'GOOGLE: google\nMICROSOFT: microsoft\nSLACK: slack\nTESTING: testing';
COMMENT ON COLUMN "oauthtoken"."access_token" IS 'protected_column';
COMMENT ON COLUMN "oauthtoken"."refresh_token" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "organizationupdatesconfiguration" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "update_schedule" TEXT,
    "frequency" VARCHAR(255) NOT NULL DEFAULT 'weekly',
    "goal_update_question" TEXT NOT NULL,
    "organization_id" UUID NOT NULL UNIQUE REFERENCES "organization" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "organizationupdatesconfiguration"."frequency" IS 'WEEKLY: weekly\nMONTHLY: monthly';
CREATE TABLE IF NOT EXISTS "gmailaccount" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "email" TEXT NOT NULL,
    "history_id" TEXT NOT NULL,
    "synced_history_id" TEXT,
    "last_sync_at" TIMESTAMPTZ,
    "watch_expires_at" TIMESTAMPTZ,
    "last_push_received_at" TIMESTAMPTZ,
    "last_auth_error" TEXT,
    "last_auth_errored_at" TIMESTAMPTZ,
    "contacts_sync_token" TEXT,
    "other_contacts_sync_token" TEXT,
    "contacts_last_synced_at" TIMESTAMPTZ,
    "contacts_sync_status" VARCHAR(24),
    "onboarding_mailbox_sync_started_at" TIMESTAMPTZ,
    "onboarding_mailbox_sync_completed_at" TIMESTAMPTZ,
    "history_sync_locked_at" TIMESTAMPTZ,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_gmailaccoun_user_id_98b824" UNIQUE ("user_id", "email")
);
CREATE INDEX IF NOT EXISTS "idx_gmailaccoun_history_d6a7cf" ON "gmailaccount" ("history_sync_locked_at") WHERE history_sync_locked_at IS NOT NULL;
COMMENT ON COLUMN "gmailaccount"."contacts_sync_status" IS 'RATE_LIMITED: rate_limited\nINSUFFICIENT_PERMISSIONS: insufficient_permissions\nERROR: error\nSUCCESS: success';
CREATE TABLE IF NOT EXISTS "notionconnection" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "access_token" TEXT NOT NULL,
    "workspace_id" TEXT,
    "workspace_name" TEXT,
    "bot_id" TEXT,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_notionconne_user_id_61322a" UNIQUE ("user_id")
);
COMMENT ON COLUMN "notionconnection"."access_token" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "notionpage" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "notion_page_id" TEXT NOT NULL,
    "title" TEXT,
    "kind" VARCHAR(255) NOT NULL DEFAULT 'page',
    "parent_notion_id" TEXT,
    "parent_kind" TEXT,
    "notion_last_edited_time" TIMESTAMPTZ,
    "last_synced_at" TIMESTAMPTZ,
    "is_selected_for_sync" BOOL NOT NULL DEFAULT False,
    "selected_descendant_count" INT NOT NULL DEFAULT 0,
    "total_descendant_count" INT NOT NULL DEFAULT 0,
    "counts_authoritative" BOOL NOT NULL DEFAULT False,
    "content_text" TEXT,
    "document_id" UUID REFERENCES "document" ("id") ON DELETE SET NULL,
    "notion_connection_id" UUID NOT NULL REFERENCES "notionconnection" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_notionpage_notion__2a4e74" UNIQUE ("notion_connection_id", "notion_page_id")
);
CREATE INDEX IF NOT EXISTS "idx_notionpage_user_id_d158f4" ON "notionpage" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_notionpage_notion__27cd46" ON "notionpage" ("notion_connection_id");
COMMENT ON COLUMN "notionpage"."kind" IS 'PAGE: page\nDATABASE: database';
CREATE TABLE IF NOT EXISTS "recallaicalendaruser" (
    "id" VARCHAR(255) NOT NULL PRIMARY KEY,
    "external_id" TEXT NOT NULL,
    "connections" JSONB NOT NULL,
    "preferences" JSONB NOT NULL,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_recallaical_id_e2817e" UNIQUE ("id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_recallaical_user_id_1876f2" ON "recallaicalendaruser" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_recallaical_id_e2817e" ON "recallaicalendaruser" ("id", "user_id");
CREATE TABLE IF NOT EXISTS "recallaimeeting" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "external_id" VARCHAR(500) UNIQUE,
    "provider_meeting_id" TEXT,
    "bot_id" TEXT,
    "bot_status" VARCHAR(255) NOT NULL DEFAULT '',
    "bot_sub_status" VARCHAR(255) NOT NULL DEFAULT '',
    "meeting_platform" VARCHAR(255),
    "will_record" BOOL NOT NULL DEFAULT False,
    "meeting_id" UUID NOT NULL REFERENCES "meeting" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_recallaimee_meeting_753c2c" ON "recallaimeeting" ("meeting_id");
CREATE INDEX IF NOT EXISTS "idx_recallaimee_id_a6f3bf" ON "recallaimeeting" ("id", "meeting_id", "bot_id", "external_id");
COMMENT ON COLUMN "recallaimeeting"."bot_status" IS 'NONE: \nSCHEDULED: scheduled\nUNSCHEDULABLE: unschedulable\nDELETED: deleted\nREADY: ready\nJOINING_CALL: joining_call\nIN_WAITING_ROOM: in_waiting_room\nPARTICIPANT_IN_WAITING_ROOM: participant_in_waiting_room\nIN_CALL_NOT_RECORDING: in_call_not_recording\nRECORDING_PERMISSION_ALLOWED: recording_permission_allowed\nRECORDING_PERMISSION_DENIED: recording_permission_denied\nIN_CALL_RECORDING: in_call_recording\nCALL_ENDED: call_ended\nRECORDING_DONE: recording_done\nDONE: done\nFATAL: fatal\nANALYSIS_DONE: analysis_done\nANALYSIS_FAILED: analysis_failed\nMEDIA_EXPIRED: media_expired';
COMMENT ON COLUMN "recallaimeeting"."bot_sub_status" IS 'NONE: \nZOOM_LOCAL_RECORDING_DISABLED: zoom_local_recording_disabled\nZOOM_LOCAL_RECORDING_REQUEST_DISABLED: zoom_local_recording_request_disabled\nZOOM_LOCAL_RECORDING_REQUEST_DISABLED_BY_HOST: zoom_local_recording_request_disabled_by_host\nZOOM_BOT_IN_WAITING_ROOM: zoom_bot_in_waiting_room\nZOOM_HOST_NOT_PRESENT: zoom_host_not_present\nZOOM_LOCAL_RECORDING_REQUEST_DENIED_BY_HOST: zoom_local_recording_request_denied_by_host\nZOOM_LOCAL_RECORDING_DENIED: zoom_local_recording_denied\nZOOM_LOCAL_RECORDING_GRANT_NOT_SUPPORTED: zoom_local_recording_grant_not_supported\nZOOM_SDK_KEY_BLOCKED_BY_HOST_ADMIN: zoom_sdk_key_blocked_by_host_admin\nCALL_ENDED_BY_HOST: call_ended_by_host\nCALL_ENDED_BY_PLATFORM_IDLE: call_ended_by_platform_idle\nCALL_ENDED_BY_PLATFORM_MAX_LENGTH: call_ended_by_platform_max_length\nCALL_ENDED_BY_PLATFORM_WAITING_ROOM_TIMEOUT: call_ended_by_platform_waiting_room_timeout\nTIMEOUT_EXCEEDED_WAITING_ROOM: timeout_exceeded_waiting_room\nTIMEOUT_EXCEEDED_NOONE_JOINED: timeout_exceeded_noone_joined\nTIMEOUT_EXCEEDED_EVERYONE_LEFT: timeout_exceeded_everyone_left\nTIMEOUT_EXCEEDED_SILENCE_DETECTED: timeout_exceeded_silence_detected\nTIMEOUT_EXCEEDED_ONLY_BOTS_IN_CALL: timeout_exceeded_only_bots_in_call\nTIMEOUT_EXCEEDED_MAX_DURATION: timeout_exceeded_max_duration\nBOT_KICKED_FROM_CALL: bot_kicked_from_call\nBOT_KICKED_FROM_WAITING_ROOM: bot_kicked_from_waiting_room\nBOT_RECEIVED_LEAVE_CALL: bot_received_leave_call\nTIMEOUT_EXCEEDED_ONLY_BOTS_DETECTED_USING_PARTICIPANT_EVENTS: timeout_exceeded_only_bots_detected_using_participant_events\nTIMEOUT_EXCEEDED_RECORDING_PERMISSION_DENIED: timeout_exceeded_recording_permission_denied\nBOT_ERRORED: bot_errored\nMEETING_NOT_FOUND: meeting_not_found\nMEETING_NOT_STARTED: meeting_not_started\nMEETING_REQUIRES_SIGN_IN: meeting_requires_sign_in\nMEETING_LINK_EXPIRED: meeting_link_expired\nMEETING_LINK_INVALID: meeting_link_invalid\nMEETING_PASSWORD_INCORRECT: meeting_password_incorrect\nMEETING_LOCKED: meeting_locked\nMEETING_FULL: meeting_full\nMEETING_ENDED: meeting_ended\nGOOGLE_MEET_INTERNAL_ERROR:';
COMMENT ON COLUMN "recallaimeeting"."meeting_platform" IS 'GOOGLE_MEET: google_meet\nMICROSOFT_TEAMS: microsoft_teams\nMICROSOFT_TEAMS_LIVE: microsoft_teams_live\nUNKNOWN: unknown\nWEBEX: webex\nZOOM: zoom';
CREATE TABLE IF NOT EXISTS "slackcontent" (
    "tags" JSONB NOT NULL,
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "category" VARCHAR(255) NOT NULL,
    "source_id" TEXT NOT NULL,
    "source_url" TEXT NOT NULL,
    "content_type" VARCHAR(255) NOT NULL,
    "sharing" VARCHAR(255) NOT NULL DEFAULT 'private',
    "allowed_user_ids" JSONB NOT NULL,
    "title" TEXT NOT NULL,
    "title_normalized" TEXT NOT NULL,
    "author" TEXT,
    "author_normalized" TEXT,
    "preview_content" TEXT,
    "preview_content_normalized" TEXT,
    "index_content" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "embedding" vector(1536) NOT NULL DEFAULT '[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]',
    "text_search" TSVECTOR,
    "last_indexed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lookup_key" TEXT,
    "lookup_priority" INT NOT NULL DEFAULT 0,
    "is_ai_excluded" BOOL NOT NULL DEFAULT False,
    "lookup_search" TSVECTOR,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "slackcontent"."category" IS 'DOCUMENT: document\nACTIVITY: activity\nPERSON: person';
COMMENT ON COLUMN "slackcontent"."content_type" IS 'MEETING: meeting\nMEETING_TRANSCRIPT: meeting_transcript\nPOST: post\nPOST_COMMENT: post_comment\nGOAL_COMMENT: goal_comment\nUSER: user\nEMAIL_CONTACT: email_contact\nDOCUMENT: document\nGOAL: goal\nDECISION: decision\nFILE: file\nEMAIL_THREAD: email_thread\nSLACK_MESSAGE: slack_message\nCHAT: chat\nCHAT_HISTORY: chat_history';
COMMENT ON COLUMN "slackcontent"."sharing" IS 'PRIVATE: private\nORGANIZATION: organization';
COMMENT ON COLUMN "slackcontent"."title" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."title_normalized" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."preview_content" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."preview_content_normalized" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."index_content" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."text_search" IS 'protected_column';
COMMENT ON COLUMN "slackcontent"."lookup_search" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "jobgroup" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "total_jobs" INT NOT NULL DEFAULT 0,
    "remaining_jobs" INT NOT NULL DEFAULT 0,
    "callback_job_type" TEXT,
    "callback_job_details" JSONB
);
CREATE TABLE IF NOT EXISTS "job" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "job_type" VARCHAR(500) NOT NULL,
    "job_details" JSONB NOT NULL,
    "perform_at" TIMESTAMPTZ,
    "started_at" TIMESTAMPTZ,
    "completed_at" TIMESTAMPTZ,
    "terminated_at" TIMESTAMPTZ,
    "error" TEXT,
    "task_name" VARCHAR(500),
    "queue" VARCHAR(255) NOT NULL DEFAULT 'miscellaneous',
    "group_id" UUID REFERENCES "jobgroup" ("id") ON DELETE CASCADE,
    "rescheduled_from_id" UUID REFERENCES "job" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_job_job_typ_0040b1" ON "job" ("job_type", "job_details");
CREATE INDEX IF NOT EXISTS "idx_job_group_i_64669d" ON "job" ("group_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_job_group_i_7f0448" ON "job" ("group_id") WHERE error IS NOT NULL;
CREATE INDEX IF NOT EXISTS "idx_job_created_366d29" ON "job" ("created_at") WHERE task_name IS NULL AND started_at IS NULL AND completed_at IS NULL AND terminated_at IS NULL;
CREATE INDEX IF NOT EXISTS "idx_job_created_366d29" ON "job" ("created_at") WHERE task_name IS NOT NULL AND completed_at IS NULL AND terminated_at IS NULL;
CREATE INDEX IF NOT EXISTS "idx_job_complet_a3d690" ON "job" ("completed_at") WHERE completed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS "idx_job_termina_991b2b" ON "job" ("terminated_at") WHERE terminated_at IS NOT NULL;
COMMENT ON COLUMN "job"."queue" IS 'UI: ui\nEMAIL: email\nPUSH: push\nINDEXING: indexing\nMISCELLANEOUS: miscellaneous\nONBOARDING_SYNC: onboarding-sync\nMAINTENANCE: maintenance';
CREATE TABLE IF NOT EXISTS "meetingjob" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "job_id" UUID NOT NULL REFERENCES "job" ("id") ON DELETE CASCADE,
    "meeting_id" UUID NOT NULL REFERENCES "meeting" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_meetingjob_meeting_ae80de" ON "meetingjob" ("meeting_id");
CREATE INDEX IF NOT EXISTS "idx_meetingjob_job_id_db7adc" ON "meetingjob" ("job_id");
CREATE TABLE IF NOT EXISTS "research" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "topic" TEXT NOT NULL,
    "max_breadth" INT NOT NULL DEFAULT 3,
    "max_depth" INT NOT NULL DEFAULT 2,
    "max_learnings" INT NOT NULL DEFAULT 10,
    "sources" JSONB NOT NULL,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "job_id" UUID REFERENCES "job" ("id") ON DELETE SET NULL,
    "organization_id" UUID NOT NULL REFERENCES "organization" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_research_job_id_2bcefc" ON "research" ("job_id");
CREATE TABLE IF NOT EXISTS "researchquestion" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "body" TEXT NOT NULL,
    "title" TEXT,
    "sources" JSONB NOT NULL,
    "response" TEXT,
    "response_completed_at" TIMESTAMPTZ,
    "response_message_id" TEXT,
    "in_reply_to_message_id" TEXT,
    "in_reply_to_subject" TEXT,
    "replying_to_message_id" TEXT,
    "cc_recipients" JSONB NOT NULL,
    "creator_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "research_id" UUID REFERENCES "research" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_researchque_researc_213262" ON "researchquestion" ("research_id");
CREATE INDEX IF NOT EXISTS "idx_researchque_respons_731904" ON "researchquestion" ("response_message_id");
COMMENT ON COLUMN "researchquestion"."body" IS 'protected_column';
COMMENT ON COLUMN "researchquestion"."response" IS 'protected_column';
CREATE TABLE IF NOT EXISTS "scheduledresearchdelivery" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "delivered_at" TIMESTAMPTZ,
    "research_id" UUID NOT NULL REFERENCES "research" ("id") ON DELETE CASCADE,
    "scheduled_research_id" UUID NOT NULL REFERENCES "scheduledresearch" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_scheduledre_researc_154eeb" ON "scheduledresearchdelivery" ("research_id");
CREATE INDEX IF NOT EXISTS "idx_scheduledre_schedul_6229c1" ON "scheduledresearchdelivery" ("scheduled_research_id");
CREATE TABLE IF NOT EXISTS "researchiteration" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "title" TEXT NOT NULL,
    "directions" TEXT NOT NULL,
    "queries_count" INT NOT NULL,
    "depth" INT NOT NULL DEFAULT 0,
    "job_id" UUID REFERENCES "job" ("id") ON DELETE SET NULL,
    "research_id" UUID NOT NULL REFERENCES "research" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_researchite_job_id_d05ac4" ON "researchiteration" ("job_id");
CREATE INDEX IF NOT EXISTS "idx_researchite_researc_4b4711" ON "researchiteration" ("research_id");
CREATE TABLE IF NOT EXISTS "researchquery" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "content_search" JSONB NOT NULL,
    "content_result_ids" JSONB NOT NULL,
    "title" TEXT NOT NULL,
    "starts_at" TIMESTAMPTZ,
    "ends_at" TIMESTAMPTZ,
    "goals" TEXT NOT NULL,
    "learnings" JSONB NOT NULL,
    "completed_at" TIMESTAMPTZ,
    "source" VARCHAR(8) NOT NULL DEFAULT 'internal',
    "iteration_id" UUID NOT NULL REFERENCES "researchiteration" ("id") ON DELETE CASCADE,
    "research_id" UUID NOT NULL REFERENCES "research" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_researchque_iterati_b2cda2" ON "researchquery" ("iteration_id");
COMMENT ON COLUMN "researchquery"."source" IS 'INTERNAL: internal\nSLACK: slack';
CREATE TABLE IF NOT EXISTS "cacheentry" (
    "id" UUID NOT NULL PRIMARY KEY,
    "cache_key" VARCHAR(500) NOT NULL UNIQUE,
    "value" TEXT,
    "set_value" JSONB NOT NULL,
    "expires_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_cacheentry_cache_k_650198" ON "cacheentry" ("cache_key");
CREATE INDEX IF NOT EXISTS "idx_cacheentry_expires_df5a30" ON "cacheentry" ("expires_at");
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
-- content.text_search is populated in the database, not the ORM: Content.save() strips it
-- from update_fields and relies on this trigger to keep it current.
CREATE OR REPLACE FUNCTION public.update_text_search() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.text_search := (
                setweight(to_tsvector('english', left(coalesce(NEW.title, ''), 10000)), 'A')
                ||
                setweight(to_tsvector('english', left(coalesce(NEW.index_content, ''), 750000)), 'C')
            );
            RETURN NEW;
        END;
        $$;
CREATE OR REPLACE TRIGGER text_search_update BEFORE INSERT OR UPDATE ON public.content FOR EACH ROW EXECUTE FUNCTION public.update_text_search();
-- Partial unique indexes. Tortoise cannot express UNIQUE ... WHERE, but the application
-- depends on these rejecting the second writer: PushSubscription.register and
-- Chat.find_or_create_by_users both catch the IntegrityError these raise to resolve races.
CREATE UNIQUE INDEX IF NOT EXISTS "pushsubscription_endpoint_active_idx" ON "pushsubscription" ("endpoint") WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS "uix_chat_members_hash" ON "chat" ("organization_id", "collaborators_hash") WHERE group_id IS NULL AND deleted_at IS NULL;
-- Query-performance indexes maintained in migration SQL rather than model Meta.
CREATE INDEX IF NOT EXISTS "idx_chatmessag_reply_t" ON "chatmessage" ("reply_to_id");
CREATE INDEX IF NOT EXISTS "idx_chatmessage_link_pr" ON "chatmessage" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_documentcomment_link_pr" ON "documentcomment" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_emailthread_link_pr" ON "emailthreadcomment" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_goalcomment_link_pr" ON "goalcomment" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_postcomment_link_pr" ON "postcomment" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_postdraftcomment_link_pr" ON "postdraftcomment" ("link_preview_id");
CREATE INDEX IF NOT EXISTS "idx_researchcom_researc_5f4889" ON "researchquestion" ("research_id");
CREATE INDEX IF NOT EXISTS "idx_workspace_assignee_id" ON "workspace" ("assignee_id");
CREATE INDEX IF NOT EXISTS "idx_meeting_organization" ON "meeting" ("organization_id");
-- CacheEntry.write upserts by raw SQL without set_value and relies on this database default.
ALTER TABLE "cacheentry" ALTER COLUMN "set_value" SET DEFAULT '{}'::jsonb;"""


async def downgrade(db: BaseDBAsyncClient | None = None) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "/IqD0Vrzr8+P//n8Dr"
)
