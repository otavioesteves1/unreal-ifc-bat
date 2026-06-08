# Importador IFC para Unreal Engine — Modo Batch

Conjunto de scripts Python que automatiza a importação de arquivos `.ifc` para o Unreal Engine sem precisar abrir a interface gráfica do editor.

---

## Como funciona

```
gerador.py  →  gera um .bat de projeto
    ↓
.bat gerado  →  chama runner.py
    ↓
runner.py  →  varre as pastas de IFC e chama o Unreal headless
    ↓
import_headless.py  →  roda dentro do Unreal e importa via Datasmith
```

---

## Pré-requisitos

- **Unreal Engine 5.x** instalado
- **Python** instalado no Windows (comando `py` disponível no terminal)
- Plugins ativos no Unreal (ver seção abaixo)

---

## 1. Ativar os plugins no Unreal

Abra o projeto no Unreal Editor e vá em **Edit → Plugins**. Ative os três plugins abaixo e **reinicie o editor** quando solicitado.

| Plugin | Onde encontrar |
|---|---|
| **Python Script Plugin** | Scripting |
| **Datasmith Importer** | Importers |
| **Datasmith IFC Importer** | Importers |

> Após reiniciar, confirme em **Edit → Project Settings → Plugins → Python** que o campo **Additional Paths** aponta para a pasta dos scripts (opcional, mas recomendado).

---

## 2. Instalar os scripts

Baixe ou clone este repositório em qualquer pasta local (ex: `C:\ferramentas\unreal-ifc-bat`):

```
git clone https://github.com/otavioesteves1/unreal-ifc-bat.git
```

A pasta deve conter:
```
gerador.py
runner.py
import_headless.py
```

---

## 3. Gerar um .bat de projeto

Execute o gerador:

```
py gerador.py
```

Preencha as abas da interface:

### Aba — Projeto
| Campo | O que preencher |
|---|---|
| **Nome do batch** | Nome do arquivo `.bat` que será criado (ex: `REPAR_quinta`) |
| **UnrealEditor.exe** | Caminho completo do executável do Unreal |
| **Arquivo .uproject** | Caminho do `.uproject` do seu projeto |
| **Content base** | Pasta dentro do Content onde os IFCs serão importados (ex: `/Game/IFC`) |
| **Level principal** | Level do Unreal que será aberto durante o import |

### Aba — Pastas IFC
Adicione as pastas do Windows onde estão os arquivos `.ifc`. O script varre apenas a raiz de cada pasta (sem subpastas).

### Aba — Filtros *(opcional)*
Textos que, se encontrados no nome do arquivo, fazem ele ser ignorado.  
Exemplo: digitar `U-2000` ignora todos os arquivos que contenham `U-2000` no nome.

### Aba — Agendamento *(opcional)*
Marque a opção para registrar uma tarefa no **Windows Task Scheduler** que rodará o `.bat` automaticamente no dia e horário escolhidos. Requer executar o gerador como **Administrador**.

Clique em **Gerar .bat**. O arquivo é salvo em `projetos/<nome>.bat`.

---

## 4. Rodar o import

Execute o `.bat` gerado (em `projetos/`):

```
projetos\REPAR_quinta.bat
```

O script irá:
1. Varrer as pastas configuradas em busca de arquivos `.ifc`
2. Detectar arquivos que estão apenas na nuvem (OneDrive) e oferecer download automático
3. Iniciar o Unreal Engine em modo headless (sem interface)
4. Importar cada IFC via Datasmith para o Content do projeto
5. Salvar o projeto automaticamente

---

## Estrutura dos arquivos

| Arquivo | Função |
|---|---|
| `gerador.py` | Interface gráfica para criar os `.bat` de projeto |
| `runner.py` | Chamado pelo `.bat`, varre os IFCs e inicia o Unreal |
| `import_headless.py` | Roda dentro do Unreal e executa o import via Datasmith |

A pasta `projetos/` é criada automaticamente pelo gerador na primeira execução.

---

## Solução de problemas

**O Unreal não encontra o script Python**  
Verifique se o plugin **Python Script Plugin** está ativo e se o caminho dos scripts está correto no `.bat` gerado.

**Nenhum arquivo importado / `result.json` não gerado**  
Abra o log do Unreal em `<projeto>\Saved\Logs\` e procure por linhas com `[IFC]` para identificar o erro.

**Agendamento falhou**  
Execute o `gerador.py` como Administrador para que o Task Scheduler aceite o registro da tarefa.

**Arquivos em nuvem não baixam**  
O OneDrive precisa estar rodando e conectado à internet no momento da execução.
