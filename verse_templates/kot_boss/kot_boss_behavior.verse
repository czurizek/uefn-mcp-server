# Boss "Kot" (testy_ai) - wersja v2: poprawki lagow animacji + dzwieki.
# Miejsce w projekcie: testy_ai/Content/KotBoss/kot_boss_behavior.verse
# (podmienia v1; kopia v1: C:\CLAUDE\backup_verse\testy_ai_kot_boss_behavior_v1.verse).
# Kod NIESKOMPILOWANY - pierwszy Build Verse Code w UEFN go sprawdzi.
# Instrukcja wgrania i lista 13 odtwarzaczy dzwieku: README.md obok.
using { /Fortnite.com/AI }
using { /Fortnite.com/Characters }
using { /Fortnite.com/Animation/PlayAnimation }
using { /Fortnite.com/Devices }
using { /Fortnite.com/Playspaces }
using { /Fortnite.com/Game }
using { /Verse.org/Assets }
using { /Verse.org/Simulation }
using { /Verse.org/Simulation/Tags }
using { /Verse.org/Random }
using { /UnrealEngine.com/Temporary/SpatialMath }
using { /UnrealEngine.com/Temporary/Diagnostics }

# =============================================================================
# TAGI DZWIEKOW BOSSA
# Kazdy Odtwarzacz dzwieku (Audio Player) z jednym z tych tagow boss odnajduje
# sam w OnBegin. Ustawienia urzadzen: Miejsce odtwarzania = Device,
# Moga slyszec = Everyone. Pomruk ma wlaczona petle (Loop Audio).
# =============================================================================
kot_dzwiek_pomruk := class(tag){}      # ciagly pomruk w petli, idzie za bossem
kot_dzwiek_dziwny := class(tag){}      # dziwne odglosy co kilka-kilkanascie sekund (kilka urzadzen)
kot_dzwiek_krok := class(tag){}        # ciezki krok (2 urzadzenia, na zmiane)
kot_dzwiek_ryk := class(tag){}
kot_dzwiek_zamach := class(tag){}
kot_dzwiek_uderzenie := class(tag){}   # huk o ziemie
kot_dzwiek_trafienie := class(tag){}   # wrzask przy zachwianiu
kot_dzwiek_smierc := class(tag){}

# Jeden atak bossa. Czasy zmierzone w Blenderze na animacjach z Mixamo
# (po przerobieniu atakow na "w miejscu" doszla 1 klatka = 0,03 s).
kot_atak := class:
    Nazwa : string = ""
    Animacja : animation_sequence
    Dlugosc : float = 1.0          # dlugosc animacji w sekundach
    ChwilaUderzenia : float = 0.5  # kiedy od startu animacji zadac obrazenia
    ChwilaZamachu : float = -1.0   # kiedy puscic swist zamachu (-1 = bez swistu)
    Huk : logic = false            # czy w chwili uderzenia gra huk o ziemie
    Obrazenia : float = 20.0
    Zasieg : float = 700.0         # promien od srodka bossa (cm)
    UnikSkokiem : logic = false    # true = gracz w powietrzu unika (fala uderzeniowa)

