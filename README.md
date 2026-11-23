# Fila Acadêmica

Bot Matrix em Python que organiza uma fila FIFO de atendimento acadêmico. Alunos
enviam comandos pelo Element; professores autorizados chamam o próximo aluno e
finalizam o atendimento. Cada sala tem uma fila independente, persistida em SQLite.

Projeto individual de graduação para Sistemas Distribuídos. Demonstra comunicação
assíncrona, troca de eventos entre processos, autorização por identidade Matrix,
idempotência, persistência e tratamento de falhas. A aplicação usa um homeserver
existente; não implementa consenso nem replicação do banco da fila.

## Tecnologias e estrutura

Python 3.11+, `asyncio`, `matrix-nio 0.25.2`, `sqlite3` da biblioteca padrão,
`python-dotenv` e Element. Não requer interface web, contêineres ou outro
serviço além de um servidor Matrix existente.

```text
src/fila_academica/
  __init__.py
  main.py              # inicialização, logs e encerramento
  config.py            # configuração e validação
  matrix_client.py     # sincronização, recebimento e envio Matrix
  command_handler.py   # comandos, permissões e deduplicação de eventos
  queue_service.py     # regras da fila, sem dependência do Matrix
  database.py          # schema, conexões e transações SQLite
docs/arquitetura.md
.env.example
.gitignore
requirements.txt
pyproject.toml
```

## Instalação no Windows (PowerShell)

Instale Python 3.11 ou superior e execute na raiz deste projeto:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
Copy-Item .env.example .env
notepad .env
```

Se a política do PowerShell impedir a ativação, use diretamente o interpretador do
ambiente, sem alterar a política da máquina:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m fila_academica.main
```

O comando de instalação editável pode baixar o backend de build `setuptools`.

## Instalação no Linux

Tenha Python 3.11+ e o módulo `venv` instalados (em Debian/Ubuntu, o pacote
`python3-venv` pode ser necessário).

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
cp .env.example .env
nano .env
```

## Configuração

Edite `.env` antes de iniciar. Os valores fornecidos são exemplos fictícios.

```dotenv
MATRIX_HOMESERVER=https://matrix.example.org
MATRIX_USER_ID=@fila_bot:example.org
MATRIX_ACCESS_TOKEN=TOKEN_DA_CONTA_DO_BOT
MATRIX_ROOM_IDS=!sala_teste:example.org,!segunda_sala:example.org
PROFESSOR_IDS=@professor:example.org
DATABASE_PATH=data/fila.sqlite3
```

| Variável | Uso |
| --- | --- |
| `MATRIX_HOMESERVER` | URL HTTP(S) do homeserver que autentica a conta do bot; prefira HTTPS. |
| `MATRIX_USER_ID` | ID completo da conta do bot, começando com `@`. |
| `MATRIX_ACCESS_TOKEN` | Token de acesso da sessão dessa conta. |
| `MATRIX_ROOM_IDS` | IDs reais das salas permitidas, separados por vírgula e iniciados por `!`. |
| `PROFESSOR_IDS` | IDs completos dos professores autorizados, separados por vírgula. |
| `DATABASE_PATH` | Arquivo SQLite; a pasta é criada automaticamente. |

Variáveis já definidas no ambiente têm prioridade sobre `.env`. Execute a partir
da raiz: `.env` e caminhos relativos do banco são resolvidos pelo diretório atual.
IDs e permissões são comparados exatamente; nomes de exibição e aliases `#sala`
não identificam uma fila ou um professor. A lista de professores vale para todas
as salas configuradas. Não publique o `.env` nem copie tokens para logs.

