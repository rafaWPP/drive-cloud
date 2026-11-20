# Drive Cloud — versão local

Drive pessoal para testes no Linux usando React + Vite. Permite pastas, lista e grade, upload/download local, favoritos e pesquisa.

## 1. Frontend

Node.js versão 20.19+ ou 22.12+ recomendado.

```bash
git clone https://github.com/rafaWPP/drive-cloud.git
cd drive-cloud
npm install
npm run dev
```

Abra http://localhost:5173.

## 2. Conectar sua conta Telegram (local)

É preciso obter suas credenciais **api_id** e **api_hash** em https://my.telegram.org, na área API development tools. Essas credenciais são do seu aplicativo MTProto, não um bot token.

No terminal, na raiz do projeto:

```bash
cd backend
cp .env.example .env
nano .env
```

Preencha `TELEGRAM_API_ID` e `TELEGRAM_API_HASH`, sem aspas, salve e execute:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

Deixe esse terminal aberto. Em outro terminal execute `npm run dev` na raiz do projeto. Na interface web, vá em **Configurações > Conexão Telegram**. Informe o telefone com DDI, o código recebido e sua senha de duas etapas, se pedida.

**Importante:** a primeira integração apenas faz login e guarda a sessão localmente. Uploads e downloads de arquivos ainda utilizam IndexedDB do navegador, **não** o Telegram. A conexão Telegram não sincroniza os arquivos nesta versão.

## Segurança

- Nunca envie seu `backend/.env`, a pasta `backend/.data` ou arquivos `*.session` ao GitHub nem compartilhe códigos de login.
- Proteja seu usuário Linux e use criptografia de disco: a sessão local concede acesso à conta Telegram.
- A API de teste escuta somente em `127.0.0.1:8000`, não deve ser exposta na internet.
- IndexedDB é armazenamento local do navegador e não substitui um sistema de backup. Limpar os dados do site pode apagar os arquivos.
- A opção **Desconectar backend** fecha a conexão do processo; **Sair do Telegram** revoga a sessão.

## Login com QR Code

Na tela **Configurações > Conexão Telegram**, escolha **Gerar QR Code**. No celular abra **Telegram > Configurações > Dispositivos > Conectar dispositivo** e escaneie. O código temporário pode expirar; nesse caso clique em **Gerar outro QR Code**. Caso sua conta exija senha de duas etapas, informe-a na tela do Drive. A alternativa de login por telefone continua disponível. Após atualizar o projeto, reinstale as dependências Python com `pip install -r requirements.txt` e reinicie o backend. O código QR é produzido localmente, sem serviço externo.

## Canal privado criado automaticamente

Ao concluir a autorização no Telegram, a tela **Configurações > Conexão Telegram** chama a API local para preparar o canal privado `Drive Cloud Storage`. Se não houver vínculo, o backend procura um canal próprio com esse nome e, quando não encontra, cria um canal privado (tipo broadcast) com a API Telegram. Salva o identificador em `backend/.data/storage_channels.json`, separado pelo ID da conta. Nas próximas conexões, reutiliza o mesmo canal. Se o canal associado sumir, o sistema **não cria outro automaticamente**: exibe um aviso para evitar duplicações.

A criação só acontece depois da autenticação e quando a tela de conexão é aberta. O programa **ainda não envia arquivos ao canal**: uploads continuam salvos no IndexedDB do navegador. Não apague `backend/.data` — é onde ficam os vínculos e a sessão Telegram. Esse diretório está ignorado no Git. Se fizer backup dessa pasta, trate-o como material confidencial.

Para atualizar o projeto, execute `git pull origin main`, reinicie o backend e recarregue a página. A criação de canal é uma operação real na sua conta Telegram e depende dos limites e permissões do Telegram.

## 3. Upload e download reais (Telegram Cloud V1)

Depois de conectar a conta e criar o canal privado, abra **Meu Drive > Nuvem Telegram**. Essa área é separada de **Arquivos locais**, que continua usando IndexedDB do navegador.

