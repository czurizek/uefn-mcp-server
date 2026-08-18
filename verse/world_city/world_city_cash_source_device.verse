# WORLD CITY - optional wiring device.
#
# Drop one of these per payout and point it at the triggers or buttons that
# already exist on the island. Every activation credits the player who caused
# it, so the leaderboard starts filling up without touching any other Verse
# file.
#
# If WORLD CITY already has its own money logic, skip this device entirely and
# call AddCash() / AddXP() from world_city_stats.verse directly instead.

using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }

world_city_cash_source_device := class(creative_device):

    # Triggers that count as a payout for whoever set them off.
    @editable
    Triggers:[]trigger_device = array{}

    # Buttons that count as a payout for whoever pressed them.
    @editable
    Buttons:[]button_device = array{}

    # Cash added to the player's all-time total per activation.
    @editable
    CashPerActivation:int = 100

    # XP added per activation. Leave at 0 if levels come from somewhere else.
    @editable
    XPPerActivation:int = 10

    OnBegin<override>()<suspends>:void=
        for (Trigger : Triggers):
            Trigger.TriggeredEvent.Subscribe(OnTriggered)
        for (Button : Buttons):
            Button.InteractedWithEvent.Subscribe(OnInteractedWith)

    OnTriggered(MaybeAgent:?agent):void=
        if (Source := MaybeAgent?, Participant := player[Source]):
            Award(Participant)

    OnInteractedWith(Source:agent):void=
        if (Participant := player[Source]):
            Award(Participant)

    Award(Participant:player):void=
        AddCash(Participant, CashPerActivation)
        AddXP(Participant, XPPerActivation)
