# WORLD CITY — tabela TOP 3 + własne miejsce

Tabela graczy dla wyspy **WORLD CITY**, napisana w Verse (Python w UEFN działa
tylko w edytorze — logika gameplay musi być w Verse).

Panel ma **zawsze 4 sloty**:

```
WORLD CITY
 #    PLAYER            CASH     LVL
 #1   Kowalski        1 240 500   42
 #2   Nowak             980 100   37
 #3   Wisniewski        640 000   31
 ─────────────────────────────────────
 #17  TY (podswietlony)  12 300    5
```

- Sloty 1–3 — TOP 3 **graczy aktualnie na tym serwerze**. Wszyscy na serwerze
  widzą te same trzy wiersze.
- Slot 4 — gracz, który patrzy na panel, wraz ze swoim miejscem w rankingu,
  nawet jeśli jest #17. Każdy widzi w tym slocie siebie.
- Ranking liczony jest z **cashu all-time** (nigdy nie spada przy wydawaniu),
  a remis rozstrzyga **poziom**. W panelu urządzenia można to odwrócić.

## Pliki

| Plik | Co robi |
|------|---------|
| `world_city_stats.verse` | Trwałe (persistent) statystyki gracza: cash all-time, XP, poziom + API: `AddCash`, `AddXP`, `SetPlayerLevel`, `GetWorldCityStats` |
| `world_city_leaderboard_device.verse` | Urządzenie z tabelą — cała UI i odświeżanie |
| `world_city_cash_source_device.verse` | Opcjonalne: podpina istniejące triggery/przyciski pod `AddCash` bez pisania kodu |

## Instalacja na mapie (np. Sp4nky)

Verse nie kompiluje się z Pythona (UEFN nie ma mostka do Verse), więc krok
„Build Verse Code" zawsze zostaje po twojej stronie. Reszta jest automatyczna.

### Wariant A — automatycznie, z Claude Code (serwer MCP z tego repo)

1. Otwórz mapę **Sp4nky** w UEFN i uruchom listener (`uefn_listener.py`).
2. Poproś Claude Code o instalację — pod spodem leci to przez `execute_python`:

   ```python
   import sys; sys.path.insert(0, r"C:/sciezka/do/uefn-mcp-server/tools")
   import install_world_city
   result = install_world_city.install(expect_project="Sp4nky")
   ```

   `expect_project` pilnuje, żeby pliki nie wjechały do innego projektu, gdyby
   w UEFN była otwarta inna wyspa. Skrypt sam znajduje `verse/world_city`
   obok siebie w repo; jeśli uruchamiasz go z innego miejsca, podaj
   `source_dir=r"...\verse\world_city"`.

3. W UEFN: **Verse > Build Verse Code** (Ctrl+Shift+B).
4. Wstaw urządzenie na mapę:

   ```python
   result = install_world_city.place_device()
   ```

   Spawnuje `world_city_leaderboard_device` w (0,0,0) i nazywa je
   `WORLD_CITY_Leaderboard` w Outlinerze. Panel jest w HUD, więc pozycja nie
   ma znaczenia. Ponowne wywołanie nie zrobi duplikatu (chyba że `force=True`).

5. Zapisz level i odpal sesję — panel jest w prawym górnym rogu.

### Wariant B — bez MCP, z menu UEFN

**Tools > Execute Python Script** → wskaż `tools/install_world_city.py`.
Skrypt skopiuje pliki, a potem sam spróbuje wstawić urządzenie (jeśli Verse
było już zbudowane) i wypisze w Output Logu, co zrobił. Po pierwszym
uruchomieniu zbuduj Verse i odpal skrypt jeszcze raz.

### Wariant C — ręcznie

Skopiuj **cały folder** `world_city` do `<Sp4nky>/Content/world_city/`
(wszystkie trzy pliki muszą zostać razem — to jeden moduł Verse),
zbuduj Verse i przeciągnij `world_city_leaderboard_device` z Content Browsera
na wyspę.