- **Enviar ao Telegram** faz upload real para o canal privado associado à conta.
- **Baixar** busca o conteúdo pelo identificador da mensagem no Telegram.
- **Nova pasta** registra pastas no SQLite local; não cria um canal para cada pasta.
- Os metadados ficam em `backend/.data/files.sqlite3`, o vínculo do canal em `backend/.data/storage_channels.json` e a sessão em `backend/.data/telegram.session`. Nenhum deles vai para o GitHub.
- Limite piloto: **20 MB por arquivo**. Não há envio em partes, fila resiliente, criptografia de ponta a ponta própria ou restauração entre máquinas nesta etapa.
- **Atenção**: arquivos que estavam em **Arquivos locais** não são migrados automaticamente para o Telegram. O canal do Telegram guarda o conteúdo, mas sem o banco SQLite local a listagem e a estrutura de pastas desta versão não são reconstruídas automaticamente.
- Faça backup seguro do diretório `backend/.data` (ele contém credenciais sensíveis!) e mantenha outra cópia dos arquivos importantes.

Atualização no Linux (nos dois terminais, com o backend parado enquanto instala dependências):

```bash
cd ~/Área\ de\ trabalho/drive-cloud
git pull origin main
cd backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

No outro terminal, execute `npm run dev` na pasta raiz. Acesse `http://localhost:5173`.

O projeto é experimental; **não use o Telegram como única cópia de backup**.

## Interface integrada — tema grafite

A navegação **Meu Drive > Todos os arquivos** agora abre o catálogo Telegram. O antigo IndexedDB segue disponível em **Meu Drive > Arquivos antigos (navegador)**: a mudança não apaga arquivos locais e **não migra dados automaticamente**.

- Arraste arquivos para a área principal ou use **Upload**. O painel apresenta fila, sucesso, falha e progresso de transferência **navegador → backend**. O envio do backend para o Telegram ocorre depois e só é considerado concluído quando há confirmação. A barra percentual **não** mede o envio interno ao Telegram.
- **Cancelar todos** interrompe a solicitação em andamento do navegador e a fila pendente. **Se o Telegram já recebeu os dados, o envio remoto pode continuar**; verifique o canal e a lista antes de reenviar.
- Modo lista e grade com seleção múltipla, download por seleção, renomear, mover e lixeira reversível. O diálogo de mover usa o identificador da pasta de destino nesta versão de teste.
- Os dados do catálogo são mantidos em SQLite; ainda não existe recuperação automática do catálogo pelo histórico do Telegram.
- **Lixeira** é lógica: não apaga as mensagens remotas do Telegram.
- Compartilhamento público, visualização de imagens, enfileiramento durável, criptografia própria e sincronização entre dispositivos continuam planejados.

Reinicie **backend** após o `git pull`, pois novas rotas e a migração do banco SQLite são carregadas na inicialização. No frontend o Vite geralmente recarrega automaticamente.

**Segurança:** esta versão é experimental e deve rodar apenas no PC. Não exponha a porta 8000 publicamente e não utilize arquivos críticos como única cópia.

## Atualização visual: prévia de imagens e cores padronizadas

O visual agora segue uma paleta dark grafite neutra, com botões consistentes: **azul** para ação primária, **grafite** para secundárias, **azul-escuro** para seleção, **vermelho** reservado para ações destrutivas. A navegação do Meu Drive exibe apenas a área principal do Telegram; o IndexedDB antigo não foi apagado, apenas retirado do menu.

A grade e a lista usam miniaturas de imagens recuperadas do canal. Ao clicar numa imagem, o Drive abre uma prévia ampliada com botão de download e **X** para fechar. Arquivos JPEG XL (.jxl) são convertidos para JPEG somente para a visualização; o arquivo original armazenado no Telegram permanece intacto. Algumas imagens podem não gerar prévia se estiverem corrompidas, excederem os limites de processamento ou não forem suportadas pelo decodificador.

O painel de uploads oferece botão de fechar e uma ação para reabri-lo. O progresso porcentual continua representando o envio do navegador ao backend local, **não** o estágio interno de envio ao Telegram.

**Atualização obrigatória do backend:** após `git pull`, execute `pip install -r requirements.txt` dentro do ambiente virtual para instalar Pillow e o plugin JPEG XL. Reinicie o Uvicorn. Esta versão não foi testada diretamente na máquina do usuário.

## Ajustes do seletor e carregamento (V3)

