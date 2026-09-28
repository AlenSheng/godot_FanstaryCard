ALTER TABLE client_settings
    ADD COLUMN announcement_title_en varchar(120) NOT NULL DEFAULT '',
    ADD COLUMN announcement_body_en varchar(6000) NOT NULL DEFAULT '';

ALTER TABLE mail_messages
    ADD COLUMN title_en varchar(160) NOT NULL DEFAULT '',
    ADD COLUMN body_en text NOT NULL DEFAULT '';

UPDATE mail_messages AS mail
SET title_en = translation.title_en,
    body_en = translation.body_en
FROM (VALUES
    ('测试邮件2：橙紫双词缀套装', 'Test Mail 2: Orange and Purple Equipment Set', 'test2 reward: an orange head piece and purple pieces for the other slots, all with matching effect and secondary affixes.'),
    ('测试邮件2：装备碎片', 'Test Mail 2: Equipment Fragments', 'test2 reward: 100,000 equipment fragments.'),
    ('测试邮件：金币', 'Test Mail: Gold', 'Test account reward: 100,000 gold.'),
    ('测试邮件：魂晶', 'Test Mail: Soul Crystals', 'Test account reward: 100,000 of each soul crystal.'),
    ('测试邮件：白色火系装备', 'Test Mail: White Fire Equipment', 'Test account reward: a full set of white fire equipment.'),
    ('测试邮件：绿色水系装备', 'Test Mail: Green Water Equipment', 'Test account reward: a full set of green water equipment.'),
    ('测试邮件：蓝色土系装备', 'Test Mail: Blue Earth Equipment', 'Test account reward: a full set of blue earth equipment.'),
    ('测试邮件：紫色木系装备', 'Test Mail: Purple Wood Equipment', 'Test account reward: a full set of purple wood equipment.'),
    ('测试邮件：橙色金系装备', 'Test Mail: Orange Metal Equipment', 'Test account reward: a full set of orange metal equipment.')
) AS translation(title, title_en, body_en)
WHERE mail.sender = 'System' AND mail.title = translation.title AND mail.title_en = '';

UPDATE mail_messages
SET title_en = 'System Mail'
WHERE title = '系统通知' AND title_en = '';

UPDATE mail_messages
SET title_en = 'Item Reclamation Notice'
WHERE title = '道具收回通知' AND title_en = '';
