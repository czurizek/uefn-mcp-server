# Asystent Doradczyni Thermomix — konspekt

Aplikacja na telefon z Androidem, która z bazy klientów i jednego opisu nowej
oferty układa **osobną wiadomość dla każdej osoby**, pokazuje ją doradczyni do
akceptacji i wysyła. Nie masówka z jednym szablonem, tylko krótki tekst
brzmiący jak pisany ręcznie do konkretnej klientki.

- **Użytkownik:** jedna osoba, niezależna doradczyni Thermomix
- **Urządzenie:** telefon z Androidem
- **Kanały:** WhatsApp i SMS
- **Skala:** ok. 100–500 kontaktów

Wersja do czytania na telefonie:
https://claude.ai/code/artifact/32036133-9836-4327-8dc8-9cc65facb34c

---

## 1. Przebieg jednej kampanii

| Krok | Co się dzieje | Kto działa |
|------|---------------|------------|
| 1 | Opis oferty: warunki, termin, dla kogo (wpisany lub podyktowany) | doradczyni |
| 2 | Dobór odbiorców z profili; osoby bez zgody są odrzucane | aplikacja |
| 3 | Dla każdej osoby powstaje osobny tekst z jej danych i historii kontaktu | aplikacja |
| 4 | Kolejka do akceptacji: poprawka, odrzucenie albo zatwierdzenie | doradczyni |
| 5 | Wysyłka rozłożona w czasie, wpis do historii klienta | aplikacja |

## 2. Skąd bierze się wrażenie osobistej wiadomości

Z konkretu, którego nie da się podstawić z szablonu. Cztery mechanizmy:

- **Głos doradczyni** — model dostaje 8–10 jej prawdziwych wiadomości jako wzór
  stylu: jak zaczyna, jak kończy, ile emoji, kiedy „Pani”, a kiedy „Ty”.
- **Twarde reguły** — model nie wymyśla liczb. Ceny, terminy i nazwy modeli
  pochodzą wyłącznie ze słownika kampanii; brak wartości oznacza brak zdania.
- **Różnorodność** — każda wiadomość musi zawierać co najmniej jeden konkret
  z profilu i mieć inne otwarcie niż trzy poprzednie.
- **Ostatnie słowo** — nic nie wychodzi bez tapnięcia. Poprawka wraca do modelu
  jako materiał na kolejne kampanie.

### Przykład: ta sama kampania, dwie klientki

Dane przykładowe.

**Grażyna K.** — TM5 z 2017, kupno na pokazie, wypieki, wnuki, ostatni kontakt
w marcu, forma zwrotu „Pani”, kanał SMS:

> Pani Grażyno, dzień dobry!
>
> Pamiętam, jak w marcu szukałyśmy razem formy do chleba — i od razu pomyślałam
> o Pani, bo Vorwerk uruchomił wymianę starszych modeli z odkupem urządzenia.
> Piątka po ośmiu latach pewnie wciąż pracuje bez zarzutu, ale wyrastanie ciasta
> prowadzi się teraz z automatu.
>
> Policzyć Pani, ile wychodzi po odkupie? Bez żadnego zobowiązania.
>
> Pozdrawiam serdecznie, Ewa

**Kasia W.** — TM6 z 2022, z polecenia, dieta bez laktozy, dwoje dzieci,
aktywne Cookidoo, forma zwrotu „Ty”, kanał WhatsApp:

> Kasiu, cześć!
>
> W Cookidoo zrobił się cały dział obiadów bez laktozy do trzydziestu minut —
> przy Twojej dwójce to chyba dokładnie to, czego szukałaś.
>
> Przy okazji jest teraz wymiana na nowy model z odkupem, ale szczerze: Twój
> sprzęt ma dopiero trzy lata i nie widzę powodu, żeby się spieszyć. Gdybyś
> kiedyś chciała porównać, odezwij się.
>
> Buziaki!

Druga wiadomość pokazuje regułę, na której zależy najbardziej: jeśli oferta
komuś nie służy, asystent ma to napisać wprost. To jest różnica między
doradczynią a spamem.

