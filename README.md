# RF Helper

Ferramentas para quem joga **RF Online em multiconta**, feitas em Python (só biblioteca padrão, sem instalar nada). A **tela inicial** (módulo *Home*) guarda os **servidores e as contas** (login, senha, personagens) e tem o botão **Play** para abrir o RF já com a conta; o **Modo grupo**, na faixa da direita, abre a janelinha que lista os clientes abertos do jogo (`RF_Online.bin`), sempre na frente, e, em cada linha, oferece:

- **Trocar de janela** com atalhos globais (módulo *Change Screen*);
- **Clicker por janela**: apertar teclas em intervalos fixos ou repetir uma **macro gravada**, sem precisar do foco do jogo (módulo *Clicker*);
- **Nome do personagem em cada linha**, descoberto sozinho pelo log do jogo, e o **perfil do clicker carregado automaticamente** para ele (módulo *Characters*).

> Este README descreve o que o programa faz **hoje**. Ele deve ser atualizado a cada mudança de comportamento, arquivo ou formato de dados.

## Requisitos

- Windows 10/11.
- Python 3.10+ (testado no 3.14). `tkinter` e `ctypes` já vêm com o Python.
- O programa **se reabre como administrador** (pede confirmação do UAC): o RF roda elevado e, sem isso, o Windows não entrega teclas ao programa com o jogo em foco nem permite enviar teclas ao jogo.

## Como executar

Na raiz do projeto (a pasta que contém `modules/`):

```
python -m modules.home            # tela inicial (servidores, contas, Modo grupo)
python -m modules.change_screen   # só a janelinha do Modo grupo, sem a tela inicial
```

`--no-admin` desativa a auto-elevação (só para testes).

## Estrutura

```
rf-helper/
├── README.md
├── modules/
│   ├── home/              tela inicial (Tk, tema escuro): servidores, contas, Play, Modo grupo
│   │   ├── __main__.py    ponto de entrada (`python -m modules.home`)
│   │   ├── app.py         janela principal (lista de servidores, cards das contas, faixa do Modo grupo)
│   │   ├── server_dialog.py   formulário de servidor
│   │   ├── account_dialog.py  formulário de conta (até 3 personagens, listas suspensas)
│   │   ├── play.py        fila de logins do botão Play (uma thread, sem Tk, testável)
│   │   ├── placement.py   leva a janela nova do RF para o canto superior esquerdo (sem Tk, testável)
│   │   ├── images.py      ícone do servidor (qualquer imagem → PNG 48 px em cache, via GDI+)
│   │   └── theme.py       cores e widgets do tema escuro (botões, lista suspensa, caixa de seleção, área rolável)
│   ├── accounts/          dados dos servidores e contas (sem Tk, testável)
│   │   ├── model.py       Server, Account, Character, raças e classes
│   │   ├── store.py       servers.json
│   │   ├── running.py     quais contas estão em jogo (PID aberto pelo Play + conta lida do log)
│   │   └── secrets.py     senhas cifradas com o DPAPI do Windows
│   ├── autologin/         login automático dirigindo o launcher do RF (sem Tk)
│   │   ├── launcher.py    o fluxo: abrir, digitar, LOGIN, escolher servidor, esperar o client (testável com launcher falso)
│   │   ├── winapi.py      processos e janelas do launcher, mensagens (ctypes)
│   │   └── __init__.py    LoginError / Cancelled
│   ├── shared/            usado por mais de um módulo
│   │   ├── branding.py    ícone do RF Helper nas janelas e na barra de tarefas
│   │   ├── logo_data.py   o logo embutido em base64 (6 tamanhos): não há imagem solta no repositório
│   │   └── screens.py     monitores e regras de posição (a janela cabe nas telas? puxar para dentro; centralizar), sem Tk
│   ├── change_screen/     janelinha do Modo grupo: lista de clientes, atalhos de troca, botões do clicker
│   │   ├── __main__.py    ponto de entrada
│   │   ├── app.py         interface (Tk), lógica das ações, auto-elevação
│   │   ├── hotkeys.py     atalhos globais (hooks de teclado e mouse)
│   │   ├── winapi.py      chamadas Win32 (ctypes)
│   │   └── config.py      config.json (atalhos, ON/OFF, posições das janelas)
│   ├── characters/        personagem de cada client, lido do log do jogo (não depende dos outros)
│   │   ├── rflog.py       leitura do rfclient.log e ligação processo ↔ personagem (sem Tk, testável)
│   │   ├── watcher.py     thread que mantém os nomes (e as contas) atualizados
│   │   └── winapi.py      caminho do .exe e hora de criação de um processo
│   └── clicker/           clicker e macro (não depende do change_screen)
│       ├── model.py       dados: ClickerConfig, KeyRow, Macro (sem Tk nem Win32)
│       ├── runner.py      execução numa thread por janela
│       ├── sender.py      envio de uma tecla à janela
│       ├── recorder.py    gravação de teclas (hook global, só enquanto grava)
│       ├── manager.py     sessão por janela, estado do ícone, eventos para a UI
│       ├── profiles.py    perfis salvos (profiles.json)
│       ├── config_window.py  janela "RF Clicker"
│       ├── macro_window.py   janela da macro
│       ├── icons.py       ícones de estado, desenhados por código
│       ├── windowing.py   detalhes das telas: sem botão X, posição lembrada, sempre dentro dos monitores
│       ├── keys.py        códigos de tecla e rótulos
│       └── winapi.py      chamadas Win32 do clicker
└── tests/                 testes automáticos (unittest)
```

---

# Módulo Home (tela inicial)

`python -m modules.home`. Três áreas: **servidores** à esquerda, **contas** no meio e, na faixa da direita, o ícone **Modo grupo**, que abre a janelinha do módulo Change Screen (troca de janelas + clicker) como uma janela da mesma aplicação. Só abre uma; fechar a janelinha não fecha a tela inicial, mas fechar a tela inicial fecha tudo.

## Posição das janelas (vale para todo o programa)

- A **tela inicial sempre abre no meio** do monitor principal (a posição dela não é lembrada).
- **Todas as outras janelas lembram onde foram deixadas**, mesmo depois de fechar o programa: o Modo grupo, as telas de atalhos, do clicker e da macro e os formulários de servidor e de conta.
- **Nenhuma janela fica escondida fora das telas.** Dá para **arrastar de um monitor para o outro** (a janela pode ficar atravessando os dois no caminho), mas ao soltar, se ela não couber nos monitores, **volta sozinha** para dentro do monitor mais próximo depois de ficar parada um instante (400 ms, e só com o mouse solto). Ao abrir, uma posição salva que caia fora das telas (monitor desligado, resolução trocada) é puxada para dentro, e **uma posição fora das telas nunca é gravada**: o que vai para o `config.json` já é a posição corrigida. Uma janela encostada na borda não conta como "fora" (a sombra invisível da moldura é descontada) e uma janela maior que o monitor fica com a barra de título visível.

### Janela do RF no canto superior esquerdo

Toda janela do **RF Online** que **aparece depois** do RF Helper abrir (pelo Play ou aberta à mão) é levada para o **canto superior esquerdo do monitor principal** (respeitando a barra de tarefas, se ela estiver em cima ou à esquerda). Regras:

