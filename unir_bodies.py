"""
unir_bodies.py
Mescla os "bodies" (StaticMeshActor _body1, _body2, ...) de cada elemento
(ator-pai) em UMA unica malha por elemento.

IMPORTANTE: roda no EDITOR COMPLETO (precisa do StaticMeshEditorSubsystem, que
NAO existe no commandlet -run=PythonScript). O runner o invoca assim:
    UnrealEditor.exe <proj> -ExecCmds=py <unir_bodies.py> -unattended -nullrhi ...

Tambem pode ser rodado manualmente no editor ja aberto (Tools > Execute Python
Script), sem custo de carregar o level.

Le main_level/content_base de config.json (se existir) e escreve merge_result.json.
A geometria e materiais sao preservados (cada body vira uma secao da malha).
"""
import unreal
import os
import json
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPTS_DIR, "config_merge.json")
RESULT_PATH = os.path.join(SCRIPTS_DIR, "merge_result.json")


def _escrever_result(d):
    try:
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def unir_bodies(main_level="", content_base="/Game/IFC"):
    sm_sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if sm_sub is None:
        unreal.log_error("[Merge] StaticMeshEditorSubsystem indisponivel "
                         "(rode no EDITOR COMPLETO, nao no commandlet).")
        _escrever_result({"merged": 0, "total": 0, "erro": "subsystem indisponivel"})
        return 0, 0

    if main_level:
        try:
            unreal.EditorLoadingAndSavingUtils.load_map(main_level)
        except Exception as e:
            unreal.log_warning(f"[Merge] nao carregou o level '{main_level}': {e}")

    asub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = asub.get_all_level_actors()

    # agrupa filhos StaticMesh por ator-pai (a hierarquia define o elemento)
    by_parent = {}
    for a in actors:
        try:
            p = a.get_attach_parent_actor()
        except Exception:
            p = None
        if p is not None:
            by_parent.setdefault(p, []).append(a)

    grupos = []
    for parent, kids in by_parent.items():
        smk = [k for k in kids if isinstance(k, unreal.StaticMeshActor)]
        if len(smk) >= 2:
            grupos.append((parent, smk))

    total = len(grupos)
    unreal.log(f"[Merge] elementos multi-body encontrados: {total}")
    if total == 0:
        _escrever_result({"merged": 0, "total": 0})
        return 0, 0

    merge_dir = content_base.rstrip("/") + "/_Merged"
    ok = 0
    t0 = time.time()
    for i, (parent, smk) in enumerate(grupos, start=1):
        try:
            opts = unreal.MergeStaticMeshActorsOptions()
            opts.set_editor_property("base_package_name", f"{merge_dir}/E_{i:06d}")
            opts.set_editor_property("destroy_source_actors", True)
            opts.set_editor_property("spawn_merged_actor", True)
            opts.set_editor_property("new_actor_label", parent.get_actor_label())
            merged = sm_sub.merge_static_mesh_actors(smk, opts)
            if merged is not None:
                ok += 1
                # mantem o merged na mesma posicao da hierarquia (sob o ator-pai)
                try:
                    merged.attach_to_actor(
                        parent, "",
                        unreal.AttachmentRule.KEEP_WORLD,
                        unreal.AttachmentRule.KEEP_WORLD,
                        unreal.AttachmentRule.KEEP_WORLD, False)
                except Exception:
                    pass
        except Exception as e:
            if i <= 5:
                unreal.log_warning(f"[Merge] elemento {i} falhou: {e}")
        if i % 200 == 0:
            unreal.log(f"[Merge] {i}/{total}...")

    dt = time.time() - t0
    unreal.log(f"[Merge] CONCLUIDO: {ok}/{total} elementos unidos em {dt:.1f}s")
    unreal.log("[Merge] Salvando...")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    _escrever_result({"merged": ok, "total": total, "tempo": round(dt, 1)})
    return ok, total


def main():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    unir_bodies(cfg.get("main_level", ""), cfg.get("content_base", "/Game/IFC"))


main()

# encerra o editor (o crash benigno de shutdown nao afeta o resultado ja salvo)
try:
    unreal.SystemLibrary.quit_editor()
except Exception:
    pass
