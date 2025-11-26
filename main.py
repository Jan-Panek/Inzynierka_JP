from machine import Pin
from rp2 import PIO, StateMachine, asm_pio
import time

# --- parametry ---
MAX_LEN = 50                 # liczba "slotow" w ramce
FREQ_HZ = 100_000_000         # zegar PIO (slot = 1/FREQ_HZ)
PIN_START = 10                  # START = HIGH -> LOW
PIN_STOP = 20                  # STOP  = LOW prefix -> HIGH reszta
PIN_SYNC = 2                   # wspólny pin synchronizacji (LOW->HIGH = start)
AUTO_DEMO = False

# --- PIO: START — HIGH przez Y, potem LOW przez X (czeka na SYNC; set w każdej iteracji) ---


@asm_pio(
    set_init=PIO.OUT_LOW,
    out_shiftdir=PIO.SHIFT_RIGHT
)
def win_pwm_packed_set_sync():
    wait(1, pin, 0)          # czekaj na SYNC (pin = in_base + 0)

    pull()                   # pierwsze słowo
    mov(x, osr)              # X = packed

    wrap_target()
    # pobierz nowe słowo, jeśli jest
    mov(osr, x)
    pull(noblock)
    mov(x, osr)

    # backup
    mov(isr, x)

    # Y = high_len (low16)
    mov(osr, x)
    out(y, 16)

    # X = low_len (high16)
    mov(osr, isr)
    out(null, 16)
    mov(x, osr)

    # HIGH przez Y slotów — set w KAŻDEJ iteracji (równe sloty jak w STOP)
    jmp(not_y, "after_hi")
    label("hi")
    set(pins, 1)
    jmp(y_dec, "hi")
    label("after_hi")

    # LOW przez X slotów — set w KAŻDEJ iteracji
    jmp(not_x, "after_lo")
    label("lo")
    set(pins, 0)
    jmp(x_dec, "lo")
    label("after_lo")

    mov(x, isr)
    wrap()

# --- PIO: STOP — LOW przez Y, potem HIGH przez X (czeka na SYNC; już set w każdej iteracji) ---


@asm_pio(
    set_init=PIO.OUT_LOW,
    out_shiftdir=PIO.SHIFT_RIGHT
)
def win_pwm_packed_low_high_sync():
    wait(1, pin, 0)          # czekaj na SYNC (pin = in_base + 0)

    pull()                   # pierwsze słowo
    mov(x, osr)

    wrap_target()
    # pobierz nowe słowo, jeśli jest
    mov(osr, x)
    pull(noblock)
    mov(x, osr)

    # backup
    mov(isr, x)

    # Y = low_len (high16)
    mov(osr, x)
    out(null, 16)
    mov(y, osr)

    # X = high_len (low16)
    mov(osr, isr)
    out(x, 16)

    # LOW przez Y slotów
    jmp(not_y, "after_low")
    label("low")
    set(pins, 0)
    jmp(y_dec, "low")
    label("after_low")

    # HIGH przez X slotów
    jmp(not_x, "after_high")
    label("high")
    set(pins, 1)
    jmp(x_dec, "high")
    label("after_high")

    mov(x, isr)
    wrap()


# --- dwie SM w tym samym bloku PIO i ze wspólnym in_base (SYNC) ---
sm_start = StateMachine(0, win_pwm_packed_set_sync,
                        freq=FREQ_HZ, set_base=Pin(PIN_START), in_base=Pin(PIN_SYNC))
sm_stop = StateMachine(4, win_pwm_packed_low_high_sync,
                       freq=FREQ_HZ, set_base=Pin(PIN_STOP),  in_base=Pin(PIN_SYNC))

# --- długości w slotach ---
len_start = 1   # START: ile slotów HIGH (0..MAX_LEN)
len_stop = 1   # STOP : ile slotów LOW na początku (0..MAX_LEN)


def _send_start():
    h = max(0, min(MAX_LEN, len_start))
    l = MAX_LEN - h
    sm_start.put(((l & 0xFFFF) << 16) | (h & 0xFFFF))
    bar = "■"*h + "□"*l
    print(f"START: [{bar}]  HIGH={h}/{MAX_LEN}")


def _send_stop():
    low_prefix = max(0, min(MAX_LEN, len_stop))
    high_rest = MAX_LEN - low_prefix
    sm_stop.put(((low_prefix & 0xFFFF) << 16) | (high_rest & 0xFFFF))
    bar = "□"*low_prefix + "■"*high_rest
    print(f"STOP : [{bar}]  LOWprefix={low_prefix}/{MAX_LEN}")


# --- SYNC start ---
sync = Pin(PIN_SYNC, Pin.OUT)
sync.value(0)              # obie SM będą czekać na wait(pin)
_send_stop()
_send_start()
sm_stop.active(1)
sm_start.active(1)

time.sleep_us(5)           # krótki oddech po active()
sync.value(1)              # wspólny start
time.sleep_us(2)
sync.value(0)              # opcjonalnie wróć na LOW

# --- info ---
frame_hz = FREQ_HZ // MAX_LEN
slot_ns = int(1_000_000_000 // FREQ_HZ)
print(
    f"SYNC na GPIO{PIN_SYNC}. START GPIO{PIN_START} i STOP GPIO{PIN_STOP} startują razem.")
print(f"Ramka ≈ {frame_hz} Hz, slot ≈ {slot_ns} ns.")
print("Sterowanie: STOP 'w'/'s' (LOW prefix +/-) | START 'i'/'k' (HIGH +/-) | 'a' auto | Ctrl+C")

last_tick = time.ticks_ms()
try:
    while True:
        if AUTO_DEMO:
            if time.ticks_diff(time.ticks_ms(), last_tick) >= 1000:
                last_tick = time.ticks_ms()
                len_stop = (len_stop + 1) % (MAX_LEN + 1)
                len_start = (len_start + 1) % (MAX_LEN + 1)
                _send_stop()
                _send_start()
            time.sleep(0.01)
        else:
            cmd = input().strip().lower()
            if cmd == 'w' and len_stop < MAX_LEN:
                len_stop += 1
                _send_stop()
            elif cmd == 's' and len_stop > 0:
                len_stop -= 1
                _send_stop()
            elif cmd == 'i' and len_start < MAX_LEN:
                len_start += 1
                _send_start()
            elif cmd == 'k' and len_start > 0:
                len_start -= 1
                _send_start()
            elif cmd == 'a':
                AUTO_DEMO = True
                print("AUTO_DEMO: ON (oba kanaly)")
            else:
                print("⛔ Uzyj: STOP 'w/s' (LOW prefix), START 'i/k' (HIGH), auto 'a'.")
except KeyboardInterrupt:
    sm_stop.active(0)
    sm_start.active(0)
    print("\nZatrzymano.")
