# Downloads nativos no desktop — Drive Cloud 0.1.9 (desenvolvimento)

## O que mudou

A tela **Meu Drive → Baixar** deixou de carregar o arquivo inteiro em um `Blob` do WebView em Linux e Windows.

- **Linux / Windows (Tauri):** o aplicativo abre o seletor nativo de destino, solicita o arquivo ao conector local, grava os bytes em partes diretamente no disco e só disponibiliza o arquivo final após confirmar o número de bytes recebido.
- **Navegador:** o navegador recebe um link de download com nome indicado pelo servidor, usando o gerenciador de downloads do próprio navegador, sem montar um `Blob` de 512 MB no JavaScript.
- **Backend:** baixa do canal Telegram para um arquivo temporário privado, confere o tamanho contra os metadados do catálogo e envia o download com o nome correto; limpa o arquivo temporário após a resposta.
- **Sem sobrescrever arquivos:** mesmo quando o destino já existe, a rotina nativa retorna uma mensagem de erro e mantém o arquivo anterior inalterado.
- **Sem acesso arbitrário a caminhos:** o nome sugerido é normalizado e o destino é escolhido por diálogo do sistema no backend Rust; a interface não pode passar um caminho para a operação.
- **Limite atual:** 512 MiB por arquivo (o mesmo limite conservador do upload).

## Testes antes de colocar em produção

1. Usar **arquivos descartáveis** de 1 MB, 20 MB e 200 MB no canal Telegram.
2. Baixar cada arquivo pelo aplicativo Linux/Windows e comparar o SHA-256 com o original.
3. Tentar salvar no destino de um arquivo existente; confirmar que o original não é alterado.
4. Cancelar o diálogo antes de escolher um caminho; confirmar que nenhum arquivo é criado.
5. Cortar a internet ou parar o conector durante o download; a versão incompleta **não deve se tornar o arquivo final**.
6. Testar disco cheio, permissões de pasta e uma pasta removida após o diálogo.
7. Confirmar nome, extensão e conteúdo de arquivos com caracteres internacionais.
8. Repetir os testes no navegador, que agora usa o fluxo de download padrão do browser.

## Limites ainda pendentes

- O download ainda **não retoma por intervalo de bytes** após fechar o aplicativo. Se falhar, inicia outra transferência.
- O backend pode usar espaço temporário equivalente ao tamanho do arquivo, e o aplicativo usa espaço temporário adicional no diretório escolhido. É necessário espaço livre em ambas as unidades.
- Downloads de pastas ZIP ainda seguem o fluxo anterior, com limite próprio.
- Uma compilação aprovada não comprova testes de integridade de ponta a ponta com Telegram ou discos reais.
- A PR #2 deve permanecer em **draft** até a validação prática; não utilizar arquivos únicos ou insubstituíveis.
