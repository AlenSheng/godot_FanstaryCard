\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE player_cards(player_id uuid,card_id varchar(80),hero_class smallint,rarity smallint,is_monster boolean,unlocked boolean,copy_count smallint,level smallint,version bigint,PRIMARY KEY(player_id,card_id));
CREATE TEMP TABLE player_card_reserves(player_id uuid,card_id varchar(80),extra_count integer,PRIMARY KEY(player_id,card_id));
CREATE TEMP TABLE card_copy_ledger(movement_id uuid PRIMARY KEY,ledger_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,player_id uuid,card_id varchar(80),delta integer,balance_after integer,reason varchar(80),request_id varchar(128),created_at timestamptz,UNIQUE(player_id,reason,request_id,card_id));
INSERT INTO player_cards VALUES('22a24303-9039-4548-88c4-ec13fbd6b3e5','declared-card',0,1,false,false,0,0,1);
INSERT INTO card_copy_ledger(movement_id,player_id,card_id,delta,balance_after,reason,request_id,created_at) VALUES('2b09d50d-b081-4a82-a85b-70b28b8ac095','22a24303-9039-4548-88c4-ec13fbd6b3e5','declared-card',-1,0,'test.declared-prior-consumption','prior',now());
PREPARE old_unlock(uuid,varchar,smallint,smallint) AS INSERT INTO player_cards(player_id,card_id,hero_class,rarity,is_monster,unlocked,copy_count,level,version)
                    VALUES($1,$2,$3,$4,false,true,1,0,1)
                    ON CONFLICT(player_id,card_id) DO UPDATE SET unlocked=true,copy_count=GREATEST(player_cards.copy_count,1),
                        version=player_cards.version+1
                    WHERE player_cards.unlocked=false OR player_cards.copy_count<1;
PREPARE grant_ledger(uuid,uuid,varchar,integer,integer,varchar,varchar,timestamptz) AS INSERT INTO card_copy_ledger(movement_id,player_id,card_id,delta,balance_after,reason,request_id,created_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8);
\echo BASELINE
WITH card_copy_chain AS (
                SELECT player_id,card_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence DESC) AS latest
                FROM card_copy_ledger
            ) SELECT (SELECT count(*) FROM card_copy_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance::bigint+delta<>balance_after)
                + (SELECT count(*) FROM card_copy_chain l
                   LEFT JOIN player_cards c USING(player_id,card_id)
                   LEFT JOIN player_card_reserves r USING(player_id,card_id)
                   WHERE l.latest=1 AND (c.player_id IS NULL OR l.balance_after<>c.copy_count+COALESCE(r.extra_count,0)));
SAVEPOINT before_unlock;
EXECUTE old_unlock('22a24303-9039-4548-88c4-ec13fbd6b3e5','declared-card',0,1);
\echo OLD_MUTATION_WITHOUT_CARD_LEDGER
WITH card_copy_chain AS (
                SELECT player_id,card_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence DESC) AS latest
                FROM card_copy_ledger
            ) SELECT (SELECT count(*) FROM card_copy_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance::bigint+delta<>balance_after)
                + (SELECT count(*) FROM card_copy_chain l
                   LEFT JOIN player_cards c USING(player_id,card_id)
                   LEFT JOIN player_card_reserves r USING(player_id,card_id)
                   WHERE l.latest=1 AND (c.player_id IS NULL OR l.balance_after<>c.copy_count+COALESCE(r.extra_count,0)));
EXECUTE grant_ledger(gen_random_uuid(),'22a24303-9039-4548-88c4-ec13fbd6b3e5','declared-card',1,1,'admin.unlock_all_cards','new-admin',now());
\echo SAME_MUTATION_WITH_TRANSACTIONAL_LEDGER
WITH card_copy_chain AS (
                SELECT player_id,card_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence DESC) AS latest
                FROM card_copy_ledger
            ) SELECT (SELECT count(*) FROM card_copy_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance::bigint+delta<>balance_after)
                + (SELECT count(*) FROM card_copy_chain l
                   LEFT JOIN player_cards c USING(player_id,card_id)
                   LEFT JOIN player_card_reserves r USING(player_id,card_id)
                   WHERE l.latest=1 AND (c.player_id IS NULL OR l.balance_after<>c.copy_count+COALESCE(r.extra_count,0)));
ROLLBACK TO SAVEPOINT before_unlock;
\echo ROLLED_BACK
WITH card_copy_chain AS (
                SELECT player_id,card_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence DESC) AS latest
                FROM card_copy_ledger
            ) SELECT (SELECT count(*) FROM card_copy_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance::bigint+delta<>balance_after)
                + (SELECT count(*) FROM card_copy_chain l
                   LEFT JOIN player_cards c USING(player_id,card_id)
                   LEFT JOIN player_card_reserves r USING(player_id,card_id)
                   WHERE l.latest=1 AND (c.player_id IS NULL OR l.balance_after<>c.copy_count+COALESCE(r.extra_count,0)));
ROLLBACK;