- Só muda a **posição**: o tamanho, a ordem das janelas e o foco continuam como estavam. Uma janela que já está no canto (o jogo nasce em `-1, 0`) não é tocada.
- O jogo cria e reposiciona a janela nos primeiros segundos, então a posição é conferida a cada 0,5 s por **8 s** depois que ela aparece. Passado isso, a janela é do usuário: pode arrastar para onde quiser (inclusive para o outro monitor) e ela não volta.
- As janelas que **já estavam abertas** quando o RF Helper iniciou não são mexidas, e janela minimizada também não.
- Só vale com o RF Helper aberto (a tela inicial faz a conferência). Para desligar não há opção ainda: é uma linha em `HomeApp.__init__` (`self.placer`).

## Servidores

- **+** (no topo da lista) abre o formulário: **nome**, **caminho do launcher** e **ícone** (opcional: png, jpg, ico, bmp, gif; é convertido para um PNG de 48 px em `%APPDATA%\ChangeScreenRF\icons`). Sem ícone, o servidor mostra a inicial do nome.
- O arquivo a informar é o **launcher** (`RF_BrasilRPG.exe` no RF Brasil), **não** o `RF_Online.bin`: o client não recebe login por linha de comando, é o launcher que autentica e entrega os dados a ele (por isso o log do client começa com `GetDataFromLauncher`). O formulário só diz "launcher" (o seletor de arquivo já filtra `.exe`) e avisa (sem bloquear) se o arquivo não existe ou se não há `RF_Online.bin` na mesma pasta.
- Ao salvar, o servidor é selecionado e o meio abre vazio, com **Adicionar conta**. **Editar** e **Excluir** (com confirmação; só apaga os dados do RF Helper, nunca o jogo) ficam ao lado do nome no cabeçalho. O servidor selecionado é lembrado.

## Contas

- **Adicionar conta**: **login** e **senha** (obrigatórios, **até 12 letras cada**: é o limite do launcher do RF; a senha vem mascarada e o botão de olho a revela), **até 3 personagens** (o RF tem 3 slots por conta) e **descrição** opcional. O formulário é compacto: uma linha por personagem, com **nome**, **raça** e **classe** em listas suspensas, nessa ordem (raça: Bellato = rosa, Cora = roxo, Accretia = branco). Um personagem começado precisa ficar completo; a linha deixada totalmente em branco é ignorada. O botão "+ Adicionar" some no terceiro. Sem e-mail e sem tag, por enquanto.
- Cada conta vira um **card de tamanho fixo**: o card sempre reserva as 3 vagas de personagem (e uma linha de descrição, cortada com "…" se for comprida), então fica igual com 0, 1, 2 ou 3 personagens. Mostra a caixa de seleção, o login, os personagens (cor da raça, nome e "Raça · Classe"), a senha mascarada com olho, o menu **⋮** (editar/excluir) e o botão de ação. As colunas se ajustam à largura da janela (1 a 3).
- **Reordenar**: arraste um card por qualquer parte dele (menos botões e a caixa de seleção) e solte sobre outro: ele ocupa o lugar do alvo. A ordem é **gravada** no `servers.json` e é a que vale para iniciar em lote.
- **Play** (botão do card) abre um launcher novo, entra com a conta e deixa o RF aberto na seleção de personagem (cerca de 35 s no total, já contando o launcher fechar). Precisa do programa **como administrador** (o launcher roda elevado; sem isso o Windows bloqueia o envio das mensagens) e do `RF_Online.bin` na mesma pasta do launcher. O botão vira **Cancelar** (entrando) ou **Sair da fila** (esperando), e o card mostra a etapa atual; erros aparecem no card e na barra de avisos, sem a senha. Se a janela for fechada com um login em andamento, o programa pergunta antes.
- **Iniciar várias contas**: marque as caixinhas (ou **Selecionar todas / Desmarcar todas**, que alterna) e clique em **Iniciar selecionadas (N)**. Entram na **fila na ordem em que os cards aparecem** (se a tela mostra rf02, rf01, rf04 e você marca as três, abrem nessa ordem). A fila é **serializada**: a próxima conta só loga **depois que o launcher da anterior fecha**. Falha numa conta não para as outras. **Cancelar fila** (aparece enquanto há fila) cancela tudo. Contas já em jogo são puladas, com aviso.
- **Conta em jogo = "❚❚ Pause" vermelho**: enquanto existir um client daquela conta, o botão vira **Pause** (e o card diz "Em jogo"). Isso evita logar de novo, o que **derruba o client anterior** (o servidor só aceita uma sessão por conta). Clicar em Pause **pede confirmação** e **encerra o processo** daquela conta (o personagem é desconectado); o botão volta a **Play** quando o processo some. A conta de cada client vem de duas fontes: o PID que o próprio Play abriu e o `SetAccountID` do `rfclient.log`, que também reconhece clients abertos por fora (launcher aberto à mão). Limitação herdada do módulo Characters: dois clients abertos fora do helper com menos de 2 s de diferença podem ficar sem conta no log; os Plays do helper não sofrem com isso (abrem um por vez e o PID é ligado direto).

## Como o login automático funciona

O login **dirige o próprio launcher** (`modules/autologin/launcher.py`); não toca no jogo nem no protocolo. Validado à mão com o launcher do RF Brasil (`RF_BrasilRPG.exe`):

1. Abre o launcher com a pasta dele como diretório de trabalho e espera a tela de login (pode demorar se ele estiver baixando um patch).
2. **Digita o ID e a senha** nos dois campos `Edit` reais do diálogo de login, enviando `WM_CHAR` (como o teclado), **sem foco e sem mexer no mouse**. Antes, seleciona tudo (`EM_SETSEL`) e apaga; depois **lê o texto do campo de ID de volta** (`WM_GETTEXT`) e só segue se for exatamente o login pedido, e se continuar assim depois de uma pausa. `WM_SETTEXT` **não serve**: o launcher não enxerga o texto posto assim ("Please input the password or ID").
3. Clica **LOGIN** com `BM_CLICK` por **`PostMessage`**: um `SendMessage` bloquearia, porque o launcher abre mensagens modais *dentro* do tratador do clique.
4. Espera a **lista de servidores**: um diálogo filho de 330×540 que fica visível (cerca de 2 s depois do LOGIN). Se aparecer uma mensagem com texto, ela vira o erro ("Wrong Account input." → "Login ou senha incorretos.") e o launcher que o programa abriu é fechado.
5. Clica na primeira linha da lista (`WM_LBUTTONDOWN/UP` no diálogo da lista, em (60, 24)): um clique simples bastou. Se o client não nascer em 15 s, tenta o duplo clique.
6. Espera surgir um **novo `RF_Online.bin`** (diferença entre os PIDs de antes e depois) e então **espera o launcher que abriu fechar** (uns 10 s; cancelar nessa fase só para de esperar, o client já abriu). Só depois devolve o PID: é isso que serializa a fila em lote.

Como foi descoberto: o launcher guarda ID, IP e uma chave de sessão (`KEY_NUM`) obtidos do servidor de login e os entrega ao client por dentro (o client é iniciado só como `.\RF_Online.bin`, sem argumentos, e o `.bin` é empacotado). Dispensar o launcher exigiria reproduzir o protocolo de login e esse repasse; foi descartado por ser frágil e arriscado (Fireguard).

