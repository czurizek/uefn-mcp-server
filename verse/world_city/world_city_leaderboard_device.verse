# WORLD CITY - top 3 leaderboard with a personal fourth slot.
#
# The panel always has four rows:
#   rows 1-3  the best three players *currently on this server*
#   row 4     the viewing player, with their own placement, even when that
#             placement is #17
#
# Ranking uses the all-time cash from world_city_stats.verse, with level as the
# tie breaker (swap the two with the SortBy option in the device panel).
# Everyone on the server sees the same first three rows; only row 4 differs.

using { /Fortnite.com/Devices }
using { /Fortnite.com/Game }
using { /Fortnite.com/UI }
using { /UnrealEngine.com/Temporary/SpatialMath }
using { /UnrealEngine.com/Temporary/UI }
using { /Verse.org/Colors }
using { /Verse.org/Simulation }

world_city_sort_mode := enum:
    # Rank by all-time cash, break ties with level.
    CashAllTime
    # Rank by level, break ties with all-time cash.
    Level

world_city_self_slot_mode := enum:
    # Row 4 always shows the viewing player, even if they are already top 3.
    AlwaysShowMe
    # Row 4 shows 4th place instead when the viewing player is already top 3.
    FourthPlaceWhenTop3

# Interpolating an agent into a message renders that player's Epic display
# name. Verse has no API that hands the name back as a plain string, so the
# name column has to go through a message like this one.
WorldCityPlayerName<localizes>(Participant:agent):message = "{Participant}"

# Wraps a runtime string as a message so it can go into a text_block.
WorldCityText<localizes>(Value:string):message = "{Value}"

WorldCityGold : color = color{R := 1.0, G := 0.84, B := 0.20}
WorldCitySilver : color = color{R := 0.80, G := 0.83, B := 0.88}
WorldCityBronze : color = color{R := 0.85, G := 0.55, B := 0.28}
WorldCityTextColor : color = color{R := 0.93, G := 0.95, B := 1.0}
WorldCityMuted : color = color{R := 0.56, G := 0.60, B := 0.70}
WorldCityAccent : color = color{R := 0.25, G := 0.85, B := 1.0}
WorldCityPanelColor : color = color{R := 0.02, G := 0.03, B := 0.07}

# Column widths, as a share of the panel. Keep the four adding up to 1.0.
WorldCityRankShare : float = 0.14
WorldCityNameShare : float = 0.44
WorldCityCashShare : float = 0.28
WorldCityLevelShare : float = 0.14

# Colour for a placement: gold, silver, bronze, then muted.
WorldCityRankColor(Rank:int):color=
    if (Rank = 1):
        WorldCityGold
    else if (Rank = 2):
        WorldCitySilver
    else if (Rank = 3):
        WorldCityBronze
    else:
        WorldCityMuted

# One player's numbers, snapshotted for a single refresh.
world_city_entry := struct:
    Participant:player
    Cash:int
    Level:int

# The widgets of a single row, kept so a refresh only changes text instead of
# rebuilding the widget tree.
world_city_row := class:
    RankText:text_block
    NameText:text_block
    CashText:text_block
    LevelText:text_block
    Highlight:color_block

# Everything belonging to one viewer's copy of the panel.
world_city_leaderboard_ui := class:
    Participant:player
    Panel:canvas
    Rows:[]world_city_row
    var IsVisible:logic = true

