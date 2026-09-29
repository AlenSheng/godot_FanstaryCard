# FantasyCard.Numerics

Offline numerical analysis tool for AG-04. It references the production Domain project so map generation, movement legality and non-choice PVE loot values come from the same code/config used by the server.

Current strategy: **VisibleBossShortestLegalPath**. Boss position is public information, so the planner uses only legal movement plus the visible Boss location; it does not inspect hidden evacuation positions or other players.

Run:

```powershell
dotnet run --project server/tools/FantasyCard.Numerics -- --samples 10000 --players 1 --seed-start 0
```

The JSON output includes P10/P50/P90/mean for cleared cells, middle-elite encounters and expected non-choice PVE gold/souls/fragments. It also computes the geometry-only minimum number of unique middle elite cells required to visit three distinct middle small-monster corners.

Phase-1 limitations are intentional: this does not yet model combat death, PVP, hidden evacuation discovery, reward-choice equipment, backpack replacement, market transfers, robot loot or paid consumables. Those belong to later AG-04 iterations; this first slice replaces invalid static route assumptions with auditable legal paths.
