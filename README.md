## Wymagania
- Windows 10/11
- Python 3.14 lub nowsze
- Raspberry Pi Pico (RP2040)

## Instalacja
1. Instalacja Python 3.14 (upewnij się aby zaznaczyć **Add Python to PATH**).
2. Sklonuj lub pobierz to repostorium.
3. Zainstaluj potrzebne rozszerzenia Python'a:
Po zainstalowaniu Pythona, możemy uruchomić skrypt **instalacja_rozszerzen.bat**.
Musimy go włączyć tylko raz i nasze środowisko powinno być gotowe do pracy.

## Uruchamianie aplikacji
Uruchamiamy poprzez włączenie skryptu **start_GUI.bat**.

## Instrukcja obsługi:
1. Najpierw należy wybrać port na którym jest podpięte Pico(GUI powinno samo wykryć, na którym COM'ie jest połączona płytka).
2. Następnie wybrać lub wpisać ścieżkę i plik do wgrania na płytkę.   
3. Wcisnąć przycisk "Wgraj na Pico" lub upewnić się, że mamy zaznaczone "Auto wgraj przy Połącz", wtedy nie musimy wgrywać sami kodu, tylko za każdym razem kod wgra się samodzielnie przy połączeniu z płytką.
4. Łączamy się z Pico przy pomocy przycisku "Połącz"     
5. Kolejno naciskamy przycisk "Restart" lub wciskamy na klawiaturze Ctrl+D, aby zrobić soft-reset na Pico co pozwoli jej uruchomić wcześniej wgrany na nią skrypt.
6. Dalej możemy sterować przuciskami lub wpisywać w oknie tekstowym pod komunikatami, odpowiadające tym przyciską litery i potwierdzamy wciskając enter.


## Częste problemy
- Pico nie zostało wykryte → sprawdzamy port COM w Menadżerze Urządzeń
- Kod wgrany ale nie włącza się → wcisnąc Restart lub (Ctrl+D)
- pip not found → przeinstalować Python z zaznaczonym Path 

## Opis programów:
main_TDC.py program dla ćwiczenia 1 i 2  
main_Vernier_TDC.py program dla ćwiczenia 3 

## LINKI
-Przydatne linki do Pobrania potrzebnego środowiska:
https://www.python.org/