Armadilhas encontradas com o launcher real (todas tratadas no código):

- O launcher **preenche sozinho o último ID salvo** ("ID SAVE") alguns instantes depois de abrir, e isso pode **sobrescrever o que o programa digitou**. Num teste real isso abriu a conta `conta01` quando se pediu a `conta02`: os dois IDs tinham o mesmo número de letras, então conferir só o **tamanho** do campo não pegou. Agora o que vale é o **texto**: relido duas vezes, com pausa, antes de clicar em LOGIN; se não bater, digita de novo (até 4 vezes) e, no fim, desiste com erro sem nunca clicar em LOGIN com o ID errado. Como rede de segurança extra, depois do login o programa compara a conta ligada ao PID com a que o log do client mostra e **avisa** se forem diferentes.
- A janelinha "conectando" (sem texto) aparece e some durante a abertura e depois do LOGIN: só mensagens **com texto** contam como aviso.
- ID e senha com mais de 12 letras são recusados pelo próprio launcher.
- O launcher não é DPI-aware: a thread do login pede "DPI não consciente" para as medidas (330×540 etc.) valerem em qualquer escala do Windows.
- Só o **primeiro servidor** da lista é suportado (`server_index` diferente de 0 vira erro): a altura das linhas da lista não foi medida.
- O texto de um campo de **senha** não pode ser lido de volta de outro processo; só o ID é conferido (o launcher não preenche senha sozinho).

## TODO

- **Classes por raça**: hoje só existem os papéis Tanker, DPS e Suporte (`CLASSES` em `modules/accounts/model.py`). Trocar por todas as classes do jogo, separadas por raça, e o formulário de conta passa a filtrar pela raça escolhida.
- E-mail e tag da conta; mais formatos/tamanhos de ícone; redesenho visual.
- Escolha de outro servidor da lista do launcher (`server_index` já é guardado, mas só o 0 funciona: falta medir a altura das linhas da lista).
- Reordenar também os servidores; arrastar vários cards de uma vez; mostrar a posição na fila ("Na fila (2º)").
- Um `.ico` do logo para um futuro executável (hoje o ícone vem do base64 embutido em `modules/shared/logo_data.py`).
- Outros servidores/launchers de RF: as medidas estão em `modules/autologin/winapi.py` (diálogo da lista, botão LOGIN, clique no servidor) e foram validadas só no RF Brasil.

---

# Módulo Change Screen

Seletor de janelas para multiconta. Lista todos os clientes abertos numa janelinha sempre na frente e permite alternar entre eles com **atalhos globais** (teclado ou botões do mouse), sem Alt+Tab nem clicar na barra de tarefas.

## O que ele faz

- **Detecta automaticamente** toda janela do processo `RF_Online.bin`: ao abrir um cliente, ele entra na lista; ao fechar, sai.
- **Lista organizável**: arraste para cima/baixo para definir a ordem; **1 clique** no nome vai direto para a janela (na hora, sem esperar).
- **O nome da linha é o personagem em jogo**, descoberto sozinho (veja o módulo *Characters*). Não há renomear à mão: se o client trocar de personagem, o nome acompanha. Enquanto não se sabe o personagem (login, seleção de personagem, log não encontrado) a linha mostra **RF 1**, **RF 2**…
- **Cada linha tem o clicker**: um **ícone de estado** à esquerda do nome (liga/desliga) e uma **engrenagem (⚙)** à direita (configura). Veja o módulo Clicker.
- **Sempre na frente** de todas as outras janelas (não só do RF). Minimizou? Vai para a barra de tarefas; ao restaurar, volta a ficar na frente.
- **Três ações com atalhos globais** que você cadastra uma vez (ficam salvos):
  1. **Próxima janela** da lista (circular: depois da última vem a primeira).
  2. **Janela anterior** da lista (circular).
  3. **Última usada**: volta para a janela de onde você veio. Ex.: foi da 1 para a 3 → aperta, volta à 1 → aperta de novo, volta à 3.
- **Botão ON/OFF** (verde/vermelho) para desligar os atalhos sem fechar o programa. Isso vale só para os atalhos de troca; os clickers não são afetados.
- **Janela compacta**; os atalhos são configurados na **engrenagem do topo (⚙)**.

## Como usar

1. Abra os clientes do RF e depois o programa (a ordem não importa; clientes abertos depois entram sozinhos).
2. Arraste as janelas na lista até ficarem na ordem que você quer.
3. Um clique no nome vai para a janela. Os nomes aparecem sozinhos assim que cada client entra no jogo.
4. Clique na **engrenagem do topo (⚙)**, depois em **Cadastrar** na ação desejada e aperte a tecla, a combinação (ex.: `Ctrl+Q`), um modificador sozinho (**Alt Gr**, Ctrl, Shift) ou um botão do mouse (lateral 1/2 ou meio). **Esc** cancela.
5. Clique em **OK** para fechar a tela de atalhos (o que você cadastrou já está salvo). Pronto: com o RF em foco, os atalhos trocam de janela, e ficam salvos para a próxima vez.

## O que cada controle faz

| Controle | Função |
|---|---|
| **ATALHOS: ON** — verde | Atalhos funcionando. Clique para desligar. |
| **ATALHOS: OFF** — vermelho | Atalhos ignorados: as teclas/botões **voltam ao normal** para o sistema e o RF **não é trazido para a frente**. Clique para ligar de novo. O estado é lembrado. |
| **⚙ do topo** | Abre a configuração dos atalhos de troca e a opção **Carregar o perfil do personagem automaticamente** (veja o módulo Clicker). Fecha pelo botão **OK** (a janela não tem o X) e reabre onde você a deixou. |
| **Nome na lista** | 1 clique = vai para a janela na hora (restaura se minimizada). Arrastar = reordenar. Duplo clique conta como um só. Só a janela em uso fica destacada (azul). |
| **Ícone de estado** (esquerda do nome) | Liga/desliga o clicker daquela janela. Não troca de janela nem inicia arraste; duplo clique nele alterna uma vez só. |
| **⚙ da linha** (direita do nome) | Leva o RF daquela linha para a frente (como se você tivesse clicado no nome) e abre a janela **RF Clicker** dela. A janela do clicker fica sempre por cima. |
| **Cadastrar** (Próxima / Anterior / Última usada) | Modo de captura: o próximo atalho que você apertar é registrado. Se o mesmo atalho já estava em outra ação, ele é removido de lá. |
| **Limpar** | Remove o atalho daquela ação. |

Observações:
- Os atalhos cadastrados são **consumidos** pelo programa quando em ON (o jogo não recebe aquela tecla). Escolha teclas que você não usa no jogo (ex.: F9–F12, botões laterais do mouse).
- Os botões esquerdo e direito do mouse **não** podem ser cadastrados. Alt Gr/Ctrl/Shift sozinhos podem; nesse caso o atalho dispara ao apertar a tecla e ela não chega ao jogo.
- A ordem da lista e as configurações do clicker valem enquanto o programa está aberto (o RF cria janelas novas a cada abertura; os nomes dos personagens são relidos do log). Só os atalhos, o ON/OFF, a opção do perfil automático e a posição da janela são salvos automaticamente; o clicker usa **perfis** (veja abaixo).
- Se o RF estiver em **tela cheia exclusiva**, nenhuma janela consegue ficar por cima dele; use modo janela/borderless.

