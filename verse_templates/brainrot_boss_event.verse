using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Fortnite.com/Playspaces }
using { /UnrealEngine.com/Temporary/SpatialMath }
using { /Verse.org/Simulation }
using { /Verse.org/Random }

# Gigantic "brainrot" boss event.
# Every JumpIntervalSeconds, the boss breathes fire and jumps toward a
# randomly-picked player currently on the island.
#
# One-time setup in UEFN (this MCP server can't do these steps for you —
# there's no Python->Verse bridge, only Verse itself can drive gameplay):
#   1. Place your giant creature as a Creative Prop Device, scaled up
#      (Details panel > Transform > Scale), anywhere on the map.
#   2. Place a VFX Creator Device where the fire breath should originate
#      (e.g. near the boss's mouth), configured with a fire/flame effect.
#   3. Verse Explorer > Add New > Empty Verse File, paste this class in,
#      then Verse > Build Verse Code.
#   4. Drag an instance of brainrot_boss_event_device into the level.
#   5. In its Details panel, assign BossProp and FireBreathVFX to the two
#      devices placed in steps 1-2.
#
# Note: device/method names (creative_prop_device.MoveTo, vfx_creator_device.Play)
# match the Verse API as of this writing. Epic reshuffles device APIs between
# seasons, so if Build Verse Code errors on a specific call, look up the
# current signature in the in-editor Verse API browser (Window > Verse API)
# and adjust that one line — the overall structure won't need to change.

brainrot_boss_event_device := class(creative_device):

    @editable
    BossProp : creative_prop_device = creative_prop_device{}

    @editable
    FireBreathVFX : vfx_creator_device = vfx_creator_device{}

    @editable
    JumpIntervalSeconds : float = 30.0

    @editable
    JumpHeight : float = 800.0

    @editable
    JumpDurationSeconds : float = 1.2

    OnBegin<override>()<suspends>:void=
        loop:
            Sleep(JumpIntervalSeconds)
            JumpToRandomOpponent()

    # Breathes fire, then arcs the boss from its current position to a
    # randomly chosen player's position, landing on top of them.
    JumpToRandomOpponent()<suspends>:void=
        Players := GetPlayspace().GetPlayers()
        if:
            Players.Length > 0
            RandomIndex := GetRandomInt(0, Players.Length - 1)
            TargetPlayer := Players[RandomIndex]
            FortChar := TargetPlayer.GetFortCharacter[]
        then:
            TargetPos := FortChar.GetTransform().Translation
            StartTransform := BossProp.GetTransform()
            StartPos := StartTransform.Translation

            FireBreathVFX.Play()

            ApexHeight := Max(StartPos.Z, TargetPos.Z) + JumpHeight
            ApexPos := vector3{X := (StartPos.X + TargetPos.X) / 2.0, Y := (StartPos.Y + TargetPos.Y) / 2.0, Z := ApexHeight}
            HalfDuration := JumpDurationSeconds / 2.0

            # Up-arc to the apex, then down-arc onto the target. Facing is
            # left as the boss's current rotation to keep this template
            # dependency-free; rotate BossProp to face TargetPos yourself
            # here if you want it to visibly turn mid-jump.
            BossProp.MoveTo(ApexPos, StartTransform.Rotation, HalfDuration)
            Sleep(HalfDuration)
            BossProp.MoveTo(TargetPos, StartTransform.Rotation, HalfDuration)
            Sleep(HalfDuration)

    Max(A : float, B : float) : float =
        if (A > B) then A else B