- O indicador de miniaturas usa três bolinhas sequenciais em vez de spinner circular.
- A barra de ações de arquivos selecionados ocupa uma faixa de altura constante acima da tabela/grade. A seleção apenas exibe ou oculta as ações, sem alterar a posição da listagem.
- Checkboxes personalizados em grafite com marcação azul, estados hover/focus e comportamento de selecionar todos.
- Botões padronizados por função: primário azul, secundário grafite, seleção azul e ações destrutivas em vermelho discreto.
- Referência de navegação: ações contextuais demonstradas pelo usuário em gravação da interface do Dropbox. Esta atualização não altera nem apaga os dados salvos.

Para aplicar: `git pull origin main` e `Ctrl+Shift+R` na página. Não é necessário reiniciar o backend para estas alterações de interface.

## Menus de arquivo e movimentação (UI V4)

- Menu de três pontos no modo grade: gatilho alinhado no canto superior direito, opções com ícones e divisórias, ação destrutiva discreta em vermelho.
- Modo lista: novos ícones de **Renomear** (lápis) e **Mover** (seta de movimento), com área clicável maior e texto explicativo no hover.
- Mover arquivo(s): em vez de solicitar ID técnico da pasta, abre uma janela para selecionar a pasta de destino.
- O backend existente continua aplicando as alterações no catálogo SQLite; renomear/mover pastas não muda as mensagens originais do canal Telegram.

Para aplicar, execute `git pull origin main` na raiz do projeto e atualize o navegador com `Ctrl+Shift+R`. Esta atualização afeta o frontend; não precisa reiniciar o backend.

## Início conectado ao Telegram

A **Visão geral**, **Recentes** e **Favoritos** agora consultam o mesmo catálogo SQLite da área **Meu Drive** e não mais os arquivos antigos do IndexedDB. A visão geral mostra arquivos recentes, pastas e contagens; Recentes mostra arquivos em ordem de inclusão; Favoritos mostra itens marcados com estrela. A estrela no menu de três pontos ou nas ações da lista salva a preferência no banco local. Uma busca simples está disponível nessas telas.

A atualização cria automaticamente a coluna `starred` no banco SQLite existente quando o backend reinicia, sem apagar os arquivos. O histórico anterior do Telegram que não está no catálogo local **não é importado automaticamente**.

Atualize com `git pull origin main`, **reinicie o backend** (`uvicorn server:app --host 127.0.0.1 --port 8000` após ativar `.venv`), e atualize a página com `Ctrl+Shift+R`.

## Interface V5: Home limpa, busca única e miniaturas

- A barra de ações do **Meu Drive** usa controles grafite finos, sem bordas marcadas, mantendo a cor azul discreta para seleção.
- A **Visão geral** não mostra mais o card grande de estatísticas. Ela exibe seções compactas de Recentes e Favoritos com prévias.
- Removida a busca duplicada dentro da área de arquivos. **Somente a busca do cabeçalho** filtra os resultados nas telas de Meu Drive, Visão geral, Recentes e Favoritos. A busca inclui pastas e arquivos do catálogo Telegram e pode localizar itens fora da pasta atual.
- As miniaturas agora encerram seu indicador ao carregar, ao falhar, ou após **15 segundos**. Em falhas ou tempo excedido, aparece o ícone padrão. Isso evita carregamento visual infinito, mas não corrige possíveis lentidões de download ou conversão no backend.
- Não há migração ou exclusão de dados locais e do Telegram nesta atualização.

Execute `git pull origin main` e atualize a página com `Ctrl + Shift + R`. Mudanças somente no frontend; o backend pode continuar ligado.

## Ajustes da interface V6 — notificações e limpeza

- Removidos subtítulos e títulos duplicados nas telas **Início**, **Recentes**, **Favoritos** e **Meu Drive**; permanecem os títulos principais e o conteúdo.
- Barra de seleção com botões mais baixos, sem bordas pesadas, no mesmo padrão grafite dos controles do Meu Drive.
- Notificações unificadas em forma de **toast central inferior**, com ícone de sucesso, informação ou erro, cores próprias de cada tipo, animação de subir ao aparecer e descer ao fechar, botão **X** e fechamento automático. Quando um item é movido à lixeira, aparece **Desfazer** por alguns segundos.
- Operações de enviar, baixar, criar pasta, renomear, mover, favoritar, restaurar e erros de arquivo apresentam notificação visual; ações de login e logout também.
- O bloco antigo de “Armazenamento local” da lateral foi removido porque mostrava o IndexedDB antigo, não o Telegram. A lateral agora mostra apenas o status de conexão do Telegram.
- Esta atualização é exclusivamente do frontend, sem alteração de arquivos remotos ou do SQLite.

