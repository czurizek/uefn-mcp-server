# Verse & UEFN — Baza Wiedzy Eksperta

> **Status:** dokument roboczy / system knowledge base
> **Zakres:** język Verse, integracja z UEFN (Unreal Editor for Fortnite), wzorce dla trybów Tycoon i GTA-RP/FFA, oraz mechanika sterowania edytorem przez `uefn-mcp-server`.
> **Ostatnia weryfikacja faktów:** sierpień 2026 (na bazie oficjalnej dokumentacji Epic Games, Book of Verse oraz analizy kodu źródłowego tego repozytorium).

---

## 0. Jak korzystać z tego dokumentu (instrukcja dla modelu)

Jesteś asystentem programistycznym wyspecjalizowanym w **Verse** (język Epic Games dla UEFN) oraz w **Unreal Editor for Fortnite**. Ten dokument to Twoja baza wiedzy referencyjnej. Zasady pracy:

1. **Priorytet poprawności składni nad estetyką.** Verse ma rygorystyczny, unikalny system efektów (`<decides>`, `<suspends>`, `<transacts>`) wymuszany przez kompilator — kod, który "wygląda dobrze" ale łamie te reguły, się nie skompiluje. Zawsze sprawdzaj zgodność z sekcją 1.
2. **Nazwy urządzeń i API dryfują między sezonami Fortnite.** Epic regularnie dodaje/zmienia urządzenia Creative i sygnatury metod. Wzorce języka (składnia, efekty, konkurencja) w tym dokumencie są stabilne i niezmienne od 2023. Nazwy konkretnych urządzeń/metod (np. dokładne pola eventu eliminacji) **należy weryfikować przez autouzupełnianie w edytorze Verse w UEFN** — jeśli coś się nie kompiluje, to pierwszy podejrzany.
3. **Rozróżniaj dwa różne mechanizmy sterowania środowiskiem**, opisane precyzyjnie w sekcji 6:
   - Pisanie **logiki gry w Verse** (`.verse` pliki) → zwykłe operacje na plikach tekstowych (Read/Write/Edit), kompilowane przez UEFN.
   - **Automatyzacja edytora/sceny** przez most Python/MCP (`uefn-mcp-server`) → osobny, ograniczony kanał, który NIE pisze Verse'a i NIE ma dostępu do runtime gry.
4. **Domyślny styl:** PascalCase dla identyfikatorów (zmienne, funkcje, klasy pól), snake_case dla nazw typów (`creative_device`, `fort_character`). To oficjalny styl Epic — trzymaj się go konsekwentnie.
5. Gdy użytkownik prosi o kod do konkretnego trybu gry (Tycoon, RP, FFA) — sekcja 4 zawiera gotowe do adaptacji szkielety. Traktuj je jako punkt wyjścia, nie kopiuj bezmyślnie nazw zmiennych z przykładu, jeśli projekt użytkownika ma już swoją konwencję.

---

## Spis treści

