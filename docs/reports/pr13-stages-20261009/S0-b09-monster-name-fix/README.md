# PR13 B09.2 formal monster catalog name fix (S0)

The production catalog contains M-FIREBAT / 火蝠. MonsterPool passed only its ID to CardDetails.localized_name, leaving the catalog row argument empty. The English name table masked the omission; Chinese displayed the raw ID. Active pool, candidate and replacement-dropdown names now use the existing CatalogIndex row. No fixture names, card numbers or pool command logic are changed.

The independent rendered-evidence verifier now compares the candidate name with the formal localized catalog. Earlier source results remain available as limited operation/Protobuf evidence and are not treated as completed name-render acceptance. A new corrected-source canonical matrix is required. The product queue still has 54 Chinese/English segments; unsupported legacy extra locales remain unaccepted.