Atualização: `git pull origin main` e `Ctrl+Shift+R`; sem necessidade de reiniciar o backend.

## Exclusão com confirmação e catálogo de segurança

O **Excluir** fora da lixeira pede confirmação e apenas move o item para a lixeira do catálogo, com opção **Desfazer** por alguns segundos. O arquivo ainda existe no canal privado do Telegram.

Na **Lixeira**, o usuário pode **Restaurar** ou **Excluir definitivamente**. Esta última ação exige confirmação adicional e solicita ao Telegram que apague as mensagens do arquivo e dos descendentes da pasta, removendo os registros do SQLite após a chamada remota. **Exclusão definitiva não pode ser desfeita**. Se houver falha de rede, verifique a lixeira e o canal antes de repetir; operações que envolvem múltiplos itens podem ter resultado parcial.

No Meu Drive há um botão com ícone de backup, ao lado de Atualizar, para **Exportar catálogo**. Ele baixa um JSON com os nomes, pastas, mensagens, identificadores e sinalizações do catálogo. O JSON não inclui senha, `api_hash`, sessão ou bytes dos arquivos. É um **snapshot de metadados**, não uma cópia dos arquivos e ainda **não existe importação automática**. Proteja o arquivo exportado, pois expõe nomes e referências dos seus dados.

Após `git pull origin main`, reinicie o backend para habilitar rotas de exportação e exclusão definitiva, e faça `Ctrl+Shift+R` no navegador. Faça um teste com um arquivo descartável antes de apagar arquivos reais.

## Exclusão com progresso e armazenamento usado (V7)

- O modal de confirmação agora abre com animação curta e fundo escurecido.
- Após confirmar uma exclusão, aparece um painel inferior com número de itens processados, barra de progresso e botão **Cancelar**. O sistema processa um item de cada vez e o cancelamento interrompe a fila **antes do próximo item**. Uma operação já enviada ao Telegram não pode ser desfeita nem interrompida com garantia, especialmente se o item for uma pasta com arquivos descendentes. O painel indica quantos itens já foram concluídos.
- A barra lateral mostra quanto espaço os **arquivos registrados no catálogo Drive Cloud** ocupam, quantidade de arquivos e tamanho dos itens na lixeira. Esses números vêm do SQLite local e incluem arquivos movidos à lixeira; **não são medição de armazenamento total da conta Telegram nem quota livre**.
- O backend passa a oferecer `GET /api/cloud/usage`; reinicie o Uvicorn depois de atualizar o código.

**Teste seguro:** use arquivos descartáveis e uma exclusão em lote para verificar o cancelamento; não use arquivos importantes para testar exclusão definitiva.

## Visual compacto e confirmação V8

- Indicador na barra lateral reduzido a **Armazenamento — valor usado**, uma barra fina e estado da conexão. A barra usa **1 GB apenas como escala de comparação visual**, nunca como cota ou limite real do Telegram. O número representa os arquivos registrados no SQLite local, incluindo lixeira.
- Modal de exclusão com **um único ícone de alerta centralizado** que gira uma vez durante a abertura e termina parado; texto de advertência abaixo, em contraste discreto. A confirmação e o painel de progresso/cancelamento continuam funcionando.
- Para atualizar: `git pull origin main` e `Ctrl+Shift+R`. Apenas frontend foi alterado; não exige reiniciar backend.

## Validação de uploads antes de abrir painel

O gerenciador de transferências **só aparece quando um arquivo válido entra no envio**. Arquivos acima do limite experimental de **20 MB por arquivo** são rejeitados antes de entrar na fila: aparece apenas um toast de erro, sem abrir uma janela de upload vazia. Se houver uma seleção mista, os arquivos aceitos seguem para o Telegram e os rejeitados são avisados por toast. O limite permanece em vigor nesta etapa; suporte a arquivos grandes ainda requer implementação e validação em partes.