---

# Módulo Characters

Descobre **qual personagem está em jogo em cada client** e dá esse nome à linha da lista. Não toca no processo do jogo: só **lê o arquivo de log que o próprio RF grava** (`NetLog\rfclient.log`, dentro da pasta de instalação do client).

## O que ele faz

- Cada linha mostra o personagem em jogo (ex.: `Guerreiro`, `Mago`, `Arqueiro`).
- **Troca de personagem**: se você volta à seleção e entra com outro personagem (ex.: de `Guerreiro` para `iGuerreiro`), o nome muda sozinho quando o novo personagem **entra no mapa**.
- **Na seleção de personagem** o client não tem personagem: a linha volta a mostrar `RF n`, e o clicker daquela janela é **parado** (teclas na seleção não fazem sentido).
- A atualização leva até cerca de 2 s depois do evento no jogo.

## Como ele sabe (o que o log tem)

O log é **um só para todos os clients** da mesma instalação, e as linhas não dizem de qual processo vêm. Cada linha é `[n] MM/DD/AA HH:MM:SS: mensagem`, e o contador `n` cresce de 1 em 1 dentro de cada client (com vários clients escrevendo juntos o jogo às vezes perde uma linha, ex.: `[783] [784] [786]`; no log real o salto nunca passou de 2). As linhas que importam:

| Linha | Significa |
|---|---|
| `[1] … GetDataFromLauncher` | Um client novo abriu. Ele começa um "fluxo" de linhas. |
| `SetAccountID conta01 …` | A conta daquele client. |
| `101 ) base result ( 0 - Guerreiro )` | O personagem **entrou no mapa**. |
| `118 ) load map ( .\map\lobby\lobby.BSP )` | O client voltou à **seleção de personagem**. |

Para ligar linha ↔ janela:
1. **Processo ↔ fluxo**: cada processo vivo é ligado ao fluxo cuja linha `[1]` tem a **mesma hora da criação do processo** (diferença de 1 a 2 s na prática).
2. **Linha ↔ fluxo**: uma linha `[n]` pertence ao fluxo cujo contador está logo antes de `n` (o menor salto, aceitando até `MAX_GAP` = 3 linhas perdidas). Se dois fluxos esperam o mesmo número, vale o que escreveu por último.

**Todos** os fluxos entram na conta, inclusive os de clients já fechados: um client fechado continua dono das suas próprias linhas, e é isso que impede que elas sejam confundidas com as de um client vivo.

## Limitações

- **Clients abertos com poucos segundos de diferença** escrevem os mesmos números de linha ao mesmo tempo, e não dá para saber de quem é cada linha. Nesse caso o programa **prefere não mostrar nome** (fica `RF n`) a mostrar o de outro client; o nome correto aparece na próxima entrada em mapa sem ambiguidade (ex.: trocar de personagem ou de mapa).
- Depende do **formato do log desse servidor** (RF Brasil, conferido na pasta `C:\RFBrasil`). Outro servidor/versão pode escrever de outro jeito.
- O log tem de estar na pasta do `.exe` do client (`<pasta do RF_Online.bin>\NetLog\rfclient.log`). Se não existir, as linhas ficam como `RF n`.
- O nome só aparece **depois de entrar no jogo**: no login e na seleção não há personagem.
- O log só cresce. A primeira leitura começa **7 dias antes** da abertura do client mais antigo (busca binária no arquivo; o log real, de 2 MB e 4 dias, é lido inteiro em ~0,5 s); depois lê só o que foi acrescentado. Um client fechado há mais de 7 dias antes do mais antigo vivo não é conhecido, mas também não escreve mais nada.

---

# Módulo Clicker

Cada janela do RF tem seu próprio clicker. Ele envia teclas **direto para a janela do jogo, sem precisar do foco** (a mesma técnica do RFClicker original: mensagens de teclado do Windows ao HWND da janela). Você escolhe, por janela, entre dois modos:

- **Click**: uma ou mais teclas, cada uma com seu intervalo em ms.
- **Macro**: uma sequência gravada de teclas e tempos, com ou sem loop.

## O ícone de estado

O ícone fica à esquerda do nome, na lista. O **desenho** mostra o modo e a **cor** mostra o estado:

| Cor | Significa |
|---|---|
| **Cinza** | Não configurado (sem tecla no modo Click, ou macro vazia). Fica inativo: clicar avisa "Configure o clicker (⚙) antes de ligar". |
| **Vermelho** | Configurado e **parado**. Clique para ligar. |
| **Verde** | **Rodando**. Clique para parar. |

Desenho de **tecla** = modo Click; **círculo com play** = modo Macro. Se a macro rodar sem loop, ao chegar ao fim o ícone volta sozinho a vermelho.

## Janela RF Clicker (⚙ da linha)

Abre já ligada àquela janela do RF (o título mostra nome e PID). Só uma por janela: clicar de novo no ⚙ traz a que já está aberta.

**Fechar**: pelo botão **OK** no canto inferior direito. As telas do clicker e da macro **não têm o botão X** (a barra de título fica só para mostrar "RF Clicker — personagem [PID]" e para arrastar), porque tudo é salvo na hora: o OK só deixa claro que está pronto. A posição de cada tela (clicker e macro) é lembrada, mesmo depois de fechar o programa, e ela nunca fica fora das telas (veja "Posição das janelas"). O **OK** da tela do clicker fecha também a tela da macro; o **OK** da macro fecha só a macro.

- **Perfil**: lista de perfis salvos, com **Salvar**, **Salvar como…** e **Excluir**. Escolher um perfil carrega a configuração inteira (modo, teclas e macro) nesta janela, substituindo a atual. O último perfil carregado ou salvo **continua selecionado** quando você reabre a tela (enquanto o RF dessa linha estiver aberto), então **Salvar** atualiza aquele perfil. Veja "Perfis" abaixo.
- **Click | Macro**: escolhe o modo desta janela. A configuração do outro modo é preservada ao alternar; só o modo escolhido roda e define o ícone.

### Modo Click

Cada linha é `[tecla] [ms] [Clear]`, e o botão **+** abaixo acrescenta mais linhas (sem limite; a lista ganha rolagem quando cresce).

- **Tecla**: clique no campo e aperte a tecla (mostra "Aperte…"). **Esc** cancela. Só **tecla única**: Ctrl/Alt/Shift sozinhos são ignorados e combinações não são suportadas.
- **ms**: intervalo entre os cliques daquela tecla (padrão 100, mínimo 10).
- **Clear**: limpa a tecla da linha; nas linhas além da primeira, remove a linha.
- Cada tecla corre com **seu próprio intervalo, de forma independente**; todas disparam uma vez assim que o clicker é ligado.

### Modo Macro

O botão **Macro…** abre a janela da macro e ao lado aparece o resumo (nº de teclas, duração, loop).

## Janela da Macro

Barra: **Record**, **Clear** e a caixa **Loop** (já marcada).

