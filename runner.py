"""
runner.py
Chamado pelo .bat gerado. Le as variaveis de ambiente IFC_*,
varre as pastas, aplica filtros, baixa arquivos da nuvem se necessario
e roda o Unreal headless.
"""

import os
import sys
import json
import subprocess
import ctypes
import threading
import time

SCRIPTS_DIR     = os.path.dirname(os.path.abspath(__file__))
HEADLESS_SCRIPT = os.path.join(SCRIPTS_DIR, "import_headless.py")
CONFIG_PATH     = os.path.join(SCRIPTS_DIR, "config.json")
RESULT_PATH     = os.path.join(SCRIPTS_DIR, "result.json")
PROGRESS_PATH   = os.path.join(SCRIPTS_DIR, "progress.json")

FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


def get_short_path(path):
    """Converte para caminho curto 8.3 do Windows (sem acentos) — seguro para passar ao Unreal via CLI."""
    if not path:
        return path
    try:
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)):
            return buf.value
    except Exception:
        pass
    return path


def get_long_path(path):
    """Converte um caminho 8.3 curto de volta ao caminho longo Unicode.

    O .bat passa caminhos curtos (ex.: MEUPRO~1.UPR) porque o CMD le em
    codepage OEM e nao lida com acentos. Mas o Unreal, ao receber o projeto
    como nome 8.3 (extensao .uproject truncada para .UPR), NAO aplica a lista
    de plugins habilitados do .uproject — entao DatasmithImporter nao carrega.
    Como o subprocess.run usa a API Unicode (CreateProcessW), podemos passar o
    caminho longo completo (com acentos) sem o problema de codepage do CMD.
    """
    if not path:
        return path
    try:
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(str(path), buf, len(buf)):
            return buf.value
    except Exception:
        pass
    return path


def _make_script_arg(path):
    """Retorna o caminho do script em formato seguro para -Script= do Unreal.

    GetShortPathNameW devolve extensao em MAIUSCULO (.PY).
    O commandlet do Unreal so reconhece arquivo se terminar em .py minusculo;
    caso contrario trata o valor como codigo Python inline e falha com
    SyntaxError ao tentar avaliar o caminho como expressao.
    """
    short = get_short_path(path)
    # Forcando extensao minuscula (.PY -> .py)
    if short.upper().endswith('.PY') and not short.endswith('.py'):
        short = short[:-3] + '.py'
    return short.replace(chr(92), '/')


def log(msg=""):
    print(msg, flush=True)


