# pico_sender_gui.py — pilot do sterowania działającym main.py na Pico
# Wymagane: 'mpremote' w PATH (pip install mpremote), pyserial (pip install pyserial)

import sys, time, threading, queue, subprocess, os, tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial, serial.tools.list_ports

BAUD = 115200

# Domyślne ustawienia do auto-wgrania na starcie (możesz zmienić):
DEFAULT_PORT = "COM3"
DEFAULT_FILE = r"C:\Users\Jon\Desktop\inzynierka\mainz.py"

def run_mpremote_copy(port: str, src_file: str) -> tuple[bool, str]:
    """Wgrywa src_file na Pico jako :main.py przez mpremote. Zwraca (ok, log)."""
    if not os.path.isfile(src_file):
        return False, f"❌ Plik nie istnieje: {src_file}"
    cmd = ["mpremote", "connect", port, "fs", "cp", src_file, ":main.py"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        ok = (res.returncode == 0)
        out = (res.stdout or "") + (res.stderr or "")
        if ok:
            return True, f"✅ Wgrano {src_file} → :main.py na {port}\n{out}"
        else:
            return False, f"⚠️ Błąd wgrywania na {port}\n{out}"
    except FileNotFoundError:
        return False, "❌ Nie znaleziono 'mpremote'. Zainstaluj: pip install mpremote (i uruchom ponownie)."
    except Exception as e:
        return False, f"⚠️ Wyjątek podczas wgrywania: {e}"

class SenderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pico pilot (w/s/a) — z Restart i wgrywaniem")
        self.geometry("900x560")

        self.ser: serial.Serial | None = None
        self.rx_q: queue.Queue[bytes] = queue.Queue()
        self.reader_thr: threading.Thread | None = None

        # ===== GÓRA: wybór portu + połączenie =====
        top = ttk.Frame(self); top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_cb = ttk.Combobox(top, width=18, state="readonly", values=self.list_ports())
        self.port_cb.pack(side="left", padx=6)
        ttk.Button(top, text="Odśwież", command=self.refresh_ports).pack(side="left", padx=6)
        self.auto_flash_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Auto-wgraj przy Połącz", variable=self.auto_flash_var).pack(side="left", padx=10)
        self.btn_connect = ttk.Button(top, text="Połącz", command=self.connect); self.btn_connect.pack(side="left", padx=6)
        self.btn_disconnect = ttk.Button(top, text="Rozłącz", command=self.disconnect, state="disabled"); self.btn_disconnect.pack(side="left", padx=6)

        # ===== LINIA: wybór pliku do wgrania =====
        flash = ttk.Frame(self); flash.pack(fill="x", padx=10, pady=(0,10))
        ttk.Label(flash, text="Plik do wgrania jako :main.py:").pack(side="left")
        self.file_entry = ttk.Entry(flash, width=60)
        self.file_entry.insert(0, DEFAULT_FILE)
        self.file_entry.pack(side="left", padx=6)
        ttk.Button(flash, text="Przeglądaj…", command=self.browse_file).pack(side="left", padx=6)
        self.btn_flash = ttk.Button(flash, text="Wgraj na Pico", command=self.flash_now)
        self.btn_flash.pack(side="left", padx=6)

        # ===== ŚRODEK: log =====
        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.txt = tk.Text(mid, height=20, wrap="word"); self.txt.pack(fill="both", expand=True)
        self.log("1) (Opcjonalnie) Wgraj plik jako :main.py\n"
                 "2) Połącz, a następnie używaj w/s/a. Restart (Ctrl+D) uruchomi :main.py od nowa.\n\n")

        # ===== DÓŁ: sterowanie =====
        bottom = ttk.Frame(self); bottom.pack(fill="x", padx=10, pady=(0,10))
        self.btn_w   = ttk.Button(bottom, text="w (++)",            command=lambda: self.send_line("w"), state="disabled")
        self.btn_s   = ttk.Button(bottom, text="s (--)",            command=lambda: self.send_line("s"), state="disabled")
        self.btn_a   = ttk.Button(bottom, text="a (AUTO)",          command=lambda: self.send_line("a"), state="disabled")
        self.btn_brk = ttk.Button(bottom, text="^C (przerwij)",     command=self.send_break,            state="disabled")
        self.btn_rst = ttk.Button(bottom, text="Restart (Ctrl+D)",  command=self.send_restart,          state="disabled")
        for b in (self.btn_w, self.btn_s, self.btn_a, self.btn_brk, self.btn_rst): b.pack(side="left", padx=6)

        # skróty klawiszowe
        self.bind_all("<Key-w>", lambda e: self.send_line("w"))
        self.bind_all("<Key-s>", lambda e: self.send_line("s"))
        self.bind_all("<Key-a>", lambda e: self.send_line("a"))

        # pętla zbierająca log
        self.after(50, self.drain_rx)

        if self.port_cb["values"]:
            # ustaw domyślnie COM3, jeśli jest na liście
            try:
                idx = self.port_cb["values"].index(DEFAULT_PORT)
                self.port_cb.current(idx)
            except ValueError:
                self.port_cb.current(0)

    # ---------- utils ----------
    def list_ports(self):
        nice, rest = [], []
        for p in serial.tools.list_ports.comports():
            if ("Pico" in p.description) or ("MicroPython" in p.description) or ("USB Serial" in p.description):
                nice.append(p.device)
            else:
                rest.append(p.device)
        return nice or rest

    def refresh_ports(self):
        vals = self.list_ports()
        self.port_cb["values"] = vals
        if vals:
            # spróbuj znów wybrać DEFAULT_PORT
            if DEFAULT_PORT in vals:
                self.port_cb.current(vals.index(DEFAULT_PORT))
            else:
                self.port_cb.current(0)

    def log(self, s: str):
        self.txt.insert("end", s)
        self.txt.see("end")

    # ---------- wgrywanie ----------
    def browse_file(self):
        path = filedialog.Open(filetypes=[("Python files","*.py"),("All files","*.*")]).show()
        if path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, path)

    def flash_now(self):
        port = self.port_cb.get() or DEFAULT_PORT
        src  = self.file_entry.get().strip()
        ok, out = run_mpremote_copy(port, src)
        self.log(out + ("\n" if not out.endswith("\n") else ""))
        if ok:
            self.log("ℹ️ Po wgraniu możesz kliknąć „Restart (Ctrl+D)”, aby uruchomić :main.py.\n")

    # ---------- połączenie ----------
    def connect(self):
        port = self.port_cb.get()
        if not port:
            messagebox.showerror("Błąd", "Wybierz port COM.")
            return

        # (opcjonalnie) Auto-wgraj przy Połącz
        if self.auto_flash_var.get():
            src = self.file_entry.get().strip()
            ok, out = run_mpremote_copy(port, src)
            self.log(out + ("\n" if not out.endswith("\n") else ""))
            if not ok:
                # nie przerywamy — może chcesz się tylko połączyć i zobaczyć log
                self.log("⚠️ Auto-wgranie nie powiodło się. Możesz spróbować ponownie przyciskiem „Wgraj na Pico”.\n")

        # teraz samo połączenie (bez resetów/ importów — to pilot)
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.05, write_timeout=1)
            self.ser.setDTR(True); self.ser.setRTS(False)
            time.sleep(0.2)
            self.ser.reset_input_buffer(); self.ser.reset_output_buffer()
            self.log(f"🔌 Połączono z {port} @ {BAUD}\n")
        except serial.SerialException as e:
            self.ser = None
            messagebox.showerror("Port zajęty / brak dostępu", str(e))
            return

        self.reader_thr = threading.Thread(target=self.reader_loop, daemon=True)
        self.reader_thr.start()

        self.btn_connect.config(state="disabled")
        self.btn_disconnect.config(state="normal")
        for b in (self.btn_w, self.btn_s, self.btn_a, self.btn_brk, self.btn_rst):
            b.config(state="normal")

    def disconnect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.ser = None
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        for b in (self.btn_w, self.btn_s, self.btn_a, self.btn_brk, self.btn_rst):
            b.config(state="disabled")
        self.log("[rozłączono]\n")

    # ---------- I/O ----------
    def reader_loop(self):
        while self.ser and self.ser.is_open:
            try:
                data = self.ser.read(1024)
            except Exception:
                break
            if data:
                self.rx_q.put(data)
            else:
                time.sleep(0.01)

    def drain_rx(self):
        try:
            while True:
                data = self.rx_q.get_nowait()
                try: self.log(data.decode("utf-8", errors="ignore"))
                except Exception: self.log(str(data))
        except queue.Empty:
            pass
        self.after(50, self.drain_rx)

    # ---------- komendy ----------
    def send_line(self, ch: str):
        """Wyślij pełną linię (CRLF), bo Twój main.py używa input()."""
        if not (self.ser and self.ser.is_open): return
        if ch not in ("w", "s", "a"): return
        try:
            self.ser.write(ch.encode("utf-8") + b"\r\n")
            self.ser.flush()
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")

    def send_break(self):
        """Wyślij Ctrl+C → KeyboardInterrupt (Twój main.py to łapie i kończy)."""
        if not (self.ser and self.ser.is_open): return
        try:
            self.ser.write(b"\x03")
            self.ser.flush()
            self.log("\n[wysłano ^C]\n")
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")

    def send_restart(self):
        """Wyślij Ctrl+D → soft reboot. Jeśli na urządzeniu jest :main.py, wystartuje od nowa."""
        if not (self.ser and self.ser.is_open): return
        try:
            self.ser.write(b"\x04")
            self.ser.flush()
            self.log("\n[wysłano Ctrl+D – soft reboot]\n")
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")

# ===== autowgrywanie PRZED startem GUI (jednorazowe) =====
def auto_flash_before_gui():
    # jeśli chcesz to pominąć, ustaw AUTO=False
    AUTO = True
    if not AUTO:
        return
    ok, out = run_mpremote_copy(DEFAULT_PORT, DEFAULT_FILE)
    print(out)
    if ok:
        print("ℹ️ Gotowe. Uruchamiam GUI…\n")
    else:
        print("ℹ️ Nie udało się auto-wgranie przed GUI. Spróbuj z przycisku w oknie.\n")

# ===== start =====
if __name__ == "__main__":
    # jednorazowa próba wgrania zanim pokaże się okno:
    auto_flash_before_gui()

    try:
        app = SenderGUI()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
