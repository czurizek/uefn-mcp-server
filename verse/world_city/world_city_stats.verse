# WORLD CITY - persistent player stats (all-time cash + level).
#
# This file owns the storage. Every other WORLD CITY file in this folder reads
# and writes through the functions below, so there is exactly one source of
# truth for a player's numbers.
#
# IMPORTANT: `world_city_player_stats` is a <persistable> struct. Once the
# island is published its field list must never change - removing or renaming a
# field wipes the saved data of every live player. Add state by bumping
# `CurrentStatsVersion` and handling the old shape in `MigrateStats()`.

using { /Verse.org/Simulation }

# Schema version written into every record.
CurrentStatsVersion : int = 1

# Level cap. XP past this point still accumulates but no longer grants levels.
MaxLevel : int = 100

# XP needed to go from `Level` to `Level + 1`: 100, 150, 200, 250, ...
XPForNextLevel(Level:int):int = 100 + 50 * (Level - 1)

world_city_player_stats := struct<persistable>:
    # Schema version of this record.
    Version:int = 1

    # Every unit of cash the player has ever collected. Spending never lowers
    # it - that is what makes the leaderboard "all time".
    CashAllTime:int = 0

    # Total XP earned.
    XP:int = 0

    # Level derived from XP, cached so a future curve change cannot demote
    # anyone who already earned their level.
    Level:int = 1

# The persistent store. A module-scoped `var weak_map(player, ...)` is the only
# shape UEFN persists between sessions.
var WorldCityStats : weak_map(player, world_city_player_stats) = map{}

# Upgrades a record written by an older version of this file.
MigrateStats(Stats:world_city_player_stats):world_city_player_stats=
    if (Stats.Version < CurrentStatsVersion):
        world_city_player_stats:
            Version := CurrentStatsVersion
            CashAllTime := Stats.CashAllTime
            XP := Stats.XP
            Level := Stats.Level
    else:
        Stats

# Reads a player's record, returning a fresh one if they have never played.
GetWorldCityStats(Participant:player):world_city_player_stats=
    if (Stats := WorldCityStats[Participant]):
        MigrateStats(Stats)
    else:
        world_city_player_stats{}

# Writes a record back to the store. Returns false only when the player has
# already left the session, in which case there is nothing left to persist.
SetWorldCityStats(Participant:player, Stats:world_city_player_stats):logic=
    var Saved:logic = false
    if (set WorldCityStats[Participant] = Stats):
        set Saved = true
    Saved

# Level that the given amount of total XP is worth.
LevelFromXP(TotalXP:int):int=
    var Level:int = 1
    var Remaining:int = TotalXP
    for (Step := 1..MaxLevel):
        Needed := XPForNextLevel(Level)
        if (Needed > 0, Remaining >= Needed, Level < MaxLevel):
            set Remaining -= Needed
            set Level += 1
    Level

# Records cash the player collected. Call this from wherever WORLD CITY pays
# out money - jobs, robberies, sales, dailies.
AddCash(Participant:player, Amount:int):void=
    if (Amount > 0):
        Stats := GetWorldCityStats(Participant)
        Updated := world_city_player_stats:
            Version := CurrentStatsVersion
            CashAllTime := Stats.CashAllTime + Amount
            XP := Stats.XP
            Level := Stats.Level
        SetWorldCityStats(Participant, Updated)

# Records XP and recomputes the level from the curve above. A recomputed level
# never lowers the stored one, so changing the curve after launch - or mixing in
# SetPlayerLevel() - cannot demote anybody.
AddXP(Participant:player, Amount:int):void=
    if (Amount > 0):
        Stats := GetWorldCityStats(Participant)
        NewXP := Stats.XP + Amount
        var NewLevel:int = Stats.Level
        EarnedLevel := LevelFromXP(NewXP)
        if (EarnedLevel > NewLevel):
            set NewLevel = EarnedLevel
        Updated := world_city_player_stats:
            Version := CurrentStatsVersion
            CashAllTime := Stats.CashAllTime
            XP := NewXP
            Level := NewLevel
        SetWorldCityStats(Participant, Updated)

# Forces a level, for islands that already track progression somewhere else.
# XP is left untouched, so switching back to AddXP() later still works.
SetPlayerLevel(Participant:player, NewLevel:int):void=
    Stats := GetWorldCityStats(Participant)
    var Clamped:int = NewLevel
    if (Clamped < 1):
        set Clamped = 1
    if (Clamped > MaxLevel):
        set Clamped = MaxLevel
    Updated := world_city_player_stats:
        Version := CurrentStatsVersion
        CashAllTime := Stats.CashAllTime
        XP := Stats.XP
        Level := Clamped
    SetWorldCityStats(Participant, Updated)

# Formats 1234567 as "1 234 567" so big numbers stay readable in the table.
FormatAmount(Value:int):string=
    Digits := "{Value}"
    Length := Digits.Length
    var Out:string = Digits
    if (Value >= 1000):
        # Leading group is whatever is left over after taking groups of three
        # off the end: 1, 2 or 3 digits.
        var Head:int = Length
        for (Step := 1..Length):
            if (Head > 3):
                set Head -= 3
        var Result:string = ""
        var Index:int = 0
        var Take:int = Head
        for (Group := 1..Length):
            if (Index < Length, Chunk := Digits.Slice[Index, Index + Take]):
                if (Index = 0):
                    set Result = Chunk
                else:
                    set Result = "{Result} {Chunk}"
                set Index += Take
                set Take = 3
        set Out = Result
    Out
