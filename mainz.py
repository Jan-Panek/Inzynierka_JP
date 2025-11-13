from machine import Pin
from rp2 import PIO, StateMachine, asm_pio
import time

# --- parametry ---
MAX_LEN = 30                  # liczba "slotów" w ramce
FREQ_HZ = 100_000_000
PIN_START = 10                  # START = stałe HIGH (GPIO)
PIN_STOP = 20                  # STOP  = okno HIGH N/MAX_LEN (PIO)
AUTO_DEMO = False                # start od automatycznego wydłużania co 1 s

# --- START jako zwykłe GPIO (pewny HIGH) ---
start_pin = Pin(PIN_START, Pin.OUT)
start_pin.value(1)



@asm_pio(
    set_init=PIO.OUT_LOW,         # STOP (GPIO20) start LOW
    out_shiftdir=PIO.SHIFT_RIGHT  # OUT pobiera najniższe bity OSR
)
def stop_pwm_packed_set():
    pull()                        # pierwsze słowo (blokująco)
    mov(x, osr)                   # X = packed

    wrap_target()

    # bezpieczna aktualizacja X (tylko jeśli przyszło nowe słowo)
    mov(osr, x)                   # OSR = stary packed
    pull(noblock)                 # jeśli FIFO puste -> OSR bez zmian
    mov(x, osr)                   # X = nowy packed albo stary

    # backup packed -> ISR
    mov(isr, x)

    # Y = high_len (dolne 16)
    mov(osr, x)
    out(y, 16)                    # Y = low16(packed)

    # X = low_len (górne 16)
    mov(osr, isr)
    out(null, 16)                 # zrzuć low16
    mov(x, osr)                   # X = high16(packed)

    # STOP = HIGH przez Y slotów
    set(pins, 1)
    label("hi")
    jmp(y_dec, "hi")

    # STOP = LOW przez X slotów
    set(pins, 0)
    label("lo")
    jmp(x_dec, "lo")

    # przywróć X = packed i kolejna ramka
    mov(x, isr)
    wrap()


# --- uruchom SM ---
sm = StateMachine(0, stop_pwm_packed_set, freq=FREQ_HZ, set_base=Pin(PIN_STOP))

length = 0  # 0..MAX_LEN


def send_packed():
    """Wyslij JEDNO 32-bit słowo: (low_len<<16)|high_len."""
    h = max(0, min(MAX_LEN, length))
    l = MAX_LEN - h
    packed = ((l & 0xFFFF) << 16) | (h & 0xFFFF)
    sm.put(packed)
    # prosta wizualizacja w konsoli:
    bar = "■" * h + "□" * l
    slot_ns = int(1_000_000_000 // FREQ_HZ)
    print(f"[{bar}]  STOP high={h}/{MAX_LEN}  | frame≈{FREQ_HZ//MAX_LEN} Hz, slot≈{slot_ns} ns")


# podaj wartość startową PRZED startem SM
send_packed()
sm.active(1)

print(f"START (GPIO{PIN_START}) = HIGH (GPIO).")
print(
    f"STOP  (GPIO{PIN_STOP}) = okno HIGH N/{MAX_LEN}.  Zmieniaj: 'w'/'s', auto: 'a', stop: Ctrl+C.")

# --- pętla główna: tryb AUTO lub ręczny (bez .any(); input blokuje tylko w trybie ręcznym) ---
last_tick = time.ticks_ms()

try:
    while True:
        if AUTO_DEMO:
            # co 1 s zwiększaj wypełnienie i wysyłaj nowy packed
            if time.ticks_diff(time.ticks_ms(), last_tick) >= 1000:
                last_tick = time.ticks_ms()
                length = (length + 1) % (MAX_LEN + 1)   # 0→1→…→MAX→0…
                send_packed()
            # mała drzemka, żeby nie mielić CPU
            time.sleep(0.01)
        else:
            # tryb ręczny: blokujący input (działa na REPL bez .any())
            cmd = input().strip().lower()
            if cmd == 'w' and length < MAX_LEN:
                length += 1
                send_packed()
            elif cmd == 's' and length > 0:
                length -= 1
                send_packed()
            elif cmd == 'a':
                AUTO_DEMO = True
                print("AUTO_DEMO: ON")
            else:
                print(f"⛔ Zakres 0–{MAX_LEN} lub uzyj 'a' by wlaczyc AUTO.")
except KeyboardInterrupt:
    sm.active(0)
    print("\nZatrzymano.")
