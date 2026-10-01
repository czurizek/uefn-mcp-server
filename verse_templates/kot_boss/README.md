# Boss „Kot” v2: wgranie poprawek lagów i dźwięków

Projekt: `testy_ai`, folder `/testy_ai/KotBoss/`. Kod: [`kot_boss_behavior.verse`](kot_boss_behavior.verse).

## Co zmienia v2

Przyczyny „zlagowanych” animacji ustalone z logów sesji testowej, od najważniejszej:

| Przyczyna | Poprawka |
|---|---|
| Zachwianie co ok. 3,5 s (próg 600 obrażeń), za każdym razem stop i animacja trafienia | Próg 2500 obrażeń, nie częściej niż co 10 s |
| Trasa do gracza liczona od nowa co 1 s, więc chód resetował się w połowie kroku | Jedno `NavigateTo`, które przerywa tylko strażnik (zasięg ataku, zachwianie, cel zniknął) |
| Ataki przesuwały ciało do przodu (skok aż o 4,85 m), potem szarpnięcie z powrotem | Animacje ataków „w miejscu”. Pierwszy import wyszedł w złej skali, patrz krok 0b |
| Mnożnik prędkości 2.0, szybszy niż krok animacji, więc stopy się ślizgały | Mnożnik 1.25 (do dostrojenia po teście, patrz niżej) |
| Ryk → tupnięcie przez `PlayAndAwait`, z mignięciem pozy spoczynkowej | Animacje zazębiają się na 0,2 s |
| Klatkowanie w trakcie uderzenia: v1 przez cały atak obraca bossa do gracza (`MaintainFocus`), a stare animacje odsuwają ciało o metry od prawdziwej pozycji NPC. Każdy skokowy obrót przerzuca odsunięte ciało łukiem | Obrót do gracza tylko przed atakiem (0,35 s), w trakcie ataku boss stoi. Do tego animacje „w miejscu” |

Dźwięki (12 plików CC0 z bigsoundbank.com, obniżone „olbrzymie”):
- pomruk w pętli, który idzie za bossem;
- dziwny odgłos co 7–16 s (nie w trakcie ryku);
- kroki w chwili postawienia stopy (0,37 s i 1,05 s cyklu chodu);
- ryk, świst zamachu, huk o ziemię;
- wrzask tylko przy zachwianiu;
- konanie.

## Krok 0: NIE zapisuj nowych animacji ataków

Sesja lokalna zaimportowała 6 animacji „w miejscu” (`/testy_ai/KotBoss/Anim/A_Kot_{JumpAttack,Swipe,Stomp,Roar,Smash,Hit}`)
i 12 dźwięków (`/testy_ai/KotBoss/Audio/S_Kot_*`) bez zapisu (`save=False`).

**Animacje są zepsute:** w trakcie ataku boss robi się ok. 100x większy. Przyczyna to przejście przez Blendera.
Mixamo zapisuje w centymetrach, Blender wczytuje szkielet ze skalą 0.01, a eksport FBX z Blendera zmienia jednostki.
Plik trafił do UEFN z dodatkowym ×100 na kościach, na to nałożył się jeszcze import ×16.
Sesja sprawdziła to tylko ponownym wczytaniem do Blendera, a nie w UEFN.

Co zrobić:
- **Nie rób Save All.** Przez **File → Choose Files to Save…** zapisz tylko `KotBoss/Audio`, a `KotBoss/Anim` odznacz.
  Restart UEFN bez zapisu animacji przywróci poprzednie wersje z dysku.
- Jeśli animacje już zostały zapisane, nic straconego. Oryginały są w `C:\CLAUDE\3D\boss_kot\mixamo\*.fbx`
  i można je zaimportować ponownie tak jak za pierwszym razem (`import_uniform_scale = 16`).

## Krok 0b: animacje „w miejscu” jeszcze raz (sesja lokalna)

Ataki trzeba przerobić na „w miejscu”, bo stare przesuwają ciało do przodu (skok o 4,85 m). Sposoby, od najprostszego:
1. Ponowny import plików `C:\CLAUDE\3D\boss_kot\mixamo_inplace\*.fbx` z `import_uniform_scale = 0.16` (16 / 100) zamiast 16.
   Najpierw tylko `A_Kot_Hit`. W podglądzie animacji porównaj długość kości z `A_Kot_Idle`. Jeśli pasuje, zrób resztę.