Copie o ID de sala inteiro: tanto `!id:servidor` quanto IDs sem domínio são aceitos.
Salas de versão 12 podem usar o formato sem domínio, conforme a
[especificação Matrix](https://spec.matrix.org/v1.16/rooms/v12/).

### Conta e credenciais Matrix

1. Crie uma conta exclusiva para o bot em um servidor Matrix existente que aceite
   seu cadastro. Entre nela pelo Element; use perfis separados para alunos e professor.
2. Anote o ID completo da conta e a URL real do homeserver. O domínio do ID nem
   sempre coincide com o endereço HTTP do servidor; confirme nas informações da sessão.
3. No Element Web/Desktop, procure nas configurações da conta a opção de token de
   acesso (em algumas versões fica em **Ajuda e sobre** / **Access Token**).
   Os rótulos variam entre versões. Copie o token apenas para o `.env` local.
4. Se o cliente não expuser essa opção, use o fluxo oficial de login suportado
   pelo servidor. A API Matrix `POST /_matrix/client/v3/login` retorna
   `user_id` e `access_token` quando o servidor permite login por senha;
   servidores com SSO podem exigir o próprio fluxo do cliente. Este projeto não
   guarda senha nem implementa autenticação alternativa.
5. Mantenha a sessão correspondente ao token ativa. Sair dela ou revogá-la pode
   invalidar o token; nesse caso obtenha outro e atualize a configuração.

Referências oficiais: [autenticação Matrix](https://spec.matrix.org/latest/client-server-api/#authentication)
e [login](https://spec.matrix.org/latest/client-server-api/#post_matrixclientv3login).

### Sala de testes no Element

1. Na conta do professor, crie uma sala privada de teste **sem criptografia E2EE**.
   Esta base não inclui suporte a chaves ou descriptografia. Se a sala já for
   criptografada, crie outra sem criptografia em um cliente que ofereça essa opção.
2. Convide a conta do bot e as duas contas de alunos. Aceite o convite na conta
   do bot pelo Element antes de iniciar o programa; o bot não aceita convites sozinho.
3. Permita que a conta do bot envie mensagens na sala.
4. Nas configurações avançadas da sala, copie o **ID interno da sala**, começando
   com `!`, para `MATRIX_ROOM_IDS`. Não use o título nem um endereço começando com `#`.
5. Copie o ID completo do professor para `PROFESSOR_IDS`.

## Execução

Com o ambiente virtual ativado e o pacote instalado:

```bash
python -m fila_academica.main
```

Também é possível usar `fila-academica`. Aguarde o log **Bot pronto** antes de
enviar comandos. A primeira sincronização de cada execução é descartada como
histórico. Comandos enviados enquanto o bot estava desligado, ou durante esse
primeiro lote, não serão executados: reenvie-os após o log de prontidão.

Use `Ctrl+C` para encerrar. Reiniciar preserva a fila, o atendimento e o histórico
desde que `DATABASE_PATH` aponte para o mesmo arquivo. Não rode duas instâncias
nem mantenha o arquivo SQLite em uma pasta sincronizada ou unidade de rede durante
a execução; use um caminho local fora do OneDrive quando necessário.

## Comandos

Envie exatamente um comando por mensagem de texto, em minúsculas e sem argumentos.

| Comando | Função | Permissão |
| --- | --- | --- |
| `!ajuda` | Lista comandos. | Todos |
| `!entrar` | Entra na fila e informa a posição. | Todos |
| `!sair` | Sai apenas da fila de espera. | Todos |
| `!fila` | Mostra os alunos em ordem FIFO. | Todos |
| `!posicao` | Informa posição ou atendimento em andamento. | Todos |
| `!proximo` | Remove o primeiro da espera e inicia seu atendimento. | Professores configurados |
| `!finalizar` | Finaliza o atendimento ativo, mantendo seu histórico. | Professores configurados |
| `!status` | Mostra atendimento atual e quantidade em espera. | Todos |

Não é possível entrar novamente enquanto estiver esperando ou em atendimento.
Ao usar `!entrar`, o bot cumprimenta o aluno pelo nome de exibição na sala:
“Olá, Ana! Você entrou na fila de atendimento. Posição: 1.” Se o nome não estiver
disponível, usa o ID Matrix. A fila e as permissões continuam identificando cada
usuário pelo ID Matrix.

Cada sala admite um atendimento ativo; finalize-o antes de chamar outro aluno.
Um aluno pode participar de filas de salas diferentes. Sair da sala Matrix não
remove automaticamente o aluno da fila; ele deve usar `!sair` antes de sair.

## Demonstração com dois alunos e um professor

Use três sessões Element: Ana (`@ana:example.org`), Bruno (`@bruno:example.org`)
e professor (`@professor:example.org`), além da conta exclusiva do bot. Substitua
os IDs pelos reais. A demonstração depende de credenciais válidas e de comunicação
com um homeserver real. Comece com uma sala sem fila/atendimento e inicie o bot.

| Passo | Quem envia | Mensagem | Resultado esperado |
| --- | --- | --- | --- |
| 1 | Ana | `!entrar` | Posição 1. |
| 2 | Bruno | `!entrar` | Posição 2. |
| 3 | Ana | `!entrar` | Entrada duplicada recusada. |
| 4 | Bruno | `!posicao` | Posição 2. |
| 5 | Professor | `!fila` | Ana antes de Bruno. |
| 6 | Ana | `!proximo` | Permissão recusada. |
| 7 | Professor | `!proximo` | Ana em atendimento; Bruno na espera. |
| 8 | Professor | `!proximo` | Recusado até finalizar Ana. |
| 9 | Ana | `!sair` | Não cancela o atendimento. |
| 10 | Professor | `!status` | Ana em atendimento, 1 em espera. |
| 11 | Operador | `Ctrl+C` e reiniciar o bot | Aguardar novamente o log de prontidão. |
| 12 | Professor | `!status` | Mesmo estado persistido. |
| 13 | Professor | `!finalizar` | Atendimento de Ana finalizado. |
| 14 | Professor | `!proximo` | Bruno em atendimento. |
| 15 | Professor | `!finalizar` | Atendimento de Bruno finalizado. |
| 16 | Professor | `!proximo` | Fila vazia. |

Para demonstrar isolamento, configure uma segunda sala e envie `!fila` nela:
seu estado não depende da primeira. Para demonstrar saída, entre com Ana e Bruno,
envie `!sair` como Ana e consulte `!posicao` como Bruno: ele passa para a posição 1.

## Falhas e limitações conhecidas

- Uma instância, um processo escritor e um arquivo SQLite local. O bot e o banco
  são pontos únicos de falha. Não há alta disponibilidade ou replicação da fila.
- Apenas salas já ingressadas, autorizadas e sem E2EE. Mensagens próprias,
  não textuais, edições e textos que não começam com `!` são ignorados.
- FIFO é a ordem de inserção confirmada pelo bot no SQLite, não o horário dos
  dispositivos dos alunos. Entrega Matrix pode sofrer atraso.
- O token de sincronização fica na memória do SDK. Quedas de rede no mesmo
  processo retomam a sincronização incremental, com espera entre tentativas.
  Após reiniciar, o novo lote inicial é ignorado, incluindo comandos do período offline.
- Uma timeline limitada pelo servidor pode omitir eventos após longas desconexões.
  Esta base não busca lacunas pelo endpoint de histórico; consulte o estado e
  reenvie o comando se necessário.
- `event_id` e alteração da fila são confirmados na mesma transação. Se a resposta
  falhar depois do commit, o estado continua alterado e repetir o mesmo evento não
  executa o comando outra vez. Consulte `!status`/`!fila` com uma nova mensagem.
  Uma futura **outbox transacional**, com envio e retentativas separados, poderia
  recuperar respostas pendentes. Hoje não existe entrega exatamente uma vez da resposta.
- Erros locais do banco encerram a execução para revisão; não se prossegue
  silenciosamente após uma transação falhar. Não há recuperação automática de
  comandos perdidos após reiniciar nem cancelamento administrativo de atendimento.
- Histórico e IDs de eventos crescem sem expurgo automático. Não há migração de
  schema, backup automático, métricas ou políticas de retenção nesta base.

A API utilizada pode ser consultada na [documentação oficial do matrix-nio](https://matrix-nio.readthedocs.io/en/latest/nio.html).
As assinaturas foram verificadas também na versão instalada, fixada em `requirements.txt`.
