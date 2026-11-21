# Vincular pastas — Drive Cloud 0.1.18 (desenvolvimento)

## Objetivo

Permitir que o usuário **escolha uma pasta do computador e uma pasta dentro do Meu Drive** para vincular as duas, de maneira semelhante ao Google Drive.

Exemplo:

- PC: `/home/rafa/Área de trabalho/sinc`
- Meu Drive: `Projetos / Sinc`

O usuário pode escolher **qualquer pasta existente no catálogo do Meu Drive, inclusive subpastas**, ou criar uma pasta nova na raiz do Meu Drive. Isso **não cria outro canal privado Telegram**.

## Fluxo de configuração

1. Escolher pasta do computador (diálogo nativo Linux/Windows).
2. Escolher pasta correspondente do Meu Drive (árvore de pastas em um seletor escuro) ou digitar o nome de uma nova pasta.
3. Selecionar:
   - **Somente backup:** PC → Meu Drive.
   - **Duas direções:** PC ↔ Meu Drive, com confirmação antes da ativação.
   - **Automático:** opção explícita, desativada por padrão, verifica a cada ~2 minutos.
4. Clicar em **Analisar** para examinar os arquivos do PC e depois **Vincular pastas**. Nada é enviado ao Telegram só por analisar os arquivos.
5. A lista mostra claramente o caminho local e o caminho correspondente no Meu Drive, e permite sincronizar manualmente, recuperar arquivos e pausar o automático.

## Segurança e limites

- Não permite vincular pasta de outra conta, com pai na lixeira, caminho de pastas em ciclo, ou pasta remota já vinculada a outra pasta local deste computador.
- Não permite criar uma pasta duplicada na raiz com nome idêntico a outra pasta ativa.
- Quando cria uma pasta remota, tenta salvar imediatamente o catálogo no canal privado para que outros dispositivos possam descobri-la. Se falhar, exibe um aviso e a opção de salvar o catálogo em Backups.
- As exclusões locais ou remotas **não** são propagadas automaticamente; versões divergentes são preservadas.
- Processa até **3 arquivos por execução**, no máximo 512 MiB por arquivo. O automático roda aproximadamente a cada 2 minutos, não é sincronização instantânea.
- **Limitação importante:** a implementação ainda não tem detecção completa de renomeações, exclusões simultâneas ou correspondência por hash de arquivos pré-existentes nas duas pastas. Ao vincular pastas que já possuem o mesmo nome de arquivo em ambos os lados, podem ocorrer versões duplicadas. Para o primeiro teste, usar pastas de arquivos descartáveis.
- Vincular uma pasta existente no Meu Drive não transfere todo o conteúdo imediatamente; execute **Sincronizar agora** (com duas direções) ou **Recuperar do Telegram**, e revise conflitos.
- Sincronização entre computadores depende de atualizar o catálogo a partir do Telegram e apontar cada computador para a mesma pasta remota; a distribuição contínua do catálogo ainda está em desenvolvimento.

## Teste de aceitação

1. Criar uma pasta `Teste` no Meu Drive.
2. Escolher uma pasta local vazia, vincular à pasta `Teste` e selecionar duas direções.
3. Criar um arquivo descartável no PC; executar sincronização e confirmar que aparece em `Meu Drive / Teste`.
4. Em outro computador, atualizar o catálogo, escolher uma pasta local vazia e vincular ao mesmo `Meu Drive / Teste`. Usar **Recuperar do Telegram** e confirmar o conteúdo.
5. Alterar um arquivo nos dois lados separadamente; conferir cópias de conflito e ausência de sobrescrita.
6. Desativar o automático, fechar/reabrir e confirmar que o vínculo e as configurações persistem.
7. Mover a pasta remota para a lixeira; confirmar que o envio é bloqueado e nenhum outro destino é criado automaticamente.
8. Testar novo vínculo em subpasta e criar pasta nova na raiz do Meu Drive.

**Ainda não usar para arquivos únicos ou críticos.** Esta PR permanece em desenvolvimento.
