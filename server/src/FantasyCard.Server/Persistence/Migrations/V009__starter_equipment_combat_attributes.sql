UPDATE equipments
SET element = 'Fire',
    secondary_trait = 'DrawInterval'
WHERE slot = 'Feet'
  AND quality = 'White'
  AND is_bound = true
  AND element IS NULL;