**Gravar**
1. **Record** vira **Stop** e a gravação começa. As teclas são capturadas **de qualquer janela** (você grava dentro do jogo), com o tempo exato entre elas.
2. Cada tecla gera uma linha **Tecla** e, entre elas, uma linha **Tempo** (ms). A primeira tecla de cada gravação não ganha Tempo à frente (para não guardar o seu tempo de reação).
3. **Stop** encerra e acrescenta um Tempo final de **1000 ms** (a pausa antes de recomeçar no loop), editável.
4. Gravar de novo **continua o histórico**: as novas teclas entram no final. Arraste-as para o meio e ajuste os tempos como quiser.
5. Teclas modificadoras (Ctrl, Alt, Shift, Win) não são gravadas.

**Editar** (depois de parar; durante a gravação a lista fica travada)
| Ação | Como |
|---|---|
| Selecionar vários | Ctrl+clique ou Shift+clique |
| Mudar tempo | Selecione uma ou mais linhas de **Tempo** e aperte **F2**. Digite o valor em ms; **Enter** ou clicar fora aplica o valor a **todas** as linhas de Tempo selecionadas; **Esc** cancela. Teclas selecionadas junto são ignoradas. |
| Mudar o tempo de uma linha | **Duplo clique** na linha de Tempo (o mesmo que F2, só nela). Duplo clique numa linha de Tecla não faz nada; com Ctrl/Shift é só seleção. |
| Reordenar | Arraste uma linha (uma por vez) |
| Remover | Selecione e aperte **Delete** |
| Apagar tudo | **Clear** (pede confirmação) |

As linhas de **Tecla** não são editáveis (só arrastar ou remover); as de **Tempo** só mudam de valor.

**Loop**: marcado, a macro percorre até a última linha e volta ao início, sem parar. Desmarcado, roda até o fim uma vez e para (o ícone volta a vermelho).

## Perfis

Um perfil guarda a configuração completa de uma janela (modo, teclas e macro). Como o HWND/PID do RF muda a cada abertura do jogo, a configuração não fica presa a uma janela: você a **salva num perfil** e a **carrega** na janela que quiser, em qualquer sessão.

- **Salvar**: grava no perfil selecionado (se nenhum, pede um nome). **Salvar como…**: pede o nome. Nos dois casos, se já existir um perfil com esse nome (inclusive o selecionado), o programa **pergunta antes de substituir**. **Excluir**: apaga o perfil selecionado (também pergunta).
- O perfil selecionado é lembrado por janela do RF: ao carregar, salvar ou ser carregado automaticamente, ele fica selecionado ao reabrir a tela. Se o perfil for excluído, a seleção some.
- Se você **editar** depois de carregar um perfil, a mudança vale só para a janela até você salvar de novo.
- Nomes: até 40 caracteres, espaços extras são removidos.

### Perfil automático por personagem

Na **⚙ do topo** (configuração do Change Screen) há a opção **Carregar o perfil do personagem automaticamente** (desligada por padrão, e lembrada).

- Ligada, quando um personagem **entra no jogo** numa janela, o programa procura um perfil com **o mesmo nome do personagem** (sem diferenciar maiúsculas) e o carrega naquela janela. Ex.: o perfil `Guerreiro` é carregado quando `Guerreiro` entra.
- Se não houver perfil com esse nome, a configuração atual da janela **não muda**.
- O clicker **nunca liga sozinho**: depois de carregar, o ícone fica vermelho e você liga quando quiser.
- Vale na **próxima** entrada de personagem. Ligar a opção não recarrega janelas que já estão em jogo.
- Para criar o perfil de um personagem: configure o clicker daquela janela e use **Salvar como…** com o nome exato do personagem.
- Se a janela de configuração estiver aberta, ela é atualizada na hora (e a janela da macro fecha).

## Quando o clicker para sozinho

- A janela do RF foi fechada.
- O Windows negou o acesso à janela (o RF está elevado e o programa não): aparece "abra o programa como administrador".
- A janela parou de responder 5 envios seguidos.
- A macro sem loop chegou ao fim.
- O client voltou à **seleção de personagem** (aparece "Clicker parado: o client voltou à seleção de personagem").
- Editar a configuração com o clicker **verde** o reinicia já com a nova configuração; se a configuração ficar vazia, ele para e o ícone vai a cinza.

## Limitações (herdadas do RFClicker original)

- **Só tecla única.** Combinações (Ctrl+1) não são suportadas.
- O RFClicker original rotulava o campo como "Key (**Non Movement**)": teclas de **movimento provavelmente não funcionam** por esse método.
- A técnica foi replicada e testada contra janelas de teste, **mas ainda não foi validada no jogo real**.
- Muitos servidores de RF **proíbem macros/automação**. Confira as regras do seu servidor antes de usar ou distribuir: contas podem ser punidas.

---

## Onde ficam os dados