# Wielki boss "Kot". Goni najblizszego gracza i bije jednym z czterech atakow.
kot_boss_behavior<public> := class(npc_behavior):

    # Zycie bossa (liczone w Verse, zeby zdazyl zagrac animacje smierci)
    @editable
    ZdrowieBossa : float = 5000.0

    # Z jakiej odleglosci boss zauwaza gracza (cm)
    @editable
    ZasiegWykrycia : float = 8000.0

    # Z jakiej odleglosci boss zaczyna atak (cm)
    @editable
    ZasiegAtaku : float = 700.0

    # Mnoznik predkosci chodu (Fortnite przycina go do 0.5 - 2.0).
    # Krok animacji chodu przy tej skali odpowiada ok. 330 cm/s - przy innej
    # predkosci stopy slizgaja sie po ziemi.
    @editable
    PredkoscPoscigu : float = 1.25

    # Co tyle otrzymanych obrazen boss sie zachwieje
    @editable
    ZachwianieCoObrazen : float = 2500.0

    # Najkrotszy odstep miedzy zachwianiami (s)
    ZachwianieMinOdstep : float = 10.0
    # Cykl chodu A_Kot_Walk i chwile postawienia stop (zmierzone w Blenderze)
    CyklChodu : float = 1.433
    KrokLewy : float = 0.37
    KrokPrawy : float = 1.05

    var Zdrowie : float = 5000.0
    var Umiera : logic = false
    var ObrazeniaOdZachwiania : float = 0.0
    var OstatnieZachwianie : float = -100.0
    var CzekaZachwianie : logic = false
    var Ryczy : logic = false
    var Ataki : []kot_atak = array{}
    var WysokoscGraczy : [agent]float = map{}
    SmiercEvent : event() = event(){}

    var DzwiekPomruk : []audio_player_device = array{}
    var DzwiekiDziwne : []audio_player_device = array{}
    var DzwiekiKrok : []audio_player_device = array{}
    var DzwiekRyk : []audio_player_device = array{}
    var DzwiekZamach : []audio_player_device = array{}
    var DzwiekUderzenie : []audio_player_device = array{}
    var DzwiekTrafienie : []audio_player_device = array{}
    var DzwiekSmierc : []audio_player_device = array{}

    OnBegin<override>()<suspends> : void =
        set Zdrowie = ZdrowieBossa
        set Ataki = array:
            kot_atak{Nazwa := "zamach", Animacja := Anim.A_Kot_Swipe, Dlugosc := 2.67, ChwilaUderzenia := 1.38, ChwilaZamachu := 1.05, Obrazenia := 30.0, Zasieg := 750.0}
            kot_atak{Nazwa := "cios", Animacja := Anim.A_Kot_Smash, Dlugosc := 4.63, ChwilaUderzenia := 1.73, ChwilaZamachu := 1.25, Huk := true, Obrazenia := 45.0, Zasieg := 800.0}
            kot_atak{Nazwa := "skok", Animacja := Anim.A_Kot_JumpAttack, Dlugosc := 3.7, ChwilaUderzenia := 1.7, Huk := true, Obrazenia := 35.0, Zasieg := 1100.0, UnikSkokiem := true}
            kot_atak{Nazwa := "tupniecie", Animacja := Anim.A_Kot_Stomp, Dlugosc := 1.87, ChwilaUderzenia := 0.76, Huk := true, Obrazenia := 25.0, Zasieg := 1000.0, UnikSkokiem := true}
        ZnajdzDzwieki()
        if:
            Agent := GetAgent[]
            Char := Agent.GetFortCharacter[]
            Nav := Char.GetNavigatable[]
            AnimCtrl := Char.GetPlayAnimationController[]
            Focus := Char.GetFocusInterface[]
        then:
            Print("[KOT] Boss gotowy, zycie {Zdrowie}")
            Char.DamagedEvent().Subscribe(PoTrafieniu)
            Nav.SetMovementSpeedMultiplier(PredkoscPoscigu)
            spawn{ PetlaPomruku(Char) }
            spawn{ PetlaDziwnychDzwiekow(Char) }
            spawn{ PetlaKrokow(Char) }
            race:
                PetlaWalki(Char, Nav, AnimCtrl, Focus)
                SmiercEvent.Await()
        else:
            Print("[KOT] BLAD: brak postaci, nawigacji lub kontrolera animacji")

    # =========================================================================
    # WALKA
    # =========================================================================

    PetlaWalki(Char : fort_character, Nav : navigatable, AnimCtrl : play_animation_controller, Focus : focus_interface)<suspends> : void =
        var LicznikAtakow : int = 0
        loop:
            if (CzekaZachwianie?):
                set CzekaZachwianie = false
                Nav.StopNavigation()
                GrajDzwiek(DzwiekTrafienie, Char, 500.0)
                AnimCtrl.PlayAndAwait(Anim.A_Kot_Hit, ?PlayRate := 1.4, ?BlendInTime := 0.15, ?BlendOutTime := 0.2)
            else if (Cel := NajblizszyGracz[Char], CelAgent := Cel.GetAgent[]):
                if (OdlegloscPozioma(Char, Cel) > ZasiegAtaku):
                    # Jedno NavigateTo do gracza (cel podaza za nim). Przerywa je tylko
                    # straznik - nie ma juz ponawiania trasy co sekunde.
                    WynikPoscigu := race:
                        block:
                            Nav.NavigateTo(MakeNavigationTarget(CelAgent), ?MovementType := movement_types.Walking, ?ReachRadius := ZasiegAtaku * 0.8, ?AllowPartialPath := true)
                            1
                        block:
                            StraznikPoscigu(Char, Cel)
                            2
                    if (WynikPoscigu = 1):
                        Sleep(0.25) # nawigacja skonczyla sie sama - krotka pauza przed ponowieniem
                else:
                    Nav.StopNavigation()
                    set LicznikAtakow += 1
                    # Obrot w strone gracza tylko przed atakiem, nie w trakcie
                    race:
                        Focus.MaintainFocus(CelAgent)
                        Sleep(0.35)
                    WykonajSerie(Char, AnimCtrl, LicznikAtakow)
                    Sleep(0.1)
            else:
                Sleep(0.5)

    # Konczy sie, gdy trzeba przerwac poscig: zachwianie, boss doszedl na zasieg
    # ataku albo cel zniknal. Sprawdza co 0,2 s.
    StraznikPoscigu(Char : fort_character, Cel : fort_character)<suspends> : void =
        loop:
            Sleep(0.2)
            if (CzekaZachwianie?):
                break
            if (not Cel.IsActive[]):
                break
            if (OdlegloscPozioma(Char, Cel) <= ZasiegAtaku):
                break

    # Co czwarty atak: ryk i tupniecie. Pozostale: losowo zamach, cios albo skok.
    WykonajSerie(Char : fort_character, AnimCtrl : play_animation_controller, Numer : int)<suspends> : void =
        if (Mod[Numer, 4] = 0, Tupniecie := Ataki[3]):
            set Ryczy = true
            AnimCtrl.Play(Anim.A_Kot_Roar, ?BlendInTime := 0.2, ?BlendOutTime := 0.2)
            Sleep(0.1)
            GrajDzwiek(DzwiekRyk, Char, 700.0)
            # Tupniecie startuje 0,2 s przed koncem ryku - animacje sie zazebiaja,
            # wiec preset nie wtraca miedzy nie postawy spoczynkowej.
            Sleep(5.4 - 0.1 - 0.2)
            set Ryczy = false
            WykonajAtak(Char, AnimCtrl, Tupniecie)
        else if (Atak := Ataki[GetRandomInt(0, 2)]):
            WykonajAtak(Char, AnimCtrl, Atak)

    WykonajAtak(Char : fort_character, AnimCtrl : play_animation_controller, Atak : kot_atak)<suspends> : void =
        ZapamietajWysokosci(Char)
        AnimCtrl.Play(Atak.Animacja, ?BlendInTime := 0.2, ?BlendOutTime := 0.25)
        var Uplynelo : float = 0.0
        if (Atak.ChwilaZamachu >= 0.0):
            Sleep(Atak.ChwilaZamachu)
            set Uplynelo = Atak.ChwilaZamachu
            GrajDzwiek(DzwiekZamach, Char, 500.0)
        Sleep(Atak.ChwilaUderzenia - Uplynelo)
        if (not Umiera?):
            if (Atak.Huk?):
                GrajDzwiek(DzwiekUderzenie, Char, 0.0)
            ZadajObrazenia(Char, Atak)
        Sleep(Atak.Dlugosc - Atak.ChwilaUderzenia - 0.2)

    # Wysokosc kazdego gracza na starcie ataku - po niej poznajemy, kto podskoczyl
    ZapamietajWysokosci(Char : fort_character) : void =
        set WysokoscGraczy = map{}
        if (Playspace := GetEntity[].GetPlayspaceForEntity[]):
            for (Gracz : Playspace.GetPlayers(), GChar := Gracz.GetFortCharacter[]):
                GraczAgent : agent = Gracz
                set WysokoscGraczy = ConcatenateMaps(WysokoscGraczy, map{GraczAgent => GChar.GetTransform().Translation.Z})

    ZadajObrazenia(Char : fort_character, Atak : kot_atak) : void =
        if (Playspace := GetEntity[].GetPlayspaceForEntity[]):
            for (Gracz : Playspace.GetPlayers(), GChar := Gracz.GetFortCharacter[], GChar.IsActive[]):
                if (OdlegloscPozioma(Char, GChar) <= Atak.Zasieg):
                    Pozycja := GChar.GetTransform().Translation
                    if (Atak.UnikSkokiem?, Start := WysokoscGraczy[Gracz], Pozycja.Z - Start > 80.0):
                        Print("[KOT] Gracz przeskoczyl fale: {Atak.Nazwa}")
                    else:
                        GChar.Damage(Atak.Obrazenia)

    OdlegloscPozioma(A : fort_character, B : fort_character)<transacts> : float =
        PA := A.GetTransform().Translation
        PB := B.GetTransform().Translation
        Distance(vector3{X := PA.X, Y := PA.Y, Z := 0.0}, vector3{X := PB.X, Y := PB.Y, Z := 0.0})

    NajblizszyGracz(Char : fort_character)<transacts><decides> : fort_character =
        Playspace := GetEntity[].GetPlayspaceForEntity[]
        var Najlepszy : ?fort_character = false
        var NajlepszaOdleglosc : float = ZasiegWykrycia
        for (Gracz : Playspace.GetPlayers(), GChar := Gracz.GetFortCharacter[], GChar.IsActive[]):
            Odl := OdlegloscPozioma(Char, GChar)
            if (Odl < NajlepszaOdleglosc):
                set NajlepszaOdleglosc = Odl
                set Najlepszy = option{GChar}
        Najlepszy?

    # Zachwianie najwyzej co ZachwianieCoObrazen i nie czesciej niz co
    # ZachwianieMinOdstep - przy progu 600 boss stawal co 3,5 s (glowny "lag").
    PoTrafieniu(Wynik : damage_result) : void =
        if (not Umiera?):
            set Zdrowie -= Wynik.Amount
            set ObrazeniaOdZachwiania += Wynik.Amount
            Print("[KOT] Trafiony za {Wynik.Amount}, zostalo {Zdrowie}")
            Teraz := GetSimulationElapsedTime()
            if (Zdrowie <= 0.0):
                set Umiera = true
                SmiercEvent.Signal()
                if (Char := fort_character[Wynik.Target]):
                    spawn{ Smierc(Char) }
            else if (ObrazeniaOdZachwiania >= ZachwianieCoObrazen, Teraz - OstatnieZachwianie >= ZachwianieMinOdstep):
                set ObrazeniaOdZachwiania = 0.0
                set OstatnieZachwianie = Teraz
                set CzekaZachwianie = true

    Smierc(Char : fort_character)<suspends> : void =
        for (Dev : DzwiekPomruk):
            Dev.Stop()
        GrajDzwiek(DzwiekSmierc, Char, 500.0)
        if (Nav := Char.GetNavigatable[]):
            Nav.StopNavigation()
        if (AnimCtrl := Char.GetPlayAnimationController[]):
            AnimCtrl.Play(Anim.A_Kot_Death, ?BlendInTime := 0.25, ?BlendOutTime := 0.0)
            # Drugi klip startuje tuz przed koncem upadku i bardzo wolno gra ostatnie
            # klatki - inaczej preset ruchu postawilby bossa z powrotem na nogi.
            Sleep(4.45)
            AnimCtrl.Play(Anim.A_Kot_Death, ?PlayRate := 0.01, ?StartPositionSeconds := 4.5, ?BlendInTime := 0.1, ?BlendOutTime := 0.0)
            Sleep(5.0)
        Char.Damage(999999.0)

    # =========================================================================
    # DZWIEKI
    # =========================================================================

    ZnajdzDzwieki() : void =
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_pomruk), Dev := audio_player_device[Obj]):
            set DzwiekPomruk += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_dziwny), Dev := audio_player_device[Obj]):
            set DzwiekiDziwne += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_krok), Dev := audio_player_device[Obj]):
            set DzwiekiKrok += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_ryk), Dev := audio_player_device[Obj]):
            set DzwiekRyk += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_zamach), Dev := audio_player_device[Obj]):
            set DzwiekZamach += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_uderzenie), Dev := audio_player_device[Obj]):
            set DzwiekUderzenie += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_trafienie), Dev := audio_player_device[Obj]):
            set DzwiekTrafienie += array{Dev}
        for (Obj : Self.FindCreativeObjectsWithTag(kot_dzwiek_smierc), Dev := audio_player_device[Obj]):
            set DzwiekSmierc += array{Dev}
        # Diagnostyka: zero przy ktoryms tagu = urzadzenie nie ma tagu, a nie blad odtwarzania
        Print("[KOT] Dzwieki: pomruk {DzwiekPomruk.Length}, dziwne {DzwiekiDziwne.Length}, kroki {DzwiekiKrok.Length}, ryk {DzwiekRyk.Length}, zamach {DzwiekZamach.Length}, huk {DzwiekUderzenie.Length}, trafienie {DzwiekTrafienie.Length}, smierc {DzwiekSmierc.Length}")

    # Przestawia urzadzenie na pozycje bossa (z przesunieciem w gore) i odtwarza.
    # Dev.Play(Agent) dziala tylko przy "Heard by Instigator", dlatego TeleportTo + Play().
    GrajNaPozycji(Dev : audio_player_device, Char : fort_character, Wysokosc : float) : void =
        T := Char.GetTransform()
        Gdzie := vector3{X := T.Translation.X, Y := T.Translation.Y, Z := T.Translation.Z + Wysokosc}
        if (Dev.TeleportTo[Gdzie, T.Rotation]):
            Dev.Play()

    # Odtwarza pierwsze urzadzenie z listy (jesli jest)
    GrajDzwiek(Lista : []audio_player_device, Char : fort_character, Wysokosc : float) : void =
        if (Dev := Lista[0]):
            GrajNaPozycji(Dev, Char, Wysokosc)

    # Pomruk gra w petli (urzadzenie ma Loop Audio) i co 0,15 s idzie za bossem
    PetlaPomruku(Char : fort_character)<suspends> : void =
        if (Dev := DzwiekPomruk[0]):
            GrajNaPozycji(Dev, Char, 400.0)
            loop:
                Sleep(0.15)
                if (Umiera?):
                    break
                T := Char.GetTransform()
                Gdzie := vector3{X := T.Translation.X, Y := T.Translation.Y, Z := T.Translation.Z + 400.0}
                if (Dev.TeleportTo[Gdzie, T.Rotation]):
                    Sleep(0.0)

    # Co 7-16 s losowy dziwny dzwiek (nie w trakcie ryku)
    PetlaDziwnychDzwiekow(Char : fort_character)<suspends> : void =
        if (DzwiekiDziwne.Length > 0):
            loop:
                Sleep(GetRandomFloat(7.0, 16.0))
                if (Umiera?):
                    break
                if (not Ryczy?, Dev := DzwiekiDziwne[GetRandomInt(0, DzwiekiDziwne.Length - 1)]):
                    GrajNaPozycji(Dev, Char, 600.0)

    # Kroki zsynchronizowane z animacja chodu: animacja startuje od klatki 0, gdy
    # boss rusza, a lewa stopa staje w 0,37 s, prawa w 1,05 s kazdego cyklu.
    # Predkosc liczona z przesuniecia pozycji (GetLinearVelocity zwraca inny typ
    # vector3 - /Verse.org/SpatialMath - i to w m/s).
    PetlaKrokow(Char : fort_character)<suspends> : void =
        var Szedl : logic = false
        var NastepnyKrok : float = 0.0
        var LewaNoga : logic = true
        var KtoreUrzadzenie : int = 0
        var OstatniPomiar : float = 0.0
        var PoprzedniaPozycja : vector3 = Char.GetTransform().Translation
        var PoprzedniCzas : float = GetSimulationElapsedTime()
        loop:
            Sleep(0.05)
            if (Umiera?):
                break
            Teraz := GetSimulationElapsedTime()
            P := Char.GetTransform().Translation
            Dt := Teraz - PoprzedniCzas
            Droga := Distance(vector3{X := P.X, Y := P.Y, Z := 0.0}, vector3{X := PoprzedniaPozycja.X, Y := PoprzedniaPozycja.Y, Z := 0.0})
            set PoprzedniaPozycja = P
            set PoprzedniCzas = Teraz
            var Predkosc : float = 0.0
            if (Dt > 0.0):
                set Predkosc = Droga / Dt
            if (Predkosc > 60.0):
                if (not Szedl?):
                    set Szedl = true
                    set LewaNoga = true
                    set NastepnyKrok = Teraz + KrokLewy
                if (Teraz >= NastepnyKrok):
                    if (DzwiekiKrok.Length > 0, Dev := DzwiekiKrok[Mod[KtoreUrzadzenie, DzwiekiKrok.Length]]):
                        GrajNaPozycji(Dev, Char, 0.0)
                    set KtoreUrzadzenie += 1
                    if (LewaNoga?):
                        set NastepnyKrok += KrokPrawy - KrokLewy
                        set LewaNoga = false
                    else:
                        set NastepnyKrok += CyklChodu - (KrokPrawy - KrokLewy)
                        set LewaNoga = true
                # Pomiar do kalibracji tempa chodu (co 3 s w ruchu)
                if (Teraz - OstatniPomiar > 3.0):
                    set OstatniPomiar = Teraz
                    Print("[KOT] Predkosc marszu: {Predkosc} cm/s (krok animacji ok. 330)")
            else:
                set Szedl = false