## 3. Czym wysyłać — decyzja o największych konsekwencjach

| Sposób | Jak działa | Wysiłek | Ryzyko | Kiedy |
|--------|-----------|---------|--------|-------|
| **Kolejka jednym tapnięciem** (start) | Aplikacja otwiera rozmowę w WhatsAppie lub SMS-ach z gotowym tekstem; doradczyni naciska „wyślij” | ok. 5 s na osobę | żadne — wysyła sama, ze swojego numeru, w istniejącym wątku | od razu |
| **Bramka SMS** | Serwis (np. SMSAPI) wysyła w tle, każdy SMS ma osobną treść, nadawca to zarejestrowana nazwa | zero | niskie — wymaga zgód i „STOP” w treści | powyżej ok. 150 osób |
| **WhatsApp Cloud API** | Oficjalne konto Meta; wiadomość startowa musi być zatwierdzonym szablonem ze zmiennymi | zero, ale kampania z wyprzedzeniem | średnie — weryfikacja firmy, akceptacja szablonów, opłata za rozmowę | gdy WhatsApp stanie się głównym kanałem |

**Czego nie robimy:** nie podpinamy się pod WhatsApp przez nieoficjalne
biblioteki udające telefon (whatsapp-web.js, Baileys itp.). To najczęstszy
pomysł w takich projektach i najszybsza droga do trwałej blokady numeru — a ten
numer to cała baza klientów. Ścieżka wykluczona na stałe, nie „na razie”.

## 4. Budowa

Aplikacja webowa (PWA) instalowana na telefonie jak zwykła ikona, bez Sklepu
Play. Otwiera się offline, dane trzyma u siebie, do internetu sięga tylko po
wygenerowanie treści.

- **Ekran** — PWA, duże przyciski, cztery widoki: Klienci, Kampania, Kolejka,
  Historia.
- **Dane** — baza w telefonie plus kopia w chmurze na wypadek zgubienia
  telefonu. Import klientów z pliku albo z kontaktów.
- **Pisanie treści** — mały serwer łączy profil klientki, opis oferty i próbki
  stylu, wywołuje model językowy i sprawdza wynik pod kątem reguł.
- **Wysyłka** — na start odnośniki `https://wa.me/<numer>?text=…` oraz
  `sms:<numer>?body=…`. Później w to samo miejsce podpinamy bramkę SMS.

### Model danych klienta

- **Podstawy** — imię, nazwisko, telefon, forma zwrotu, preferowany kanał, miasto
- **Urządzenie** — model, rok zakupu, źródło pozyskania, status Cookidoo
- **Zainteresowania** — pieczenie, dieta, dzieci, alergie, ulubione przepisy
- **Historia** — data i treść ostatniego kontaktu, reakcje, prośby o spokój
- **Zgody** — na SMS, na WhatsApp, data i sposób udzielenia, data wycofania
- **Notatki** — jedno pole wolnego tekstu

## 5. Zgody i obowiązki

- Wysyłka handlowa na telefon wymaga **wcześniejszej zgody odbiorcy**.
  Aplikacja ma to wymuszać: brak zgody = kontakt nie trafia do kampanii
  (nie: ostrzeżenie na ekranie).
- Zapis zgody trzyma datę, kanał i sposób pozyskania. Wycofanie działa
  natychmiast i jest nieodwracalne dla przyszłych wysyłek.
- W wiadomości musi być widoczne, kto pisze; w SMS także jak zrezygnować.
- Doradczyni jest administratorem danych swoich klientów: potrzebna krótka
  informacja dla klienta oraz eksport i usunięcie danych na żądanie.
- Jako **niezależna** doradczyni nie może wysyłać wiadomości wyglądających na
  oficjalny komunikat Vorwerk. Warto sprawdzić zasady użycia nazwy i logo
  w umowie.

To nie jest opinia prawna. Przed pierwszą kampanią warto dać treść zgody
i wzór wiadomości do sprawdzenia komuś, kto zna przepisy o marketingu
bezpośrednim.

