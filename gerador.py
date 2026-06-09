"""
gerador.py — Gerador de Batch para Importacao IFC  (v2)
Interface em abas — sem scroll, mais compacta e clara.

Melhorias v2:
  - Layout em abas (Projeto / Pastas / Filtros / Agendamento)
  - Preview de arquivos .ifc ao selecionar pasta
  - Botao para abrir pasta no Explorer
  - Filtros dinamicos (igual pastas: add/remove)
  - Carregar .bat existente para edicao
"""

import os
import json
import subprocess
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

SCRIPTS_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJETOS_DIR = os.path.join(SCRIPTS_DIR, "projetos")
os.makedirs(PROJETOS_DIR, exist_ok=True)

UNREAL_DEFAULT = r"C:\Program Files\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe"

DIAS_PT = ["Segunda-feira","Terca-feira","Quarta-feira",
           "Quinta-feira","Sexta-feira","Sabado","Domingo"]
DIAS_EN = {"Segunda-feira":"MON","Terca-feira":"TUE","Quarta-feira":"WED",
           "Quinta-feira":"THU","Sexta-feira":"FRI","Sabado":"SAT","Domingo":"SUN"}

COR_OK    = "#107C10"
COR_ERR   = "#C00000"
COR_HEAD  = "#1e1e1e"
COR_BTN   = "#0078d4"
COR_GERAR = "#107C10"
COR_GRAY  = "#d0d0d0"


def get_short_path(path):
    """Converte para caminho curto 8.3 do Windows (sem acentos) — seguro para .bat e CMD."""
    if not path:
        return path
    try:
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)):
            return buf.value
    except Exception:
        pass
    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITARIOS
# ═══════════════════════════════════════════════════════════════════════════════

def listar_levels_disco(uproject_path):
    content_dir = os.path.join(os.path.dirname(uproject_path), "Content")
    levels = []
    if not os.path.isdir(content_dir):
        return levels
    for root, dirs, files in os.walk(content_dir):
        dirs[:] = [d for d in dirs if d not in ("__ExternalActors__","__ExternalObjects__")]
        for f in files:
            if f.lower().endswith(".umap"):
                rel = os.path.relpath(os.path.join(root, f), content_dir)
                levels.append("/Game/" + rel.replace("\\","/").replace(".umap",""))
    return sorted(levels)


def listar_ifcs(pasta):
    if not pasta or not os.path.isdir(pasta):
        return []
    try:
        return sorted(f for f in os.listdir(pasta) if f.lower().endswith(".ifc"))
    except Exception:
        return []


def sanitizar(nome):
    return "".join(c for c in nome if c.isalnum() or c in "_-").strip("_-")


# ═══════════════════════════════════════════════════════════════════════════════
#  CARREGAR .BAT EXISTENTE
# ═══════════════════════════════════════════════════════════════════════════════

