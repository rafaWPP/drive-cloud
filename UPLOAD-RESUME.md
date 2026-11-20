# Uploads grandes com retomada — Drive Cloud 0.1.8

## O que já existe

Para arquivos **a partir de 8 MiB** e até **512 MiB**, o aplicativo faz upload em duas fases:

1. **PC → conector local:** envia partes de 1 MiB ao backend, verificadas por SHA-256. A posição recebida é mantida em um arquivo temporário privado e em metadados SQLite. Após interrupção, o usuário seleciona o **mesmo arquivo na mesma pasta do Drive Cloud** e a transferência local pode continuar do último offset confirmado. Partes duplicadas idênticas são aceitas sem acrescentar dados.
2. **Conector → Telegram:** ao completar as partes locais, o Telethon envia o arquivo ao canal privado e o catálogo recebe a referência. O Drive Cloud identifica uploads enviados com uma legenda contendo um identificador aleatório e pode recuperar a confirmação remota quando a resposta se perde.

**Limitação importante:** a retomada implementada é para a fase *PC → conector*. O envio do conector ao Telegram **não possui checkpoints de partes remotas recuperáveis** nesta versão. Se seu resultado for incerto (queda durante a confirmação do Telegram), o aplicativo bloqueia uma retransmissão automática potencialmente duplicada. Confira o canal e os registros antes de iniciar novamente.

## Teste de aceitação sugerido

- Enviar um arquivo descartável de 12 MiB por upload normal; conferir nome, tamanho e conteúdo baixado.
- Interromper a conexão com o conector após alguns blocos; selecionar o mesmo arquivo, confirmar que não começou no byte zero.
- Interromper depois que o upload local terminou e enquanto o conector envia ao Telegram; verificar o estado antes de repetir. Nunca apagar automaticamente a mensagem remota.
- Simular perda da resposta da parte: reenviar o mesmo bloco e confirmar offset idempotente. Enviar bytes diferentes com o mesmo offset e verificar resposta 409.
- Alterar o arquivo local durante uma pausa e tentar retomar; **não** usar um arquivo alterado para completar um upload parcial.
- Reiniciar o aplicativo após pausa da primeira fase e reabrir a mesma pasta; a mesma seleção deve usar a sessão local já criada.
- Confirmar isolamento entre contas/canais e o limite de 512 MiB.
- Testar falta de espaço em disco e interrupção durante o fechamento do aplicativo, sem perder catálogos existentes.

## Segurança e pendências

- O cache temporário privado ocupa espaço no disco do computador; a sessão não é apagada quando o usuário pausa.
- O frontend guarda apenas o ID aleatório do upload e uma impressão de início/fim de arquivo no armazenamento local. Isso identifica a provável mesma seleção, **não** prova o hash integral dos bytes.
- Ainda faltam: retomada de partes no próprio Telegram, política de limpeza/remoção de sessões abandonadas, escrita de downloads diretamente ao destino sem grandes Blobs no frontend, autenticação forte entre UI e backend, verificações de disco e testes reais em Linux e Windows.
- Esta branch ainda é **desenvolvimento**. Não usar arquivos insubstituíveis para testes nem mesclar sem verificação real.