### Aktualizacja

Ponowna instalacja nadpisuje tylko to, co się zmieniło, a plik zmodyfikowany
lokalnie zostawia w spokoju i mówi o tym w wyniku. Świadome nadpisanie:
`install(force=True)`.

## Ustawienia (panel Details urządzenia)

| Opcja | Domyślnie | Opis |
|-------|-----------|------|
| `Title` | `WORLD CITY` | Nagłówek nad tabelą |
| `SortBy` | `CashAllTime` | `CashAllTime` = ranking po cashu (remis: poziom), `Level` = ranking po poziomie (remis: cash) |
| `SelfSlot` | `AlwaysShowMe` | `AlwaysShowMe` = slot 4 zawsze pokazuje patrzącego gracza (także gdy jest w TOP 3), `FourthPlaceWhenTop3` = jeśli gracz jest w TOP 3, slot 4 pokazuje 4. miejsce |
| `RefreshSeconds` | `2.0` | Co ile sekund odświeżają się liczby (minimum 0.5) |
| `ShowOnJoin` | `true` | Czy panel jest widoczny od razu po dołączeniu |
| `ToggleButtons` | puste | Przyciski, które włączają/wyłączają panel temu, kto je nacisnął |
| `PanelWidth` / `PanelHeight` | `460` / `232` | Rozmiar panelu w pikselach (1080p) |
| `MarginFromRight` / `MarginFromTop` | `48` / `140` | Pozycja względem prawego górnego rogu |

Z własnego kodu Verse można też wołać `Show(Player)`, `Hide(Player)`,
`Toggle(Player)` na urządzeniu.

## Podpięcie cashu

**Wariant A — masz już swój kod cashu.** Dodaj jedną linię tam, gdzie gracz
dostaje pieniądze:

```verse
AddCash(Participant, 500)   # 500 do cashu all-time
AddXP(Participant, 25)      # opcjonalnie XP -> poziom
```

Wydawanie pieniędzy **nie** wymaga żadnej zmiany — `CashAllTime` z założenia
liczy tylko zarobek, więc ranking pokazuje realny dorobek gracza, a nie stan
portfela.

**Wariant B — bez pisania kodu.** Przeciągnij na wyspę
`world_city_cash_source_device`, wskaż w nim triggery/przyciski i ustaw
`CashPerActivation`. Jedno urządzenie na jedną kwotę.

**Poziom.** Domyślnie poziom liczy się z XP (100, 150, 200… XP na kolejny
poziom, cap 100). Jeśli WORLD CITY ma już własny system poziomów, wołaj
`SetPlayerLevel(Participant, Poziom)` i nie używaj `AddXP`.

## Ograniczenia, o których warto wiedzieć

- **Zapis między sesjami działa dopiero po opublikowaniu wyspy.** W edytorze
  dane żyją tyle, co sesja — to normalne zachowanie persistence w UEFN.
- **Po publikacji nie zmieniaj pól struktury `world_city_player_stats`.**
  Usunięcie lub zmiana nazwy pola kasuje zapisane dane wszystkich graczy.
  Nowe dane dodawaj podnosząc `CurrentStatsVersion` i obsługując stary kształt
  w `MigrateStats()`.
- **Ranking obejmuje tylko graczy obecnych na serwerze** — dokładnie tak, jak
  ma być. Verse nie daje dostępu do danych graczy spoza sesji, więc globalny
  ranking całej wyspy nie jest możliwy bez zewnętrznego backendu.
- **Nazwa gracza** trafia do tabeli przez interpolację `agent` w wiadomości
  (`"{Participant}"`) — Verse nie zwraca nicku jako `string`.
- **Rozmiaru czcionki** Verse UI nie ustawia z kodu. Wygląd reguluje się
  szerokością panelu i podziałem kolumn (`WorldCity*Share` na górze pliku
  urządzenia).
