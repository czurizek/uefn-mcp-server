# UEFN Scout

Program, ktory przeszukuje internet w poszukiwaniu narzedzi ulatwiajacych prace
w UEFN — serwerow MCP, generatorow 3D, mostow do Blendera, optymalizatorow
assetow — ocenia je i pamieta, co juz widzial. Przy kolejnym uruchomieniu
pokazuje **tylko to, co nowe**.

Dziala na dwa sposoby: z terminala (`python -m scout`) albo jako serwer MCP,
czyli Claude Code sam wykonuje wyszukiwanie w trakcie rozmowy.

Zero zaleznosci poza standardowa biblioteka Pythona. Pakiet `mcp` jest
potrzebny wylacznie do trybu serwera MCP.

---

## Szybki start

```bash
cd uefn-mcp-server

# 1. Co juz jest sprawdzone recznie — zero ruchu sieciowego
python -m scout catalog --tag priority

# 2. Jakie tematy program potrafi sledzic
python -m scout profiles

# 3. Pierwszy skan (kilka minut bez tokenu GitHuba — limit 10 zapytan/min)
python -m scout scan

# 4. Raport z bazy, bez ruchu sieciowego
python -m scout report --min-score 55
```

### Token GitHuba (zalecany)

Bez tokenu GitHub przepuszcza ~10 zapytan na minute i skaner sam sie usypia
miedzy zapytaniami. Z tokenem jest ~30/min i skan trwa sekundy zamiast minut.
Wystarczy token bez zadnych uprawnien (public repo read).

```bash
export GITHUB_TOKEN=ghp_...        # Linux / macOS
setx GITHUB_TOKEN "ghp_..."        # Windows
```

---

## Komendy

| Komenda | Do czego |
|---|---|
| `scout profiles` | lista tematow wyszukiwania i ich wag |
| `scout scan` | przeszukuje zrodla, ocenia i zapisuje wyniki |
| `scout report` | raport z bazy (bez sieci) |
| `scout catalog` | recznie zweryfikowany punkt startowy z komentarzem "jak sie to ma do UEFN" |
| `scout show <uid>` | pelne dane jednego znaleziska wraz z rozbiciem scoringu |
| `scout mark <uid> <status>` | werdykt po przejrzeniu: `watching`, `adopted`, `rejected` |
| `scout stats` | stan bazy i data ostatniego skanu |

Przydatne warianty:

```bash
python -m scout scan --profile ai-3d --limit 50      # tylko generatory 3D
python -m scout scan --source pypi                    # dorzuc PyPI (duzy indeks za pierwszym razem)
python -m scout report --new                          # tylko rzeczy nigdy wczesniej niewidziane
python -m scout report --out raport.md                # zapis do pliku
python -m scout mark ai-3d/github:foo/bar rejected --note "martwe od 2 lat"
```

---

## Tryb MCP — Claude szuka sam

Dopisz do `.mcp.json` obok wpisu `uefn`:

```json
{
  "mcpServers": {
    "uefn": {
      "command": "python",
      "args": ["C:/sciezka/uefn-mcp-server/mcp_server.py"]
    },
    "uefn-scout": {
      "command": "python",
      "args": ["-m", "scout.mcp_scout"],
      "cwd": "C:/sciezka/uefn-mcp-server",
      "env": { "GITHUB_TOKEN": "ghp_..." }
    }
  }
}
```

Po restarcie Claude Code dostaje szesc narzedzi: `scout_profiles`,
`scout_scan`, `scout_report`, `scout_catalog`, `scout_mark`, `scout_stats`.
Wtedy dziala normalna rozmowa:

> *"Poszukaj nowych narzedzi do generowania modeli 3D i powiedz, ktore z nich
> realnie wpina sie w moj pipeline UEFN."*

---

## Profile wyszukiwania

Kazdy profil to jeden temat: wlasne zapytania do kazdego zrodla, wlasne slowa
kluczowe podbijajace trafnosc, wlasne slowa wykluczajace i wlasna waga.

| Profil | Temat |
|---|---|
| `ai-3d` | generatory 3D z tekstu/obrazu (waga najwyzsza) |
| `uefn` | narzedzia dotykajace wprost UEFN, Verse, Fortnite Creative |
| `unreal-mcp` | serwery MCP do Unreal Engine — zrodlo wzorcow do przeniesienia |
| `blender-bridge` | Blender jako etap czyszczenia mesha przed importem |
| `texturing` | generatory tekstur i materialow PBR |
| `procedural` | proceduralne generowanie geometrii i leveli |
| `pipeline` | LOD, kolizje, walidacja, budzet pamieci |
| `agent-tooling` | wzorce narzedzi MCP w gamedevie |

Profile siedza w `scout/data/profiles.json` — to zwykly JSON, mozna dopisac
wlasny temat bez dotykania kodu.

---

## Jak liczony jest scoring

```
score = 100 × trafnosc × jakosc × waga_profilu
```

**Trafnosc** (0–1) mnozy calosc, a nie dodaje sie do niej. To celowe: pakiet z
50 tysiacami gwiazdek, ktory tylko przypadkiem zawiera slowo "model", ma
wygrywac z niczym.

- brak ktoregokolwiek slowa z `require_any` → **0**, wynik wypada
- trafienie slowa z `negative` → **0**, wynik wypada
- kazde slowo z `boost` podnosi trafnosc z nasyceniem (4 trafienia to juz duzo)

**Jakosc** to suma trzech skladnikow plus baza 0,25:

| Skladnik | Waga | Znaczenie |
|---|---|---|
| swiezosc | 0,30 | polowiczny zanik ~6 miesiecy od ostatniego commita |
| adopcja | 0,25 | log10 z gwiazdek: ~30 gwiazdek to polowa skali |
| wykonalnosc | 0,20 | czy to cos instalowalnego (MCP, plugin, CLI, API), czy lista linkow |

Rozbicie kazdego wyniku widac w `scout show <uid>`.

---

## Zrodla

| Zrodlo | Co daje | Uwagi |
|---|---|---|
| `github` | repozytoria | najwazniejsze zrodlo; token mocno przyspiesza |
| `mcp_registry` | oficjalny rejestr MCP | serwery gotowe do instalacji |
| `npm` | pakiety JS/TS | wiekszosc serwerow MCP w TypeScript |
| `pypi` | pakiety Python | poza domyslnym zestawem: pierwszy raz pobiera duzy indeks |

Domyslnie: `github`, `mcp_registry`, `npm`. PyPI dodajesz przez `--source pypi`.
Awaria jednego zrodla nie przerywa skanu — bledy ladują w sekcji raportu.

---

## Baza

SQLite w `~/.uefn-scout/scout.sqlite3` (mozna nadpisac przez `UEFN_SCOUT_DB`).
Trzyma date pierwszego zobaczenia — stad dziala `--new` — oraz Twoj werdykt,
ktorego kolejny skan **nie nadpisuje**.

## Testy

```bash
python tests/test_scout.py
```

Kompletnie offline: scoring, baza, raporty i parser odpowiedzi GitHuba na
zapisanej odpowiedzi API.