1. [Fundamenty języka Verse](#1-fundamenty-języka-verse)
2. [Zarządzanie urządzeniami (Devices) i eventami](#2-zarządzanie-urządzeniami-devices-i-eventami)
3. [Tworzenie Verse UI (Widżety)](#3-tworzenie-verse-ui-widżety)
4. [Wzorce logiki dla konkretnych trybów](#4-wzorce-logiki-dla-konkretnych-trybów)
5. [Dobre praktyki i częste błędy](#5-dobre-praktyki-i-częste-błędy)
6. [Jak działać w edytorze — mechanizm MCP](#6-jak-działać-w-edytorze--mechanizm-mcp)

---

## 1. Fundamenty języka Verse

### 1.1 Charakterystyka języka

Verse to statycznie typowany język **funkcyjno-logiczny** (functional-logic) stworzony przez Epic Games (przy udziale Simona Peytona Jonesa, współtwórcy Haskella) do skalowania na masowe, trwałe, wieloosobowe światy. Kluczowe cechy różniące go od C++/C#/Blueprint:

- **Brak wyjątków (exceptions).** Kontrola przepływu oparta jest na koncepcie **niepowodzenia (failure)** jako wartości pierwszej klasy — wyrażenie albo się "udaje" (zwraca wartość), albo "zawodzi" (nie zwraca niczego). To fundamentalnie różni się od `try/catch`.
- **System efektów (effect system).** Sygnatura funkcji deklaruje w `<specyfikatorach>`, co funkcja *może* robić: czy może zawieść, czy może się zawiesić (asynchroniczność), czy może mieć skutki uboczne. Kompilator to wymusza.
- **Współbieżność strukturalna jako obywatel pierwszej klasy** (`sync`, `race`, `rush`, `branch`) — nie przez callbacki czy Promise-like API, tylko wbudowaną składnię blokową.
- **Edytor (Python) vs Runtime (Verse) — rozdział całkowity.** Verse działa w czasie gry (runtime, multiplayer, deterministyczny). Python w UEFN działa tylko w edytorze (offline, do automatyzacji contentu). Nie ma mostu Verse↔Python — patrz sekcja 6.2.
- Kod Verse pliku `.verse` umieszczony w folderze `Content/` Twojego projektu UEFN jest kompilowany przez UEFN; klasy dziedziczące po `creative_device` stają się automatycznie urządzeniami, które można przeciągnąć na scenę (Outliner/Content Browser).

### 1.2 Pliki, moduły, `using`

Każdy plik `.verse` domyślnie tworzy **moduł** odpowiadający strukturze folderów w Content Browser. Importujesz inne moduły (w tym API silnika) przez `using`:

```verse
using { /Fortnite.com/Devices }              # klasy urządzeń Creative (button_device, trigger_device, ...)
using { /Fortnite.com/Characters }            # fort_character i powiązane typy
using { /Fortnite.com/Playspace }             # GetPlayspace(), eventy dołączania/opuszczania graczy
using { /Verse.org/Simulation }               # Sleep, podstawy współbieżności
using { /Verse.org/Random }                   # GetRandomInt, GetRandomFloat
using { /UnrealEngine.com/Temporary/Diagnostics } # Print()
using { /UnrealEngine.com/Temporary/UI }      # canvas, overlay, stack_box, button, text_block...
using { /UnrealEngine.com/Temporary/SpatialMath } # vector3, vector2, rotation, transform
```

Definicję modułu można też zadeklarować jawnie:

```verse
MyGameModule := module:
    SomeConstant : int = 42
```

### 1.3 Zmienne: `var`, `set`, wiązania niemutowalne

Verse rozróżnia **wiązanie niemutowalne** (domyślne, preferowane) od **zmiennej mutowalnej**:

```verse
# Wiązanie niemutowalne (immutable binding) — nie da się przypisać ponownie.
# To jest DOMYŚLNY, zalecany sposób. Operator `:=` wiąże nazwę z wartością raz.
Score : int = 0
PlayerName : string = "Nieznajomy"

# Zmienna mutowalna — wymaga jawnego `var` przy deklaracji.
var Health : int = 100

# Każda mutacja WYMAGA słowa kluczowego `set` — nie ma zwykłego `Health = 90`.
set Health = 90
set Health -= 10          # operatory złożone działają: += -= *= /=
```

**Częsty błąd:** próba `Health = 90` bez `set` — kompilator zgłosi błąd, bo bez `set` to jest próba porównania/wiązania, nie mutacji.

Pola klas działają identycznie — pole mutowalne wymaga `var`:

```verse
my_class := class:
    var Health : int = 100      # mutowalne pole
    MaxHealth : int = 100       # niemutowalne pole (ustawiane raz przy konstrukcji)
```

### 1.4 System typów

| Typ | Opis | Przykład |
|---|---|---|
| `int` | liczba całkowita (64-bit) | `42` |
| `float` | liczba zmiennoprzecinkowa | `3.14` |
| `logic` | boolean | `true`, `false` |
| `string` | tekst | `"hello"` |
| `char` | pojedynczy znak (rzadko używany bezpośrednio) | — |
| `message` | tekst lokalizowalny (używany w UI, `Print`) | `"Witaj, {PlayerName}!"` |
| `vector3` | wektor 3D (pozycja) | `vector3{X:=0.0, Y:=0.0, Z:=0.0}` |
| `vector2` | wektor 2D (używany w UI) | `vector2{X:=0.5, Y:=0.5}` |
| `rotation` | rotacja | z `MakeRotation`/`IdentityRotation()` |
| `transform` | pozycja + rotacja + skala | pole `.Translation`, `.Rotation`, `.Scale` |
| `?t` | typ opcjonalny (patrz 1.8) | `?int`, `?player` |
| `[]t` | tablica (array) | `[]int` |
| `[K]V` | mapa | `[string]int` |
| `tuple(a, b, ...)` | krotka | `tuple(int, string)` |
| `type` | typ jako wartość (metaprogramowanie) | — |

Verse jest **silnie statycznie typowany** — brak niejawnej konwersji `int → float`; trzeba jawnie: `IntValue / 1.0` albo funkcji konwertujących.

### 1.5 Klasy, struktury, interfejsy, enumy

```verse
# STRUCT — typ WARTOŚCIOWY (kopiowany przy przypisaniu). Idealny dla danych bez tożsamości.
weapon_stats := struct:
    Damage : int = 10
    FireRate : float = 0.5

# CLASS — typ REFERENCYJNY (przypisanie kopiuje referencję, nie dane).
# Domyślna baza dla urządzeń i obiektów z tożsamością/cyklem życia.
player_state := class:
    var Health : int = 100
    var Team : int = 0

# ENUM
game_phase := enum:
    Warmup
    Playing
    Ended

# INTERFACE — kontrakt, klasy mogą implementować wiele interfejsów naraz.
damageable := interface:
    OnDamaged(Amount : int) : void

# Dziedziczenie klasy + implementacja interfejsu (Verse wspiera wielodziedziczenie interfejsów)
enemy_npc := class(base_actor, damageable):
    OnDamaged<override>(Amount : int) : void =
        Print("Otrzymano {Amount} obrażeń")
```

Specyfikatory klas: `<abstract>` (nie można instancjonować wprost), `<final>` (nie można dziedziczyć), `<persistable>` (kwalifikuje typ do zapisu trwałego — patrz 4.1.1), `<unique>` (używany przy niektórych typach danych porównywalnych po tożsamości).

### 1.6 Funkcje i specyfikatory efektów (Effect Specifiers)

Sygnatura funkcji: `Nazwa(Parametry)<specyfikatory>:TypZwracany = Ciało`.

```verse
Add(A : int, B : int) : int =
    A + B

Greet(Name : string)<transacts>:void=
    Print("Cześć, {Name}!")
```

To jest **najważniejsza koncepcyjnie część Verse** dla modelu piszącego kod: każda funkcja deklaruje zestaw *efektów*, czyli co wolno jej robić. Kompilator odrzuci kod, który używa efektu nie zadeklarowanego w sygnaturze.

| Specyfikator | Znaczenie | Konsekwencja dla wywołującego |
|---|---|---|
| `<computes>` | Czysta funkcja: brak skutków ubocznych, zawsze się kończy, zawsze się udaje | Można wołać wszędzie |
| `<varies>` | Wynik może się różnić dla tych samych argumentów (losowość, odczyt stanu zmiennego) | Można wołać wszędzie |
| `<transacts>` | Może modyfikować stan (`set`), ale nie zawiesza i nie zawodzi trwale — mutacje wykonane po drodze są **wycofywane (rollback)**, jeśli otaczające wyrażenie ostatecznie zawiedzie | Wołaj tam, gdzie dozwolone mutacje |
| `<decides>` | Może **zawieść** (nie zwrócić wartości) | Wołana **tylko** wewnątrz kontekstu błędu, składnia wywołania `Func[Args]` (nawiasy **kwadratowe**!) |
| `<suspends>` | Może **zawiesić** wykonanie (`Sleep`, `Await`, `sync/race/rush/branch`) | Wołana tylko z `OnBegin`, wnętrza `spawn`, lub innej funkcji `<suspends>` |
| `<native>` | Implementacja w silniku (C++), brak ciała Verse | — |
| `<override>` | Nadpisuje metodę klasy bazowej/interfejsu | — |
| `<public>` `<protected>` `<internal>` `<private>` | Widoczność | — |

Efekty "siły" (`<computes>`/`<varies>`/`<transacts>`) bywają częściowo wnioskowane przez kompilator, ale `<decides>` i `<suspends>` **zawsze trzeba deklarować jawnie**, bo zmieniają samą konwencję wywołania (nawiasy kwadratowe / wymóg kontekstu zawieszającego).

Częste kombinacje: `<decides><transacts>` (funkcja, która może zawieść ORAZ mutuje stan po drodze), `<suspends><transacts>`.

### 1.7 Konteksty błędu (Failure Contexts) — serce Verse

To jest **unikalna cecha Verse** i najczęstsze źródło błędów kompilacji dla osób przechodzących z innych języków.

**Koncepcja:** wyrażenie w Verse albo **się udaje** (produkuje wartość) albo **zawodzi** (nie produkuje niczego — nie jest to `null`, nie jest to wyjątek, to brak wykonania dalszej ścieżki). Niepowodzenie **napędza sterowanie przepływem** zamiast klasycznych `if/else` na wartościach boolowskich.

**Funkcje `<decides>` wywołuje się nawiasami kwadratowymi `[...]`, nie okrągłymi:**

```verse
# Deklaracja funkcji, która MOŻE zawieść:
GetPositiveOrFail(N : int)<decides><transacts> : int =
    if (N > 0):
        N
    # brak `else` — jeśli warunek nie jest spełniony, cały `if` (a więc i funkcja) zawodzi

# Wywołanie — zauważ nawiasy KWADRATOWE:
Result := GetPositiveOrFail[5]
```

**Konteksty błędu** to miejsca, gdzie wolno umieścić wyrażenie failable: warunek `if`, filtr `for`, ciało funkcji `<decides>`, klauzula `case`. Poza takim kontekstem kompilator zgłosi błąd typu *"this expression must be inside a failure context"*.

```verse
# `if` jako kontekst błędu — wiele warunków oddzielonych przecinkiem = logiczne AND,
# każdy musi się powieść, w kolejności (short-circuit):
UpgradeItem(Agent : agent) : void =
    if (Player := player[Agent], Economy := PlayerEconomyData[Player], Economy.Cash >= 100):
        Print("Gracz ma wystarczająco gotówki")
    else:
        Print("Warunek nie spełniony")
```

**Operator zapytania `?`** — wyodrębnia wartość z wyrażenia failable (typowo z opcjonału), zawodząc, jeśli go brak. Używany tylko wewnątrz kontekstu błędu:

```verse
CheckStock(MaybeCount : ?int)<decides><transacts> : int =
    Count := MaybeCount?      # jeśli MaybeCount to `false` (pusty opcjonał), cała funkcja zawodzi tutaj
    Count
```

**Operatory porównania są niejawnie failable:** `=` (równość) i `<>` (nierówność) w pozycji warunku same w sobie są testem, który się "udaje" albo "zawodzi" — nie trzeba ich owijać w dodatkowe konstrukcje.

**`case` — dopasowanie wzorca**, z domyślną gałęzią `_`:

```verse
DescribeCount(N : int) : string =
    case (N):
        0 => "brak"
        1 => "jeden"
        _ => "wiele"
```

**Forma wyrażeniowa `if...then...else`** (inline, przydatna w jednolinijkowych przypisaniach):

```verse
Bonus : int = if (IsVip?) then 50 else 0
```

### 1.8 Typy opcjonalne (Optionals)

Opcjonał to niemutowalny kontener, który albo zawiera wartość typu `t`, albo jest pusty. Typ zapisuje się `?t`.

```verse
# Konstrukcja niepustego opcjonału:
A : ?int = option{42}

# Pusty opcjonał = specjalna stała `false` (NIE null, NIE 0!):
var MaybeTarget : ?player = false

# Przypisanie:
set MaybeTarget = option{SomePlayer}
```

**Bezpieczne odpakowanie** — zawsze przez operator `?` wewnątrz kontekstu błędu, nigdy przez "wymuszone" odpakowanie (Verse celowo nie ma odpowiednika `!` z innych języków):

```verse
GreetIfPresent(MaybeName : ?string) : void =
    if (Name := MaybeName?):
        Print("Cześć, {Name}!")
    else:
        Print("Brak imienia.")
```

**Dopasowanie wzorca na opcjonale przez `case`:**

```verse
case (MaybeName : ?string):
    Name : string => Print("Cześć, {Name}")
    false => Print("Brak imienia")
```

**Indeksowanie tablic i map jest z natury failable** (może nie istnieć indeks/klucz) — dlatego też używa nawiasów kwadratowych i musi być w kontekście błędu:

```verse
Scores : [string]int = map{"Alice" => 10, "Bob" => 5}

GetScore(Name : string) : int =
    if (Value := Scores[Name]):
        Value
    else:
        0
```

**Pułapka na początkujących:** `?` w pozycji **typu** (`?player`) i `?` w pozycji **wyrażenia** (`SomeOptional?`) to dwa różne użycia tego samego znaku — nie mylić.

### 1.9 `suspends` — funkcje asynchroniczne

`<suspends>` oznacza, że funkcja może **zawiesić** bieżące wykonanie w czasie (np. czekać, poczekać na event) bez blokowania reszty gry. To odpowiednik `async` w innych ekosystemach, ale zintegrowany ze strukturalną współbieżnością (sekcja 1.10).

```verse
using { /Verse.org/Simulation }

WaitThenPrint()<suspends>:void=
    Sleep(2.0)                      # zawiesza wykonanie TEJ funkcji na 2 sekundy
    Print("Minęły 2 sekundy")
```

**Gdzie `<suspends>` można wywoływać:**
- Wewnątrz `OnBegin<override>()<suspends>:void=` (punkt wejścia urządzenia — sam jest `<suspends>`).
- Wewnątrz innej funkcji oznaczonej `<suspends>`.
- Wewnątrz bloku `spawn` (uruchamia nowy, niezależny kontekst współbieżny — patrz 1.10) — **nawet z funkcji, która sama NIE jest `<suspends>`**, np. z handlera eventu.
- Wewnątrz `sync` / `race` / `rush` / `branch`.

**NIE można** wywołać `Sleep`/`Await` bezpośrednio wewnątrz zwykłego handlera eventu (te domyślnie nie są `<suspends>`) — trzeba opakować w `spawn:`:

```verse
# Handler subskrybowany przez .Subscribe() zwykle NIE jest suspends:
OnButtonPressed(Agent : agent) : void =
    spawn:
        DelayedReward(Agent)   # dopiero WEWNĄTRZ spawn wolno użyć Sleep

DelayedReward(Agent : agent)<suspends>:void=
    Sleep(3.0)
    Print("Nagroda po 3 sekundach")
```

`Await()` na evencie zawiesza do czasu jego zasygnalizowania i zwraca payload:

```verse
WaitForTrigger(Trigger : trigger_device)<suspends>:void=
    Agent := Trigger.TriggeredEvent.Await()
    Print("Trigger aktywowany")
```

### 1.10 Współbieżność: `sync` / `race` / `rush` / `branch` / `spawn`

Verse ma **strukturalną współbieżność** jako wbudowaną składnię blokową. Wszystkie poniższe wymagają efektu `<suspends>` w otaczającej funkcji (poza `spawn`, patrz niżej). Każda "gałąź" bloku to jedno wyrażenie — żeby zgrupować kilka kroków w jednej gałęzi, użyj `block:`.

| Konstrukcja | Semantyka | Kiedy użyć |
|---|---|---|
| `sync` | Uruchamia gałęzie **równolegle**, czeka aż **WSZYSTKIE** się zakończą | Gdy potrzebujesz wyników/zakończenia obu zadań (np. animacja + dźwięk) |
| `race` | Uruchamia gałęzie równolegle, kończy się gdy **PIERWSZA zakończy się** (sukces LUB porażka), **anuluje resztę** | Timeout vs event ("co pierwsze": timer czy input gracza) |
| `rush` | Jak `race`, ale kończy się dopiero gdy **PIERWSZA ODNIESIE SUKCES** — porażki nie przerywają czekania na pozostałe gałęzie | Gdy próbujesz kilku metod i akceptujesz pierwszą, która się faktycznie uda |
| `branch` | Odpala gałąź **bez czekania** na nią (kontynuuje dalej natychmiast); gałąź jest **automatycznie anulowana**, gdy wykonanie opuści otaczający zakres funkcji | Efekty "fire and forget" powiązane cyklem życia z bieżącą funkcją (np. animacja drzwi, która ma się przerwać, gdy device zostanie zniszczony) |
| `spawn` | Jedyna **niestrukturalna** współbieżność — uruchamia zadanie całkowicie niezależne, które **przeżyje** zakres funkcji tworzącej. Wywoływalne nawet z funkcji BEZ `<suspends>` | Zadania, które muszą się dokończyć niezależnie od cyklu życia wywołującego (zapis danych, analytics, logika gracza po opuszczeniu triggera) |

```verse
# SYNC — czekaj na oba
PlayIntro()<suspends>:void=
    sync:
        PlayAnimation()
        PlaySound()
    Print("Oba zakończone")

# RACE — pierwsze co się skończy, wygrywa; drugie jest anulowane
WaitButtonOrTimeout(Button : button_device)<suspends>:void=
    race:
        block:
            Button.InteractedWithEvent.Await()
            Print("Gracz kliknął przed czasem")
        block:
            Sleep(5.0)
            Print("Upłynął czas — timeout")

# RUSH — czekaj, aż KTÓRAŚ próba się uda (porażki nie przerywają czekania na resztę)
TryConnectAnyServer()<suspends><decides>:server_handle=
    rush:
        TryConnect(PrimaryServer)
        TryConnect(BackupServer)

# BRANCH — odpal i kontynuuj; automatycznie anulowane po opuszczeniu funkcji
OpenDoor()<suspends>:void=
    branch:
        AnimateDoorSwing()   # jeśli OpenDoor() zakończy się wcześniej, animacja zostaje przerwana
    Print("Komenda otwarcia wysłana")

# SPAWN — niezależne zadanie, przeżywa funkcję wywołującą; działa NAWET z funkcji bez <suspends>
OnPlayerScored(Agent : agent) : void =
    spawn:
        PersistScoreAsync(Agent)   # zapisze się, nawet jeśli OnPlayerScored już dawno zwróciło
```

**Ważne zastrzeżenie o `branch` vs `spawn`:** `branch` NIE nadaje się do zadań, które *muszą* się dokończyć (np. zapis postępu gracza) — zostanie brutalnie anulowane, gdy tylko otaczająca funkcja zakończy działanie. Do takich zadań zawsze używaj `spawn`.

### 1.11 Pętle i iteracja

```verse
# Pętla nieskończona — wymaga <suspends> jeśli w środku jest Sleep/Await, albo `break`
GeneratorLoop()<suspends>:void=
    loop:
        Sleep(1.0)
        GenerateResource()

# for po kolekcji
for (Item : SomeArray):
    Print("{Item}")

# for po zakresie
for (I := 0..9):
    Print("Numer {I}")

# for z FILTREM (kontekst błędu!) — iteruje tylko po elementach spełniających warunek
for (Item : SomeArray, Item > 5):
    Print("Duży element: {Item}")

# for jako filter+map jednocześnie — bardzo idiomatyczne w Verse:
# zbiera tylko te elementy, dla których ValidateItem się powiodło
ValidItems := for (Item : RawItems, Valid := ValidateItem[Item]):
    Valid

break    # przerywa najbliższą pętlę (loop/for)
```

### 1.12 Tablice i mapy

```verse
# Tablica — literał i pusta tablica mutowalna
Numbers : []int = array{1, 2, 3}
var GrowingList : []int = array{}
set GrowingList += array{4}          # "dodawanie" = konkatenacja przez `+=`

# Mapa — literał i dostęp
Scores : [string]int = map{"Alice" => 10, "Bob" => 5}
var MutableMap : [player]int = map{}
set MutableMap[SomePlayer] = 100     # ustawienie/nadpisanie klucza (działa też dla nowych kluczy)

# Odczyt jest failable (patrz 1.8) — indeksowanie może nie trafić klucza/indeksu
if (Value := Scores["Alice"]):
    Print("{Value}")
```

### 1.13 Interpolacja stringów i typ `message`

```verse
PlayerName : string = "Kowalski"
Score : int = 42

# Interpolacja `{}` wewnątrz literału tekstowego — działa zarówno dla `string`, jak i `message`
Print("Gracz {PlayerName} ma {Score} punktów")

# Widżety UI (sekcja 3) oczekują typu `message` (tekst lokalizowalny) — literały
# stringowe konwertują się do `message` automatycznie w kontekście, który tego wymaga.
```

### 1.14 Ściągawka składni

```verse
# Deklaracje
Const := Value                          # wiązanie niemutowalne
var Mutable : type = Value              # zmienna
set Mutable = NewValue                  # jedyny sposób mutacji

# Funkcja zwykła / decides / suspends
F(X : int) : int = X + 1
G(X : int)<decides> : int = if (X > 0) then X
H()<suspends>:void = Sleep(1.0)

# Wywołania
F(5)            # zwykłe wywołanie — nawiasy okrągłe
G[5]            # wywołanie funkcji <decides> — nawiasy KWADRATOWE
Arr[0]          # indeksowanie (też failable → nawiasy kwadratowe)

# Klasa/struct — konstrukcja literałowa
Instance := my_class{FieldA := 1, FieldB := "x"}

# Kontekst błędu
if (X := MightFail[]):  ... else: ...
for (Item : Collection, Cond): ...
case (X): Pattern => ... _ => ...
```

---

## 2. Zarządzanie urządzeniami (Devices) i eventami

### 2.1 `creative_device` — punkt wejścia

Każdy plik Verse, który ma stać się przeciągalnym urządzeniem w UEFN, definiuje klasę dziedziczącą po `creative_device`. Po udanej kompilacji urządzenie pojawia się w Content Browser i można je przeciągnąć na scenę (Outliner).

```verse
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

my_first_device := class(creative_device):

    OnBegin<override>()<suspends>:void=
        Print("Urządzenie uruchomione")
```

`OnBegin` to punkt wejścia wywoływany raz na starcie sesji gry — analogiczny do `BeginPlay` w UE. Jest `<suspends>`, więc możesz w nim bezpośrednio subskrybować eventy, czekać (`Sleep`), i odpalać strukturalną współbieżność.

### 2.2 Linkowanie urządzeń: `@editable`

Aby kod Verse mógł sterować urządzeniem umieszczonym na scenie (np. konkretnym `button_device`), deklarujesz pole ze specyfikatorem **`@editable`** (atrybut, nie efekt — inna składnia niż `<>`). Pole musi mieć wartość domyślną (konwencjonalnie pusty konstruktor typu).

```verse
tycoon_manager := class(creative_device):

    @editable
    UpgradeButton : button_device = button_device{}

    @editable
    SpawnPoint : player_spawner_device = player_spawner_device{}

    # Tablica edytowalnych referencji — pozwala podpiąć wiele urządzeń tego samego typu
    @editable
    AllDoors : []mover_device = array{}
```

**Po stronie edytora:** po skompilowaniu Verse'a, w panelu **Details** urządzenia (tego samego typu co Twoja klasa, przeciągniętego na scenę) pojawi się pole z nazwą `UpgradeButton` — tam **ręcznie** (lub przez MCP, patrz sekcja 6) przypisuje się referencję do konkretnego `button_device` umieszczonego na mapie. Bez tego kroku pole pozostaje "puste" (wskazuje na domyślny, nieaktywny obiekt) i kod się skompiluje, ale nie zadziała w praktyce — **to jeden z najczęstszych błędów "kod jest OK, ale nic się nie dzieje"**.

### 2.3 Subskrybowanie eventów

Urządzenia eksponują eventy jako pola, na których wołasz `.Subscribe(FunkcjaHandler)`. Handler musi mieć sygnaturę zgodną z payloadem eventu (najczęściej `(Agent : agent) : void`).

```verse
OnBegin<override>()<suspends>:void=
    UpgradeButton.InteractedWithEvent.Subscribe(OnUpgradePressed)

OnUpgradePressed(Agent : agent) : void =
    Print("Przycisk naciśnięty")
```

**Odsubskrybowanie** (ważne przy dynamicznie tworzonych obiektach, żeby uniknąć wycieków/wywołań na nieistniejących danych):

```verse
UpgradeButton.InteractedWithEvent.Unsubscribe(OnUpgradePressed)
```

**Wykrywanie dołączenia/opuszczenia gracza** — przez globalny playspace, nie przez konkretne urządzenie:

```verse
using { /Fortnite.com/Playspace }

OnBegin<override>()<suspends>:void=
    Playspace := GetPlayspace()
    Playspace.PlayerAddedEvent().Subscribe(OnPlayerJoined)
    Playspace.PlayerRemovedEvent().Subscribe(OnPlayerLeft)

OnPlayerJoined(Agent : agent) : void =
    Print("Nowy gracz dołączył")

OnPlayerLeft(Agent : agent) : void =
    Print("Gracz opuścił grę — tu sprzątamy jego stan (patrz 2.8)")
```

### 2.4 Bezpieczne rzutowanie (casting): `agent` → `player` → `fort_character`

`agent` to najogólniejszy typ uczestnika w Verse (może to być gracz, ale teoretycznie też inny byt sterowany). Eventy urządzeń niemal zawsze dostarczają `agent`. Żeby dostać się do danych gracza (inwentarz, ruch, zdrowie), musisz go **bezpiecznie zrzutować** — a rzutowanie w Verse jest z natury failable (może się nie udać, np. dla agenta niebędącego graczem), więc korzysta z nawiasów kwadratowych `[]` i kontekstu błędu.

```verse
using { /Fortnite.com/Characters }

OnAnyEvent(Agent : agent) : void =
    # Krok 1: agent -> player (może zawieść — stąd nawiasy kwadratowe + if)
    if (Player := player[Agent]):
        Print("To jest gracz: {Player}")

        # Krok 2: player -> fort_character (dostęp do ruchu, zdrowia, stanów)
        if (FortChar := Player.GetFortCharacter[]):
            Print("Postać ma HP: {FortChar.GetCurrentHealth()}")
    else:
        Print("Ten agent nie jest graczem (np. NPC)")
```

**Łączenie wielu rzutowań w jednym `if` przez przecinki** (idiomatyczny, zwięzły wzorzec — każdy człon musi się powieść, w kolejności):

```verse
HandleInteraction(Agent : agent) : void =
    if (Player := player[Agent], FortChar := Player.GetFortCharacter[], FortChar.IsActive[]):
        FortChar.Damage(10.0)
```

`fort_character` udostępnia m.in. eventy `DamagedEvent`, informacje o ruchu (kucanie, bieg, skok) oraz metody takie jak teleportacja czy modyfikacja zdrowia — dokładny zestaw metod sprawdzaj przez autouzupełnianie, bo bywa rozszerzany między sezonami.

### 2.5 Wywoływanie akcji na urządzeniach

Po zdobyciu referencji do urządzenia (przez `@editable`) wołasz na nim metody bezpośrednio:

```verse
tycoon_manager := class(creative_device):

    @editable
    RewardGranter : item_granter_device = item_granter_device{}

    @editable
    DoorMover : mover_device = mover_device{}

    @editable
    StatusHUD : hud_message_device = hud_message_device{}

    GrantRewardTo(Agent : agent) : void =
        RewardGranter.GrantItem(Agent)
        StatusHUD.Show(Agent)

    OpenDoor()<suspends>:void=
        DoorMover.MoveTo(EndPosition, 2.0)   # typowa sygnatura: cel + czas trwania
        Sleep(2.0)
```

### 2.6 Popularne urządzenia — punkt startowy

Poniższa tabela to **punkt startowy**, nie wyczerpująca lista — Epic dodaje urządzenia co sezon. Zawsze weryfikuj dokładne nazwy metod/eventów przez autouzupełnianie edytora.

| Urządzenie | Typowe zastosowanie | Typowe eventy/metody |
|---|---|---|
| `trigger_device` | wykrywanie wejścia w strefę | `TriggeredEvent` |
| `button_device` | interaktywny przycisk 3D w świecie | `InteractedWithEvent` |
| `conditional_button_device` | przycisk aktywny tylko po spełnieniu warunku | `InteractedWithEvent`, `Enable()`, `Disable()` |
| `player_spawner_device` | punkt startowy gracza | `SpawnedEvent` |
| `item_granter_device` | przyznawanie itemów graczowi | `GrantItem(Agent)` |
| `damage_device` | zadawanie obrażeń w obszarze | `DamagedEvent` |
| `elimination_manager_device` | globalne śledzenie eliminacji | `EliminatedEvent` |
| `hud_message_device` | krótkie komunikaty na ekranie | `Show(Agent)`, `Hide(Agent)` |
| `class_designer_device` | systemy ról/frakcji (Policja/Cywil itd.) | przypisywanie klas graczom |
| `mover_device` / `prop_mover_device` | ruchome platformy, drzwi, windy (tycoon) | `MoveTo`, `MoveStopEvent` |
| `mutator_zone_device` | modyfikatory gracza w strefie (grawitacja, prędkość) | wejście/wyjście ze strefy |
| `vehicle_spawner_device` | spawn pojazdów (mapy RP/GTA) | `SpawnedEvent` |
| `score_manager_device` | wbudowany system punktacji per gracz/drużyna | `Award`, `GetScore` |

### 2.7 Własne eventy (custom events)

Możesz definiować własny system pub-sub niezależny od urządzeń — przydatne do komunikacji między własnymi klasami/managerami:

```verse
currency_changed_payload := struct:
    Player : player
    NewAmount : int

economy_events := class:
    CurrencyChangedEvent : event(currency_changed_payload) = event(currency_changed_payload){}

# Emisja:
EconomyEvents.CurrencyChangedEvent.Signal(currency_changed_payload{Player := P, NewAmount := 500})

# Subskrypcja z innego device'a:
EconomyEvents.CurrencyChangedEvent.Subscribe(OnCurrencyChanged)

OnCurrencyChanged(Payload : currency_changed_payload) : void =
    Print("{Payload.Player} ma teraz {Payload.NewAmount}")
```

### 2.8 Zarządzanie stanem per-gracz i sprzątanie

Bardzo częsty wzorzec: trzymać stan gracza w mapie `[player]T`, tworzyć wpis przy dołączeniu, usuwać przy opuszczeniu — inaczej mapa rośnie w nieskończoność przez całą sesję (wyciek pamięci na dużych sesjach/wielu rundach).

```verse
var PlayerStates : [player]player_state = map{}

OnPlayerJoined(Agent : agent) : void =
    if (Player := player[Agent]):
        set PlayerStates[Player] = player_state{}

OnPlayerLeft(Agent : agent) : void =
    if (Player := player[Agent]):
        # Verse nie ma "RemoveKey" na zwykłej `var` mapie w prosty sposób we wszystkich wersjach —
        # bezpieczny, przenośny wzorzec to przebudowanie mapy bez danego klucza,
        # albo (jeśli dostępne w Twojej wersji API) dedykowana metoda usuwania klucza mapy.
        Print("Sprzątanie stanu gracza, który opuścił sesję")
```

> **Uwaga praktyczna:** jeśli stan MA przetrwać między sesjami (np. poziom gracza w tycoonie), nie używaj zwykłej `map` — użyj **Verse Persistence** (`weak_map(player, t)`, opisane szczegółowo w sekcji 4.1.1), która automatycznie ładuje/zapisuje dane gracza między wejściami na wyspę.

### 2.9 Pełny przykładowy device (spinający całą sekcję 2)

```verse
using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Fortnite.com/Playspace }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

reward_zone_manager := class(creative_device):

    @editable
    ZoneTrigger : trigger_device = trigger_device{}

    @editable
    RewardGranter : item_granter_device = item_granter_device{}

    @editable
    CooldownSeconds : float = 5.0

    var PlayersOnCooldown : [player]logic = map{}

    OnBegin<override>()<suspends>:void=
        ZoneTrigger.TriggeredEvent.Subscribe(OnZoneEntered)

    OnZoneEntered(Agent : agent) : void =
        if (Player := player[Agent], not PlayersOnCooldown[Player]?):
            RewardGranter.GrantItem(Agent)
            spawn:
                ApplyCooldown(Player)

    ApplyCooldown(Player : player)<suspends>:void=
        set PlayersOnCooldown[Player] = true
        Sleep(CooldownSeconds)
        set PlayersOnCooldown[Player] = false
```

Zwróć uwagę na `not PlayersOnCooldown[Player]?` — `not` neguje wynik odpytania opcjonału/mapy w kontekście błędu, klasyczny wzorzec "guard clause" w Verse.

---

## 3. Tworzenie Verse UI (Widżety)

### 3.1 Dwa światy UI w UEFN

Rozróżnij dwa zupełnie różne mechanizmy budowania interfejsu w UEFN:

1. **Urządzenia UI** (np. `hud_message_device`, `timer_device`) — gotowe elementy z panelu Details, zero kodu, ograniczona personalizacja.
2. **Verse UI (widżety w kodzie)** — pełna kontrola nad layoutem, stylem i logiką, pisana w 100% w Verse. Ta sekcja dotyczy wyłącznie tego drugiego podejścia.

Kluczowy fakt: **niestandardowy widżet Verse jest zawsze przypisany do konkretnego gracza** — tylko ten gracz go widzi. Nie ma "globalnego" UI bez iterowania po graczach.

### 3.2 Podstawowe klocki układu: `canvas`, `overlay`, `stack_box`

```verse
using { /UnrealEngine.com/Temporary/UI }
using { /UnrealEngine.com/Temporary/SpatialMath }
```

- **`canvas`** — swobodne pozycjonowanie absolutne/zakotwiczone (anchors + offsets), jak `Canvas Panel` w UMG. Najczęściej używany kontener najwyższego poziomu dla HUD-u.
- **`overlay`** — nakłada elementy jeden na drugim (warstwy, np. tło + tekst na wierzchu).
- **`stack_box`** — układa dzieci w kolumnę lub rząd (jak `VerticalBox`/`HorizontalBox`), świetny do list (np. lista przedmiotów w sklepie).

**`canvas` z pozycjonowaniem przez `canvas_slot`, `anchors`, `margin`:**

```verse
BuildRootCanvas() : canvas =
    canvas:
        Slots := array:
            canvas_slot:
                Widget := TitleText
                Anchors := anchors{Minimum := vector2{X := 0.5, Y := 0.0}, Maximum := vector2{X := 0.5, Y := 0.0}}
                Offsets := margin{Top := 40.0, Left := -150.0, Right := 150.0, Bottom := 80.0}
                Alignment := vector2{X := 0.5, Y := 0.0}
```

`Anchors` (0..1 w przestrzeni ekranu) + `Offsets` (piksele względem kotwicy) + `Alignment` (punkt zaczepienia widżetu względem jego własnego rozmiaru) razem dają pełną kontrolę pozycjonowania — identyczna logika jak w UMG.

**`stack_box` dla listy elementów sklepu:**

```verse
BuildShopList(Items : []string) : stack_box =
    stack_box:
        Orientation := orientation.Vertical
        Slots := for (ItemName : Items):
            stack_box_slot:
                Widget := text_block{DefaultText := "{ItemName}"}
                Padding := margin{Top := 4.0, Bottom := 4.0}
```

### 3.3 Widżety treści: `text_block`, `button`, `texture_block`, `color_block`

```verse
# Tekst
TitleText : text_block = text_block{DefaultText := "Sklep Ulepszeń"}

# Przycisk z tekstem (button_loud = wariant z domyślnym stylem "przycisk")
BuyButton : button = button_loud{DefaultText := "Kup za 100"}

# Tło koloru / obrazek
Background : color_block = color_block{DefaultColor := NamedColors.Black, DefaultOpacity := 0.6}
Icon : texture_block = texture_block{DefaultImage := SomeTexture}
```

Aktualizacja tekstu w locie — **zawsze przez `SetText`**, nigdy przez rekonstrukcję widżetu od zera (patrz 3.8):

```verse
BuyButton.SetText("Kup za {CurrentCost}")
```

### 3.4 `player_ui` i cykl życia widżetu

Widżet trzeba jawnie **dodać** do gracza (`AddWidget`) i jawnie **usunąć** (`RemoveWidget`), inaczej zostanie na ekranie na stałe (albo, gorzej, zduplikuje się przy ponownym wywołaniu).

```verse
using { /Fortnite.com/Characters }
using { /UnrealEngine.com/Temporary/UI }

ShowShopFor(Agent : agent) : void =
    if (Player := player[Agent], PlayerUI := GetPlayerUI[Player]):
        NewShopUI := BuildShopWidget()
        # player_ui_slot z InputMode.All pozwala graczowi używać kursora (klikanie przycisków)
        PlayerUI.AddWidget(NewShopUI, player_ui_slot{InputMode := ui_input_mode.All})

HideShopFor(Agent : agent, Widget : canvas) : void =
    if (Player := player[Agent], PlayerUI := GetPlayerUI[Player]):
        PlayerUI.RemoveWidget(Widget)
```

**Kluczowy wzorzec: pamiętaj referencję widżetu per gracz**, żeby móc go później usunąć/zaktualizować:

```verse
var ActiveShopWidgets : [player]canvas = map{}

ToggleShop(Agent : agent) : void =
    if (Player := player[Agent], PlayerUI := GetPlayerUI[Player]):
        if (ExistingWidget := ActiveShopWidgets[Player]?):
            # widżet już otwarty -> zamknij
            PlayerUI.RemoveWidget(ExistingWidget)
            var NewMap : [player]canvas = map{}
            set ActiveShopWidgets = NewMap   # uproszczone czyszczenie wpisu, patrz uwaga w 2.8
        else:
            NewWidget := BuildShopWidget()
            PlayerUI.AddWidget(NewWidget, player_ui_slot{InputMode := ui_input_mode.All})
            set ActiveShopWidgets[Player] = NewWidget
```

**Sprzątanie przy opuszczeniu gry:** subskrybuj `PlayerRemovedEvent()` (sekcja 2.3) i tam wywołuj `RemoveWidget` dla każdego aktywnego widżetu tego gracza — inaczej referencje wiszą w mapie bez sensu.

### 3.5 Krok po kroku: budowa HUD-u

1. **Zaprojektuj strukturę drzewa widżetów na papierze** — zawsze jeden korzeń (`canvas` lub `overlay`), potem zagnieżdżone kontenery, na końcu liście (`text_block`, `button`).
2. **Napisz funkcję budującą, która zwraca gotowy widżet** (`() : canvas = ...`) — trzymaj budowę w jednym miejscu, żeby móc łatwo przebudować przy zmianie danych.
3. **Zarejestruj handlery interakcji PRZED dodaniem widżetu do gracza** (patrz 3.6) — subskrypcja na przycisku, który nie jest jeszcze wyświetlony, jest bezpieczna, ale musi nastąpić zanim gracz zdąży kliknąć.
4. **Dodaj widżet przez `player_ui.AddWidget`**, zapisz referencję w mapie per-gracz.
5. **Aktualizuj przez `SetText`/przebudowę**, nigdy nie zostawiaj "martwych" widżetów bez ścieżki usunięcia.

### 3.6 Obsługa interakcji (kliknięcia przycisków)

```verse
BuildBuyButton(Cost : int, OnBuy : type { _(agent) : void }) : button =
    NewButton := button_loud{DefaultText := "Kup za {Cost}"}
    NewButton.OnClick().Subscribe(OnBuy)
    return NewButton
```

`OnClick()` zwraca obiekt eventu, na którym wołasz `.Subscribe(Handler)` dokładnie jak na evencie urządzenia (sekcja 2.3). Handler dostaje `agent` klikającego gracza — **kluczowe**, bo pozwala odróżnić, KTÓRY gracz z wielu patrzących na własną kopię tego samego UI nacisnął przycisk:

```verse
shop_widget_controller := class(creative_device):

    var ShopWidgets : [player]canvas = map{}

    OnBuyClicked(Agent : agent) : void =
        if (Player := player[Agent], Economy := PlayerEconomyData[Player], Economy.Cash >= 100):
            Print("Zakup potwierdzony dla {Player}")
        else:
            Print("Za mało środków")
```

### 3.7 Pełny przykład: sklep z przyciskiem i etykietą waluty

```verse
using { /Fortnite.com/Devices }
using { /Fortnite.com/Characters }
using { /Fortnite.com/Playspace }
using { /UnrealEngine.com/Temporary/UI }
using { /UnrealEngine.com/Temporary/SpatialMath }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

shop_ui_device := class(creative_device):

    @editable
    OpenShopButton : button_device = button_device{}

    var ShopWidgets : [player]canvas = map{}
    var CashLabels : [player]text_block = map{}

    OnBegin<override>()<suspends>:void=
        OpenShopButton.InteractedWithEvent.Subscribe(OnOpenShop)
        GetPlayspace().PlayerRemovedEvent().Subscribe(OnPlayerLeft)

    OnOpenShop(Agent : agent) : void =
        if (Player := player[Agent], PlayerUI := GetPlayerUI[Player]):
            if (Existing := ShopWidgets[Player]?):
                CloseShop(Player, PlayerUI, Existing)
            else:
                OpenShop(Player, PlayerUI)

    OpenShop(Player : player, PlayerUI : player_ui) : void =
        CashLabel := text_block{DefaultText := "Gotówka: {GetCash(Player)}"}
        BuyButton := button_loud{DefaultText := "Kup ulepszenie (100)"}
        BuyButton.OnClick().Subscribe(OnBuyPressed)

        Root := canvas:
            Slots := array:
                canvas_slot:
                    Widget := CashLabel
                    Anchors := anchors{Minimum := vector2{X := 0.02, Y := 0.02}, Maximum := vector2{X := 0.02, Y := 0.02}}
                    Offsets := margin{Left := 0.0, Top := 0.0, Right := 200.0, Bottom := 40.0}
                canvas_slot:
                    Widget := BuyButton
                    Anchors := anchors{Minimum := vector2{X := 0.5, Y := 0.5}, Maximum := vector2{X := 0.5, Y := 0.5}}
                    Offsets := margin{Left := -100.0, Top := -25.0, Right := 100.0, Bottom := 25.0}
                    Alignment := vector2{X := 0.5, Y := 0.5}

        PlayerUI.AddWidget(Root, player_ui_slot{InputMode := ui_input_mode.All})
        set ShopWidgets[Player] = Root
        set CashLabels[Player] = CashLabel

    OnBuyPressed(Agent : agent) : void =
        if (Player := player[Agent]):
            if (TrySpend(Player, 100)):
                if (Label := CashLabels[Player]?):
                    Label.SetText("Gotówka: {GetCash(Player)}")
                Print("Zakup udany")
            else:
                Print("Za mało gotówki")

    CloseShop(Player : player, PlayerUI : player_ui, Widget : canvas) : void =
        PlayerUI.RemoveWidget(Widget)
        # (uproszczone) w realnym kodzie usuń też wpisy z map ShopWidgets/CashLabels dla Player

    OnPlayerLeft(Agent : agent) : void =
        if (Player := player[Agent], PlayerUI := GetPlayerUI[Player], Widget := ShopWidgets[Player]?):
            PlayerUI.RemoveWidget(Widget)
```

*(Funkcje `GetCash`/`TrySpend` odsyłają do wzorca ekonomii z sekcji 4.1 — logikę UI zawsze trzymaj oddzielnie od logiki stanu.)*

### 3.8 Dobre praktyki UI

- **Nigdy nie twórz nowego drzewa widżetów co klatkę/co event.** Buduj raz, potem tylko `SetText`/zmieniaj widoczność. Rekonstrukcja całego `canvas` przy każdej zmianie danych jest kosztowna i powoduje migotanie.
- **Zawsze paruj `AddWidget` z odpowiadającym `RemoveWidget`** — zwłaszcza w handlerze opuszczenia gracza (`PlayerRemovedEvent`). Widżet-sierota po disconnect gracza to częsty powód "duchów" UI w testach z botami.
- **`player_ui_slot{InputMode := ui_input_mode.All}` tylko gdy naprawdę potrzebujesz kursora** (np. sklep, menu) — dla czystego HUD-u (licznik, pasek zdrowia) zostaw domyślny tryb, żeby nie blokować sterowania postacią.
- **Trzymaj stan (mapy per-gracz) i budowę UI w jednym device'ie** lub jasno rozgraniczonych klasach — rozjazd "kto jest źródłem prawdy o gotówce" (UI czy manager ekonomii) to najczęstsza przyczyna niespójnych liczb na ekranie.
- **Testuj z co najmniej 2 botami jednocześnie** — błędy w mapach `[player]widget` (np. nadpisywanie się nawzajem) ujawniają się dopiero przy wielu graczach.

---

## 4. Wzorce logiki dla konkretnych trybów

### 4.1 Tycoon — bezpieczna ekonomia wewnętrzna

Rdzeń każdego tycoona: **jedno źródło prawdy o walucie gracza**, generator przychodu w czasie, i **atomowa** weryfikacja przed każdym zakupem (żeby dwa szybkie kliknięcia nie kupiły dwóch ulepszeń za cenę jednego).

#### 4.1.1 Model danych waluty (trwały, Verse Persistence)

Jeśli chcesz, żeby postęp gracza przetrwał między sesjami, użyj **Verse Persistence**: specjalny typ `<persistable>` + globalna (na poziomie **modułu**, nie klasy!) zmienna `weak_map(player, t)`. Silnik automatycznie ładuje dane gracza przy dołączeniu i zapisuje w tle.

```verse
using { /Fortnite.com/Players }

# Typ danych, które mają przetrwać sesję. WYMAGANE: wartości domyślne na każdym polu
# (nowe pola dodane później muszą też mieć default, inaczej złamiesz zapisy graczy, którzy już grali).
player_economy := class<persistable>:
    Cash        : int = 0
    TotalEarned : int = 0
    UpgradeTier : int = 0

# MUSI być zadeklarowana na poziomie MODUŁU (poza jakąkolwiek klasą device'a).
# Twardy limit Epic: maksymalnie 2 zmienne weak_map(player, ...) na cały projekt.
var PlayerEconomyData : weak_map(player, player_economy) = map{}
```

#### 4.1.2 Generator waluty w czasie

```verse
using { /Verse.org/Simulation }

tycoon_generator_manager := class(creative_device):

    @editable
    GeneratorInterval : float = 3.0

    @editable
    GeneratorAmount : int = 10

    var GeneratorActive : [player]logic = map{}

    OnBegin<override>()<suspends>:void=
        GetPlayspace().PlayerAddedEvent().Subscribe(OnPlayerJoined)
        GetPlayspace().PlayerRemovedEvent().Subscribe(OnPlayerLeft)

    OnPlayerJoined(Agent : agent) : void =
        if (Player := player[Agent]):
            GetOrCreateEconomy(Player)
            set GeneratorActive[Player] = true
            spawn:
                RunGeneratorLoop(Player)

    OnPlayerLeft(Agent : agent) : void =
        if (Player := player[Agent]):
            set GeneratorActive[Player] = false   # flaga zatrzymuje pętlę na następnej iteracji

    # Współbieżna pętla PER GRACZ — spawn odseparowuje ją od cyklu życia handlera OnPlayerJoined.
    RunGeneratorLoop(Player : player)<suspends>:void=
        loop:
            Sleep(GeneratorInterval)
            if (GeneratorActive[Player]?):
                AddCash(Player, GeneratorAmount)
            else:
                break   # gracz wyszedł -> zakończ pętlę i zwolnij zasoby

    GetOrCreateEconomy(Player : player) : player_economy =
        if (Existing := PlayerEconomyData[Player]):
            return Existing
        NewData := player_economy{}
        set PlayerEconomyData[Player] = NewData
        return NewData

    AddCash(Player : player, Amount : int)<transacts>:void=
        Economy := GetOrCreateEconomy(Player)
        set PlayerEconomyData[Player] = player_economy:
            Cash        := Economy.Cash + Amount
            TotalEarned := Economy.TotalEarned + Amount
            UpgradeTier := Economy.UpgradeTier
```

**Dlaczego "cały obiekt na nowo" zamiast mutacji pola?** `player_economy` jest typem persystowalnym i traktujemy go jak **niemutowalny snapshot** podmieniany atomowo w `weak_map`. To eliminuje całą klasę błędów "częściowego zapisu" (np. gdyby dwie współbieżne operacje mutowały różne pola tego samego obiektu w locie, jedna mogłaby nadpisać zmianę drugiej). Zawsze czytaj aktualny stan, buduj nowy snapshot, podmieniaj całość.

#### 4.1.3 Weryfikacja zasobów przed zakupem (atomowy zakup)

**Najczęstszy błąd w tycoonach:** sprawdzenie salda i odjęcie kosztu w dwóch osobnych krokach, między którymi gracz zdąży kliknąć drugi raz (double-spend przez podwójny event kliknięcia w tej samej klatce/ticku). Rozwiązanie: sprawdzenie i odjęcie **muszą być w tej samej funkcji `<transacts>`, bez żadnego `Sleep`/`Await` pomiędzy nimi** — dzięki modelowi wykonania Verse (kooperatywny, bez wywłaszczania w trakcie `<transacts>`) to gwarantuje atomowość.

```verse
TryPurchaseUpgrade(Player : player, Cost : int)<transacts><decides>:void=
    Economy := GetOrCreateEconomy(Player)
    # Warunek i mutacja w JEDNEJ funkcji transactional — żadnego zawieszenia między nimi.
    if (Economy.Cash >= Cost):
        set PlayerEconomyData[Player] = player_economy:
            Cash        := Economy.Cash - Cost
            TotalEarned := Economy.TotalEarned
            UpgradeTier := Economy.UpgradeTier + 1
    else:
        # <decides> bez wartości w tej gałęzi = jawna porażka; wołający dostaje `false`
        false?

OnUpgradeButtonPressed(Agent : agent) : void =
    if (Player := player[Agent]):
        if (TryPurchaseUpgrade[Player, UpgradeCost]):
            Print("Ulepszenie kupione — poziom {GetOrCreateEconomy(Player).UpgradeTier}")
        else:
            Print("Odrzucono zakup: za mało środków")
```

**Dodatkowa warstwa bezpieczeństwa — throttling kliknięć**, żeby ograniczyć spam eventów u źródła (nie tylko poprawność, ale i wydajność):

```verse
var PurchaseCooldown : [player]logic = map{}

OnUpgradeButtonPressed(Agent : agent) : void =
    if (Player := player[Agent], not PurchaseCooldown[Player]?):
        spawn:
            GuardedPurchase(Player)

GuardedPurchase(Player : player)<suspends>:void=
    set PurchaseCooldown[Player] = true
    if (TryPurchaseUpgrade[Player, UpgradeCost]):
        Print("Zakup OK")
    Sleep(0.3)   # minimalny odstęp między próbami zakupu tego samego gracza
    set PurchaseCooldown[Player] = false
```

#### 4.1.4 Zbieranie surowców z dropów (kolizja/trigger → waluta)

```verse
resource_drop_collector := class(creative_device):

    @editable
    CollectionTrigger : trigger_device = trigger_device{}

    @editable
    ValuePerCollection : int = 5

    OnBegin<override>()<suspends>:void=
        CollectionTrigger.TriggeredEvent.Subscribe(OnCollected)

    OnCollected(Agent : agent) : void =
        if (Player := player[Agent]):
            AddCash(Player, ValuePerCollection)
```

To jest ten sam `AddCash` co w 4.1.2 — **jedna funkcja mutująca walutę, wołana z wielu miejsc** (generator, zbieractwo, questy) to podstawowa zasada "single source of truth" dla ekonomii tycoona.

---

### 4.2 Mapy GTA / RP / FFA (styl "sp4nky")

Dla map typu GTA V RP / FFA kluczowe systemy to: **role/frakcje**, **poziom poszukiwania (wanted level)**, **gotówka-przy-sobie vs bank** (z ryzykiem utraty przy śmierci — mechanika "rabunku"), oraz **tablica wyników FFA**.

#### 4.2.1 System frakcji/ról

```verse
player_role := enum:
    Civilian
    Police
    Criminal

var PlayerRoles : [player]player_role = map{}

role_manager := class(creative_device):

    @editable
    PoliceClassDesigner : class_designer_device = class_designer_device{}

    @editable
    CriminalClassDesigner : class_designer_device = class_designer_device{}

    AssignRole(Player : player, Role : player_role) : void =
        set PlayerRoles[Player] = Role
        case (Role):
            player_role.Police =>
                PoliceClassDesigner.Assign(Player)   # dokładna sygnatura zależy od API sezonu — zweryfikuj w edytorze
            player_role.Criminal =>
                CriminalClassDesigner.Assign(Player)
            player_role.Civilian =>
                Print("Gracz jako cywil — bez modyfikatorów klasy")

    IsPolice(Player : player) : logic =
        if (Role := PlayerRoles[Player]?):
            Role = player_role.Police
        else:
            false
```

#### 4.2.2 Wanted level — narastanie i naturalny rozpad w czasie

```verse
using { /Verse.org/Simulation }

var WantedLevels : [player]int = map{}

wanted_level_manager := class(creative_device):

    @editable
    MaxWantedLevel : int = 5

    @editable
    DecayIntervalSeconds : float = 15.0

    OnBegin<override>()<suspends>:void=
        GetPlayspace().PlayerAddedEvent().Subscribe(OnPlayerJoined)

    OnPlayerJoined(Agent : agent) : void =
        if (Player := player[Agent]):
            set WantedLevels[Player] = 0
            spawn:
                RunWantedDecay(Player)

    # Wywoływane z logiki "przestępstwa" (np. atak na NPC, kradzież pojazdu, strzelanina w bezpiecznej strefie)
    AddWantedLevel(Player : player, Amount : int)<transacts>:void=
        Current := WantedLevels[Player] or 0
        NewLevel := Clamp(Current + Amount, 0, MaxWantedLevel)
        set WantedLevels[Player] = NewLevel
        BroadcastWantedChange(Player, NewLevel)

    # Powolny naturalny spadek poziomu, dopóki gracz unika konfliktu — klasyczna mechanika GTA.
    RunWantedDecay(Player : player)<suspends>:void=
        loop:
            Sleep(DecayIntervalSeconds)
            if (Level := WantedLevels[Player]?, Level > 0):
                set WantedLevels[Player] = Level - 1
                BroadcastWantedChange(Player, Level - 1)
            else if (not WantedLevels[Player]?):
                break   # gracz opuścił sesję, mapa już nie ma wpisu -> zakończ pętlę

    BroadcastWantedChange(Player : player, NewLevel : int) : void =
        Print("{Player}: poziom poszukiwania = {NewLevel}")
        # Tu podłącz aktualizację UI (SetText na widżecie gwiazdek, sekcja 3.6)

Clamp(Value : int, Min : int, Max : int) : int =
    if (Value < Min) then Min else if (Value > Max) then Max else Value
```

*(Operator `or` powyżej: `WantedLevels[Player] or 0` to skrót "użyj wartości z opcjonału, a jeśli pusty, użyj wartości domyślnej" — bardzo częsty idiom zamiast pełnego `if/else`.)*

#### 4.2.3 Ekonomia RP: gotówka przy sobie vs bank, rabunek po śmierci

Typowy wzorzec map RP: gracz nosi ograniczoną gotówkę (`CashOnHand`), którą traci (częściowo) po eliminacji — w przeciwieństwie do `BankBalance`, które jest bezpieczne.

```verse
rp_player_economy := class<persistable>:
    BankBalance : int = 0
    CashOnHand  : int = 0

var RPEconomyData : weak_map(player, rp_player_economy) = map{}

rp_economy_manager := class(creative_device):

    @editable
    LossPercentOnDeath : int = 50   # ile % CashOnHand gracz traci przy eliminacji

    DepositToBank(Player : player, Amount : int)<transacts><decides>:void=
        Data := GetOrCreateRP(Player)
        if (Data.CashOnHand >= Amount):
            set RPEconomyData[Player] = rp_player_economy:
                BankBalance := Data.BankBalance + Amount
                CashOnHand  := Data.CashOnHand - Amount
        else:
            false?

    # Wywołaj z handlera eliminacji (elimination_manager_device.EliminatedEvent, sekcja 2.6)
    OnPlayerEliminated(Victim : player, MaybeKiller : ?player) : void =
        Data := GetOrCreateRP(Victim)
        Lost := (Data.CashOnHand * LossPercentOnDeath) / 100
        set RPEconomyData[Victim] = rp_player_economy:
            BankBalance := Data.BankBalance
            CashOnHand  := Data.CashOnHand - Lost

        # Rabunek: skradziona gotówka trafia do zabójcy, jeśli to gracz (a nie np. środowisko)
        if (Killer := MaybeKiller?, Lost > 0):
            KillerData := GetOrCreateRP(Killer)
            set RPEconomyData[Killer] = rp_player_economy:
                BankBalance := KillerData.BankBalance
                CashOnHand  := KillerData.CashOnHand + Lost
            Print("{Killer} obrabował {Victim} na {Lost}")

    GetOrCreateRP(Player : player) : rp_player_economy =
        if (Existing := RPEconomyData[Player]):
            return Existing
        NewData := rp_player_economy{}
        set RPEconomyData[Player] = NewData
        return NewData
```

#### 4.2.4 FFA: respawn, killfeed, leaderboard

```verse
using { /Fortnite.com/Devices }

var KillCounts : [player]int = map{}

ffa_match_manager := class(creative_device):

    @editable
    EliminationManager : elimination_manager_device = elimination_manager_device{}

    @editable
    RespawnDelaySeconds : float = 3.0

    OnBegin<override>()<suspends>:void=
        EliminationManager.EliminatedEvent.Subscribe(OnEliminated)

    # Dokładny kształt payloadu (kto zginął / kto zabił) zależy od aktualnej wersji API —
    # zweryfikuj sygnaturę w edytorze; poniżej typowy dwuagentowy wzorzec.
    OnEliminated(EliminatedAgent : agent, EliminatingAgent : agent) : void =
        if (Killer := player[EliminatingAgent]):
            Current := KillCounts[Killer] or 0
            set KillCounts[Killer] = Current + 1
            BroadcastKillfeed(Killer, EliminatedAgent)

        if (Victim := player[EliminatedAgent]):
            spawn:
                RespawnAfterDelay(Victim)

    RespawnAfterDelay(Victim : player)<suspends>:void=
        Sleep(RespawnDelaySeconds)
        Print("Respawn dla {Victim}")
        # Tu: teleportacja na losowy player_spawner_device, reset ekwipunku itd.

    BroadcastKillfeed(Killer : player, EliminatedAgent : agent) : void =
        Print("{Killer} wyeliminował przeciwnika")

    GetLeaderboardSorted() : []player =
        # Prosty przykład — do prawdziwego sortowania po Kills warto trzymać
        # równoległą tablicę kluczy albo użyć własnej funkcji sortującej.
        for (Entry : KillCounts):
            Entry.Key
```

#### 4.2.5 Strefy specjalne (bezpieczna strefa, strefa napadu) i pojazdy

```verse
zone_type := enum:
    SafeZone
    RobberyZone

zone_controller := class(creative_device):

    @editable
    ZoneVolume : trigger_device = trigger_device{}

    @editable
    Kind : zone_type = zone_type.SafeZone

    OnBegin<override>()<suspends>:void=
        ZoneVolume.TriggeredEvent.Subscribe(OnEnter)

    OnEnter(Agent : agent) : void =
        if (Player := player[Agent]):
            case (Kind):
                zone_type.SafeZone =>
                    Print("{Player} wszedł w bezpieczną strefę — obrażenia od graczy wyłączone")
                zone_type.RobberyZone =>
                    Print("{Player} wszedł w strefę napadu — rozpoczyna się event napadu")
```

Pojazdy w mapach RP zwykle spawnujesz przez `vehicle_spawner_device` (edytowalna referencja jak każde inne urządzenie), a przypisanie "właściciela" pojazdu do konkretnego gracza trzymasz we własnej mapie `[player]vehicle_reference`, analogicznie do wzorców z sekcji 4.1/4.2 — logika przypisania własności to zwykły `weak_map`/`map`, nie osobny mechanizm.

---

## 5. Dobre praktyki i częste błędy

### 5.1 Najczęstsze błędy kompilatora i ich przyczyny

| Komunikat / objaw | Najczęstsza przyczyna | Rozwiązanie |
|---|---|---|
| *"This expression must be inside a failure context"* | Wywołanie funkcji `<decides>` (albo indeksowanie tablicy/mapy, albo `?` na opcjonale) poza `if`/`for`/`case`/ciałem funkcji `<decides>` | Owiń w `if (X := Expr[]): ...` albo dodaj `<decides>` do sygnatury otaczającej funkcji |
| *"Cannot call a <suspends> function from a non-suspends context"* | `Sleep`/`Await`/`race` itp. wewnątrz zwykłego handlera eventu | Owiń wywołanie w `spawn:` albo dodaj `<suspends>` do sygnatury (jeśli to możliwe w danym miejscu) |
| Błąd przypisania / "cannot assign" | Próba `X = Y` zamiast `set X = Y`, albo mutacja pola bez `var` | Dodaj `set`; upewnij się, że pole/zmienna ma `var` |
| Kod kompiluje się, ale urządzenie "nic nie robi" | Pole `@editable` nie zostało powiązane z faktycznym urządzeniem na scenie w panelu Details | Sprawdź w edytorze, czy referencja jest ustawiona (nie jest domyślnym pustym obiektem) |
| Wywołanie `Func(Args)` zamiast `Func[Args]` dla funkcji `<decides>` | Pomylenie konwencji wywołania | Nawiasy kwadratowe dla WSZYSTKICH funkcji `<decides>` i indeksowań |
| Nieoczekiwany rollback mutacji wewnątrz `if` | Mutacja (`set`) wykonana w warunku `if`, który finalnie zawiódł — semantyka `<transacts>` cofa takie zmiany | To zamierzone zachowanie języka, nie bug — projektuj logikę z jego świadomością, nie polegaj na "efektach ubocznych" wewnątrz nieudanych warunków |
| `weak_map` persystencji nie zapisuje danych | Zmienna zadeklarowana wewnątrz klasy zamiast na poziomie modułu, albo przekroczony limit 2 zmiennych weak_map(player,...) na projekt | Przenieś deklarację na najwyższy poziom pliku; skonsoliduj dane w jednym typie `<persistable>` |

### 5.2 Pułapki współbieżności i race conditions

- **Double-spend przy szybkich kliknięciach.** Jeśli handler eventu robi `Sleep`/`Await` między sprawdzeniem a mutacją stanu, dwa niemal jednoczesne eventy mogą oba przejść walidację przed pierwszą mutacją. Rozwiązanie: sprawdzenie+mutacja w jednej funkcji `<transacts>` bez zawieszenia pomiędzy nimi (patrz 4.1.3), ewentualnie dodatkowy cooldown/lock per gracz.
- **`branch` do zadań, które muszą się dokończyć.** `branch` jest anulowany, gdy wykonanie opuści otaczającą funkcję — używanie go do zapisu stanu/danych trwałych gubi dane, gdy funkcja zwróci szybciej niż zadanie się skończy. Do takich zadań zawsze `spawn`.
- **Nieskończone `loop` bez `break` i bez `Sleep`.** Pętla bez punktu zawieszenia (`Sleep(0.0)` minimum) w praktyce zawiesza/zabija wątek edytora lub runtime na czas kompilacji/testów. Każda pętla `loop` powinna mieć w środku albo `Sleep`, albo jawny warunek `break`.
- **Zombie-subskrypcje po opuszczeniu gracza.** Jeśli subskrybujesz eventy na obiektach powiązanych z konkretnym graczem (np. jego własny UI), zawsze odsubskrybuj / posprzątaj w handlerze `PlayerRemovedEvent` — inaczej handler może odpalić się na nieaktualnych danych.
- **Wyścig między `OnBegin` różnych urządzeń.** `OnBegin` wielu device'ów uruchamia się w niezdefiniowanej kolejności względem siebie — nie zakładaj, że urządzenie A zdążyło się zainicjalizować, zanim odpali się `OnBegin` urządzenia B, jeśli B odwołuje się do stanu A. W razie potrzeby użyj krótkiego `Sleep(0.0)` na starcie, albo jawnej synchronizacji przez eventy "gotowości".

### 5.3 Wydajność i optymalizacja

- **Nie odbudowuj drzewa widżetów UI co klatkę** — patrz 3.8. To najdroższa i najczęstsza pułapka wydajnościowa dla map z rozbudowanym UI.
- **Unikaj ciężkiej pracy w `OnBegin`**, jeśli blokuje inicjalizację innych systemów — rozważ rozbicie startu na `spawn` dla części nieistotnych natychmiast.
- **Interwały `Sleep` w pętlach generatorów** (tycoon) nie powinny być zbyt krótkie (poniżej ~0.1s) bez wyraźnej potrzeby — każdy tick generatora per gracz sumuje się przy dużej liczbie graczy jednocześnie.
- **Struktury (`struct`) zamiast klas (`class`) dla małych, częstych danych** (np. `vector3`-podobne pakiety danych) — struktury są typami wartościowymi i unikają narzutu referencji/GC tam, gdzie tożsamość obiektu nie ma znaczenia.
- **Jedna funkcja mutująca = jedno źródło prawdy.** Rozproszenie logiki "kto zmienia walutę gracza" po wielu miejscach w kodzie utrudnia optymalizację (i debugowanie) w miarę wzrostu projektu.

### 5.4 Struktura projektu i konwencje nazewnictwa

- **PascalCase** dla zmiennych, pól, funkcji, parametrów (`PlayerHealth`, `TryPurchaseUpgrade`).
- **snake_case** dla nazw typów: klas, structów, enumów, interfejsów (`creative_device`, `player_economy`, `zone_type`).
- Prefiksy `On` dla handlerów eventów (`OnPlayerJoined`, `OnUpgradePressed`), `Try` dla funkcji `<decides>` które mogą zawieść w sposób "spodziewany" (`TryPurchaseUpgrade`), `Get`/`GetOrCreate` dla akcesorów.
- **Jeden device = jedna odpowiedzialność.** Zamiast jednego gigantycznego `game_manager` device'a robiącego wszystko, dziel na `economy_manager`, `ui_controller`, `wanted_level_manager`, itd., komunikujące się przez własne eventy (2.7) albo bezpośrednie referencje `@editable`.
- Trzymaj dane trwałe (`<persistable>`) w osobnych, małych typach zamiast jednego wielkiego "worka" — łatwiej o bezbolesną migrację schematu (nowe pola z wartością domyślną są bezpieczne; usuwanie/zmiana typu istniejącego pola psuje zapisane dane graczy).

### 5.5 Testowanie

- Testuj zawsze **z co najmniej 2 botami/graczami jednocześnie** (Play in UEFN pozwala dodać boty) — większość błędów w mapach `[player]T` i logice ekonomii ujawnia się dopiero przy więcej niż jednym uczestniku.
- Testuj **wejście i wyjście z sesji** (dołączanie w trakcie trwającej rozgrywki, opuszczanie w trakcie animacji/cooldownu) — to najczęstsze źródło "zawieszonych" stanów.
- Dla mechanik z `Sleep`/`race`/`rush` testuj celowo **skrajne czasy** (np. kliknięcie dokładnie w momencie upływu timeoutu w `race`), żeby złapać błędy "off-by-one-tick".
- Obserwuj **Output Log w edytorze** (`Window > Developer Tools > Output Log` w UEFN, albo przez `get_editor_log` z MCP — sekcja 6) pod kątem ostrzeżeń kompilatora Verse, które nie blokują builda, ale sygnalizują potencjalne problemy.

---

## 6. Jak działać w edytorze — mechanizm MCP

Ta sekcja opisuje **dokładnie** ten mechanizm, z którego korzysta model działający w tym repozytorium (`uefn-mcp-server`), żeby ingerować w środowisko UEFN spoza samego kodu Verse.

### 6.1 Architektura

```
Claude Code  <--stdio-->  MCP Server (mcp_server.py)  <--HTTP :8765-->  Listener (uefn_listener.py, wewnątrz UEFN)
```

Dwa niezależne procesy Python połączone HTTP na localhost:

1. **`uefn_listener.py`** — działa **wewnątrz procesu edytora UEFN** (Python 3.11 wbudowany w UEFN). Uruchamia serwer HTTP na wątku daemon, ale **wszystkie wywołania `unreal.*` są przekładane na główny wątek edytora** przez callback ticku (`register_slate_post_tick_callback`) — bo Unreal Python API nie jest thread-safe. Żądanie trafia do kolejki, tick handler odpala je na głównym wątku (do 5 komend na klatkę), wynik wraca przez słownik chroniony blokadą.
2. **`mcp_server.py`** — działa jako **osobny proces zewnętrzny** (Python 3.10+, z zainstalowanym SDK `mcp`). To on wystawia 28 narzędzi (tools) do Claude Code przez protokół MCP po `stdio`. Każde narzędzie to cienki wrapper: serializuje parametry do JSON, robi `POST http://127.0.0.1:8765`, parsuje odpowiedź.

**Dlaczego dwa procesy, a nie jeden?** SDK `mcp` wymaga `asyncio`/`pydantic`, których nie da się doinstalować do wbudowanego Pythona UEFN (brak `pip`). Rozdzielenie pozwala też restartować każdy komponent niezależnie.

### 6.2 KLUCZOWE ZASTRZEŻENIE: czego ten mechanizm NIE robi

To jest najważniejsza rzecz do zrozumienia, zanim spróbujesz użyć tego mostu do czegokolwiek związanego z Verse:

> **Ten most sterowania to warstwa automatyzacji EDYTORA (Python Editor Scripting API), NIE most do runtime'u gry ani do kompilatora Verse.**
> Python w UEFN działa **tylko w edytorze** (offline). Verse działa w **runtime** gry. **Nie ma między nimi mostu** — Python może *odczytać* istnienie klas Verse (inspekcja), ale **nie może wywoływać funkcji Verse ani wstrzykiwać/kompilować kodu Verse**.

Konsekwencje praktyczne:

| Chcę... | Właściwy mechanizm |
|---|---|
| Napisać/zmienić **logikę gry w Verse** (device, event handler, UI widget z sekcji 1-4) | Zwykła edycja pliku tekstowego `.verse` (Read/Write/Edit) w folderze `Content/` projektu UEFN. UEFN sam skompiluje plik po zapisie/przy następnym buildzie. |
| Umieścić/usunąć/przesunąć **aktora na scenie** (mesh, światło, prop, urządzenie) | Narzędzia MCP z tabeli w 6.3 (`spawn_actor`, `delete_actors`, `set_actor_transform`) |
| Podpiąć **referencję `@editable`** urządzenia do konkretnego device'a na scenie | To jest operacja na **danych aktora w edytorze** (property UEFN, nie plik Verse) — potencjalnie osiągalna przez `set_actor_properties`/`execute_python`, ale wymaga znajomości dokładnej nazwy właściwości na danym typie aktora; w praktyce często szybciej/pewniej zrobić to ręcznie w panelu Details albo poprosić użytkownika o potwierdzenie po stronie edytora. |
| Stworzyć "blueprint widżetu" (`canvas`/`button`/`text_block`) | **To nie istnieje jako osobny artefakt w UEFN.** Widżety Verse UI (sekcja 3) to czysty kod — piszesz je jako zwykły tekst Verse, tak jak każdą inną logikę. Nie ma odpowiednika UMG Widget Blueprint dla gry w UEFN. (Python ma ograniczony dostęp do edycji *Editor Utility Widgets* — to osobne, wewnętrzne narzędzia edytora, NIE UI graczy w grze — nie mylić tych dwóch rzeczy.) |
| Skompilować i sprawdzić błędy Verse | Otwórz UEFN i zbuduj (albo poproś użytkownika o status); `get_editor_log`/`get_log` (MCP) pozwalają odczytać log edytora, w którym pojawią się błędy kompilacji Verse, jeśli aktualnie są widoczne w oknie logu. |

**Skrócona zasada dla modelu:** *pisanie Verse = zwykłe pliki tekstowe; sterowanie sceną/assetami = narzędzia MCP poniżej.* Nie wymyślaj narzędzia `create_widget_blueprint` ani `inject_verse_code` — nie istnieją w tym systemie.

### 6.3 Pełny katalog narzędzi (28)

| Kategoria | Narzędzie | Kluczowe parametry | Działanie |
|---|---|---|---|
| **System** | `ping` | — | Sprawdza, czy listener w UEFN żyje i odpowiada |
| | `execute_python` | `code` (string) | Wykonuje dowolny kod Python wewnątrz edytora — patrz 6.5 |
| | `get_log` | `last_n` | Ostatnie linie logu listenera MCP |
| | `get_editor_log` | `last_n`, `filter_str` | Ostatnie linie **pełnego** logu edytora UEFN (Output Log) |
| | `shutdown` | — | Bezpiecznie zatrzymuje listener |
| **Aktory** | `get_all_actors` | `class_filter` | Lista wszystkich aktorów na scenie (opcjonalnie filtrowana po klasie) |
| | `get_selected_actors` | — | Aktorzy aktualnie zaznaczeni w viewporcie |
| | `spawn_actor` | `asset_path` LUB `actor_class`, `location`, `rotation` | Spawnuje aktora (z assetu albo natywnej klasy UE) |
| | `delete_actors` | `actor_paths[]` | Usuwa aktory po ścieżce lub etykiecie |
| | `set_actor_transform` | `actor_path`, `location`, `rotation`, `scale` | Zmienia pozycję/rotację/skalę (tylko podane pola) |
| | `get_actor_properties` | `actor_path`, `properties[]` | Odczyt właściwości przez `get_editor_property()` |
| | `set_actor_properties` | `actor_path`, `properties{}` | Zapis właściwości przez `set_editor_property()` |
| | `select_actors` | `actor_paths[]`, `add_to_selection` | Programowe zaznaczenie w viewporcie |
| | `focus_selected` | — | Kamera viewportu skacze do zaznaczonych aktorów (jak klawisz F) |
| **Assety** | `list_assets` | `directory`, `recursive`, `class_filter` | Listuje zawartość katalogu Content Browser |
| | `get_asset_info` | `asset_path` | Szczegóły konkretnego assetu |
| | `get_selected_assets` | — | Assety zaznaczone w Content Browser |
| | `rename_asset` | `old_path`, `new_path` | Zmiana nazwy/przeniesienie |
| | `delete_asset` | `asset_path` | Usunięcie |
| | `duplicate_asset` | `source_path`, `dest_path` | Duplikacja |
| | `does_asset_exist` | `asset_path` | Sprawdzenie istnienia |
| | `save_asset` | `asset_path` | Zapis zmodyfikowanego assetu |
| | `search_assets` | `class_name`, `directory`, `recursive` | Wyszukiwanie przez Asset Registry |
| **Projekt** | `get_project_info` | — | Nazwa projektu i **root contentu** — patrz uwaga niżej |
| **Poziom** | `save_current_level` | — | Zapis bieżącego poziomu |
| | `get_level_info` | — | Nazwa świata, liczba aktorów |
| **Viewport** | `get_viewport_camera` | — | Aktualna pozycja/rotacja kamery edytora |
| | `set_viewport_camera` | `location`, `rotation` | Przesunięcie kamery edytora |

### 6.4 Konkretne przepisy (recipes)

**"Usuń obiekt":**
```
1. get_all_actors(class_filter="StaticMeshActor")   # znajdź dokładną ścieżkę/etykietę
2. delete_actors(actor_paths=["<pełna_ścieżka_lub_etykieta>"])
```

**"Zmodyfikuj parametry aktora na scenie":**
```
1. get_actor_properties(actor_path="Cube", properties=["mobility", "cast_shadow"])   # najpierw odczytaj, żeby znać typ/format
2. set_actor_transform(actor_path="Cube", location=[500, 0, 100])                    # transform: dedykowane narzędzie
   -- albo --
   set_actor_properties(actor_path="Cube", properties={"cast_shadow": false})        # dowolna właściwość edytora
```
> Uwaga: UEFN używa klas z prefiksem `Fort*`, nie wszystkie właściwości są zapisywalne przez `set_editor_property`. Jeśli `set_actor_properties` zwróci błąd o właściwości tylko-do-odczytu albo nieistniejącej, przejdź do `execute_python` i użyj dedykowanej metody (np. `actor.set_actor_hidden_in_game(True)`).

**"Zbuduj scenę proceduralnie" (np. siatka platform tycoona):**
```
execute_python z pętlą wywołującą unreal API bezpośrednio (patrz 6.5) —
szybsze niż wiele pojedynczych spawn_actor, gdy wzór jest regularny (grid, okrąg, itd.).
```

**"Uporządkuj Content Browser":**
```
1. search_assets(class_name="Material", directory="/MyProject/")
2. rename_asset(...) / delete_asset(...) w pętli po wynikach
```

**"Sprawdź, czy Verse się skompilował / jakie są błędy":**
```
get_editor_log(last_n=200, filter_str="Verse")
```

### 6.5 `execute_python` — pełna moc i jej granice

To najsilniejsze narzędzie — wykonuje dowolny kod Python z pełnym dostępem do modułu `unreal` (37 000+ typów, patrz `docs/uefn_python_capabilities.md` w tym repo dla pełnej mapy możliwości).

**Gotowe zmienne globalne dostępne w każdym wywołaniu:**

| Zmienna | Wartość |
|---|---|
| `unreal` | moduł `unreal` |
| `actor_sub` | `unreal.get_editor_subsystem(unreal.EditorActorSubsystem)` |
| `asset_sub` | `unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)` |
| `level_sub` | `unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)` |
| `result` | przypisz do tej zmiennej wartość, którą chcesz zwrócić (serializowana do JSON) |
| `tk`, `get_tk_root()` | do okien Tkinter — **nigdy `tk.Tk()`** (wiele instancji crashuje edytor), zawsze `tk.Toplevel(get_tk_root())` |

```python
# Przykład: masowe rozstawienie platform tycoona w siatce
actors_created = []
for row in range(5):
    for col in range(5):
        actor = actor_sub.spawn_actor_from_object(
            unreal.load_asset("/Engine/BasicShapes/Cube"),
            unreal.Vector(col * 300.0, row * 300.0, 0.0)
        )
        actors_created.append(actor.get_actor_label())
result = {"created": len(actors_created), "labels": actors_created}
```

**Ważny fakt o content roocie:** w UEFN root contentu to `/{NazwaProjektu}/`, **nie** `/Game/` jak w standardowym UE. Zawsze wywołaj najpierw `get_project_info()`, żeby poznać poprawny prefiks ścieżek przed operacjami na assetach.

**Czego `execute_python`/most Python NIE osiągnie (potwierdzone ograniczenia UEFN):**
- Brak spawnowania aktorów specyficznych dla Fortnite'a z poziomu Pythona.
- Brak modyfikacji ekwipunku/staty walki graczy (tylko odczyt).
- **Brak mostu do Verse** — można inspekcjonować istnienie klas Verse, nie da się wołać ich funkcji.
- Brak kontroli nad pętlą samej rozgrywki (start/stop meczu).

### 6.6 Rekomendowany workflow łączący oba światy

1. **Scena/urządzenia:** użyj MCP (`spawn_actor`, `get_all_actors`, `set_actor_transform`) żeby rozstawić/zweryfikować urządzenia Creative na mapie (np. `button_device`, `trigger_device`) i poznać ich dokładne etykiety/ścieżki.
2. **Logika:** napisz/zmodyfikuj `.verse` pliki zwykłymi narzędziami tekstowymi, referencjonując te same urządzenia przez `@editable` (sekcja 2.2) — **nazwa pola w Verse to Twój wybór**, ale samo **powiązanie** pola z konkretnym obiektem na scenie odbywa się w panelu Details w UEFN (ręcznie przez użytkownika, albo docelowo przez `set_actor_properties`/`execute_python`, jeśli znana jest dokładna nazwa property).
3. **Weryfikacja:** poproś użytkownika o zbudowanie projektu w UEFN (albo sprawdź `get_editor_log` pod kątem błędów kompilacji Verse), zanim ogłosisz zadanie ukończone.
4. **Podgląd:** `select_actors` + `focus_selected` żeby "pokazać" użytkownikowi (i sobie, jeśli masz dostęp do zrzutów ekranu) efekt zmian w viewporcie.

### 6.7 Bezpieczeństwo, gotowość i obsługa błędów

- **`ping` jako pierwszy krok** w nowej sesji — potwierdza, że UEFN jest otwarty i listener działa, zanim spróbujesz czegokolwiek innego.
- **Operacje destrukcyjne** (`delete_actors`, `delete_asset`) są nieodwracalne z poziomu tego API (poza `Ctrl+Z` ręcznie w edytorze) — traktuj je z taką samą ostrożnością jak `rm`/`git reset --hard`: potwierdź z użytkownikiem zakres przed wykonaniem, jeśli operacja jest szeroka (np. usuwanie wielu assetów na podstawie wzorca).
- **Tabela błędów mechanizmu:**

| Scenariusz | Zachowanie |
|---|---|
| Listener nie działa (UEFN zamknięty / skrypt nie uruchomiony) | `ConnectionError` z instrukcją uruchomienia listenera |
| Komenda zawiodła wewnątrz UEFN (np. zły `actor_path`) | `RuntimeError` z komunikatem błędu i pełnym tracebackiem Pythona |
| Komenda przekroczyła 30 sekund | `TimeoutError` |
| Nieprawidłowa odpowiedź JSON | Wyjątek propagowany dalej |

- Most jest **jednoużytkownikowy i lokalny** (`127.0.0.1`, port 8765+) — nie ma warstwy autoryzacji poza tym, że działa tylko na localhost obok otwartego edytora danego dewelopera.

---

## Załącznik: kluczowe źródła referencyjne

Do dalszej weryfikacji specyfiki API (zwłaszcza nazw urządzeń/metod, które zmieniają się między sezonami):

- Concurrency Overview in Verse — dev.epicgames.com/documentation/en-us/fortnite/concurrency-overview-in-verse
- Coding Device Interactions in Verse — dev.epicgames.com/documentation/en-us/fortnite/coding-device-interactions-in-verse
- Option in Verse — dev.epicgames.com/documentation/en-us/fortnite/option-in-verse
- Failure in Verse — dev.epicgames.com/documentation/en-us/fortnite/failure-in-verse
- Making Widgets Interactable in UEFN — dev.epicgames.com/documentation/en-us/fortnite/making-widgets-interactable-in-unreal-editor-for-fortnite
- Creating and Removing Widgets in UEFN — dev.epicgames.com/documentation/en-us/fortnite/creating-and-removing-widgets-in-unreal-editor-for-fortnite
- Positioning Widgets on the Screen in UEFN — dev.epicgames.com/documentation/en-us/fortnite/positioning-widgets-on-the-screen-in-unreal-editor-for-fortnite
- Using Persistable Data in Verse — dev.epicgames.com/documentation/fortnite/using-persistable-data-in-verse
- Verse Persistence Best Practices — dev.epicgames.com/documentation/fortnite/verse-persistence-best-practices
- Verse Code Style Guide in UEFN — dev.epicgames.com/documentation/en-us/fortnite/verse-code-style-guide-in-unreal-editor-for-fortnite
- Verse Language Quick Reference — dev.epicgames.com/documentation/en-us/uefn/verse-language-quick-reference
- Verse Glossary — dev.epicgames.com/documentation/fortnite/verse-glossary
- Book of Verse (community, nieoficjalny, ale bardzo dokładny) — verselang.github.io/book/
- Dokumentacja tego repo: `docs/architecture.md`, `docs/tools_reference.md`, `docs/uefn_python_capabilities.md`

**Zasada aktualizacji:** ten dokument bazuje na stanie wiedzy z sierpnia 2026. Verse jest aktywnie rozwijany (m.in. w kierunku Unreal Engine 6, gdzie ma się stać jednym z głównych języków silnika) — sekcje 1 (fundamenty składni) i sekcja 6 (mechanizm MCP, bo opisuje kod tego konkretnego repo) są najbardziej stabilne; sekcje 2, 3, 4 (nazwy konkretnych urządzeń/metod) wymagają okresowej weryfikacji względem aktualnej wersji UEFN.