Pasta `%APPDATA%\ChangeScreenRF\`:

**`config.json`** (Change Screen):

```json
{
  "enabled": true,
  "auto_profile": false,
  "hotkeys": {
    "next": {"type": "key", "vk": 120, "ctrl": false, "alt": false, "shift": false, "label": "F9"},
    "prev": {"type": "mouse", "button": "x1", "ctrl": false, "alt": false, "shift": false, "label": "Mouse lateral 1 (X1)"},
    "last": null
  },
  "position": "+100+100",
  "windows": {"settings": "+520+310", "clicker": "+330+210", "macro": "+470+260", "server_dialog": "+300+200", "account_dialog": "+300+200"}
}
```

**`servers.json`** (Home): servidores, contas e personagens. **As senhas vão cifradas** com o DPAPI do Windows (`"password": "dpapi:..."`), nunca em texto puro; só o mesmo usuário do Windows, no mesmo computador, consegue abri-las. Copiar o arquivo para outro PC/usuário mantém tudo menos as senhas (o card avisa "ilegível: edite a conta"; o texto cifrado antigo é preservado no arquivo até a senha ser digitada de novo). Ícones convertidos ficam em `icons\<id do servidor>.png`.

```json
{
  "version": 1,
  "last_server": "3f9c1a2b7d10",
  "servers": [
    {
      "id": "3f9c1a2b7d10", "name": "RF Brasil", "launcher_path": "C:\\RFBrasil\\RF_BrasilRPG.exe",
      "icon_path": "C:\\Imagens\\rf.png", "server_index": 0,
      "accounts": [
        {"id": "a1b2c3d4e5f6", "login": "conta01", "password": "dpapi:AQAAANCM...", "description": "principal",
         "characters": [{"name": "Guerreiro", "race": "accretia", "class": "DPS"}]}
      ]
    }
  ]
}
```

**`profiles.json`** (Clicker):

```json
{
  "version": 1,
  "profiles": {
    "Farm": {
      "mode": "macro",
      "keys": [{"vk": 88, "label": "X", "ms": 100}],
      "macro": {
        "loop": true,
        "events": [
          {"kind": "key", "value": 65, "label": "A"},
          {"kind": "delay", "value": 250, "label": ""}
        ]
      }
    }
  }
}
```

`vk` é o código de tecla virtual do Windows; em `events`, `value` é o `vk` (kind `key`) ou os milissegundos (kind `delay`). Apagar um arquivo restaura os padrões; arquivo ausente ou corrompido é tolerado (entradas inválidas são descartadas).

## Solução de problemas

- **Play diz "Abra o RF Helper como administrador"**: o launcher roda elevado e o Windows bloqueia mensagens de um programa comum. Abra com `python -m modules.home` e aceite o UAC (sem `--no-admin`).
- **O card mostra "Pause" mas não abri essa conta**: há um client vivo cujo log diz que é dessa conta (aberto por fora ou de uma sessão anterior). Pause o encerra; se for outro login que não deveria estar aberto, confira o `SetAccountID` no `NetLog\rfclient.log`.
- **Aviso "o Play abriu a conta X"**: o launcher entrou com outro ID (o ID salvo). O programa já confere o campo antes do LOGIN, então isso só deve acontecer se o launcher mudar o campo depois; feche aquele client com Pause e tente de novo.
- **Play diz "Login ou senha incorretos"**: confira a conta (editar → senha). Lembre que o launcher só aceita até 12 letras.
- **Play diz que o jogo não abriu / o launcher não respondeu**: o launcher pode estar baixando um patch, o servidor pode estar fora do ar, ou a conta já está em jogo. Abra o launcher à mão uma vez e veja a mensagem dele.
- **O card mostra "ilegível: edite a conta"**: a senha foi gravada por outro usuário/PC do Windows (o DPAPI não abre). Edite a conta e digite a senha de novo.
- **Atalhos funcionam uma vez e depois "param" com o RF em foco**: isolamento UIPI do Windows (RF elevado × programa comum). O programa se reabre como administrador sozinho; aceite o UAC.
- **Uma janela do RF não aparece na lista**: só entram janelas visíveis, com título, do processo `RF_Online.bin`. Se o executável tiver outro nome, altere `PROCESS_NAME` em `modules/change_screen/app.py`.
- **Atalho não responde**: confira se está em ON (verde) e se o atalho aparece cadastrado.
- **A linha mostra `RF 1` em vez do personagem**: o client ainda não entrou no jogo (login/seleção), o log `NetLog\rfclient.log` não está na pasta do `.exe`, o client foi aberto junto de outro com poucos segundos de diferença (veja Limitações do módulo Characters) ou o servidor usa outro formato de log. Entrar com o personagem (ou trocar de mapa) costuma resolver.
- **O perfil automático não carregou**: confira se a opção está ligada na ⚙ do topo e se o perfil tem **exatamente o nome do personagem**.
- **O ícone do clicker não liga (continua cinza)**: falta configurar. Abra o ⚙ da linha e cadastre uma tecla (modo Click) ou grave uma macro (modo Macro).
- **O clicker liga mas o jogo não reage**: confirme que o programa está como administrador; teclas de movimento podem não funcionar por esse método (veja Limitações).
- **A gravação da macro não captura nada**: o programa precisa estar como administrador para enxergar as teclas com o RF em foco.

---

## Para desenvolvedores / agentes

### Fluxo de eventos (atalhos de troca)

```
tecla/botão do mouse
  → hook LL (thread de hooks, hotkeys.py::_handle)
      · injetado/modificador → repassa
      · modo captura → consome, põe ("capture", binding|None) na queue
      · enabled=False → repassa (CallNextHookEx)
      · bate com binding → consome, põe ("action", nome) na queue
  → App._poll_events (thread do Tk, a cada 10 ms) lê a queue
  → App._do_action → App._goto → winapi.activate
```

A thread dos hooks **nunca toca no Tk nem ativa janelas**; só enfileira. O `down` consumido é registrado em `_swallowed` para consumir também o `up` e o auto-repeat.

### Fluxo do clicker

```
clique no ícone da linha / ⚙ da linha            (App._on_press/_on_release → _button_at)
  → ClickerManager.toggle / open_config           (thread do Tk)
      → Runner(hwnd, cópia da config).start()      thread própria, por janela
          modo click: heap de "próximo disparo" por tecla, prazos absolutos
          modo macro: percorre as linhas; Tempo = Event.wait, Tecla = send_key
          cada tecla: sender.send_key → SendMessageTimeoutW × 4
              WM_ACTIVATE(1) → WM_KEYDOWN(vk) → WM_KEYUP(vk) → WM_NCACTIVATE(0)
      ← ao terminar (fim, janela fechou, erro): on_exit → queue
  → App._poll_events chama ClickerManager.poll() → on_change(hwnd) → App._refresh_row (troca o ícone)
```

A thread do Runner **nunca toca no Tk**: só enfileira o motivo do término. O runner recebe uma **cópia** da configuração; editar a config não altera uma execução em curso (o manager reinicia o runner com a nova cópia).

### Fluxo do nome do personagem

```
App._poll_windows (1 s)  → CharacterWatcher.set_pids(pids das linhas)       (acorda a thread se mudou)
  CharacterWatcher (thread, a cada 2 s)
    → winapi.process_info(pid)          caminho do .exe + hora de criação (em cache por pid)
    → CharacterTracker.refresh(...)     lê só o que cresceu em <pasta do .exe>\\NetLog\\rfclient.log
    → {pid: CharacterInfo(nome|None, conta)}  (guardado sob lock)
App._apply_characters → CharacterWatcher.names()
    · pid ausente  → ainda não sabe: não mexe na linha
    · nome mudou   → texto da linha, ClickerManager.set_title, ClickerManager.character_changed