def is_local(path):
    """Retorna False se o arquivo estiver apenas na nuvem (OneDrive cloud-only)."""
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == 0xFFFFFFFF:
            return True
        return not bool(attrs & FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    except Exception:
        return True


def tamanho_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0


def baixar_arquivo(path, nome, idx, total, resultados):
    """Forca o download de um arquivo cloud-only via OneDrive."""
    try:
        mb = tamanho_mb(path)
        log(f"  [{idx}/{total}] Baixando: {nome}  ({mb:.1f} MB)...")
        with open(path, 'rb') as f:
            while f.read(1024 * 512):
                pass
        timeout = 60
        inicio  = time.time()
        while time.time() - inicio < timeout:
            if is_local(path):
                log(f"  [{idx}/{total}] OK: {nome}")
                resultados[path] = True
                return
            time.sleep(1)
        log(f"  [{idx}/{total}] [!] Timeout aguardando {nome}")
        resultados[path] = False
    except Exception as e:
        log(f"  [{idx}/{total}] [!] Erro ao baixar {nome}: {e}")
        resultados[path] = False


def baixar_em_paralelo(arquivos_nuvem, max_paralelo=3):
    """Baixa varios arquivos do OneDrive em paralelo. Retorna dict {path: True/False}."""
    resultados = {}
    semaforo   = threading.Semaphore(max_paralelo)
    threads    = []
    total      = len(arquivos_nuvem)

    def worker(path, nome, idx):
        with semaforo:
            baixar_arquivo(path, nome, idx, total, resultados)

    for i, (path, nome) in enumerate(arquivos_nuvem, start=1):
        t = threading.Thread(target=worker, args=(path, nome, i), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    return resultados


# ── Progresso ─────────────────────────────────────────────────────────────────

def fmt_tempo(seg):
    """Formata segundos em MM:SS ou HH:MM:SS. Retorna '--:--' para valores invalidos."""
    if seg is None or seg < 0:
        return "--:--"
    s = int(seg)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def barra_progresso(atual, total, largura=28):
    """Barra ASCII de progresso: [####--------]"""
    if total <= 0:
        return "[" + "-" * largura + "]"
    feitos = min(int(largura * atual / total), largura)
    return "[" + "#" * feitos + "-" * (largura - feitos) + "]"


def monitorar_progresso(total_esperado, parar):
    """
    Thread: le progress.json a cada 0.5s e exibe barra de progresso
    no terminal enquanto o Unreal Engine processa os IFCs.
    """
    spinner = ["|", "/", "-", "\\"]
    idx     = 0
    inicio  = time.time()
    ultima  = ""

    while not parar.is_set():
        try:
            if os.path.exists(PROGRESS_PATH):
                with open(PROGRESS_PATH, "r", encoding="utf-8") as fh:
                    prog = json.load(fh)

                atual   = prog.get("current", 0)
                total   = prog.get("total", total_esperado) or total_esperado
                arquivo = os.path.basename(prog.get("current_file", ""))
                t_ini   = prog.get("started_at", time.time())
                elapsed = time.time() - t_ini
                ok      = prog.get("ok", 0)
                falhou  = prog.get("falhou", 0)
                restante = (elapsed / atual * (total - atual)) if atual > 0 else -1

                if len(arquivo) > 34:
                    arquivo = arquivo[:31] + "..."

                barra = barra_progresso(atual, total)
                linha = (
                    f"  {barra}  {atual}/{total}"
                    f"  {arquivo:<37}"
                    f"  {fmt_tempo(elapsed)} / ~{fmt_tempo(restante)}"
                    f"  ok:{ok} err:{falhou}"
                )
            else:
                spin    = spinner[idx % len(spinner)]
                idx    += 1
                elapsed = time.time() - inicio
                linha   = f"  {spin}  Inicializando Unreal Engine...  {fmt_tempo(elapsed)}"

        except Exception:
            spin    = spinner[idx % len(spinner)]
            idx    += 1
            elapsed = time.time() - inicio
            linha   = f"  {spin}  Aguardando...  {fmt_tempo(elapsed)}"

        linha_pad = f"\r{linha:<79}"
        if linha_pad != ultima:
            sys.stdout.write(linha_pad)
            sys.stdout.flush()
            ultima = linha_pad

        time.sleep(0.5)

    sys.stdout.write("\r" + " " * 79 + "\r")
    sys.stdout.flush()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    SEP = "=" * 62

    log()
    log(SEP)
    log("  IMPORTADOR IFC — RUNNER")
    log(SEP)

    # ── Ler configuracao das variaveis de ambiente ────────────────────────────
    nome         = os.environ.get("IFC_NOME",         "batch")
    unreal       = os.environ.get("IFC_UNREAL",       "")
    projeto      = get_long_path(os.environ.get("IFC_PROJETO", ""))
    content_base = os.environ.get("IFC_CONTENT_BASE", "/Game/IFC")
    level        = os.environ.get("IFC_LEVEL",        "")
    filtros_str  = os.environ.get("IFC_FILTROS",      "")

    log(f"  Batch   : {nome}")
    log(f"  Projeto : {os.path.basename(projeto)}")
    log(f"  Level   : {level}")
    log(f"  Destino : {content_base}")

    pastas  = [os.environ.get(f"IFC_PASTA_{i}", "").strip() for i in range(1, 11)]
    pastas  = [p for p in pastas if p]
    filtros = [f.strip().lower() for f in filtros_str.split(",") if f.strip()]
    if filtros:
        log(f"  Filtros : {', '.join(filtros)}")
    log()

    # ── Validacoes ────────────────────────────────────────────────────────────
    for campo, valor, msg in [
        ("UnrealEditor.exe", unreal,  "Verifique IFC_UNREAL no .bat"),
        ("Projeto",          projeto, "Verifique IFC_PROJETO no .bat"),
    ]:
        if not valor or not os.path.isfile(valor):
            log(f"  [ERRO] {campo} nao encontrado: {valor}")
            log(f"         {msg}")
            input("\n  Pressione Enter para sair...")
            sys.exit(1)

    if not level:
        log("  [ERRO] Level nao configurado. Verifique IFC_LEVEL no .bat")
        input("\n  Pressione Enter para sair...")
        sys.exit(1)

    if not pastas:
        log("  [ERRO] Nenhuma pasta configurada.")
        input("\n  Pressione Enter para sair...")
        sys.exit(1)

    # ── Varrer pastas ─────────────────────────────────────────────────────────
    log("  Varrendo pastas...")
    log()

    ifc_locais = []
    ifc_nuvem  = []
    ignorados  = []

    for pasta in pastas:
        if not os.path.isdir(pasta):
            log(f"  [!] Pasta nao encontrada: {pasta}")
            continue
        try:
            arquivos = sorted(f for f in os.listdir(pasta) if f.lower().endswith(".ifc"))
        except PermissionError:
            log(f"  [!] Sem permissao para acessar: {pasta}")
            continue

        c_local = c_nuvem = c_filtro = 0
        for f in arquivos:
            caminho = os.path.join(pasta, f)
            if any(filtro in f.lower() for filtro in filtros):
                ignorados.append(f)
                c_filtro += 1
                continue
            if is_local(caminho):
                ifc_locais.append(caminho)
                c_local += 1
            else:
                ifc_nuvem.append((caminho, f))
                c_nuvem += 1

        partes = []
        if c_local:  partes.append(f"{c_local} local{'is' if c_local  > 1 else ''}")
        if c_nuvem:  partes.append(f"{c_nuvem} na nuvem")
        if c_filtro: partes.append(f"{c_filtro} filtrado{'s' if c_filtro > 1 else ''}")
        resumo    = "  |  ".join(partes) if partes else "nenhum .ifc encontrado"
        nome_past = os.path.basename(pasta.rstrip("\\/")) or pasta
        log(f"  {nome_past:<32}  {resumo}")

    log()

    # ── Resumo do escaneamento ────────────────────────────────────────────────
    total_mb_local = sum(tamanho_mb(p) for p in ifc_locais)
    log(f"  Locais      : {len(ifc_locais):>3} arquivo(s)  ({total_mb_local:.0f} MB)")
    if ifc_nuvem:
        total_mb_nuvem = sum(tamanho_mb(p) for p, _ in ifc_nuvem)
        log(f"  Na nuvem    : {len(ifc_nuvem):>3} arquivo(s)  ({total_mb_nuvem:.0f} MB)")
    if ignorados:
        log(f"  Filtrados   : {len(ignorados):>3} arquivo(s)")
    log()

    # ── Tratar arquivos em nuvem ──────────────────────────────────────────────
    if ifc_nuvem:
        total_mb = sum(tamanho_mb(p) for p, _ in ifc_nuvem)
        log(f"  {len(ifc_nuvem)} arquivo(s) estao na nuvem ({total_mb:.0f} MB total).")
        resp = input("  Baixar do OneDrive agora? (S/N): ").strip().lower()
        log()
        if resp == "s":
            log("  Iniciando download...")
            resultados   = baixar_em_paralelo(ifc_nuvem, max_paralelo=3)
            baixados_ok  = [p for p, ok in resultados.items() if ok]
            baixados_err = [p for p, ok in resultados.items() if not ok]
            ifc_locais.extend(baixados_ok)
            log()
            log(f"  Download: {len(baixados_ok)} OK  |  {len(baixados_err)} com erro")
            if baixados_err:
                for p in baixados_err:
                    log(f"    [!] {os.path.basename(p)}")
            log()
        else:
            log("  Arquivos em nuvem ignorados nesta execucao.")
            log()

    # ── Verificacao final ─────────────────────────────────────────────────────
    log(f"  Para importar : {len(ifc_locais)} arquivo(s)")
    log()

    if not ifc_locais:
        log("  Nenhum arquivo disponivel para importar. Encerrando.")
        input("\n  Pressione Enter para sair...")
        return

    # ── Escrever config.json ──────────────────────────────────────────────────
    for p in (RESULT_PATH, PROGRESS_PATH):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "ifc_files":    ifc_locais,
            "main_level":   level,
            "content_base": content_base,
            "uproject":     projeto,
        }, f, indent=2, ensure_ascii=False)

    # ── Rodar Unreal headless ─────────────────────────────────────────────────
    log("  Iniciando Unreal Engine em modo headless...")
    log("  (aguarde — a inicializacao pode levar alguns minutos)")
    log()

    parar    = threading.Event()
    t_mon    = threading.Thread(
        target=monitorar_progresso,
        args=(len(ifc_locais), parar),
        daemon=True
    )
    t_mon.start()
    t_inicio = time.time()

    subprocess.run([
        unreal, projeto,
        "-run=PythonScript",
        "-unattended",
        "-nullrhi",
        "-nopause",
        "-nosplash",
        "-NoSound",
        "-log",
        f"-Script={_make_script_arg(HEADLESS_SCRIPT)}",
    ])

    parar.set()
    t_mon.join(timeout=2)

    tempo_total = time.time() - t_inicio

    try:
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
    except Exception:
        pass

    # ── Resultado ─────────────────────────────────────────────────────────────
    log()
    log(SEP)
    log_dir = os.path.join(os.path.dirname(projeto), "Saved", "Logs")

    if os.path.exists(RESULT_PATH):
        with open(RESULT_PATH, "r", encoding="utf-8") as f:
            result = json.load(f)
        ok     = result.get("ok",     0)
        falhou = result.get("falhou", 0)
        erros  = result.get("erros",  [])
        os.remove(RESULT_PATH)

        log()
        log("  CONCLUIDO" + (" COM SUCESSO" if falhou == 0 else " COM FALHAS"))
        log()
        log(f"  Importados   : {ok}")
        log(f"  Falhas       : {falhou}")
        log(f"  Filtrados    : {len(ignorados)}")
        log(f"  Tempo total  : {fmt_tempo(tempo_total)}")

        if erros:
            log()
            log("  Arquivos com falha:")
            for e in erros:
                log(f"    [!] {e}")

        if falhou > 0:
            log()
            log(f"  Log detalhado: {log_dir}")
    else:
        log()
        log("  [!] Script de import nao gerou resultado.")
        log("      Verifique se o plugin Python esta ativo no projeto.")
        log(f"  Log: {log_dir}")

    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)

    log()
    log(SEP)
    log()
    resp = input("  Abrir o projeto no Unreal para conferir? (S/N): ").strip().lower()
    if resp == "s":
        subprocess.Popen([unreal, projeto])


if __name__ == "__main__":
    main()
