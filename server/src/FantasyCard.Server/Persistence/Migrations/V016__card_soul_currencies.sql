ALTER TABLE economy_ledger DROP CONSTRAINT economy_ledger_currency_check;
ALTER TABLE economy_ledger ADD CONSTRAINT economy_ledger_currency_check
    CHECK (currency IN ('Gold', 'Diamond', 'WarriorSoul', 'ClassSoul',
                        'PriestSoul', 'MageSoul', 'GuardianSoul', 'EquipmentFragments'));