```

`ClickerManager.character_changed(hwnd, nome)`: `None` para o clicker; com nome e `auto_profile` ligado, carrega `profiles.find(nome)` via `replace_config` e atualiza a janela de configuração aberta (`ConfigWindow.reload`).

### Modelo de estado

**Change Screen (`App`)**
- `entries`: lista ordenada de `Entry(hwnd, fallback, title, pid)`; a ordem define próxima/anterior. `Entry.character` é o personagem lido do log e `Entry.name` = personagem ou `fallback` ("RF n"). Atualizada por `_poll_windows` (1 s) e pelo arrasto. Identidade = HWND (iid do Treeview = `str(hwnd)`).
- `current` / `previous`: HWNDs da janela do RF usada por último e da usada antes (alimenta "Última usada"). `_sync_foreground` (a cada 150 ms e antes de cada ação) acompanha trocas feitas pelo usuário.
- `hotkeys.enabled` / `cfg["enabled"]`: ON/OFF mestre, lido pelo hook a cada evento.
- `capturing`: ação em cadastro (`None` fora da captura). Bindings: `{"type": "key"|"mouse", "vk"|"button", "ctrl", "alt", "shift", "label"}`.
- `row_button`: `(iid, "icon"|"gear")` quando o clique começou num botão da linha.

**Clicker**
- `ClickerManager._sessions[hwnd] = Session(cfg, runner, config_win)`. Estado do ícone derivado: **cinza** se `cfg.is_configured()` é falso; **verde** se há runner vivo; senão **vermelho**.
- `ClickerConfig(mode, keys, macro)`: `keys` é a lista do modo Click (`KeyRow(vk, label, ms)`; `vk == 0` = linha vazia); `macro` é `Macro(events, loop)` com `MacroEvent(kind="key"|"delay", value, label)`. `is_configured()` olha só o modo ativo.
- Gravação: `Macro.start_recording / record_key / stop_recording` concentram as regras (sem Tempo antes da 1ª tecla, Tempo final só se a última linha não for Tempo e algo foi gravado).

### Decisões e armadilhas

- **Home**: a tela inicial usa só widgets `tk` com cores explícitas (nada de `ttk.Style` global): a janelinha do Modo grupo usa ttk e não pode mudar de aparência quando a tela inicial está aberta. Raça e classe usam uma **lista suspensa própria** (`theme.Dropdown`: caixa + popup `Toplevel` sem borda) em vez do Combobox do ttk, que só aceita tema escuro mudando o tema global. O popup é descendente do diálogo, então funciona dentro do diálogo modal (que usa `grab_set`). Variáveis que sobrevivem aos widgets (a seleção dos cards, `BooleanVar`) precisam remover o `trace` quando o widget é destruído (`Checkbox`, `Dropdown`), senão o Tk dispara callbacks em widgets que não existem mais.
- **Card de altura fixa**: as vagas livres de personagem usam a mesma estrutura de uma linha preenchida (quadradinho no lugar da bolinha + rótulo em branco). Um primeiro teste mostrou 4 px a mais por vaga vazia quando o espaço reservado tinha estrutura diferente; o smoke da interface confere que todos os cards têm a mesma altura.
- **Conta em jogo**: `RunningAccounts` (puro) une `bind(login, pid)` (o PID que o Play devolveu) e o `SetAccountID` do log (`CharacterWatcher.accounts()`), sempre só para PIDs vivos; `update()` devolve os **desencontros** (PID ligado a uma conta, log dizendo outra), que a tela mostra como erro. A fila lê `running_ids` (um `frozenset` trocado por inteiro) de outra thread, então ninguém altera o conjunto no lugar. O Pause usa `Win32Api.kill` (TerminateProcess, o app já é administrador) em **todos** os PIDs da conta.
- **Ícone**: o logo (PNG com transparência) foi reduzido para 16, 24, 32, 48, 64 e 256 px e embutido em base64 (`shared/logo_data.py`, ~36 KB); `branding.apply` o aplica com `iconphoto(True, ...)` para valer também nas janelas criadas depois, e `branding.prepare` define um AppUserModelID próprio antes do Tk, para a barra de tarefas não agrupar sob o Python. Os tamanhos pequenos são pré-gerados porque o Tk só reduz por inteiros (ficaria serrilhado).
- **Modo grupo embutido**: `change_screen.App` aceita um `Toplevel` (e `on_closed`). Com o Tk da tela inicial vivo, os laços de `after()` do `App` precisam parar quando ele fecha (`_closed`), senão continuam disparando sobre widgets destruídos. A tela inicial **relê o `config.json`** antes de gravar a posição de um diálogo (`_remember_window`), porque o `App` do grupo grava o próprio dicionário (posições das telas) no mesmo arquivo enquanto ela está aberta.
- **Senhas**: DPAPI via ctypes (`accounts/secrets.py`), com entropia fixa do app. `store.save` retorna `False` e **não grava nada** se alguma senha não puder ser cifrada (preferível a gravar em texto puro). Senha ilegível vira `Account.password = None` e o texto cifrado antigo fica em `unreadable_token`, que o `save` devolve ao arquivo se a senha não for redigitada. Isso protege o arquivo (backup, nuvem), não contra quem já está logado como o usuário.
- **Autologin**: toda a lógica fica em `launcher.login`, que recebe um `api` (a `Win32Api`, ou um launcher falso nos testes) e relógio/`sleep` injetáveis; os testes (`tests/test_autologin.py`) cobrem sucesso, senha errada, mensagem desconhecida, cancelar (antes e depois de escolher o servidor), limite de 12 letras, ID salvo misturado, launcher mudo, duplo clique e que **outros launchers/clients já abertos nunca são tocados** (só os PIDs novos de `RF_BrasilRPG.exe` contam). O launcher que o programa abriu é fechado em erro ou cancelamento, mas **não** depois de o servidor ter sido escolhido (ele fecha sozinho).
- **Play**: `PlayController` roda os logins numa thread única e **nunca toca no Tk** (mesmo padrão do clicker): a tela chama `drain()` a cada 100 ms. Sair da fila é imediato (o job cancelado é pulado sem evento); cancelar o que está rodando seta um `threading.Event` que o login confere a cada etapa. A senha só existe no `Job` e nunca vai para eventos, mensagens ou logs; exceções inesperadas mostram só o tipo.
- `accounts` e `autologin` não dependem de Tk; só `home` depende deles (e do `change_screen`/`clicker`).
- `SetForegroundWindow` é restrito pelo Windows: `winapi.activate` usa um toque de ALT sintético e, se falhar, `AttachThreadInput` (eventos injetados são ignorados pelo hook).
- Callbacks dos hooks (`HOOKPROC`) ficam como atributos para o GC não coletá-los (`HotkeyManager`, `KeyRecorder`).
- Modificadores sozinhos (Alt Gr = `VK_RMENU` 0xA5, Ctrl, Shift) são cadastráveis como atalho de troca; o Alt Gr injeta um Ctrl falso (scan `0x21D`) que o hook ignora.
- Cliques na lista: o clique age no `ButtonRelease` (arrastar nunca aciona "ir para"). Não há mais renomear nem espera por duplo clique. O `<Double-1>` fica ligado só para **engolir o 2º clique** de um duplo (devolve `"break"`): sem isso, um duplo clique no ícone ligaria e desligaria o clicker. Cliques no ícone/⚙ da linha seguem um caminho à parte (`row_button`): o ícone só liga/desliga; o ⚙ chama `_goto` (o RF vem para a frente) e depois abre a configuração.
- **Telas sem X**: `windowing.hide_close_button` tira `WS_SYSMENU` do estilo da moldura (o pai do HWND do Tk) e força o redesenho da borda; a barra de título continua com o título (nome e PID) e deixa arrastar. É o OK que fecha. Sem Windows/ctypes a função falha em silêncio e a tela fica com o X normal.
- **Posição das telas**: cada tela grava `winfo_x/winfo_y` ao fechar (OK, ou o programa fechando). O `clicker` não conhece o `config.json`: o `ClickerManager` recebe `get_position(nome)`/`set_position(nome, '+x+y')` do app, e é o app que guarda em `windows`. A janelinha do Modo grupo usa a chave `position` (validada com `POSITION_RE` ao ler o arquivo: uma string inválida derrubaria o `geometry`). **Todas** passam por `windowing`: `visible_position` descarta um canto que não cai em nenhum monitor (consulta cada monitor com `EnumDisplayMonitors`, não o retângulo da área virtual, que inclui vazios entre monitores de tamanhos diferentes), `keep_on_screen(win)` confere ao abrir e depois de cada movimento (usa `GetWindowRect` da moldura, com a sombra de 12 px descontada, e espera o botão do mouse soltar para não brigar com o arrasto) e `current_position(win)` devolve sempre uma posição já corrigida, que é o que se grava. A conta (`fits`, `clamp`, `center_in`) é pura, em `shared/screens.py`: `clamp` desloca o mínimo para o monitor com mais área em comum (ou o mais próximo). `center_on_screen` só é usado pela tela inicial e, na primeira abertura, pelo Modo grupo.
- **Perfil lembrado**: `Session.profile` guarda o nome do último perfil carregado/salvo; a tela o seleciona no combobox ao abrir se `profiles.find` ainda o encontrar. A sessão some quando o RF fecha.
- Na lista, o ícone é a **imagem do item** do Treeview e o ⚙ é uma coluna de dados (`gear`). A detecção do clique usa `identify_element` (`image` e `Treeitem.indicator`) e `identify_column` (`#1`).
- O `clicker` tem seu próprio `winapi.py` e **não importa** o `change_screen`; só o `change_screen` importa o `clicker` (dependência de mão única).
- O Runner usa **prazos absolutos** (sem acumular deriva), `Event.wait` (Stop imediato) e `timeBeginPeriod(1)` enquanto houver runner ativo. Uma thread por janela garante que as 4 mensagens de cada tecla nunca se misturem com as de outra tecla da mesma janela.
- O envio usa `SendMessageTimeoutW` (250 ms, `SMTO_ABORTIFHUNG`) para um jogo travado não segurar o Stop. O `lParam` das mensagens é 0, como no original (ainda não validado no jogo).
- A janela de destino é sempre o **HWND da linha**; nada procura janela por classe/título. Nos testes, o alvo é uma janela falsa criada pelo próprio teste.
- Editar a config enquanto o clicker roda é agrupado (300 ms) e reinicia o runner uma vez; o manager espera o runner antigo terminar (até 0,3 s) antes de iniciar o novo.
- Carregar um perfil (à mão ou automático) fecha a janela da macro aberta (ela apontaria para a macro antiga).
- **Characters, atribuição de linhas** (`modules/characters/rflog.py`): vale o fluxo com o **menor salto** de contador (`MAX_GAP` = 3), e **todos** os fluxos do log participam, vivos ou não. Duas versões anteriores falharam em dados reais: (1) saltos de até 20 com só os vivos na conta **trocavam nomes entre clients**; (2) `n - 1` exato com só os vivos funcionou com 3 clients, mas com 6 o contador de um vivo parou numa linha perdida (`[785]` nunca apareceu) enquanto um client **já fechado** com o mesmo contador seguia escrevendo; o vivo "adotava" essas linhas, ficava adiantado e mostrava o personagem do client fechado (caso real: o 18336, da Maga, mostrava Guerreiro e não se corrigia ao trocar de personagem). Com todos os fluxos na conta, o fechado fica com as próprias linhas. Empates (dois fluxos esperando o mesmo `n`) vão para o que escreveu por último; se os dois escreveram a menos de `TIE_WINDOW` (2 s) um do outro, o conteúdo da linha (conta, personagem, lobby) é **ignorado** e o contador só avança. Uma troca de identidade entre dois fluxos é permanente depois do empate, por isso o código prefere calar a chutar.
- Ao entrar ou sair um client vivo, o `CharacterTracker` **relê a janela do log do zero** (a partir de `READ_MARGIN` = 7 dias antes do processo mais antigo, que muda quando o mais antigo fecha). Se o arquivo encolher (recriado), o estado também é zerado.
- O `base result ( 0 - … )` só é aceito com código `0`. A mensagem de lobby só vale em `load map ( .\map\lobby\… )` (a palavra "lobby" em outras linhas é ignorada).
- A thread do `CharacterWatcher` engole exceções: ler o log nunca derruba o programa; sem resultado, a linha fica como está.