def parsear_bat(bat_path):
    config = {"pastas": [], "filtros": []}
    pastas_tmp = {}
    try:
        with open(bat_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line.upper().startswith("SET IFC_"):
                    continue
                kv = line[4:]
                if "=" not in kv:
                    continue
                key, val = kv.split("=", 1)
                key = key.upper()
                if   key == "IFC_NOME":         config["nome"]         = val
                elif key == "IFC_UNREAL":        config["unreal"]       = val
                elif key == "IFC_PROJETO":       config["projeto"]      = val
                elif key == "IFC_CONTENT_BASE":  config["content_base"] = val
                elif key == "IFC_LEVEL":         config["level"]        = val
                elif key == "IFC_FILTROS":
                    config["filtros"] = [f.strip() for f in val.split(",") if f.strip()]
                elif key.startswith("IFC_PASTA_") and val.strip():
                    idx = int(key.replace("IFC_PASTA_",""))
                    pastas_tmp[idx] = val.strip()
    except Exception as e:
        messagebox.showerror("Erro", f"Nao foi possivel ler o .bat:\n{e}")
        return None
    config["pastas"] = [pastas_tmp[k] for k in sorted(pastas_tmp)]
    return config


# ═══════════════════════════════════════════════════════════════════════════════
#  GERAR .BAT
# ═══════════════════════════════════════════════════════════════════════════════

def gerar_bat(config):
    nome    = config["nome"]
    pastas  = config.get("pastas", [])
    filtros = config.get("filtros", [])
    data    = datetime.now().strftime("%Y-%m-%d %H:%M")
    runner    = get_short_path(os.path.join(SCRIPTS_DIR, "runner.py"))

    # Caminhos curtos 8.3 — evitam problemas de encoding do CMD com acentos
    # NOTA: Unreal exe fica em C:\Program Files\... (sem acentos), nao usa short path
    # pois get_short_path pode retornar UNREAL~4.EXE (exe errado) se houver varios
    # executaveis UNREAL*.EXE na mesma pasta (UnrealEditor-Cmd.exe, UnrealFrontend.exe, etc.)
    unreal_s  = config["unreal"]
    projeto_s = get_short_path(config["projeto"])
    pastas_s  = [get_short_path(p) for p in pastas]

    linhas_pastas = []
    for i in range(1, max(len(pastas_s) + 1, 6)):
        val = pastas_s[i-1] if i <= len(pastas_s) else ""
        linhas_pastas.append(f"set IFC_PASTA_{i}={val}")
    linhas_pastas.append("REM  Para mais pastas: adicione set IFC_PASTA_6=...  IFC_PASTA_7=... etc.")

    bat = f"""@echo off
setlocal EnableDelayedExpansion
title Importador IFC -- {nome}
color 0A

REM ================================================================
REM  {nome}
REM  Gerado em: {data}
REM ================================================================
REM
REM  CONFIGURACAO -- edite as variaveis abaixo se necessario
REM
REM ================================================================

set IFC_NOME={nome}
set IFC_UNREAL={unreal_s}
set IFC_PROJETO={projeto_s}
set IFC_CONTENT_BASE={config['content_base']}
set IFC_LEVEL={config['level']}

REM  Pastas onde buscar arquivos .ifc (deixe em branco para ignorar)
{chr(10).join(linhas_pastas)}

REM  Filtros de exclusao -- arquivos com esses textos serao IGNORADOS
REM  Formato: texto1,texto2,texto3  (sem espacos entre as virgulas)
set IFC_FILTROS={','.join(filtros)}

REM ================================================================

echo.
echo  Batch: !IFC_NOME!
echo  Projeto: !IFC_PROJETO!
echo.

py "{runner}"

echo.
pause
"""
    bat_path = os.path.join(PROJETOS_DIR, f"{nome}.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat)
    return bat_path


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENDAMENTO
# ═══════════════════════════════════════════════════════════════════════════════

def agendar_windows(config, bat_path):
    nome     = config["nome"]
    dia_pt   = config.get("agenda_dia",  "Quinta-feira")
    hora     = config.get("agenda_hora", "01:00")
    dia_en   = DIAS_EN.get(dia_pt, "THU")
    task     = f"IFC_Import_{nome}"
    bat_s    = get_short_path(bat_path)
    proj_s   = get_short_path(PROJETOS_DIR)
    log      = os.path.join(proj_s, f"{nome}.log")
    tr       = f'cmd /c "\\"{bat_s}\\" > \\"{log}\\" 2>&1"'
    cmd      = f'schtasks /create /tn "{task}" /tr "{tr}" /sc WEEKLY /d {dia_en} /st {hora} /f /rl HIGHEST'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0, task, (result.stdout + result.stderr).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()
    root.title("Gerador de Batch — Importador IFC")
    root.resizable(True, True)
    root.minsize(720, 520)

    root.update_idletasks()
    W, H = 820, 600
    root.geometry(f"{W}x{H}+{(root.winfo_screenwidth()-W)//2}+{(root.winfo_screenheight()-H)//2}")
    # NOTA: -topmost removido — causava messagebox aparecer atrás da janela principal

    # ── estilo ttk ───────────────────────────────────────────────────────────
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TNotebook",        background="#f0f0f0", borderwidth=0)
    style.configure("TNotebook.Tab",    font=("Arial",10,"bold"), padding=[16,6],
                    background="#d0d0d0", foreground="#333333")
    style.map("TNotebook.Tab",
              background=[("selected","#ffffff")],
              foreground=[("selected","#1F4E79")])
    style.configure("TFrame",           background="#ffffff")
    style.configure("TLabel",           background="#ffffff", font=("Arial",9))
    style.configure("TCombobox",        font=("Arial",9))

    # ── header ───────────────────────────────────────────────────────────────
    header = tk.Frame(root, bg=COR_HEAD, height=48)
    header.pack(side="top", fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="  Gerador de Batch — Importador IFC",
             bg=COR_HEAD, fg="white",
             font=("Arial", 12, "bold")).pack(side="left", pady=10)

    def on_carregar_bat():
        p = filedialog.askopenfilename(
            initialdir=PROJETOS_DIR,
            title="Selecionar .bat para editar",
            filetypes=[("Batch files","*.bat"),("Todos","*.*")])
        if not p:
            return
        cfg = parsear_bat(p)
        if cfg:
            popular_formulario(cfg)
            messagebox.showinfo("Carregado", f"Configuracao carregada de:\n{p}", parent=root)

    tk.Button(header, text="Carregar .bat existente",
              command=on_carregar_bat,
              bg="#444444", fg="white", relief="flat",
              font=("Arial", 9), padx=10, pady=6).pack(side="right", padx=14, pady=8)

    # ── footer (empacotado antes das abas) ────────────────────────────────────
    footer = tk.Frame(root, bg="#e8e8e8", height=58)
    footer.pack(side="bottom", fill="x")
    footer.pack_propagate(False)

    def on_gerar():
        cfg = montar_config()
        if not cfg:
            return
        bat = gerar_bat(cfg)
        if var_agendar.get():
            ok, task, msg = agendar_windows(cfg, bat)
            if ok:
                messagebox.showinfo("Sucesso!",
                    f"Batch gerado:\n{bat}\n\n"
                    f"Tarefa agendada:\n  {task}\n"
                    f"  {cfg['agenda_dia']} as {cfg['agenda_hora']}", parent=root)
            else:
                messagebox.showwarning("Batch gerado — Agendamento falhou",
                    f"Batch: {bat}\n\nErro:\n{msg}\n\n"
                    "Execute o gerador como Administrador para agendar.", parent=root)
        else:
            messagebox.showinfo("Batch gerado!",
                f"Arquivo criado:\n{bat}", parent=root)

    tk.Button(footer, text="  Gerar .bat  ", command=on_gerar,
              bg=COR_GERAR, fg="white", relief="flat",
              font=("Arial", 11, "bold"), padx=16, pady=9).pack(side="left", padx=14, pady=10)
    tk.Button(footer, text="Abrir pasta projetos/",
              command=lambda: os.startfile(PROJETOS_DIR),
              bg="#555555", fg="white", relief="flat",
              font=("Arial", 9), padx=10, pady=9).pack(side="left", pady=10)

    # ── notebook de abas ─────────────────────────────────────────────────────
    nb = ttk.Notebook(root)
    nb.pack(side="top", fill="both", expand=True, padx=0, pady=0)

    def tab(titulo):
        frame = ttk.Frame(nb)
        nb.add(frame, text=f"  {titulo}  ")
        return frame

    # ════════════════════════════════════════════════════════════════════════
    # ABA 1 — PROJETO
    # ════════════════════════════════════════════════════════════════════════
    t1 = tab("Projeto")

    def rotulo(parent, texto, row, col=0, sticky="w", pady=4):
        tk.Label(parent, text=texto, font=("Arial",9), bg="white",
                 fg="#333333").grid(row=row, column=col, sticky=sticky,
                                    padx=(16,4), pady=pady)

    def entrada(parent, row, default="", col=1, width=52):
        var = tk.StringVar(value=default)
        tk.Entry(parent, textvariable=var, font=("Arial",9),
                 width=width, relief="solid", bd=1
                 ).grid(row=row, column=col, columnspan=2, sticky="ew",
                        padx=(0,16), pady=4)
        return var

    def botao_browse(parent, row, col, command, texto="..."):
        tk.Button(parent, text=texto, command=command, width=3,
                  relief="flat", bg=COR_GRAY, font=("Arial",9)
                  ).grid(row=row, column=col, padx=(0,4), pady=4)

    t1.columnconfigure(1, weight=1)
    t1.configure(style="TFrame")

    tk.Label(t1, text="", bg="white").grid(row=0, column=0, pady=6)  # spacer topo

    rotulo(t1, "Nome do batch:", 1)
    var_nome = tk.StringVar(value="REPAR_quinta")
    tk.Entry(t1, textvariable=var_nome, font=("Arial",9), width=40,
             relief="solid", bd=1).grid(row=1, column=1, columnspan=2,
                                         sticky="ew", padx=(0,16), pady=4)
    tk.Label(t1, text="Use: letras, numeros, _ e -    ex: REPAR_quinta",
             font=("Arial",8), fg="#888888", bg="white"
             ).grid(row=2, column=1, columnspan=2, sticky="w", padx=(0,16))

    rotulo(t1, "UnrealEditor.exe:", 3)
    var_unreal = tk.StringVar(value=UNREAL_DEFAULT)
    tk.Entry(t1, textvariable=var_unreal, font=("Arial",9),
             relief="solid", bd=1).grid(row=3, column=1, sticky="ew", padx=(0,4), pady=4)
    def browse_unreal():
        p = filedialog.askopenfilename(filetypes=[("Executavel","*.exe"),("Todos","*.*")])
        if p: var_unreal.set(p.replace("/","\\"))
    botao_browse(t1, 3, 2, browse_unreal)

    rotulo(t1, "Arquivo .uproject:", 4)
    var_projeto = tk.StringVar()
    tk.Entry(t1, textvariable=var_projeto, font=("Arial",9),
             relief="solid", bd=1).grid(row=4, column=1, sticky="ew", padx=(0,4), pady=4)
    def browse_projeto():
        p = filedialog.askopenfilename(filetypes=[("Unreal Project","*.uproject"),("Todos","*.*")])
        if p: var_projeto.set(p.replace("/","\\"))
    botao_browse(t1, 4, 2, browse_projeto)

    rotulo(t1, "Content base:", 5)
    var_content = tk.StringVar(value="/Game/IFC")
    tk.Entry(t1, textvariable=var_content, font=("Arial",9), width=30,
             relief="solid", bd=1).grid(row=5, column=1, columnspan=2,
                                         sticky="w", padx=(0,16), pady=4)

    rotulo(t1, "Level principal:", 6)
    var_level = tk.StringVar()
    combo_lvl = ttk.Combobox(t1, textvariable=var_level, state="readonly", width=52)
    combo_lvl.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(0,16), pady=4)

    lbl_lvl_status = tk.Label(t1, text="", font=("Arial",8), fg="#888888", bg="white")
    lbl_lvl_status.grid(row=7, column=1, columnspan=2, sticky="w", padx=(0,16))

    def atualizar_levels(*_):
        p = var_projeto.get().strip()
        if not p or not os.path.isfile(p):
            return
        lbl_lvl_status.config(text="Escaneando levels...", fg="#888888")

        def scan():
            lvls = listar_levels_disco(p)
            def update():
                combo_lvl["values"] = lvls
                if lvls:
                    if not var_level.get() or var_level.get() not in lvls:
                        var_level.set(lvls[0])
                    lbl_lvl_status.config(text=f"{len(lvls)} level(s) encontrado(s)", fg=COR_OK)
                else:
                    lbl_lvl_status.config(text="Nenhum level encontrado", fg=COR_ERR)
            root.after(0, update)

        threading.Thread(target=scan, daemon=True).start()

    var_projeto.trace_add("write", atualizar_levels)

    # ════════════════════════════════════════════════════════════════════════
    # ABA 2 — PASTAS IFC
    # ════════════════════════════════════════════════════════════════════════
    t2 = tab("Pastas IFC")
    t2.configure(style="TFrame")

    tk.Label(t2, text="  Cada pasta e varrida na raiz (sem subpastas).",
             font=("Arial",9), fg="#555555", bg="white"
             ).pack(anchor="w", padx=16, pady=(10,4))

    # scrollable area para as linhas de pasta
    canvas2  = tk.Canvas(t2, bg="white", highlightthickness=0)
    vsb2     = ttk.Scrollbar(t2, orient="vertical", command=canvas2.yview)
    frame_p  = tk.Frame(canvas2, bg="white")
    frame_p.bind("<Configure>",
                 lambda e: canvas2.configure(scrollregion=canvas2.bbox("all")))
    canvas2.create_window((0,0), window=frame_p, anchor="nw")
    canvas2.configure(yscrollcommand=vsb2.set)
    canvas2.pack(side="top", fill="both", expand=True, padx=0, pady=0)
    vsb2.pack(side="right", fill="y")
    canvas2.bind_all("<MouseWheel>",
                     lambda e: canvas2.yview_scroll(int(-1*(e.delta/120)), "units"))

    pastas_vars = []

    def add_pasta_row(valor=""):
        container = tk.Frame(frame_p, bg="white")
        container.pack(fill="x", padx=16, pady=(4,0))

        row_top = tk.Frame(container, bg="white")
        row_top.pack(fill="x")

        num = len(pastas_vars) + 1
        tk.Label(row_top, text=f"Pasta {num}:", width=8, anchor="w",
                 font=("Arial",9), bg="white").pack(side="left")

        var = tk.StringVar(value=valor)
        pastas_vars.append(var)

        entry = tk.Entry(row_top, textvariable=var, font=("Arial",9),
                         relief="solid", bd=1)
        entry.pack(side="left", fill="x", expand=True, padx=(0,4))

        # preview label
        lbl_prev = tk.Label(container, text="", font=("Arial",8),
                            fg=COR_OK, bg="white", anchor="w")
        lbl_prev.pack(fill="x", padx=(64,0), pady=(0,2))

        def atualizar_preview(*_):
            caminho = var.get().strip()

            def scan():
                ifcs = listar_ifcs(caminho)
                def update():
                    if not ifcs:
                        lbl_prev.config(
                            text="  Nenhum .ifc encontrado" if caminho else "",
                            fg=COR_ERR if caminho else "#888888")
                    else:
                        exemplo = ", ".join(ifcs[:3])
                        if len(ifcs) > 3:
                            exemplo += f"  ... (+{len(ifcs)-3})"
                        lbl_prev.config(
                            text=f"  {len(ifcs)} arquivo(s):  {exemplo}",
                            fg=COR_OK)
                root.after(0, update)

            threading.Thread(target=scan, daemon=True).start()

        var.trace_add("write", atualizar_preview)
        if valor:
            atualizar_preview()

        def browse_pasta():
            p = filedialog.askdirectory()
            if p:
                var.set(p.replace("/","\\"))

        def abrir_pasta():
            p = var.get().strip()
            if p and os.path.isdir(p):
                os.startfile(p)
            else:
                messagebox.showwarning("Aviso","Pasta nao encontrada.", parent=root)

        def remover():
            if var in pastas_vars:
                pastas_vars.remove(var)
            container.destroy()

        tk.Button(row_top, text="...", command=browse_pasta, width=3,
                  relief="flat", bg=COR_GRAY).pack(side="left", padx=(0,2))
        tk.Button(row_top, text="Abrir", command=abrir_pasta, width=5,
                  relief="flat", bg="#ddeeff",
                  font=("Arial",8)).pack(side="left", padx=(0,2))
        tk.Button(row_top, text="X", command=remover, width=3,
                  relief="flat", bg="#ffcccc").pack(side="left")

    for _ in range(3):
        add_pasta_row()

    btn_frame_p = tk.Frame(t2, bg="white")
    btn_frame_p.pack(fill="x", padx=16, pady=8)
    tk.Button(btn_frame_p, text="+ Adicionar pasta",
              command=add_pasta_row,
              relief="flat", bg=COR_GRAY,
              font=("Arial",9), padx=8, pady=4).pack(side="left")

    # ════════════════════════════════════════════════════════════════════════
    # ABA 3 — FILTROS
    # ════════════════════════════════════════════════════════════════════════
    t3 = tab("Filtros")
    t3.configure(style="TFrame")

    tk.Label(t3,
             text="  Arquivos cujo nome contiver qualquer um desses textos serao IGNORADOS.\n"
                  "  Exemplo: digitar  U-2000  ignora todos os arquivos que contenham 'U-2000'.",
             font=("Arial",9), fg="#444444", bg="white", justify="left"
             ).pack(anchor="w", padx=16, pady=(10,8))

    frame_f = tk.Frame(t3, bg="white")
    frame_f.pack(fill="x", padx=16)
    filtro_vars = []

    def add_filtro_row(valor=""):
        row = tk.Frame(frame_f, bg="white")
        row.pack(fill="x", pady=3)

        num = len(filtro_vars) + 1
        tk.Label(row, text=f"Filtro {num}:", width=8, anchor="w",
                 font=("Arial",9), bg="white").pack(side="left")

        var = tk.StringVar(value=valor)
        filtro_vars.append(var)

        tk.Entry(row, textvariable=var, font=("Arial",9),
                 width=28, relief="solid", bd=1).pack(side="left", padx=(0,8))

        def remover():
            if var in filtro_vars:
                filtro_vars.remove(var)
            row.destroy()

        tk.Button(row, text="X", command=remover, width=3,
                  relief="flat", bg="#ffcccc").pack(side="left")

    add_filtro_row()  # começa com 1

    tk.Button(t3, text="+ Adicionar filtro",
              command=add_filtro_row,
              relief="flat", bg=COR_GRAY,
              font=("Arial",9), padx=8, pady=4
              ).pack(anchor="w", padx=16, pady=8)

    tk.Label(t3,
             text="  Dica: os filtros nao diferenciam maiusculas de minusculas.",
             font=("Arial",8), fg="#888888", bg="white"
             ).pack(anchor="w", padx=16)

    # ════════════════════════════════════════════════════════════════════════
    # ABA 4 — AGENDAMENTO
    # ════════════════════════════════════════════════════════════════════════
    t4 = tab("Agendamento")
    t4.configure(style="TFrame")

    tk.Label(t4, text="", bg="white").pack(pady=8)

    var_agendar = tk.BooleanVar(value=False)
    tk.Checkbutton(t4, text="Agendar automaticamente ao gerar o .bat",
                   variable=var_agendar, font=("Arial",10),
                   bg="white").pack(anchor="w", padx=20)

    frame_ag = tk.Frame(t4, bg="white")
    frame_ag.pack(anchor="w", padx=40, pady=10)

    tk.Label(frame_ag, text="Dia da semana:", font=("Arial",9),
             bg="white").grid(row=0, column=0, sticky="w", pady=6, padx=(0,8))
    var_dia = tk.StringVar(value="Quinta-feira")
    ttk.Combobox(frame_ag, textvariable=var_dia, values=DIAS_PT,
                 state="readonly", width=18).grid(row=0, column=1, sticky="w")

    tk.Label(frame_ag, text="Horario:", font=("Arial",9),
             bg="white").grid(row=1, column=0, sticky="w", pady=6, padx=(0,8))
    var_hora = tk.StringVar(value="01:00")
    tk.Entry(frame_ag, textvariable=var_hora, font=("Arial",9),
             width=8, relief="solid", bd=1).grid(row=1, column=1, sticky="w")
    tk.Label(frame_ag, text=" formato HH:MM", font=("Arial",8),
             fg="#888888", bg="white").grid(row=1, column=2, sticky="w", padx=6)

    separador = tk.Frame(t4, bg="#dddddd", height=1)
    separador.pack(fill="x", padx=20, pady=16)

    info = tk.Label(t4,
                    text="O que acontece ao clicar 'Gerar .bat' com agendamento ativo:\n\n"
                         "  1. O arquivo .bat e criado em projetos/\n"
                         "  2. Uma tarefa e registrada no Windows Task Scheduler\n"
                         "  3. Na data/hora escolhida, o Windows roda o .bat automaticamente\n"
                         "  4. O log de execucao fica em projetos/{nome}.log\n\n"
                         "Sem agendamento: o .bat e criado mas precisa ser rodado manualmente.",
                    font=("Arial",9), fg="#444444", bg="white",
                    justify="left")
    info.pack(anchor="w", padx=20)

    # ════════════════════════════════════════════════════════════════════════
    # POPULAR FORMULARIO (usado ao carregar .bat)
    # ════════════════════════════════════════════════════════════════════════
    def popular_formulario(cfg):
        var_nome.set(cfg.get("nome", ""))
        var_unreal.set(cfg.get("unreal", UNREAL_DEFAULT))
        var_projeto.set(cfg.get("projeto", ""))
        var_content.set(cfg.get("content_base", "/Game/IFC"))
        var_level.set(cfg.get("level", ""))

        # Limpa e repopula pastas
        for widget in frame_p.winfo_children():
            widget.destroy()
        pastas_vars.clear()
        for p in cfg.get("pastas", []):
            add_pasta_row(p)
        if not cfg.get("pastas"):
            for _ in range(3):
                add_pasta_row()

        # Limpa e repopula filtros
        for widget in frame_f.winfo_children():
            widget.destroy()
        filtro_vars.clear()
        for ft in cfg.get("filtros", []):
            add_filtro_row(ft)
        if not cfg.get("filtros"):
            add_filtro_row()

        # Agendamento
        if cfg.get("agenda_dia"):
            var_dia.set(cfg["agenda_dia"])
        if cfg.get("agenda_hora"):
            var_hora.set(cfg["agenda_hora"])

        # Vai para aba Projeto
        nb.select(0)

    # ════════════════════════════════════════════════════════════════════════
    # MONTAR CONFIG
    # ════════════════════════════════════════════════════════════════════════
    def montar_config():
        nome = sanitizar(var_nome.get())
        if not nome:
            messagebox.showerror("Erro","Nome invalido.", parent=root)
            nb.select(0); return None

        projeto = var_projeto.get().strip()
        if not projeto or not os.path.isfile(projeto):
            messagebox.showerror("Erro","Selecione um .uproject valido.", parent=root)
            nb.select(0); return None

        if not var_level.get().strip():
            messagebox.showerror("Erro","Selecione um level.", parent=root)
            nb.select(0); return None

        pastas = [v.get().strip() for v in pastas_vars if v.get().strip()]
        if not pastas:
            messagebox.showerror("Erro","Adicione ao menos 1 pasta de IFCs.", parent=root)
            nb.select(1); return None

        return {
            "nome":         nome,
            "unreal":       var_unreal.get().strip(),
            "projeto":      projeto,
            "content_base": var_content.get().strip() or "/Game/IFC",
            "level":        var_level.get().strip(),
            "pastas":       pastas,
            "filtros":      [v.get().strip() for v in filtro_vars if v.get().strip()],
            "agenda_dia":   var_dia.get(),
            "agenda_hora":  var_hora.get().strip(),
        }

    root.mainloop()


if __name__ == "__main__":
    main()
