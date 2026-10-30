-- Old mail keeps its original prose; no title-based inference or reward replay.
ALTER TABLE mail_messages
    ADD COLUMN template_id varchar(80) NOT NULL DEFAULT '',
    ADD COLUMN template_args jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN sender_role varchar(16) NOT NULL DEFAULT '',
    ADD CONSTRAINT ck_mail_template_args_object CHECK (jsonb_typeof(template_args) = 'object'),
    ADD CONSTRAINT ck_mail_sender_role CHECK (sender_role IN ('', 'system', 'admin'));
