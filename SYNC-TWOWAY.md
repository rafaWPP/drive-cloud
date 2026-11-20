# Sincronização em duas direções — versão de desenvolvimento

A atualização desta branch é **experimental do ponto de vista de integridade de dados**, mesmo que o app não apresente rótulos experimentais na interface. Não usar como backup único ou com documentos insubstituíveis.

## Como funciona

- **Backup** (padrão): lê arquivos da pasta local, envia novos/alterados ao canal Telegram. Não propaga exclusões do PC. Um snapshot do catálogo é enviado após cada lote concluído, limitado a 2 MiB.
- **Duas direções** (ativação explícita por pasta): procura snapshots recentes do catálogo no canal privado, faz *união aditiva* dos registros ausentes, baixa arquivos que estão na pasta remota e envia alterações locais. Roda manualmente ou, quando habilitado, pelo agendador a cada 2 minutos.
- **Conflitos**: nunca substitui um arquivo local ao recuperar do Telegram. Conteúdos divergentes produzem arquivos com o sufixo `(Telegram-<id>)`. Uma cópia já existente é reutilizada quando idêntica; caso contrário, cria-se novo nome seguro.
- **Deleções**: não são propagadas entre máquinas. Revisões anteriores ficam referenciadas na lixeira do catálogo e suas mensagens não são apagadas pela sincronização.
- **Segurança**: cada catálogo importado é validado contra a conta/canal ativos; caminhos remotos não podem escapar da pasta escolhida; arquivos são recebidos inicialmente na pasta privada do aplicativo.
- **Transferências**: uploads/downloads têm limite atual de 512 MiB por arquivo. Lotes de até três arquivos por rodada. Não há retomada de bytes/checkpoints após interrupção.

## Teste entre dois computadores

1. **Use somente arquivos descartáveis** e reserve outra cópia de tudo.
2. No PC A, conecte a conta Telegram, crie um backup de pasta, faça a sincronização e verifique a opção de catálogo em **Backups**.
3. No PC B, conecte **a mesma conta e canal privado**, abra **Sincronização → Buscar backups de outros dispositivos no Telegram**, escolha uma pasta local vazia e vincule o mesmo **Backup • nome**.
4. Clique em **Recuperar do Telegram**, analise a contagem e confirme. Confirme que arquivos novos foram baixados.
5. Edite arquivos com o mesmo nome nos dois computadores; execute a sincronização em modo **Duas direções** e verifique que nenhum arquivo local foi substituído e que as cópias conflitantes foram preservadas.
6. Exclua um arquivo no PC e confirme que a mensagem remota ainda existe no canal.
7. Reinicie ambos os apps e repita a sincronização verificando que não surgem cópias repetidas idênticas.

## Limitações importantes

- Histórico de snapshots atualmente limitado a **120** mensagens de catálogo para conciliação. Ao atingir o limite, a importação segura retorna erro e pede manutenção. Não se apagam snapshots automaticamente.
- Conflitos de **metadados** (renomear/mover a mesma entrada em dispositivos diferentes, favoritos, lixeira) não são mesclados: a versão local é preservada e a diferença é reportada.
- Não há bloqueio/consenso distribuído entre dispositivos, nem garantia de uma ordem total de eventos. É uma base conservadora *add-only*, não um mecanismo de sincronização distribuída final.
- Reconciliação de arquivos com nomes modificados é tratada como criação de arquivo novo; exclusões são ignoradas.
- O sistema ainda requer testes reais extensivos em Linux/Windows e não possui agente Android.
- O aplicativo não oferece compartilhamento público seguro nem licença comercial nesta branch.

**Critério de release:** build e testes CI passando não bastam; validar o fluxo inteiro com dois computadores e testar alterações concorrentes, rede offline, quedas de energia, arquivos grandes, permissões, nomes reservados e pouco espaço em disco.