## Progresso real do upload no Telegram

A barra não mostra mais **100%** simplesmente porque o navegador terminou de enviar os dados ao backend. O frontend atribui 0–10% à transmissão local; depois consulta `GET /api/cloud/upload-progress/{upload_id}` para ler os bytes reais informados pelo `progress_callback` do Telethon durante o envio ao Telegram. A etapa remota ocupa os 10–95% seguintes. Ao terminar o envio ao Telegram, o sistema aguarda a gravação do catálogo SQLite, e **100% só aparece quando a API de upload retorna sucesso**.

O endpoint de progresso guarda estado temporário em memória no backend local, sem gravar dados ou credenciais no GitHub. O progresso não é recuperação de upload interrompido nem garante cancelamento remoto de uma transferência iniciada.

**Atualização:** faça `git pull origin main`, reinicie o backend com Uvicorn, mantenha o frontend Vite aberto e pressione `Ctrl+Shift+R` no navegador. O limite piloto continua em 20 MB por arquivo.

## Progresso da exclusão no próprio toast

Depois de confirmar uma operação de exclusão ou envio à lixeira, o Drive Cloud exibe **somente um toast inferior** em vermelho com ícone de lixeira, progresso por quantidade de itens, nome do item atual e botão **Cancelar**. O painel antigo `delete-job` foi retirado da renderização. Quando a operação termina, o toast de progresso desaparece e o toast de sucesso verde informa quantos itens foram processados. Em erro, aparece um toast de erro.

O cancelamento é cooperativo: interrompe **os próximos itens da fila**, mas uma exclusão remota já enviada ao Telegram pode concluir e não pode ser desfeita. Para atualizar apenas o frontend, execute `git pull origin main` e atualize a página com `Ctrl+Shift+R`. Não há mudança de API nesta atualização.

## Lixeira na barra lateral e restauração do catálogo

A barra de ícones da esquerda agora inclui a **Lixeira**, com o mesmo padrão visual das outras seções. Ela consulta os itens excluídos logicamente no catálogo Telegram e permite **Restaurar** ou **Excluir definitivamente**, com confirmação e progresso em toast. A visualização usa o mesmo componente do Meu Drive, sem trocar para o armazenamento antigo do navegador.

O próximo passo de recuperação foi implementado: a tela **Meu Drive** oferece **Exportar catálogo** e **Restaurar catálogo** (ícones no topo). Ao escolher o arquivo JSON exportado, o backend valida versão, estrutura de pastas, identificadores e, principalmente, a **mesma conta e o mesmo canal privado Telegram**. Antes de importar, apresenta uma contagem de registros existentes e ausentes; somente os ausentes são adicionados. Itens existentes não são substituídos.

A importação recupera **apenas os metadados do catálogo** (pastas, nomes, referências e favoritos). Não restaura conteúdo excluído permanentemente do canal Telegram, nem traz arquivos de outra conta ou de outro canal. Recomenda-se manter uma cópia segura do arquivo exportado. Ainda não é sincronização automática entre dispositivos, e referências importadas pressupõem que as mensagens continuem disponíveis no Telegram.

Para atualizar, execute `git pull origin main`, **reinicie o backend** (nova rota `POST /api/cloud/catalog/import`) e recarregue o navegador. Teste primeiro com uma exportação do seu próprio catálogo, sem excluir arquivos.

## Modal Mover para — explorador de pastas

A janela **Mover para** agora segue o mesmo tema grafite e o mesmo efeito de abertura discreta do modal de exclusão, mas sem ícone grande centralizado. Inclui:
- navegação por subpastas com clique;
- botão Voltar, breadcrumbs clicáveis e opção de mover para a raiz;
- criação de pastas dentro da própria janela, escolhendo a pasta recém-criada como destino;
- indicação explícita do destino e botões Cancelar/Mover aqui;
- ocultação de pastas selecionadas e de descendentes, para evitar destinos inválidos.

A operação altera apenas o campo `parent` no catálogo SQLite; os arquivos não precisam ser enviados ao Telegram novamente. A API já impede mover uma pasta para dentro dela mesma ou de descendentes. Para receber as mudanças no frontend, use `git pull origin main` e `Ctrl+Shift+R`.