### Testes

```
python -m unittest discover -s tests -t .
```

Cobrem a janela do RF no canto (`tests/test_placement.py`: janela nova movida só na posição, barra de tarefas, já no canto, o jogo reposicionando a janela, prazo de 8 s, janela minimizada, janela já aberta, erros do Windows) e a regra de posição das janelas (`tests/test_screens.py`: puras, com monitores de tamanhos diferentes e coordenadas negativas; `tests/test_windowing.py`: com janelas Tk e monitores falsos: centralizar, abrir fora das telas, soltar escondida, atravessar dois monitores) e as contas (`tests/test_accounts.py`: validação, no máximo 3 personagens, ida e volta do `servers.json`, senha fora do arquivo em texto puro, DPAPI, senha ilegível preservada), a fila do Play (`tests/test_play.py`: um por vez, erros sem vazar a senha, cancelar na fila e rodando), o login automático contra um launcher falso (`tests/test_autologin.py`: inclusive ID salvo que sobrescreve o digitado e espera pelo fechamento do launcher), as contas em jogo (`tests/test_running.py`), o ícone embutido (`tests/test_branding.py`) e o modelo (edição e gravação da macro), os perfis (salvar/carregar/excluir/`find`, arquivo corrompido), o runner (períodos, ausência de deriva, sequência de mensagens sem mistura, Stop imediato, loop × sem loop, janela fechada), o manager (cinza → vermelho → verde, reinício ao editar, `character_changed`: perfil automático, parar na seleção), o `config.json` do Change Screen (inclusive as posições das janelas) e o módulo Characters (`tests/test_rflog.py`: log sintético com vários clients intercalados, troca de personagem pelo lobby, regressão de linhas de outros clients, de client fechado que arrastava o vivo e de linha perdida no contador, empates sem nome errado, leitura incremental e linha cortada, arquivo recriado, log grande com busca binária). O clicker usa uma janela falsa (`tests/fake_window.py`). **Nenhum teste fala com o RF real nem lê o seu log.**

Teste manual do nome (com os clients reais): a linha mostra o personagem de cada client; voltar à seleção devolve `RF n` e para o clicker; entrar com outro personagem atualiza o nome; com a opção ligada e um perfil com o nome do personagem, ele é carregado sem ligar o clicker.

Já validado no jogo real (launcher e conta de teste): login de ponta a ponta, espera do launcher fechar (~12 s), conta do client lida do log, Pause (os dois `kill` terminaram os processos) e o caso do ID salvo (corrigido; ver Armadilhas). Ainda **não** validado com o jogo real: iniciar em lote com duas contas diferentes e Pause de um client aberto por fora.

Teste manual do Play (com o RF real): cadastrar `RF_BrasilRPG.exe`, uma conta e clicar em Play como administrador: o launcher abre, o login é digitado e o client nasce logado, na seleção de personagem. Repetir com uma senha errada (mensagem em português e launcher fechado) e com Play em duas contas (a segunda espera na fila). Já validado com o launcher e uma conta reais: caminho de sucesso (client aberto em ~20 s) e de senha errada.

Teste manual da interface (com 1 cliente do RF): ícone cinza → vermelho → verde; a tecla chega ao jogo sem foco; macro com e sem loop; Ctrl+clique + F2 em vários tempos e duplo clique em um tempo; OK fecha as telas e elas reabrem no mesmo lugar, com o perfil selecionado; Salvar sobre um perfil pergunta antes; arrastar/remover linhas; salvar, carregar e excluir perfil; fechar o RF derruba o clicker; rodar como administrador e sem.

### Ideias de melhoria

- Atalho global para ligar/desligar clickers, e "ir direto para a janela N".
- Arrastar várias linhas da macro de uma vez; mostrar a linha em execução durante a reprodução.
- Validar o envio no jogo real (inclusive `lParam` com scan code) e, se preciso, outra técnica para teclas de movimento.
- Quando a opção do perfil automático for ligada, aplicar também aos personagens que já estão em jogo.
- Resolver o empate de clients abertos juntos (hoje fica sem nome) com outra fonte além do log.
- Ícone na bandeja; iniciar com o Windows; aplicar o tema escuro também à janelinha do Modo grupo.
- Ver a seção **TODO** do módulo Home (classes por raça, e-mail/tag, conta ↔ janela, Play em lote).

> Mantenha este README atualizado a cada mudança de comportamento, arquivo ou formato dos dados.