## 6. Plan wdrożenia

**F0 — Dane i zgody (2–3 dni).** Jedyna część, którą musi wykonać doradczyni.
Spisanie klientów do arkusza, ustalenie kto i kiedy zgodził się na wiadomości,
zebranie 8–10 prawdziwych wysłanych wiadomości.

**F1 — Działający asystent (1–2 tygodnie).** Lista klientów i profil na
telefonie, opis oferty, generowanie wiadomości, kolejka do akceptacji, wysyłka
jednym tapnięciem. Na końcu tej fazy idzie pierwsza prawdziwa kampania.

**F2 — Porządek i pamięć (1 tydzień).** Historia wysyłek, blokada „nie pisz
częściej niż raz na X tygodni”, segmenty klientów, zapisane kampanie,
przypomnienia o urodzinach i rocznicach zakupu.

**F3 — Wysyłka bez klikania (opcja).** Bramka SMS z zarejestrowaną nazwą
nadawcy i obsługą „STOP”, ewentualnie WhatsApp Cloud API, prosty raport
odpowiedzi. Tylko gdy lista urośnie na tyle, że kolejka zacznie męczyć.

## 7. Koszty przy ok. 100 wiadomościach miesięcznie

Wartości orientacyjne, do potwierdzenia u dostawców.

| Pozycja | Start | Miesięcznie |
|---------|-------|-------------|
| Hosting aplikacji | 0 zł | 0 zł |
| Baza danych | 0 zł | 0 zł |
| Pisanie wiadomości (model językowy) | 0 zł | ok. 2–8 zł |
| Wysyłka tapnięciem | 0 zł | 0 zł (abonament) |
| Bramka SMS (F3) | jednorazowa rejestracja nadawcy | ok. 10–20 zł |
| WhatsApp Cloud API (F3) | 0 zł | ok. 20–30 zł |

## 8. Ryzyka

| Zagrożenie | Zabezpieczenie |
|-----------|----------------|
| Blokada numeru za masową wysyłkę | Żadnej nieoficjalnej automatyzacji WhatsAppa; wysyłka z ręki albo kanałem oficjalnym, rozłożona w czasie |
| Wiadomości brzmią jak od bota | Próbki stylu, obowiązkowy konkret z profilu, rotacja otwarć, akceptacja każdej wiadomości |
| Model wymyśla cenę albo warunek | Liczby i terminy wyłącznie ze słownika kampanii; wiadomość ze zmyśloną liczbą nie przechodzi kontroli |
| Wysyłka do osoby bez zgody | Zgoda jako warunek wejścia do kampanii, sprawdzany po stronie serwera |
| Klient dostaje trzecią wiadomość w miesiącu | Blokada częstotliwości na poziomie klienta, wspólna dla kampanii |
| Doradczyni gubi się w aplikacji | Jeden główny przycisk, tryb kolejki bez menu, cofanie ostatniej akcji |
| Zgubiony albo zepsuty telefon | Kopia bazy w chmurze, logowanie z drugiego urządzenia |

## 9. Do ustalenia przed startem

1. **Ilu jest klientów i w jakiej postaci** — kontakty w telefonie, zeszyt,
   arkusz? Od tego zależy długość fazy F0.
2. **Który kanał przeważa** — przy przewadze WhatsAppa kolejka tapnięciem
   wystarczy na długo; przy przewadze SMS-ów wcześniej sięgniemy po bramkę.
3. **Czy zgody marketingowe są zebrane** — jeśli nie, pierwszą kampanią jest
   kampania o zgodę, do osób będących i tak w bieżącym kontakcie.
4. **Próbki stylu** — kilkanaście prawdziwych wiadomości. Jedyna rzecz, której
   nie da się obejść ani wygenerować, a decyduje o całej reszcie.

---

Kolejny krok po odpowiedziach z sekcji 9: makieta czterech ekranów i szkielet
bazy klientów, żeby faza F0 mogła ruszyć równolegle z budową.