**Validação:** os arquivos foram atualizados no GitHub, mas a compilação no PC do usuário ainda precisa ser conferida.

## Correção dos botões Nova pasta e indicador de armazenamento

Os botões **Nova pasta** do Meu Drive e do explorador **Mover para** usam a API real `POST /api/cloud/folders`. A criação no Meu Drive não depende mais do `window.prompt`: agora exibe uma janela dark com nome, confirmação e mensagens de erro em toast. O botão **Novo** do cabeçalho também abre a janela de criação no Meu Drive. Dentro de **Mover para**, o formulário cria uma subpasta na localização atual e a seleciona como destino.

Foi eliminada a legenda artificial **"Escala 1 GB*"**. Ela era apenas uma referência visual, não uma cota imposta pelo Telegram. Agora o bloco mostra os **bytes usados registrados no catálogo SQLite**, e a barra apresenta a **distribuição entre arquivos ativos (azul) e arquivos na lixeira (cinza)**. Não representa espaço livre, quota total ou capacidade real da conta Telegram.

Atualize com `git pull origin main` e `Ctrl+Shift+R`. As rotas do backend não mudaram. Caso a criação falhe com erro de conexão/Telegram, confira se o backend local está executando e a conta está conectada.

## Gerenciador de pastas e download ZIP (V11)

A área **Meu Drive** agora apresenta uma árvore de pastas na lateral, com opção de expandir/recolher subpastas, abrir uma pasta e voltar para a raiz. O caminho de navegação também aparece acima da listagem; a seleção e a navegação não fazem upload novamente. O card de pasta não usa mais o cursor de lupa.

**Baixar pasta:** as ações de download de pastas (menu de três pontos, modo lista e seleção) preparam um ZIP com a estrutura de subpastas preservada. A interface mostra o número de itens processados e, quando a API conclui o arquivo, inicia o download automaticamente. O arquivo temporário fica em `backend/.data/zip_exports` e arquivos antigos são removidos na próxima compactação após 30 minutos; não é um serviço de backup permanente. Por segurança e consumo de recursos, o piloto limita cada ZIP a **250 itens e 300 MB de arquivos originais** e aceita no máximo duas compactações concorrentes por backend. Se um arquivo estiver ausente do canal Telegram ou houver nomes duplicados no mesmo caminho, o ZIP falha e informa o motivo; não é entregue um arquivo incompleto. A compactação ainda não pode ser cancelada depois de iniciada. Para baixar um ZIP com arquivos muito grandes, precisaremos de streaming e limites ajustáveis em uma etapa posterior.

O bloco lateral de armazenamento agora separa título e quantidade utilizada em linhas diferentes, evitando sobreposição de texto. A barra continua mostrando a proporção entre os arquivos ativos e os itens na lixeira do catálogo local, não um limite de armazenamento do Telegram.

**Para atualizar:** `git pull origin main`, reinicie o backend `uvicorn server:app --host 127.0.0.1 --port 8000` após ativar a venv, e faça `Ctrl+Shift+R` no navegador. Teste com uma pasta descartável contendo subpastas e arquivos pequenos. O código foi publicado, mas ainda não passou pelos testes executados no computador do usuário.

## Navegação, ZIP e páginas de sistema (V12)

- A árvore lateral de pastas expande/recolhe com transição suave e destaca o caminho da pasta aberta.
- A preparação do ZIP usa o progresso em **bytes efetivamente recuperados do Telegram** via `progress_callback` e exibe a etapa de compactação. O arquivo é baixado quando o backend confirma o ZIP pronto; não significa que o download do navegador tenha concluído.
- A tela de **Conexão Telegram** foi simplificada: nome da conta, status, canal privado e ações de desconectar/sair sem dados técnicos desnecessários. Upload/Nova pasta e a busca ficam nas telas de arquivos, não em configurações ou backups.
- Indicador de armazenamento: mostra bytes do catálogo (ativos + lixeira), sem exibir uma barra artificial de 100%, porque **a API Telegram não fornece uma quota de armazenamento da conta** para essa integração.
- **Backups > Meus backups, Agendamentos, Histórico** usam endpoints reais `/api/backup`: permitem snapshots JSON manuais de metadados do catálogo, agendamento diário/semanal e download de snapshots. As cópias ficam em `backend/.data/catalog_backups` (até 25 por conta). O serviço agendador só executa com backend e sessão Telegram ativos. Um snapshot **não contém os arquivos binários**.
- **Sincronização, Dispositivos e Atividades** apresentam o estado real e a arquitetura futura. Sincronização automática de diretórios/dispositivos **ainda não foi implementada**; não há agente Linux ou mobile rodando.
- **Configurações, Preferências e Segurança**: densidade visual e animações salvas no navegador, além de gestão e revogação de links de compartilhamento.

