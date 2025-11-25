from machine import Pin
from rp2 import PIO, StateMachine, asm_pio
import time

# --- parametry ---
MAX_LEN = 50                 # liczba "slotow" w ramce
FREQ_HZ = 100_000_000        # zegar PIO (slot = 1/FREQ_HZ)
PIN_START = 10               # START = okno HIGH N/MAX_LEN (PIO) — HIGH -> LOW
PIN_STOP = 20                # STOP  = LOW prefix -> HIGH reszta
AUTO_DEMO = False            # auto: krok co 1 s na obu kanalach

# --- PIO: START — HIGH przez Y, potem LOW przez X ---


@asm_pio(
    set_init=PIO.OUT_LOW,
    out_shiftdir=PIO.SHIFT_RIGHT
)
def win_pwm_packed_set():
    pull()                 # pierwsze slowo
    mov(x, osr)            # X = packed

    wrap_target()
    # pobierz nowe slowo, jeśli jest
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

    # HIGH przez Y slotow (zero-safe)
    jmp(not_y, "after_hi")
    set(pins, 1)
    label("hi")
    jmp(y_dec, "hi")
    label("after_hi")

    # LOW przez X slotow (zero-safe)
    jmp(not_x, "after_lo")
    set(pins, 0)
    label("lo")
    jmp(x_dec, "lo")
    label("after_lo")

    mov(x, isr)
    wrap()

# --- PIO: STOP — LOW przez Y, potem HIGH przez X ---


@asm_pio(
    set_init=PIO.OUT_LOW,
    out_shiftdir=PIO.SHIFT_RIGHT
)
def win_pwm_packed_low_high():
    pull()                 # pierwsze slowo
    mov(x, osr)            # X = packed

    wrap_target()
    # pobierz nowe slowo, jeśli jest
    mov(osr, x)
    pull(noblock)
    mov(x, osr)

    # backup
    mov(isr, x)

    # Y = low_len (high16)
    mov(osr, x)
    out(null, 16)          # >>16
    mov(y, osr)            # Y = high16(packed) = dlugość LOW prefix

    # X = high_len (low16)
    mov(osr, isr)
    out(x, 16)             # X = low16(packed) = dlugość HIGH reszta

    # LOW przez Y slotow (zero-safe)
    jmp(not_y, "after_low")
    set(pins, 0)
    label("low")
    jmp(y_dec, "low")
    label("after_low")

    # HIGH przez X slotow (zero-safe)
    jmp(not_x, "after_high")
    set(pins, 1)
    label("high")
    jmp(x_dec, "high")
    label("after_high")

    mov(x, isr)
    wrap()


# --- dwie SM: START (HIGH->LOW) i STOP (LOW->HIGH) ---
sm_start = StateMachine(0, win_pwm_packed_set,
                        freq=FREQ_HZ, set_base=Pin(PIN_START))
sm_stop = StateMachine(4, win_pwm_packed_low_high,
                       freq=FREQ_HZ, set_base=Pin(PIN_STOP))

# --- dlugości w slotach ---
len_start = 0   # START: ile slotow HIGH (0..MAX_LEN)
len_stop = 0   # STOP : ile slotow LOW na poczatku (0..MAX_LEN)


def _send_start():
    """START: (low_len<<16) | high_len  [generuje HIGH->LOW]"""
    h = max(0, min(MAX_LEN, len_start))
    l = MAX_LEN - h
    packed = ((l & 0xFFFF) << 16) | (h & 0xFFFF)
    sm_start.put(packed)
    bar = "■"*h + "□"*l
    print(f"START: [{bar}]  HIGH={h}/{MAX_LEN}")


def _send_stop():
    """STOP: (low_prefix<<16) | high_rest  [generuje LOW->HIGH]"""
    low_prefix = max(0, min(MAX_LEN, len_stop))       # ile LOW od poczatku
    high_rest = MAX_LEN - low_prefix                  # reszta HIGH
    packed = ((low_prefix & 0xFFFF) << 16) | (high_rest & 0xFFFF)
    sm_stop.put(packed)
    bar = "□"*low_prefix + "■"*high_rest
    print(f"STOP : [{bar}]  LOWprefix={low_prefix}/{MAX_LEN}")


# --- start ---
_send_stop()
_send_start()
sm_stop.active(1)
sm_start.active(1)

frame_hz = FREQ_HZ // MAX_LEN
slot_ns = int(1_000_000_000 // FREQ_HZ)
print(
    f"START (GPIO{PIN_START}) = HIGH okno, STOP (GPIO{PIN_STOP}) = LOW prefix → HIGH reszta.")
print(f"Ramka ≈ {frame_hz} Hz, slot ≈ {slot_ns} ns.")
print("Sterowanie: STOP 'w'/'s' (LOW prefix +/-) | START 'i'/'k' (HIGH +/-) | 'a' auto | Ctrl+C")

last_tick = time.ticks_ms()

try:
    while True:
        if AUTO_DEMO:
            if time.ticks_diff(time.ticks_ms(), last_tick) >= 1000:
                last_tick = time.ticks_ms()
                # krok na obu kanalach
                # rośnie LOW-prefix STOP
                len_stop = (len_stop + 1) % (MAX_LEN + 1)
                # rośnie HIGH START
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
