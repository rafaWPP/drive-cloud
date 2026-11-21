# Drive Cloud — desenvolvimento da sincronização e distribuição

Este plano reúne as etapas no mesmo projeto, mas **não significa que estão implementadas**. A prioridade é preservar dados existentes e avançar em alterações testáveis.

## Etapa 1 — Catálogo salvo no Telegram (em implementação nesta branch)

- Snapshot manual do catálogo JSON no canal privado de armazenamento.
- Consulta do snapshot mais recente, validação da conta e canal e download do JSON.
- Sem exclusão de arquivos e sem substituir automaticamente o SQLite local.
- Limite inicial de 10 mil itens e 2 MiB por snapshot.
- Necessário testar com uma conta Telegram real e dois dispositivos.
- Antes de restaurar automaticamente: validar cada nó, conflitos, histórico e integridade das referências.

## Etapa 2 — Reconciliação e restauração segura

- Recuperar catálogo ao entrar em um novo dispositivo sem perder alterações locais.
- Identificadores estáveis de dispositivo, revisões, tombstones de exclusão, detecção e resolução de conflitos.
- Sincronização incremental e índices para catálogos grandes, evitando sobrescrever mudanças concorrentes.
- Não apagar conteúdo remoto em caso de erro ou restauração incompleta.

## Etapa 3 — Pastas do PC

- Agente instalado Windows/Linux que observa diretórios escolhidos pelo usuário.
- Modo backup unidirecional antes de sincronização bidirecional.
- Controle de exclusões, renomeações, arquivos temporários, padrões de ignorar, links simbólicos e conflitos.
- Sincronização em segundo plano, pausas, histórico e retomada.

## Etapa 4 — Arquivos grandes

- Upload em partes conforme limites da API Telegram, integridade e ordem de blocos.
- Checkpoints duráveis e downloads com retomada.
- Limites de disco e memória, deduplicação opcional e recuperação de arquivos incompletos.

## Etapa 5 — Windows e Android

- Instaladores Windows assináveis, sidecar/local process e testes Windows.
- Projeto Android com acesso mediado a arquivos, permissões e regras de execução em segundo plano do Android.
- Não assumir que o executável Python de Linux funciona no Android.

## Etapa 6 — Compartilhamento, segurança e venda

- Compartilhamento com outros usuários sem expor sessão Telegram ou API local.
- Autenticação entre a interface e backend local, além da porta aleatória.
- Avaliar restrições/termos de uso do Telegram antes da distribuição comercial.
- Licenciamento de pagamento único, política de atualizações, instaladores e backups.
- Links públicos genéricos precisam de uma arquitetura própria: não surgem automaticamente sem servidor.

## Critério de conclusão

Uma etapa só estará pronta quando testes automatizados, builds de cada sistema e testes práticos passarem. A aprovação de um build Tauri não valida sincronização e recuperação entre máquinas.
