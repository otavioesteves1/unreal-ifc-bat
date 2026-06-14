"""
import_headless.py
Roda DENTRO do Unreal em modo headless (sem UI).
Le config.json gerado pelo launcher.py e importa os IFCs.
"""

import unreal
import os
import json
import re
import time

SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH   = os.path.join(SCRIPTS_DIR, "config.json")
RESULT_PATH   = os.path.join(SCRIPTS_DIR, "result.json")
PROGRESS_PATH = os.path.join(SCRIPTS_DIR, "progress.json")

# ── parse de nome (mesmo do script principal) ─────────────────────────────────
_AVEVA = re.compile(r"^U-([^-]+)-([^_]+)_ET4\.ifc$", re.IGNORECASE)
_REVIT  = re.compile(r"^([A-Za-z]+)_INT-MO-[\d.]+-([0-9]+)-", re.IGNORECASE)

def parse_filename(filename):
    m = _AVEVA.match(filename)
    if m:
        return m.group(1), m.group(2).upper()
    m = _REVIT.match(filename)
    if m:
        return m.group(2), m.group(1).upper()
    return "Outros", os.path.splitext(filename)[0]


def ensure_content_path(path):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


def limpar_assets_existentes(dest_path, ifc_filename):
    scene_name = os.path.splitext(ifc_filename)[0].replace(".", "_")
    subdir = f"{dest_path}/{scene_name}"
    if unreal.EditorAssetLibrary.does_directory_exist(subdir):
        unreal.log(f"[IFC] Substituindo existente: {scene_name}")
        unreal.EditorAssetLibrary.delete_directory(subdir)


def escrever_progresso(atual, total, arquivo, inicio, ok, falhou, fase="importando"):
    """Grava progresso em progress.json para o runner.py exibir em tempo real."""
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "current":      atual,
                "total":        total,
                "current_file": arquivo,
                "started_at":   inicio,
                "ok":           ok,
                "falhou":       falhou,
                "fase":         fase,
            }, f)
    except Exception:
        pass


def import_ifc(ifc_path, dest_path):
    name = os.path.basename(ifc_path)
    try:
        scene = unreal.DatasmithSceneElement.construct_datasmith_scene_from_file(ifc_path)
        if scene is None:
            unreal.log_warning(f"[IFC] retornou None: {name}")
            return False
        try:
            opts = scene.get_options(unreal.DatasmithImportBaseOptions)
            if opts:
                opts.set_editor_property("scene_handling",   unreal.DatasmithImportScene.CURRENT_LEVEL)
                opts.set_editor_property("include_geometry",  True)
                opts.set_editor_property("include_material",  True)
                opts.set_editor_property("include_light",     False)
                opts.set_editor_property("include_camera",    False)
                opts.set_editor_property("include_animation", False)
        except Exception as e:
            unreal.log_warning(f"[IFC] Aviso opcoes: {e}")
        result = scene.import_scene(dest_path)
        scene.destroy_scene()
        if result:
            unreal.log(f"[IFC] OK: {name}")
            return True
        unreal.log_warning(f"[IFC] import_scene retornou False: {name}")
        return False
    except Exception as e:
        unreal.log_error(f"[IFC] FALHOU ({e}): {name}")
        return False


def main():
    # ── 1. Ler config ───────────────────────────────────────────────────────
    if not os.path.exists(CONFIG_PATH):
        unreal.log_error(f"[Headless] config.json nao encontrado: {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    ifc_files    = config.get("ifc_files", [])
    main_level   = config.get("main_level", "")
    content_base = config.get("content_base", "/Game/IFC")

    if not ifc_files:
        unreal.log_warning("[Headless] Nenhum arquivo no config.json.")
        return

    unreal.log(f"[Headless] {len(ifc_files)} arquivo(s) — level: {main_level}")

    # ── 2. Abrir level ──────────────────────────────────────────────────────
    try:
        unreal.EditorLoadingAndSavingUtils.load_map(main_level)
    except Exception as e:
        unreal.log_error(f"[Headless] Nao foi possivel abrir o level: {e}")
        return

    # ── 3. Importar ─────────────────────────────────────────────────────────
    ok, falhou = 0, 0
    erros      = []
    total      = len(ifc_files)
    inicio_imp = time.time()

    with unreal.ScopedSlowTask(total, "Importando IFCs...") as slow:
        slow.make_dialog(False)   # False = sem botao cancelar em modo headless
        for i, ifc_path in enumerate(ifc_files, start=1):
            filename = os.path.basename(ifc_path)
            slow.enter_progress_frame(1, filename)

            # Sinaliza para o runner: iniciando arquivo i
            escrever_progresso(i - 1, total, ifc_path, inicio_imp, ok, falhou)

            site, discipline = parse_filename(filename)
            dest = f"{content_base}/{site}/{discipline}"
            ensure_content_path(dest)
            limpar_assets_existentes(dest, filename)

            if import_ifc(ifc_path, dest):
                ok += 1
            else:
                falhou += 1
                erros.append(filename)

            # Sinaliza para o runner: arquivo i concluido
            escrever_progresso(i, total, ifc_path, inicio_imp, ok, falhou)

    # ── 4. Salvar tudo ──────────────────────────────────────────────────────
    # Sinaliza fase "salvando" para o runner: aqui o Unreal constroi as malhas
    # e salva os pacotes — pode levar varios minutos e nao tem progresso por item.
    unreal.log("[Headless] Salvando...")
    escrever_progresso(total, total, "", inicio_imp, ok, falhou, fase="salvando")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)

    # ── 5. Escrever result.json para o runner saber o resultado ─────────────
    try:
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"ok": ok, "falhou": falhou, "erros": erros}, f)
    except Exception as e:
        unreal.log_warning(f"[Headless] Nao foi possivel escrever result.json: {e}")

    # ── 6. Limpar arquivos temporarios ──────────────────────────────────────
    for p in (CONFIG_PATH, PROGRESS_PATH):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    unreal.log(
        f"\n[Headless] CONCLUIDO — Importados: {ok}  Falhas: {falhou}\n"
    )


main()
