# pico_sender_gui.py — GUI do sterowania programem na Pico (SET/STOP)
# START (GPIO10): HIGH okno — i (HIGH +), k (HIGH -)
# STOP  (GPIO20): LOW prefix → HIGH — w (LOW +), s (LOW -)
# Dodatkowo: a (AUTO), ^C (przerwij), Ctrl+D (restart), opcjonalne wgrywanie przez mpremote

import sys
import time
import threading
import queue
import subprocess
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports

BAUD = 115200

# Domyślne ściezki/port
DEFAULT_PORT = "COM3"
# plik do wgrania jako :main.py
DEFAULT_FILE = r"C:/Users/Student/Desktop/Inzynierka_JP/Skrypty/main_TDC.py"


def run_mpremote_copy(port: str, src_file: str):
    """Wgraj src_file na Pico jako :main.py przy uzyciu mpremote."""
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
            return False, f"⚠️ Blad wgrywania na {port}\n{out}"
    except FileNotFoundError:
        return False, "❌ Nie znaleziono 'mpremote'. Zainstaluj: pip install mpremote"
    except Exception as e:
        return False, f"⚠️ Wyjatek podczas wgrywania: {e}"


class SenderGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(
            "Pico START/STOP — i/k (START HIGH), w/s (STOP LOW prefix), a, ^C, Ctrl+D")
        self.geometry("900x560")

        self.ser: serial.Serial | None = None
        self.rx_q: queue.Queue[bytes] = queue.Queue()
        self.reader_thr: threading.Thread | None = None

        # ===== GoRA: Port + polaczenie =====
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Port:").pack(side="left")
        self.port_cb = ttk.Combobox(
            top, width=20, state="readonly", values=self.list_ports())
        self.port_cb.pack(side="left", padx=6)
        ttk.Button(top, text="Odśwież", command=self.refresh_ports).pack(
            side="left", padx=6)

        self.auto_flash_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto-wgraj przy Połacz",
                        variable=self.auto_flash_var).pack(side="left", padx=10)

        self.btn_connect = ttk.Button(top, text="Połacz", command=self.connect)
        self.btn_connect.pack(side="left", padx=6)
        self.btn_disconnect = ttk.Button(
            top, text="Rozłacz", command=self.disconnect, state="disabled")
        self.btn_disconnect.pack(side="left", padx=6)

        # ===== Wgrywanie pliku =====
        flash = ttk.Frame(self)
        flash.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(flash, text="Plik do wgrania jako :main.py:").pack(
            side="left")
        self.file_entry = ttk.Entry(flash, width=70)
        self.file_entry.insert(0, DEFAULT_FILE)
        self.file_entry.pack(side="left", padx=6)
        ttk.Button(flash, text="Przegladąj…",
                   command=self.browse_file).pack(side="left", padx=6)
        self.btn_flash = ttk.Button(
            flash, text="Wgraj na Pico", command=self.flash_now)
        self.btn_flash.pack(side="left", padx=6)

        # ===== Log =====
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt = tk.Text(mid, height=18, wrap="word")
        self.txt.pack(fill="both", expand=True)
        self.log(
            "Sterowanie:\n"
            "- START (GPIO10): i = HIGH + (dłuższe HIGH), k = HIGH - (krótsze HIGH)\n"
            "- STOP  (GPIO20): w = LOW + (dłuższy początkowy LOW), s = LOW - (krótszy LOW)\n"
            "- a = AUTO, ^C = przerwij, Ctrl+D = restart\n\n"

        )

        # ===== Sterowanie =====
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        # STOP (LOW prefix)
        stop_frame = ttk.LabelFrame(
            bottom, text="Sygnał STOP (GPIO20)")
        stop_frame.pack(side="left", padx=8, pady=4)
        self.btn_w = ttk.Button(stop_frame, text="Krok do przodu (w)", width=18,
                                command=lambda: self.send_line("w"), state="disabled")
        self.btn_s = ttk.Button(stop_frame, text="krok w tył  (s)", width=16,
                                command=lambda: self.send_line("s"), state="disabled")
        self.btn_w.grid(row=0, column=0, padx=6, pady=8)
        self.btn_s.grid(row=0, column=1, padx=6, pady=8)

        # START (HIGH okno)
        start_frame = ttk.LabelFrame(bottom, text="Sygnał START (GPIO10)")
        start_frame.pack(side="left", padx=8, pady=4)
        self.btn_i = ttk.Button(start_frame, text="Krok do przodu  (i)", width=18,
                                command=lambda: self.send_line("i"), state="disabled")
        self.btn_k = ttk.Button(start_frame, text="Krok w tył  (k)", width=16,
                                command=lambda: self.send_line("k"), state="disabled")
        self.btn_i.grid(row=0, column=0, padx=6, pady=8)
        self.btn_k.grid(row=0, column=1, padx=6, pady=8)

        # AUTO / System
        sys_frame = ttk.LabelFrame(bottom, text="AUTO / System")
        sys_frame.pack(side="left", padx=8, pady=4)
        self.btn_a = ttk.Button(sys_frame, text="a  (AUTO ON)", width=14,
                                command=lambda: self.send_line("a"), state="disabled")
        self.btn_brk = ttk.Button(sys_frame, text="^C  (przerwij)", width=14,
                                  command=self.send_break, state="disabled")
        self.btn_rst = ttk.Button(sys_frame, text="Restart (Ctrl+D)", width=14,
                                  command=self.send_restart, state="disabled")
        self.btn_a.grid(row=0, column=0, padx=6, pady=6)
        self.btn_brk.grid(row=1, column=0, padx=6, pady=6)
        self.btn_rst.grid(row=2, column=0, padx=6, pady=6)

        # Skroty klawiszowe
        self.bind_all("<Key-i>", lambda e: self.send_line("i"))
        self.bind_all("<Key-k>", lambda e: self.send_line("k"))
        self.bind_all("<Key-w>", lambda e: self.send_line("w"))
        self.bind_all("<Key-s>", lambda e: self.send_line("s"))
        self.bind_all("<Key-a>", lambda e: self.send_line("a"))

        # Asynchroniczny odbior
        self.after(50, self.drain_rx)

        # Domyślny wybor portu
        vals = self.port_cb["values"]
        if vals:
            try:
                self.port_cb.current(vals.index(DEFAULT_PORT))
            except ValueError:
                self.port_cb.current(0)

        # Zbior przyciskow do masowego enable/disable
        self._to_enable = [
            self.btn_i, self.btn_k,
            self.btn_w, self.btn_s,
            self.btn_a, self.btn_brk, self.btn_rst
        ]

    # ===== Utils =====
    def list_ports(self):
        nice, rest = [], []
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            if ("pico" in desc) or ("micropython" in desc) or ("usb serial" in desc):
                nice.append(p.device)
            else:
                rest.append(p.device)
        return nice or rest

    def refresh_ports(self):
        vals = self.list_ports()
        self.port_cb["values"] = vals
        if vals:
            if DEFAULT_PORT in vals:
                self.port_cb.current(vals.index(DEFAULT_PORT))
            else:
                self.port_cb.current(0)
        self.log("🔄 Odświeżono liste portow.\n")

    def log(self, s: str):
        self.txt.insert("end", s)
        self.txt.see("end")

    # ===== Wgrywanie =====
    def browse_file(self):
        path = filedialog.Open(
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]).show()
        if path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, path)

    def flash_now(self):
        port = self.port_cb.get() or DEFAULT_PORT
        src = self.file_entry.get().strip()
        ok, out = run_mpremote_copy(port, src)
        self.log(out + ("\n" if not out.endswith("\n") else ""))
        if ok:
            self.log(
                "ℹ️ Po wgraniu kliknij „Restart (Ctrl+D)”, aby uruchomić :main.py.\n")

    # ===== Polaczenie =====
    def connect(self):
        port = self.port_cb.get()
        if not port:
            messagebox.showerror("Bład", "Wybierz port COM.")
            return

        # (opcjonalnie) auto-wgraj
        if self.auto_flash_var.get():
            src = self.file_entry.get().strip()
            ok, out = run_mpremote_copy(port, src)
            self.log(out + ("\n" if not out.endswith("\n") else ""))
            if not ok:
                self.log(
                    "⚠️ Auto-wgranie nie powiodło się. Możesz użyć „Wgraj na Pico”.\n")

        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.05, write_timeout=1)
            self.ser.setDTR(True)
            self.ser.setRTS(False)
            time.sleep(0.2)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.log(f"🔌 Połaczono z {port} @ {BAUD}\n")
        except serial.SerialException as e:
            self.ser = None
            messagebox.showerror("Port zajety / brak dostepu", str(e))
            return

        self.reader_thr = threading.Thread(
            target=self.reader_loop, daemon=True)
        self.reader_thr.start()
        self.btn_connect.config(state="disabled")
        self.btn_disconnect.config(state="normal")
        for b in self._to_enable:
            b.config(state="normal")

    def disconnect(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.ser = None
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        for b in self._to_enable:
            b.config(state="disabled")
        self.log("[rozlaczono]\n")

    # ===== I/O =====
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
                try:
                    self.log(data.decode("utf-8", errors="ignore"))
                except Exception:
                    self.log(str(data))
        except queue.Empty:
            pass
        self.after(60, self.drain_rx)

    # ===== Komendy =====
    def send_line(self, ch: str):
        if not (self.ser and self.ser.is_open):
            return
        if ch not in ("i", "k", "w", "s", "a"):
            return
        try:
            self.ser.write(ch.encode("utf-8") + b"\r\n")
            self.ser.flush()
            # lokalny echo:
            self.log(f"> {ch}\n")
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")

    def send_break(self):
        if not (self.ser and self.ser.is_open):
            return
        try:
            self.ser.write(b"\x03")  # Ctrl+C
            self.ser.flush()
            self.log("\n[wyslano ^C]\n")
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")

    def send_restart(self):
        if not (self.ser and self.ser.is_open):
            return
        try:
            self.ser.write(b"\x04")  # Ctrl+D
            self.ser.flush()
            self.log("\n[wyslano Ctrl+D – soft reboot]\n")
        except Exception as e:
            self.log(f"\n[write error: {e}]\n")


if __name__ == "__main__":
    try:
        app = SenderGUI()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
