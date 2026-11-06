using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Rooms;

public sealed partial class BattleRoom
{
    private PveBattleState CreateOriginalPve(ChaosMapCell cell)=>PveBattleFactory.Create(cell,
        Season is null?null:_catalog.Configuration.SeasonDifficulty(Season.Difficulty),
        Season is not null&&_catalog.UsesPublishedConfiguration?_catalog.Configuration.SeasonThemes?.Selected:null,
        Season is not null&&_catalog.UsesPublishedConfiguration?_catalog.Configuration.SeasonMonsterTuning:null);
}
