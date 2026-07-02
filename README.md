# Importador IFC para Unreal Engine — Modo Batch

Conjunto de scripts Python que automatiza a importação de arquivos `.ifc` para o Unreal Engine (via Datasmith) sem precisar abrir a interface do editor. Gera um `.bat` por projeto, roda o Unreal em modo headless e — opcionalmente — agenda a execução e une os *bodies* de cada elemento.

---

## Como funciona

```
gerador.py            →  interface para montar um .bat de projeto
    ↓
<nome>.bat            →  chama runner.py
    ↓
runner.py             →  varre as pastas, COPIA os .ifc para dentro do projeto
                         (evita usar a rede no import) e chama o Unreal headless
    ↓
import_headless.py    →  roda dentro do Unreal (commandlet) e importa via Datasmith
    ↓  (opcional, se "Unir bodies" estiver ligado)
unir_bodies.py        →  roda no editor completo e mescla os _bodyN de cada
                         elemento numa malha só
```

---

## Pré-requisitos

- **Unreal Engine 5.x** instalado
- **Python** no Windows (comando `py` disponível no terminal — vem com o instalador oficial do python.org)
- Plugins ativos no Unreal (ver abaixo)

---

## 1. Ativar os plugins no Unreal

Abra o projeto no Unreal Editor, vá em **Edit → Plugins**, ative os plugins abaixo e **reinicie o editor**.

| Plugin | Categoria | Para quê |
|---|---|---|
| **Python Editor Script Plugin** | Scripting | rodar os scripts |
| **Datasmith Importer** | Importers | importação Datasmith |
| **Datasmith CAD Importer** | Importers | leitura de arquivos IFC |

> ⚠️ Se o import falhar com `module 'unreal' has no attribute 'DatasmithSceneElement'`, é sinal de que os plugins Datasmith não carregaram — confira se estão ativos e reinicie o editor.

---

## 2. Instalar os scripts

Clone o repositório em qualquer pasta local:

```
git clone https://github.com/otavioesteves1/unreal-ifc-bat.git
```

A pasta contém:

| Arquivo | Função |
|---|---|
| `gerador.py` | Interface gráfica para criar os `.bat` de projeto |
| `runner.py` | Chamado pelo `.bat`; varre os IFCs, copia para o projeto e inicia o Unreal |
| `import_headless.py` | Roda dentro do Unreal e importa via Datasmith |
| `unir_bodies.py` | (opcional) Une os *bodies* de cada elemento numa malha só |
| `Gerador-Admin.bat` | Abre o gerador como Administrador (necessário só para agendar) |

---

## 3. Gerar um .bat de projeto

```
py gerador.py
```

### Aba — Projeto
| Campo | O que preencher |
|---|---|
| **Nome do batch** | Nome do `.bat` que será criado (ex: `REPAR_quinta`) |
| **UnrealEditor.exe** | Caminho completo do executável do Unreal |
| **Arquivo .uproject** | Caminho do `.uproject` do seu projeto |
| **Content base** | Pasta no Content onde os IFCs entram (ex: `/Game/IFC`) |
| **Level principal** | Level aberto durante o import |
| ☑ **Unir bodies** | (opcional) Mescla `_body1`, `_body2`... de cada elemento numa malha só. Passo extra em editor completo — mais lento, porém deixa a cena mais leve. |

### Aba — Pastas IFC
Adicione as pastas onde estão os `.ifc`. Cada pasta é varrida **apenas na raiz** (sem subpastas). A lista mostra, por pasta, os arquivos que serão importados.

### Aba — Filtros *(opcional)*
Textos que, se aparecerem no nome do arquivo, fazem ele ser **ignorado**. Ex.: `U-2000` ignora tudo que contenha `U-2000`.

### Aba — Agendamento *(opcional)*
Marque para registrar uma tarefa no **Windows Task Scheduler** que roda o `.bat` sozinho no dia/horário escolhidos. **Requer Administrador** (ver seção 5).

Clique em **Gerar .bat** — o arquivo vai para `projetos/<nome>.bat`.