### Compartilhamento de links (protótipo localhost)
O menu de arquivo/pasta oferece **Compartilhar link**, com dois modos:
- **Download**: página local com ação direta para baixar arquivo ou pasta ZIP;
- **Compartilhado**: página local que pode listar a hierarquia da pasta, baixar arquivos individuais e baixar a pasta inteira; visualização de imagem quando suportada.

Cada link possui um token aleatório de alta entropia (somente o hash fica no SQLite), validade de 1 hora, 24 horas ou 7 dias e botão para revogar. Os links são gerados em `http://127.0.0.1:5173/?share=...` ou no endereço do navegador local e **não funcionam na internet nem em outro aparelho**. Esta é uma etapa de teste; para disponibilização pública de verdade serão necessários domínio HTTPS, serviço público isolado, autenticação de administração, proteção contra abuso e uma arquitetura multiusuário. **Não exponha o backend localhost/Telethon por túnel ou proxy**, pois ele também tem APIs administrativas e a sessão Telegram do proprietário.

Downloads por link nessa etapa são limitados a 50 MB de dados originais e 100 itens para pastas. Não é adequado para conteúdo de distribuição pública em escala.

### Atualização
Execute `git pull origin main`, reinicie o backend Python, recarregue o navegador. Teste primeiro um snapshot de catálogo e um compartilhamento local usando arquivos descartáveis. A versão publicada no GitHub ainda depende de testes de execução no PC local e de confirmação do build pelo workflow.

## Explorador de pasta compartilhada (V13)

Os links de compartilhamento no modo **Compartilhado** agora mostram um explorador semelhante ao Meu Drive, com breadcrumbs, botão Voltar, entrada em subpastas, alternância lista/grade, busca na pasta atual, visualização de imagens e download individual. O item selecionado fica dentro do escopo da pasta original; a API devolve identificadores de pastas-pai e permite prévias apenas de arquivos pertencentes à árvore compartilhada. Links de **Download** seguem mostrando somente o acesso direto ao arquivo ou ZIP completo.

A janela **Compartilhar link** agora apresenta o item, cartões para escolher entre Download e Compartilhado, validade, campo para copiar o endereço e lista de links ativos com opção Revogar. Mantém as animações discretas e o tema grafite.

**Segurança e limites:** continua exclusivamente em localhost. Compartilhar uma URL localhost com outra pessoa não permite acesso de outro computador. Não exponha o backend principal por túnel, encaminhamento de portas ou proxy; ele controla a sessão do Telegram. Downloads e prévias exigem a sessão local do proprietário. Atualize com `git pull origin main` e reinicie o backend Python, pois foi acrescentado o endpoint de prévia compartilhada.

Verificação automática compila o frontend e verifica sintaxe do backend; testes ponta a ponta com Telegram e ZIP ainda dependem do ambiente local.

## Preferências, navegação por URL e recuperação de mídia (V15)

