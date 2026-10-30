# Additive system-content metadata

These additions preserve protocol version 1 and every previously assigned field number. Existing original-language and English fallback text remains populated. Old clients can ignore the new fields; mail without metadata remains authored text and is not inferred from its title or sender.

`http/v1/game.proto`, `MailItemResponse` appends:

- `template_id = 12`: optional stable system template identifier.
- `template_args = 13`: repeated `MailTemplateArgument { string key = 1; string value = 2; }`.
- `sender_role = 14`: optional `system` or `admin`, emitted only from a known server role.

Arguments are logically a dictionary with unique, nonempty, case-sensitive keys. Duplicate keys are invalid, including when their values agree. Values are opaque strings. This uses the existing repeated-message codec rather than introducing a map or a JSON-in-Protobuf payload.

The current seed identifiers are `seed_gold`, `seed_souls`, `seed_white_fire`, `seed_green_water`, `seed_blue_earth`, `seed_purple_wood`, `seed_orange_metal`, `seed2_mixed_set`, and `seed2_fragments`. Seeds retain static fallback copy and the original reward amounts, with an empty argument list. `item_reclamation` carries `kind`, `amount`, and the exact administrator-authored `reason`. Template replacement is a single pass over the original template; inserted values must never be expanded or translated again.

`realtime/v1/realtime.proto` appends:

- `RoomRelicPile.owner_name_is_fallback = 5`: optional boolean.
- `RoomDuel.opponent_name_is_fallback = 16`: optional boolean.

An absent flag means false. True marks the actual null-name fallback and allows the client to display its `traveler_default_name` locale entry. A real name equal to the fallback text is preserved and has a false flag. Existing `owner_name` and `opponent_name` remain present for older clients. Both the snapshot relic list and on-demand relic contents use the same origin decision.

System fallback text is generated from the current client locale authoring source into `server/config/system_mail_locales.json` (`schema_version: 1`, `locales` dictionaries), embedded in the server assembly as `FantasyCard.SystemMailLocales.json`. The server reads the Chinese and English entries to produce legacy fallback text. No per-language database columns are added. V030 adds only template metadata defaults and does not rewrite historical text, claims, or rewards.

After these sources are released from their current validation freeze, regenerate the client schema with `python tools/generate_network_protocol.py`, then verify it with `python tools/generate_network_protocol.py --check`. This implementation does not run that generator or modify client files.