> 💡 O botão **Carregar .bat existente** reabre um `.bat` já gerado para edição.

---

## 4. Rodar o import

Rode o `.bat` gerado (em `projetos/`). Ele:

1. Varre as pastas em busca de `.ifc` (baixa do OneDrive se algum estiver só na nuvem);
2. **Copia os IFCs para `<projeto>/IFC_Source/<data>/`** — o import trabalha 100% local, sem usar a rede (a pasta antiga é limpa a cada execução);
3. Sobe o Unreal em modo headless e importa cada IFC via Datasmith;
4. Salva o projeto;
5. Se **Unir bodies** estiver ligado, roda o passo de merge (seção 6);
6. Mostra o progresso em tempo real e o tempo decorrido.

> ⚡ **Desempenho:** a geração de *lightmap UV* fica desligada por padrão (build ~2× mais rápido, sem impacto visual com iluminação dinâmica). O tempo depende principalmente do **build das malhas** — importar com o PC ocioso é bem mais rápido. Mantenha o **projeto fora do OneDrive** para não sofrer com a sincronização de milhares de assets.

---

## 5. Rodar como Administrador (só para agendar)

O agendamento usa o `schtasks` do Windows, que exige Administrador. Basta dar **duplo-clique em `Gerador-Admin.bat`** e aceitar o aviso (UAC) — o gerador abre já elevado. O título da janela mostra `[Administrador]` e a aba Agendamento indica o status.

O import em si **não** precisa de Administrador — só o registro da tarefa agendada.

---

## 6. Unir bodies (opcional)

O IFC traz cada elemento (válvula, tubo, caixa...) com vários *solids*, e o Datasmith cria um mesh por solid (`_body1`, `_body2`...), todos filhos de um ator-pai. Com **Unir bodies** ligado, cada elemento vira **uma malha só** (materiais viram seções), o que reduz muito a contagem de atores/draw calls.

- Roda automaticamente após o import quando a opção está marcada.
- **Precisa do editor completo** (o commandlet do import não tem o subsystem de merge), por isso é um passo à parte.
- Também pode ser rodado **manualmente** no editor já aberto: **Tools → Execute Python Script → `unir_bodies.py`** (sem custo de abrir o level, pois ele já está carregado).
- O elemento unido recebe o nome do elemento **sem a contagem** (ex.: `..._body1_8` → `..._body`).

---

## Opções avançadas (variáveis no `.bat`)

Dá para editar o `.bat` gerado e ajustar:

| Variável | Padrão | Efeito |
|---|---|---|
| `IFC_UNIR_BODIES` | `0` | `1` = une os bodies de cada elemento após importar |
| `IFC_LIGHTMAP_UV` | *(vazio)* | `1` = gera lightmap UV (necessário só para **assar** iluminação estática; mais lento) |
| `IFC_FILTROS` | *(vazio)* | textos separados por vírgula que excluem arquivos |

---

## Solução de problemas

**`module 'unreal' has no attribute 'DatasmithSceneElement'`**
Plugins Datasmith não carregaram. Ative **Datasmith Importer** e **Datasmith CAD Importer** e reinicie o editor. (Evite passar o `.uproject` por caminho curto 8.3 — o gerador já cuida disso.)

**Nenhum arquivo importado / `result.json` não gerado**
Abra o log em `<projeto>\Saved\Logs\` e procure por `[IFC]` para ver o erro de cada arquivo.

**Import muito lento**
Rode com o PC ocioso (o build das malhas é pesado), mantenha o **projeto fora do OneDrive** e deixe o `IFC_LIGHTMAP_UV` desligado.

**Agendamento falhou**
Abra com o `Gerador-Admin.bat` (Administrador) para o Task Scheduler aceitar o registro.

**Arquivos em nuvem não baixam**
O OneDrive precisa estar rodando e conectado no momento da execução.

**Unir bodies não faz nada / erro de subsystem**
O merge só roda no **editor completo** — pelo pipeline (`IFC_UNIR_BODIES=1`) ou manualmente via *Execute Python Script*. Não funciona no modo headless do import.