world_city_leaderboard_device := class(creative_device):

    # Headline shown above the table.
    @editable
    Title:string = "WORLD CITY"

    # What the placement is based on.
    @editable
    SortBy:world_city_sort_mode = world_city_sort_mode.CashAllTime

    # What row 4 shows when the viewer is already in the top 3.
    @editable
    SelfSlot:world_city_self_slot_mode = world_city_self_slot_mode.AlwaysShowMe

    # How often the numbers are re-read, in seconds (minimum 0.5).
    @editable
    RefreshSeconds:float = 2.0

    # Show the panel as soon as a player joins.
    @editable
    ShowOnJoin:logic = true

    # Optional buttons that toggle the panel for whoever pressed them.
    @editable
    ToggleButtons:[]button_device = array{}

    @editable
    PanelWidth:float = 460.0

    @editable
    PanelHeight:float = 210.0

    # Distance from the right edge of the screen, in 1080p pixels.
    @editable
    MarginFromRight:float = 48.0

    # Distance from the top edge of the screen, in 1080p pixels.
    @editable
    MarginFromTop:float = 140.0

    # One entry per player currently on this server.
    var PlayerUIs:[]world_city_leaderboard_ui = array{}

    OnBegin<override>()<suspends>:void=
        for (Button : ToggleButtons):
            Button.InteractedWithEvent.Subscribe(OnToggleButton)

        Playspace := GetPlayspace()
        Playspace.PlayerAddedEvent().Subscribe(OnPlayerAdded)
        Playspace.PlayerRemovedEvent().Subscribe(OnPlayerRemoved)

        for (Participant : Playspace.GetPlayers()):
            CreateUIFor(Participant)

        var Period:float = RefreshSeconds
        if (Period < 0.5):
            set Period = 0.5

        loop:
            Refresh()
            Sleep(Period)

    # --- events -----------------------------------------------------------

    OnPlayerAdded(Added:player):void=
        # A joining player's UI is not ready on the same frame as the event.
        spawn{AddPlayerWhenReady(Added)}

    AddPlayerWhenReady(Added:player)<suspends>:void=
        Sleep(1.0)
        CreateUIFor(Added)
        Refresh()

    OnPlayerRemoved(Removed:player):void=
        RemoveUIFor(Removed)
        Refresh()

    OnToggleButton(Presser:agent):void=
        if (Participant := player[Presser]):
            Toggle(Participant)

    # --- public helpers, callable from your own Verse code ----------------

    Show(Participant:player):void=
        for (UI : PlayerUIs, UI.Participant = Participant):
            UI.Panel.SetVisibility(widget_visibility.Visible)
            set UI.IsVisible = true

    Hide(Participant:player):void=
        for (UI : PlayerUIs, UI.Participant = Participant):
            UI.Panel.SetVisibility(widget_visibility.Collapsed)
            set UI.IsVisible = false

    Toggle(Participant:player):void=
        var CurrentlyVisible:logic = false
        for (UI : PlayerUIs, UI.Participant = Participant, UI.IsVisible?):
            set CurrentlyVisible = true
        if (CurrentlyVisible?):
            Hide(Participant)
        else:
            Show(Participant)

    # --- UI lifecycle -----------------------------------------------------

    CreateUIFor(NewPlayer:player):void=
        var AlreadyPresent:logic = false
        for (Existing : PlayerUIs, Existing.Participant = NewPlayer):
            set AlreadyPresent = true

        if (not AlreadyPresent?, PlayerUI := GetPlayerUI[NewPlayer]):
            NewRows := array{MakeRow(), MakeRow(), MakeRow(), MakeRow()}
            NewPanel := MakePanel(NewRows)
            NewUI := world_city_leaderboard_ui:
                Participant := NewPlayer
                Panel := NewPanel
                Rows := NewRows
            PlayerUI.AddWidget(NewPanel, player_ui_slot{InputMode := ui_input_mode.None})
            if (not ShowOnJoin?):
                NewPanel.SetVisibility(widget_visibility.Collapsed)
                set NewUI.IsVisible = false
            set PlayerUIs += array{NewUI}

    RemoveUIFor(Participant:player):void=
        if (PlayerUI := GetPlayerUI[Participant]):
            for (UI : PlayerUIs, UI.Participant = Participant):
                PlayerUI.RemoveWidget(UI.Panel)
        RemainingUIs := for (UI : PlayerUIs, not UI.Participant = Participant):
            UI
        set PlayerUIs = RemainingUIs

    # --- refresh ----------------------------------------------------------

    Refresh():void=
        Entries := CollectEntries()
        Sorted := SortEntries(Entries)
        for (UI : PlayerUIs):
            UpdateUI(UI, Sorted)

    # Only players on this server are considered - GetPlayers() never reaches
    # past the current session.
    CollectEntries():[]world_city_entry=
        var Entries:[]world_city_entry = array{}
        for (Each : GetPlayspace().GetPlayers()):
            Stats := GetWorldCityStats(Each)
            Entry := world_city_entry:
                Participant := Each
                Cash := Stats.CashAllTime
                Level := Stats.Level
            set Entries += array{Entry}
        Entries

    # True when A should be placed above B.
    IsBetter(A:world_city_entry, B:world_city_entry):logic=
        var PrimaryA:int = A.Cash
        var PrimaryB:int = B.Cash
        var SecondaryA:int = A.Level
        var SecondaryB:int = B.Level
        if (SortBy = world_city_sort_mode.Level):
            set PrimaryA = A.Level
            set PrimaryB = B.Level
            set SecondaryA = A.Cash
            set SecondaryB = B.Cash

        var Better:logic = false
        if (PrimaryA > PrimaryB):
            set Better = true
        else if (PrimaryA = PrimaryB, SecondaryA > SecondaryB):
            set Better = true
        Better

    # Selection sort - the list is at most one server's worth of players.
    SortEntries(Entries:[]world_city_entry):[]world_city_entry=
        var Remaining:[]world_city_entry = Entries
        var Sorted:[]world_city_entry = array{}
        for (Pass := 1..Entries.Length):
            var BestIndex:int = 0
            for (Index -> Candidate : Remaining):
                if (Best := Remaining[BestIndex], IsBetter(Candidate, Best)?):
                    set BestIndex = Index
            if (Best := Remaining[BestIndex]):
                set Sorted += array{Best}
                Rest := for (Index -> Entry : Remaining, Index <> BestIndex):
                    Entry
                set Remaining = Rest
        Sorted

    UpdateUI(UI:world_city_leaderboard_ui, Sorted:[]world_city_entry):void=
        # Rows 1-3: the podium, identical for everyone on the server.
        for (Index := 0..2):
            if (Row := UI.Rows[Index]):
                if (Entry := Sorted[Index]):
                    var IsSelf:logic = false
                    if (Entry.Participant = UI.Participant):
                        set IsSelf = true
                    ApplyEntry(Row, Index + 1, Entry, IsSelf)
                else:
                    ApplyEmptyRow(Row, Index + 1)

        # Row 4: the viewing player and their own placement.
        if (SelfRow := UI.Rows[3]):
            var SelfRank:int = 0
            var SelfEntry:?world_city_entry = false
            for (Index -> Entry : Sorted, Entry.Participant = UI.Participant):
                set SelfRank = Index + 1
                set SelfEntry = option{Entry}

            var ShowFourthPlace:logic = false
            if (SelfSlot = world_city_self_slot_mode.FourthPlaceWhenTop3, SelfRank > 0, SelfRank <= 3):
                set ShowFourthPlace = true

            if (ShowFourthPlace?):
                if (Fourth := Sorted[3]):
                    ApplyEntry(SelfRow, 4, Fourth, false)
                else:
                    ApplyEmptyRow(SelfRow, 4)
            else if (Entry := SelfEntry?):
                ApplyEntry(SelfRow, SelfRank, Entry, true)
            else:
                ApplyEmptyRow(SelfRow, 0)

    ApplyEntry(Row:world_city_row, Rank:int, Entry:world_city_entry, IsSelf:logic):void=
        Row.RankText.SetText(WorldCityText("#{Rank}"))
        Row.RankText.SetTextColor(WorldCityRankColor(Rank))
        Row.NameText.SetText(WorldCityPlayerName(Entry.Participant))
        Row.CashText.SetText(WorldCityText(FormatAmount(Entry.Cash)))
        Row.LevelText.SetText(WorldCityText("{Entry.Level}"))

        var RowColor:color = WorldCityTextColor
        var RowOpacity:float = 0.0
        if (IsSelf?):
            set RowColor = WorldCityAccent
            set RowOpacity = 0.28
        Row.NameText.SetTextColor(RowColor)
        Row.CashText.SetTextColor(RowColor)
        Row.LevelText.SetTextColor(RowColor)
        Row.Highlight.SetOpacity(RowOpacity)

    # Rank 0 means "no placement", which is what a player whose stats have not
    # loaded yet gets in row 4.
    ApplyEmptyRow(Row:world_city_row, Rank:int):void=
        var RankLabel:string = "-"
        if (Rank > 0):
            set RankLabel = "#{Rank}"
        Row.RankText.SetText(WorldCityText(RankLabel))
        Row.RankText.SetTextColor(WorldCityMuted)
        Row.NameText.SetText(WorldCityText("-"))
        Row.NameText.SetTextColor(WorldCityMuted)
        Row.CashText.SetText(WorldCityText("-"))
        Row.CashText.SetTextColor(WorldCityMuted)
        Row.LevelText.SetText(WorldCityText("-"))
        Row.LevelText.SetTextColor(WorldCityMuted)
        Row.Highlight.SetOpacity(0.0)

    # --- widget construction ----------------------------------------------

    MakeCell(Label:string, Justification:text_justification, TextColor:color):text_block=
        text_block:
            DefaultText := WorldCityText(Label)
            DefaultTextColor := TextColor
            DefaultJustification := Justification

    MakeRow():world_city_row=
        world_city_row:
            RankText := MakeCell("-", text_justification.Center, WorldCityMuted)
            NameText := MakeCell("-", text_justification.Left, WorldCityTextColor)
            CashText := MakeCell("-", text_justification.Right, WorldCityTextColor)
            LevelText := MakeCell("-", text_justification.Right, WorldCityTextColor)
            Highlight := color_block{DefaultColor := WorldCityAccent, DefaultOpacity := 0.0}

    # Lays four widgets out with the same column shares everywhere, so the
    # header and every row line up.
    MakeColumns(RankWidget:widget, NameWidget:widget, CashWidget:widget, LevelWidget:widget):stack_box=
        stack_box:
            Orientation := orientation.Horizontal
            Slots := array:
                stack_box_slot:
                    Widget := RankWidget
                    Distribution := option{WorldCityRankShare}
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Center
                stack_box_slot:
                    Widget := NameWidget
                    Distribution := option{WorldCityNameShare}
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Center
                stack_box_slot:
                    Widget := CashWidget
                    Distribution := option{WorldCityCashShare}
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Center
                stack_box_slot:
                    Widget := LevelWidget
                    Distribution := option{WorldCityLevelShare}
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Center

    MakeRowWidget(Row:world_city_row):widget=
        Columns := MakeColumns(Row.RankText, Row.NameText, Row.CashText, Row.LevelText)
        overlay:
            Slots := array:
                overlay_slot:
                    Widget := Row.Highlight
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Fill
                overlay_slot:
                    Widget := Columns
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Center
                    Padding := margin{Left := 8.0, Top := 3.0, Right := 8.0, Bottom := 3.0}

    MakeHeaderWidget():widget=
        RankHeader := MakeCell("#", text_justification.Center, WorldCityMuted)
        NameHeader := MakeCell("PLAYER", text_justification.Left, WorldCityMuted)
        CashHeader := MakeCell("CASH", text_justification.Right, WorldCityMuted)
        LevelHeader := MakeCell("LVL", text_justification.Right, WorldCityMuted)
        MakeColumns(RankHeader, NameHeader, CashHeader, LevelHeader)

    MakeDivider():widget=
        color_block:
            DefaultColor := WorldCityMuted
            DefaultOpacity := 0.35
            DefaultDesiredSize := vector2{X := 1.0, Y := 1.0}

    # Title, header, three podium rows, divider, personal row.
    MakeContent(Rows:[]world_city_row):widget=
        var ContentSlots:[]stack_box_slot = array{}

        TitleBlock := MakeCell(Title, text_justification.Left, WorldCityAccent)
        TitleSlot := stack_box_slot:
            Widget := TitleBlock
            HorizontalAlignment := horizontal_alignment.Fill
            Padding := margin{Left := 8.0, Bottom := 6.0}
        set ContentSlots += array{TitleSlot}

        HeaderSlot := stack_box_slot:
            Widget := MakeHeaderWidget()
            HorizontalAlignment := horizontal_alignment.Fill
            Padding := margin{Left := 8.0, Right := 8.0, Bottom := 2.0}
        set ContentSlots += array{HeaderSlot}

        for (Index -> Row : Rows):
            # Row 4 is the personal one, so it gets a divider above it.
            if (Index = 3):
                DividerSlot := stack_box_slot:
                    Widget := MakeDivider()
                    HorizontalAlignment := horizontal_alignment.Fill
                    Padding := margin{Top := 6.0, Bottom := 6.0}
                set ContentSlots += array{DividerSlot}
            RowSlot := stack_box_slot:
                Widget := MakeRowWidget(Row)
                HorizontalAlignment := horizontal_alignment.Fill
            set ContentSlots += array{RowSlot}

        stack_box:
            Orientation := orientation.Vertical
            Slots := ContentSlots

    MakePanel(Rows:[]world_city_row):canvas=
        Background := color_block{DefaultColor := WorldCityPanelColor, DefaultOpacity := 0.62}
        Body := overlay:
            Slots := array:
                overlay_slot:
                    Widget := Background
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Fill
                overlay_slot:
                    Widget := MakeContent(Rows)
                    HorizontalAlignment := horizontal_alignment.Fill
                    VerticalAlignment := vertical_alignment.Top
                    Padding := margin{Left := 14.0, Top := 12.0, Right := 14.0, Bottom := 12.0}

        # Anchored to the top-right corner of the screen.
        PanelAnchors := anchors{Minimum := vector2{X := 1.0, Y := 0.0}, Maximum := vector2{X := 1.0, Y := 0.0}}
        LeftOffset := 0.0 - MarginFromRight
        PanelOffsets := margin{Left := LeftOffset, Top := MarginFromTop, Right := PanelWidth, Bottom := PanelHeight}

        canvas:
            Slots := array:
                canvas_slot:
                    Anchors := PanelAnchors
                    Alignment := vector2{X := 1.0, Y := 0.0}
                    Offsets := PanelOffsets
                    SizeToContent := false
                    Widget := Body
