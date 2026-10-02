# -*- coding: utf-8 -*-
"""
transcriptor_gui.py
Interfaz grafica para transcribir grabaciones de pantalla con Whisper local
(faster-whisper). Genera .txt y .srt junto a cada video. Nada sale de tu equipo.

Requisito (una vez):  pip install faster-whisper
Ejecutar:             python transcriptor_gui.py
  (En Spyder: Run > Configuration per file > "Execute in an external system terminal",
   o simplemente correrlo desde Anaconda Prompt.)
"""

import os
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # evita bloqueo de red corporativa

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

EXTENSIONES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg"}
MODELOS = ["tiny", "base", "small", "medium", "large-v3"]
IDIOMAS = {"Autodetectar": None, "Inglés": "en", "Español": "es"}


def formato_srt(seg: float) -> str:
    ms = int(round(seg * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


class TranscriptorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Transcriptor de grabaciones · Whisper local")
        root.geometry("820x600")
        root.minsize(680, 480)

        self.cola = queue.Queue()
        self.archivos: list[Path] = []
        self.trabajando = False
        self.cancelar = threading.Event()
        self.modelo_cache = {}  # reutiliza el modelo entre corridas

        self._construir_ui()
        self.root.after(100, self._procesar_cola)

    # ---------------------------------------------------------------- UI
    def _construir_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- Archivos
        marco_arch = ttk.LabelFrame(self.root, text="1. Grabaciones")
        marco_arch.pack(fill="x", **pad)
        ttk.Button(marco_arch, text="Elegir carpeta...", command=self.elegir_carpeta).pack(side="left", **pad)
        ttk.Button(marco_arch, text="Elegir archivos...", command=self.elegir_archivos).pack(side="left", **pad)
        self.lbl_archivos = ttk.Label(marco_arch, text="Ningún archivo seleccionado")
        self.lbl_archivos.pack(side="left", **pad)

        # --- Opciones
        marco_op = ttk.LabelFrame(self.root, text="2. Opciones")
        marco_op.pack(fill="x", **pad)

        ttk.Label(marco_op, text="Modelo:").grid(row=0, column=0, sticky="w", **pad)
        self.var_modelo = tk.StringVar(value="small")
        self.cmb_modelo = ttk.Combobox(marco_op, textvariable=self.var_modelo, values=MODELOS, width=22)
        self.cmb_modelo.grid(row=0, column=1, sticky="w", **pad)
        ttk.Button(marco_op, text="Modelo local...", command=self.elegir_modelo_local).grid(row=0, column=2, **pad)

        ttk.Label(marco_op, text="Idioma:").grid(row=1, column=0, sticky="w", **pad)
        self.var_idioma = tk.StringVar(value="Inglés")
        ttk.Combobox(marco_op, textvariable=self.var_idioma, values=list(IDIOMAS),
                     state="readonly", width=22).grid(row=1, column=1, sticky="w", **pad)

        self.var_traducir = tk.BooleanVar(value=False)
        ttk.Checkbutton(marco_op, text="Traducir al inglés", variable=self.var_traducir).grid(
            row=0, column=3, sticky="w", **pad)
        self.var_sobrescribir = tk.BooleanVar(value=False)
        ttk.Checkbutton(marco_op, text="Volver a transcribir los que ya tienen .txt",
                        variable=self.var_sobrescribir).grid(row=1, column=3, sticky="w", **pad)

        # --- Acciones
        marco_acc = ttk.Frame(self.root)
        marco_acc.pack(fill="x", **pad)
        self.btn_iniciar = ttk.Button(marco_acc, text="▶  Transcribir", command=self.iniciar)
        self.btn_iniciar.pack(side="left", **pad)
        self.btn_cancelar = ttk.Button(marco_acc, text="■  Cancelar", command=self.cancelar_trabajo, state="disabled")
        self.btn_cancelar.pack(side="left", **pad)
        ttk.Button(marco_acc, text="Abrir carpeta de resultados", command=self.abrir_carpeta).pack(side="right", **pad)

        # --- Progreso
        marco_prog = ttk.Frame(self.root)
        marco_prog.pack(fill="x", **pad)
        self.lbl_estado = ttk.Label(marco_prog, text="Listo.")
        self.lbl_estado.pack(anchor="w")
        self.barra_archivo = ttk.Progressbar(marco_prog, maximum=100)
        self.barra_archivo.pack(fill="x", pady=2)
        self.barra_total = ttk.Progressbar(marco_prog, maximum=100)
        self.barra_total.pack(fill="x", pady=2)

        # --- Texto en vivo
        marco_log = ttk.LabelFrame(self.root, text="Transcripción en vivo")
        marco_log.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(marco_log, wrap="word", font=("Consolas", 10), state="disabled")
        scroll = ttk.Scrollbar(marco_log, command=self.txt.yview)
        self.txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

    # ---------------------------------------------------------- Selección
    def elegir_carpeta(self):
        carpeta = filedialog.askdirectory(title="Carpeta con grabaciones")
        if carpeta:
            self._set_archivos(sorted(p for p in Path(carpeta).iterdir() if p.suffix.lower() in EXTENSIONES))

    def elegir_archivos(self):
        rutas = filedialog.askopenfilenames(
            title="Grabaciones",
            filetypes=[("Audio/Video", " ".join(f"*{e}" for e in sorted(EXTENSIONES))), ("Todos", "*.*")])
        if rutas:
            self._set_archivos([Path(r) for r in rutas])

    def elegir_modelo_local(self):
        carpeta = filedialog.askdirectory(title="Carpeta del modelo (con model.bin)")
        if carpeta:
            if not (Path(carpeta) / "model.bin").exists():
                messagebox.showwarning("Modelo", "Esa carpeta no tiene model.bin")
                return
            self.var_modelo.set(carpeta)

    def _set_archivos(self, archivos):
        self.archivos = archivos
        if not archivos:
            self.lbl_archivos.config(text="No se encontraron audios/videos")
        elif len(archivos) == 1:
            self.lbl_archivos.config(text=archivos[0].name)
        else:
            self.lbl_archivos.config(text=f"{len(archivos)} archivos en {archivos[0].parent.name}")

    def abrir_carpeta(self):
        if not self.archivos:
            return
        carpeta = str(self.archivos[0].parent)
        if sys.platform.startswith("win"):
            os.startfile(carpeta)
        else:
            subprocess.Popen(["xdg-open", carpeta])

    # ------------------------------------------------------------ Trabajo
    def iniciar(self):
        if not self.archivos:
            messagebox.showinfo("Transcriptor", "Primero elige una carpeta o archivos.")
            return
        pendientes = self.archivos if self.var_sobrescribir.get() else \
            [a for a in self.archivos if not a.with_suffix(".txt").exists()]
        if not pendientes:
            messagebox.showinfo("Transcriptor", "Todos ya tienen su .txt.\nMarca 'Volver a transcribir' si quieres repetirlos.")
            return

        self.trabajando = True
        self.cancelar.clear()
        self.btn_iniciar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self._limpiar_log()
        opciones = {
            "modelo": self.var_modelo.get().strip(),
            "idioma": IDIOMAS[self.var_idioma.get()],
            "traducir": self.var_traducir.get(),
        }
        threading.Thread(target=self._trabajo, args=(pendientes, opciones), daemon=True).start()

    def cancelar_trabajo(self):
        self.cancelar.set()
        self.cola.put(("estado", "Cancelando al terminar el segmento actual..."))

    def _cargar_modelo(self, nombre):
        if nombre in self.modelo_cache:
            return self.modelo_cache[nombre]
        from faster_whisper import WhisperModel
        dispositivo, tipo = "cpu", "int8"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                dispositivo, tipo = "cuda", "float16"
        except Exception:
            pass
        self.cola.put(("estado", f"Cargando modelo '{Path(nombre).name}' en {dispositivo.upper()} "
                                 "(la primera vez se descarga, puede tardar)..."))
        modelo = WhisperModel(nombre, device=dispositivo, compute_type=tipo)
        self.modelo_cache[nombre] = modelo
        return modelo

    def _trabajo(self, archivos, op):
        try:
            modelo = self._cargar_modelo(op["modelo"])
        except Exception as e:
            self.cola.put(("error", f"No se pudo cargar el modelo:\n{e}"))
            self.cola.put(("fin", None))
            return

        total = len(archivos)
        for n, archivo in enumerate(archivos, start=1):
            if self.cancelar.is_set():
                break
            self.cola.put(("total", (n - 1) / total * 100))
            self.cola.put(("archivo", 0))
            self.cola.put(("log", f"\n===== ({n}/{total}) {archivo.name} =====\n"))
            t0 = time.time()
            try:
                segmentos, info = modelo.transcribe(
                    str(archivo), language=op["idioma"],
                    task="translate" if op["traducir"] else "transcribe",
                    vad_filter=True, beam_size=5)
                self.cola.put(("estado", f"({n}/{total}) {archivo.name} · idioma {info.language} · "
                                         f"{info.duration / 60:.1f} min"))
                lineas, srt = [], []
                for i, seg in enumerate(segmentos, start=1):
                    if self.cancelar.is_set():
                        break
                    texto = seg.text.strip()
                    if not texto:
                        continue
                    marca = formato_srt(seg.start)[:8]
                    lineas.append(f"[{marca}] {texto}")
                    srt.append(f"{i}\n{formato_srt(seg.start)} --> {formato_srt(seg.end)}\n{texto}\n")
                    self.cola.put(("log", f"[{marca}] {texto}\n"))
                    if info.duration:
                        self.cola.put(("archivo", min(seg.end / info.duration, 1) * 100))

                if self.cancelar.is_set():
                    self.cola.put(("log", "-- cancelado, no se guardó este archivo --\n"))
                    break
                archivo.with_suffix(".txt").write_text("\n".join(lineas), encoding="utf-8")
                archivo.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
                self.cola.put(("archivo", 100))
                self.cola.put(("log", f"✔ Guardado {archivo.stem}.txt / .srt ({time.time() - t0:.0f} s)\n"))
            except Exception as e:
                self.cola.put(("log", f"✖ ERROR con {archivo.name}: {e}\n"))

        self.cola.put(("total", 100 if not self.cancelar.is_set() else self.barra_total["value"]))
        self.cola.put(("estado", "Cancelado." if self.cancelar.is_set() else "¡Terminado!"))
        self.cola.put(("fin", None))

    # ---------------------------------------------- Comunicación con la UI
    def _procesar_cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "log":
                    self.txt.config(state="normal")
                    self.txt.insert("end", dato)
                    self.txt.see("end")
                    self.txt.config(state="disabled")
                elif tipo == "estado":
                    self.lbl_estado.config(text=dato)
                elif tipo == "archivo":
                    self.barra_archivo["value"] = dato
                elif tipo == "total":
                    self.barra_total["value"] = dato
                elif tipo == "error":
                    messagebox.showerror("Error", dato)
                    self.lbl_estado.config(text="Error al cargar el modelo.")
                elif tipo == "fin":
                    self.trabajando = False
                    self.btn_iniciar.config(state="normal")
                    self.btn_cancelar.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._procesar_cola)

    def _limpiar_log(self):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")
        self.barra_archivo["value"] = 0
        self.barra_total["value"] = 0


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError:
        pass
    TranscriptorApp(root)
    root.mainloop()
