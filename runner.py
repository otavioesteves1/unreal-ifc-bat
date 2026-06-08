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

FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


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
    """
    Forca o download de um arquivo cloud-only.
    Abrir o arquivo em Python dispara o download automatico do OneDrive.
    """
    try:
        mb = tamanho_mb(path)
        log(f"  [{idx}/{total}] Baixando: {nome}  ({mb:.1f} MB)...")

        # Abre e le o arquivo inteiro — isso dispara e aguarda o download do OneDrive
        with open(path, 'rb') as f:
            while f.read(1024 * 512):  # le em chunks de 512KB
                pass

        # Confirma que agora esta local
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
    """
    Baixa varios arquivos do OneDrive em paralelo (ate max_paralelo ao mesmo tempo).
    Retorna dict {path: True/False}.
    """
    resultados  = {}
    semaforo    = threading.Semaphore(max_paralelo)
    threads     = []
    total       = len(arquivos_nuvem)

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


def main():
    log()
    log("=" * 62)
    log("  IMPORTADOR IFC — RUNNER")
    log("=" * 62)

    # ── Ler configuracao das variaveis de ambiente ────────────────────────────
    nome         = os.environ.get("IFC_NOME",         "batch")
    unreal       = os.environ.get("IFC_UNREAL",       "")
    projeto      = os.environ.get("IFC_PROJETO",      "")
    content_base = os.environ.get("IFC_CONTENT_BASE", "/Game/IFC")
    level        = os.environ.get("IFC_LEVEL",        "")
    filtros_str  = os.environ.get("IFC_FILTROS",      "")

    log(f"  Batch   : {nome}")
    log(f"  Projeto : {os.path.basename(projeto)}")
    log(f"  Level   : {level}")
    log(f"  Destino : {content_base}")

    pastas = [os.environ.get(f"IFC_PASTA_{i}", "").strip()
              for i in range(1, 11)]
    pastas = [p for p in pastas if p]

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
    ifc_locais    = []   # prontos para importar
    ifc_nuvem     = []   # precisam ser baixados: (path, nome)
    ignorados     = []

    for pasta in pastas:
        if not os.path.isdir(pasta):
            log(f"  [!] Pasta nao encontrada: {pasta}")
            continue

        log(f"  Varrendo: {pasta}")
        try:
            arquivos = sorted(f for f in os.listdir(pasta) if f.lower().endswith(".ifc"))
        except PermissionError:
            log(f"      [!] Sem permissao para acessar.")
            continue

        for f in arquivos:
            caminho = os.path.join(pasta, f)

            if any(filtro in f.lower() for filtro in filtros):
                ignorados.append(f)
                log(f"      [FILTRADO] {f}")
                continue

            if is_local(caminho):
                ifc_locais.append(caminho)
                log(f"      [local]  {f}  ({tamanho_mb(caminho):.1f} MB)")
            else:
                ifc_nuvem.append((caminho, f))
                log(f"      [nuvem]  {f}  ({tamanho_mb(caminho):.1f} MB)")

    log()

    # ── Tratar arquivos em nuvem ──────────────────────────────────────────────
    if ifc_nuvem:
        total_mb = sum(tamanho_mb(p) for p, _ in ifc_nuvem)
        log("  ══════════════════════════════════════════════════════════")
        log(f"  {len(ifc_nuvem)} arquivo(s) estao apenas na nuvem ({total_mb:.0f} MB total).")
        log("  E possivel baixar agora automaticamente antes de importar.")
        log("  ══════════════════════════════════════════════════════════")
        log()

        resp = input("  Baixar arquivos da nuvem agora? (S/N): ").strip().lower()

        if resp == "s":
            log()
            log("  Iniciando download do OneDrive...")
            log("  (o OneDrive precisa estar rodando e conectado)")
            log()

            resultados = baixar_em_paralelo(ifc_nuvem, max_paralelo=3)

            baixados_ok  = [p for p, ok in resultados.items() if ok]
            baixados_err = [p for p, ok in resultados.items() if not ok]

            ifc_locais.extend(baixados_ok)

            log()
            log(f"  Download: {len(baixados_ok)} OK | {len(baixados_err)} com erro")
            if baixados_err:
                for p in baixados_err:
                    log(f"    [!] Falha: {os.path.basename(p)}")
            log()
        else:
            log("  Arquivos em nuvem serao ignorados nesta execucao.")
            log()

    # ── Resumo final ──────────────────────────────────────────────────────────
    log(f"  Para importar : {len(ifc_locais)} arquivo(s)")
    log(f"  Filtrados     : {len(ignorados)}")
    log(f"  Nuvem (skip)  : {len([p for p, _ in ifc_nuvem if p not in ifc_locais])}")
    log()

    if not ifc_locais:
        log("  Nenhum arquivo disponivel para importar. Encerrando.")
        input("\n  Pressione Enter para sair...")
        return

    # ── Escrever config.json ──────────────────────────────────────────────────
    if os.path.exists(RESULT_PATH):
        os.remove(RESULT_PATH)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "ifc_files":    ifc_locais,
            "main_level":   level,
            "content_base": content_base,
            "uproject":     projeto,
        }, f, indent=2, ensure_ascii=False)

    # ── Rodar Unreal headless ─────────────────────────────────────────────────
    log("  Iniciando Unreal Engine em modo headless...")
    log("  (aguarde — pode levar varios minutos)")
    log()

    subprocess.run([
        unreal, projeto,
        "-run=PythonScript",
        f"-Script={HEADLESS_SCRIPT}",
        "-unattended",
        "-nullrhi",
        "-nopause",
        "-nosplash",
        "-NoSound",
        "-log",
    ])

    # ── Verificar resultado ───────────────────────────────────────────────────
    log()
    log("=" * 62)
    log_dir = os.path.join(os.path.dirname(projeto), "Saved", "Logs")

    if os.path.exists(RESULT_PATH):
        with open(RESULT_PATH, "r", encoding="utf-8") as f:
            result = json.load(f)
        ok     = result.get("ok", 0)
        falhou = result.get("falhou", 0)
        os.remove(RESULT_PATH)
        log()
        if ok > 0:
            log(f"  Concluido!  Importados: {ok}  |  Falhas: {falhou}")
        else:
            log(f"  [!] Nenhum arquivo importado. Falhas: {falhou}")
            log(f"      Log: {log_dir}")
    else:
        log()
        log("  [!] Script de import nao gerou resultado.")
        log("      O Unreal pode nao ter conseguido executar o script.")
        log(f"      Log: {log_dir}")

    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)

    log()
    resp = input("  Deseja abrir o projeto no Unreal para conferir? (S/N): ").strip().lower()
    if resp == "s":
        subprocess.Popen([unreal, projeto])


if __name__ == "__main__":
    main()