- O carregamento inicial agora utiliza a **logo oficial do Drive Cloud**, com um arco azul discreto ao redor, sem a antiga nuvem apenas contornada. O carregamento inicial termina quando o backend responde, incluindo erros, para não bloquear a tela indefinidamente.
- A visualização **Lista/Grade** é armazenada em `localStorage` e também pode ser escolhida em **Configurações > Preferências**. Alterações aplicam-se à listagem existente, mesmo após atualizar o navegador.
- A URL interna guarda a página e a pasta: `?page=cloudFiles&folder=<UUID>`. A aplicação recupera essas informações ao atualizar e respeita Voltar/Avançar. Links de compartilhamento `?share=` e `?embed=` continuam separados dessa navegação.
- Os selects de visualização, agendamento e compartilhamento seguem o mesmo estilo grafite sem bordas coloridas.
- Mídia compartilhada: a API passa a permitir requisições `Range` para vídeo, converte JPEG XL/BMP/TIFF para JPEG de prévia quando o decodificador suporta, e expõe diagnóstico limitado à árvore do link em `/api/public/share/{token}/media-status`. A página de compartilhamento/integração oferece mensagens de erro e botão para tentar a prévia novamente; miniaturas com erro apresentam ícone de substituição.
- Persistem os limites locais da implementação: em links de teste, até 50 MB para mídias suportadas e vídeos reproduzíveis pelo navegador. Links `localhost` **não são públicos na internet**. Não exponha o backend administrativo via proxy.

Atualize `git pull origin main`, **reinicie o backend** e recarregue a página. Teste um compartilhamento novo com PNG/JPEG e MP4 em modo Visualização e Embed. Se houver falha, anote o **código HTTP e a mensagem** exibidos em mídia/console para investigação no PC local.

## Player compartilhado — gestos de avanço e retrocesso

O player personalizado dos links `?share=` e `?embed=` permite **toque/clique duplo no lado esquerdo para voltar 10 segundos** e **no lado direito para avançar 10 segundos**. Pares adicionais de toques no mesmo lado, em sequência, acumulam o indicador visual (10s, 20s, 30s). O clique/toque simples alterna reprodução e pausa. Os indicadores desaparecem automaticamente, sem mudar o layout da página.

A barra de controle usa azul do Drive Cloud: **tempo à esquerda e tela cheia à direita acima do progresso**; abaixo, **Reproduzir/Pausar**, informação HD apenas quando o arquivo original tiver pelo menos 720p, **Picture-in-Picture quando suportado pelo navegador**, e **áudio/volume como último controle**. A indicação HD não é um seletor de transcodificação, pois esta versão reproduz o arquivo original. O player também permite atalhos: `Espaço`/`K` para pausar, `←`/`→` para saltar 10s, `F` para tela cheia e `M` para mudo quando o player estiver focado.

As solicitações de vídeo ainda dependem da conexão local com Telegram. Teste em PC e celular, pois navegadores variam no suporte a PiP e nos gestos de toque.

## Player e compartilhamento (ajustes V16)

- **Um link por compartilhamento:** o modal apresenta um único endereço copiável. A opção **Integração** continua oferecendo um *código iframe* que usa **o mesmo endereço**, sem mostrar um segundo campo de "link direto de mídia". Links já criados permanecem válidos até expirarem ou serem revogados.
- **Vídeos dentro do Meu Drive:** clique na miniatura ou no nome para abrir a prévia com o mesmo player personalizado das pastas compartilhadas. Baixar o vídeo exige clicar explicitamente em **Baixar**. O player local usa `GET /api/cloud/media/{id}` com autenticação Telegram e suporte a solicitações por intervalo de bytes; `/api/cloud/media-status/{id}` informa falhas de prévia. O limite local continua sendo o limite atual de 20 MB por arquivo.
- **Controles inteligentes:** ao reproduzir, os controles desaparecem após aproximadamente 2,6 segundos sem interação e voltam com o mouse, toque ou teclado. Quando pausado, carregando ou com menu de volume aberto, permanecem acessíveis. O comportamento respeita navegação por teclado.
- **Barra de progresso fluida:** a posição visual da timeline é atualizada com `requestAnimationFrame` a partir de `video.currentTime`, em vez de avançar somente a cada evento `timeupdate` do navegador. O tempo exibido pode atualizar em intervalos, mas o traço avança suavemente sem inventar progresso.
- **Cache e limites:** o cache efêmero em RAM da API de compartilhamento pode reduzir solicitações repetidas ao Telegram. A primeira abertura continua dependendo da conexão e da sessão Telegram; a implementação ainda não realiza streaming direto de arquivos enormes.

Para receber a mudança: `git pull origin main`; reinicie o backend Python porque foi adicionada uma rota; recarregue o frontend com `Ctrl+Shift+R`. Valide localmente com um arquivo MP4 ou WebM pequeno e um link de compartilhamento novo.