2. Jeśli skala nadal się nie zgadza, poprawić eksport w Blenderze (zastosować skalę szkieletu przed eksportem albo
   dobrać `global_scale` / `apply_scale_options`), a potem sprawdzić wynik **w UEFN**, nie w Blenderze.
3. Ominąć Blendera: wyzerować X/Y toru kości `mixamorig:Hips` bezpośrednio w UEFN (Python, AnimationDataController
   na kopii animacji). To ryzykowne pod kątem crashy, więc najpierw na kopii.

Po imporcie obejrzeć każdą animację w podglądzie, zanim cokolwiek zostanie zapisane.

## Krok 1: kod

1. Podmień zawartość `Documents\Fortnite Projects\testy_ai\Content\KotBoss\kot_boss_behavior.verse` na plik z tego folderu.
2. **Verse → Build Verse Code**. Kod nie był jeszcze kompilowany. Jeśli wyskoczy błąd, wklej go Claude'owi.

## Krok 2: 13 odtwarzaczy dźwięku

Tagi `kot_dzwiek_*` pojawią się w edytorze dopiero po udanym Build Verse Code z kroku 1.

Ustawienia wspólne dla wszystkich (Audio Player / Odtwarzacz dźwięku):
- Play Location = **Device**
- Can Be Heard By = **Everyone**
- Visible In Game = **Off**
- wszystkie AutoPlay = **Off**

Pozycja nie ma znaczenia, bo boss sam przestawia urządzenia do siebie. Postaw je np. obok spawnera.

| # | Tag Verse | Dźwięk (`/testy_ai/KotBoss/Audio/`) | Loop Audio | Restart Audio When Activated |
|---|---|---|---|---|
| 1 | `kot_dzwiek_pomruk` | `S_Kot_LoopAmbient` | **On** | Off |
| 2–6 | `kot_dzwiek_dziwny` | `S_Kot_Weird1` … `S_Kot_Weird5` (po jednym na urządzenie) | Off | On |
| 7–8 | `kot_dzwiek_krok` | `S_Kot_Footstep` (oba urządzenia, grają na zmianę) | Off | On |
| 9 | `kot_dzwiek_ryk` | `S_Kot_Roar` | Off | On |
| 10 | `kot_dzwiek_zamach` | `S_Kot_Swipe` | Off | On |
| 11 | `kot_dzwiek_uderzenie` | `S_Kot_Slam` | Off | On |
| 12 | `kot_dzwiek_trafienie` | `S_Kot_Hit` | Off | On |
| 13 | `kot_dzwiek_smierc` | `S_Kot_Death` | Off | On |

Tag dodajesz tak: zaznacz urządzenie, w panelu Details kliknij **+ Add**, wybierz **Verse Tag Markup**, a potem w polu Tags
dodaj element i wybierz tag z listy.

**Uwaga przy kopiowaniu** istniejącego „Odtwarzacz dźwięku” (tego od przechodniów): kopia ma tag `npc_death_sound`.
Usuń go, bo inaczej przechodnie mogą przejąć dźwięk bossa jako swój dźwięk śmierci.

## Krok 3: test

W logu sesji szukaj:
- `[KOT] Dzwieki: pomruk 1, dziwne 5, kroki 2, ryk 1, zamach 1, huk 1, trafienie 1, smierc 1`. Zero przy którymś = urządzenie nie ma tagu.
- `[KOT] Predkosc marszu: X cm/s`. Krok animacji pasuje do ok. 330 cm/s. Jeśli X jest daleko od 330, ustaw
  `PredkoscPoscigu = 1.25 × 330 / X` (Fortnite przycina do 0.5–2.0) w kodzie albo w NPCDef.

Co obejrzeć:
- uderzenia bez klatkowania. Jeśli nadal klatkuje, zrób dwa podejścia: (a) stój w miejscu i nie strzelaj,
  (b) biegaj wokół bossa i nie strzelaj. Jeśli klatkuje tylko w (b), winny jest obrót, a nie animacja.
  Jeśli w obu, a podgląd animacji w edytorze też szarpie, winny jest sam asset;
- chód podczas ostrzału bez stawania co 3–4 s;
- skok z uderzeniem bez szarpnięcia na koniec (animacje „w miejscu” nie były jeszcze oglądane w grze);
- czy zapętlony pomruk idzie za bossem. To nieudokumentowane. Jeśli zostaje w miejscu startu, trzeba odtwarzać krótki
  pomruk od nowa zamiast pętli.
