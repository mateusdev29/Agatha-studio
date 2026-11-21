# AGATHA SOUZA STUDIO — Gestão do Estúdio

Sistema administrativo **privado** para gestão de um estúdio de tatuagem (uso inicial: Agatha Souza).
É independente do site público *Agatha Souza Tattoo*: nenhum arquivo é compartilhado.

**Stack:** Python · Flask · SQLAlchemy · SQLite · Flask-Login · Flask-WTF · Flask-Migrate · HTML/CSS/JS vanilla · Chart.js (local).

## Módulos
Visão Geral · Dashboard · Agenda · Projetos · Orçamentos · Clientes · Anamnese · Estoque · Financeiro · Satisfação ·
Preferências Corporais · Configurações. Detalhes de cada regra de negócio na seção *Decisões e regras*.

## Requisitos
- Python 3.11 ou superior (testado em 3.12). No Windows, marque **"Add python.exe to PATH"** ao instalar.

## Iniciar (Windows) — um único comando
Dentro da pasta do projeto:
```bat
start.bat
```
Na primeira vez ele cria o ambiente virtual, instala as dependências, cria o `.env`, o banco e a administradora.
Nas próximas, só confere tudo (sem apagar nada) e sobe o servidor. Abra **http://127.0.0.1:5000**.
(No PowerShell use `.\start.bat`. No Mac/Linux: `./start.sh`.)

Variações: `start.bat setup` só prepara (não inicia) · `start.bat debug` inicia em modo debug · `start.bat login` aplica o login e a senha do `.env` (veja abaixo).

### O que o `start.bat` faz, nesta ordem
1. Procura Python 3.11+ (`py -3` ou `python`) e avisa com clareza se não achar.
2. Cria o `.venv` (e recria sozinho se a pasta foi movida e o venv quebrou). Só reinstala dependências se o `requirements.txt` mudou.
3. `python bootstrap.py`: cria o `.env` a partir do `.env.example` e preenche **apenas o que estiver em branco**
   (`SECRET_KEY` e, uma única vez, a senha da administradora). Nunca altera valor já preenchido.
4. `flask setup`: ver abaixo.
5. Escolhe a primeira porta livre a partir da 5000 e inicia o Flask.

### `flask --app wsgi setup` (alias `init`) — seguro e repetível
- Banco inexistente → cria; existente → mantém tudo. Executa só as migrations **pendentes**; se houver migration pendente
  e o banco já tiver dados, faz **backup antes** em `instance/backups/` (mantém os 5 últimos).
- Se o banco tiver tabelas mas **nenhum controle de migrations**, recusa e não toca em nada.
- Garante os dados-base (regiões do corpo, categorias, serviços, perguntas da anamnese) sem duplicar.
- Se **não existir nenhuma administradora ativa**, cria uma com `DEV_ADMIN_*` do `.env`. **Nunca** recria, sobrescreve nem
  troca a senha de usuário existente, e **nunca** gera senha nova a cada início. Em produção não cria usuário (use `create-user`).

## Primeiro login
Na primeira execução, o sistema cria o `.env` e gera uma senha aleatória para a administradora. O terminal mostra a senha uma vez; guarde-a.

- Para usar **outro e-mail ou senha**, edite `DEV_ADMIN_EMAIL` e `DEV_ADMIN_PASSWORD` no `.env` e rode **`start.bat login`**.
- **Já tinha um banco com outra senha (ou esqueceu)?** O `start.bat` normal nunca sobrescreve contas existentes, de propósito.
  Rode **`start.bat login`** uma vez: ele aplica o e-mail/senha do `.env` à conta (sem apagar nenhum dado) e destrava a conta se estiver bloqueada.
- A cada início o terminal mostra qual e-mail usar. A senha é a de `DEV_ADMIN_PASSWORD` no `.env`.
- Defina uma senha forte e exclusiva antes de colocar o sistema na internet.
- Comandos equivalentes: `flask --app wsgi set-login` (aplica o `.env`) e `flask --app wsgi reset-password` (pergunta e-mail e nova senha).

## Configurar o `.env`
| Variável | Descrição |
|---|---|
| `APP_ENV` | `development` (padrão) ou `production` |
| `SECRET_KEY` | Assina o login. **Tem de ser sempre a mesma** neste computador; o `start.bat` gera uma vez e grava. Manual: `python -c "import secrets; print(secrets.token_hex(32))"`. Obrigatória em produção. |
| `DATABASE_URL` | Opcional. Padrão: SQLite em `instance/studio.db` |
| `DEV_ADMIN_NAME` / `DEV_ADMIN_EMAIL` / `DEV_ADMIN_PASSWORD` | Login da administradora (só desenvolvimento). Senha com 10+ caracteres; em branco = o sistema gera e grava uma vez. Se a senha tiver `#` precedido de espaço ou aspas, coloque-a entre aspas. |
| `RESTIC_REPOSITORY` | Opcional. Repositório Restic remoto para backup cifrado; para Dropbox use `rclone:dropbox:Agatha-Studio-Backups`. |
| `RESTIC_PASSWORD_FILE` | Opcional. Caminho do arquivo local com a senha do repositório Restic. Mantenha-o fora da pasta do projeto e acessível somente à conta do Windows que executa o backup. |

Valores já definidos no ambiente real do Windows têm prioridade sobre o `.env`. O `.env` pode ser salvo pelo Bloco de Notas (BOM e CRLF são tratados).
Trocar `DEV_ADMIN_*` depois **não altera** o usuário existente: para mudar a senha use *Configurações > Perfil*.

## Primeira instalação em outro computador
1. Instale o Python 3.11+ (marcando "Add python.exe to PATH") e copie/extraia a pasta do projeto.
2. **Para levar os dados:** com o sistema **fechado**, copie `instance\studio.db` e a pasta `uploads\` (ou use `flask --app wsgi backup` e copie o arquivo de `instance\backups\`). **Não** copie `.venv` (o `start.bat` recria).
   Para uma instalação limpa, não copie `instance\`.
3. Execute `start.bat`. Se copiou o `.env`, ele é reaproveitado; senão é criado e a senha da administradora aparece uma vez na tela.

## Comandos avançados (continuam funcionando)
```bash
flask --app wsgi db upgrade        # migrations manualmente
flask --app wsgi seed-base         # dados-base (idempotente)
flask --app wsgi seed-dev-user     # [DEV] cria o usuário do .env (erra se já existir)
flask --app wsgi seed-demo         # [DEV] dados FICTÍCIOS marcados com [DEMO]
flask --app wsgi create-user       # [PRODUÇÃO] cria a usuária com senha digitada (mín. 10)
flask --app wsgi backup            # cópia consistente do banco em instance/backups/
flask --app wsgi reset-password    # esqueceu a senha? redefine UMA conta (pede e-mail e nova senha; destrava a conta)
flask --app wsgi run --debug       # servidor manual
```
Após alterar modelos: `flask --app wsgi db migrate -m "descrição"` e depois `db upgrade`.

## Login: se cair sozinho
- A sessão usa o cookie `agatha_studio_session` (nome próprio, para não colidir com outro app Flask em `127.0.0.1`, como o site público).
- A sessão não é derrubada por troca de rede (Wi-Fi/4G), então funciona no celular. Ela só se perde se a `SECRET_KEY` **mudar**.
- No celular pela rede local, inicie o Flask com `--host 0.0.0.0` e acesse `http://IP-DO-PC:5000`; mantenha `APP_ENV=development`
  (em `production` o cookie é `Secure` e o navegador o descarta em `http://`).

## Testes
```bash
python -m pytest
```
A suíte cobre cada módulo e também **testes transversais** que valem para todas as rotas (inclusive futuras): exigem
login, rejeitam POST sem CSRF, não aceitam GET em rotas que alteram estado e não fazem consultas N+1 nas listas.

## Produção (checklist)
1. `APP_ENV=production` e `SECRET_KEY` definida (o sistema **não inicia** sem ela). Cookies saem `Secure`/`HttpOnly`/`SameSite=Lax`.
2. Sirva por HTTPS atrás de um servidor WSGI (ex.: `gunicorn wsgi:app`), com **uma instância** (SQLite) e proxy reverso.
3. **Não exponha `uploads/` nem `instance/`** no servidor web: as imagens só são servidas pelo Flask, autenticadas.
4. **Backups:** rode `flask --app wsgi backup` (cópia consistente em `instance/backups/`, mesmo com o sistema aberto) e guarde também a pasta `uploads/`.
5. Crie a usuária com `flask create-user`; não use o seed de desenvolvimento.
6. A expiração de orçamentos roda no primeiro acesso logado de cada hora; não requer tarefa agendada.

### Backup externo diário (Windows)
O comando `flask --app wsgi backup-offsite` usa Restic para cifrar e enviar uma cópia consistente do SQLite e a pasta `uploads/` ao Dropbox. Instale Restic e rclone, coloque ambos no `PATH` do Windows e faça uma única configuração OAuth com `rclone config`, usando o nome do remoto `dropbox`. O rclone guarda o token da conta no perfil do Windows; não envie esse arquivo nem dados reais de clientes para GitHub.

Crie uma senha longa e exclusiva para o repositório Restic e guarde-a em um arquivo fora do projeto, com acesso limitado à conta do Windows do estúdio. O Dropbox não consegue descriptografar o conteúdo sem essa senha: guarde uma cópia segura dela separadamente. Inicialize o repositório uma só vez (substitua o caminho pelo real):
```powershell
restic -r rclone:dropbox:Agatha-Studio-Backups --password-file 'C:\caminho\seguro\restic-password.txt' init
```
No `.env`, configure `RESTIC_REPOSITORY=rclone:dropbox:Agatha-Studio-Backups` e `RESTIC_PASSWORD_FILE` com o mesmo caminho do arquivo de senha. Em seguida, rode o comando manualmente e confirme que criou um snapshot:
```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi backup-offsite
restic -r rclone:dropbox:Agatha-Studio-Backups --password-file 'C:\caminho\seguro\restic-password.txt' snapshots
```

Depois do teste manual, crie a tarefa diária (padrão: 22:00) no PowerShell, dentro da pasta do projeto:
```powershell
.\scripts\install_daily_backup_task.ps1
```
Para escolher outro horário use `-Time '23:30'`. A tarefa roda sob a conta atual do Windows quando ela estiver conectada; se o computador estiver desligado, o Task Scheduler tenta executá-la no próximo login. O Histórico do Agendador de Tarefas mostra o resultado. Cada execução mantém também o snapshot local do banco (os cinco mais recentes); os snapshots remotos não são apagados automaticamente, para preservar histórico até definirmos uma política de retenção.

## Segurança
- Senhas com hash (scrypt); bloqueio de 15 min após 5 falhas; erro de login genérico; `?next=` validado; logout só por POST.
- Todas as rotas administrativas exigem login; CSRF em todo POST; ORM (sem SQL montado à mão); validação no servidor.
- CSP restritiva (`script-src 'self'`, sem `style=""`/`<script>` inline), `nosniff`, `X-Frame-Options: DENY`; fontes e Chart.js locais, sem CDN.
- **Uploads:** conteúdo validado com Pillow (a extensão enviada é ignorada), imagem re-codificada (remove EXIF/GPS e cargas anexadas),
  nome gerado pelo servidor, limites de tamanho/pixels/quantidade, servido só por rota autenticada.
- **Anamnese (dado de saúde):** ficha imutável com aceite e assinatura; nunca aparece em dashboards, gráficos, logs ou na página do
  cliente; a página de leitura usa `Cache-Control: no-store`.
- Chaves estrangeiras do SQLite ligadas (por padrão ele as ignora). O modo WAL **não** é usado de propósito: o banco é um único arquivo, seguro de copiar.

## Decisões e regras
**Gerais:** dinheiro em centavos inteiros (digita-se `1.200,50`); enums gravados como texto; horários da agenda em horário local
do estúdio, `created_at` em UTC; busca sem distinção de maiúsculas, mas **não ignora acentos** (limitação do SQLite).

**Clientes:** arquivar em vez de excluir (preserva histórico). **Projetos:** não são excluídos (use *Cancelado*); uploads de referência com miniatura.
**Orçamentos:** status por máquina de estados; só envia/aprova com valor definido e validade em dia; *aprovar e criar projeto* é atômico
e nunca duplica; com projeto criado o orçamento fica travado; expiração automática; texto pronto para WhatsApp (sem observações internas).
**Agenda:** semana começa na segunda; sem sobreposição de horários; remarcar preserva o histórico e leva o sinal junto; só marca *realizado* após o início.
**Sinal no Financeiro:** no atendimento, *Lançar no Financeiro* cria uma receita vinculada (categoria *Sinal / Entrada*, com cliente, projeto, forma de
pagamento e situação *recebido* ou *a receber*). Só pode existir **um** lançamento de sinal por atendimento (também garantido por um índice único no
banco). Depois de lançado, o **Financeiro é a fonte da verdade**: alterar o valor lá atualiza o atendimento, cliente e projeto seguem o atendimento, e o
campo do sinal fica travado na Agenda. **Remarcar** leva o lançamento para o novo atendimento (sem duplicar). **Cancelar nunca altera o dinheiro**: o
sistema avisa e a devolução fica a seu critério no Financeiro. Excluir o lançamento libera o atendimento para lançar de novo.
**Financeiro:** só lançamentos *pagos* entram em faturamento/despesas/lucro; pendências aparecem à parte.
**Estoque:** saldo nunca negativo; cada movimentação guarda a variação e o saldo resultante; quantidade só muda por movimentação.
**Satisfação:** nota de 0 a 10; NPS = %promotores (9-10) − %detratores (0-6), exibido a partir de 5 avaliações; uma avaliação por atendimento.
**Dashboard** (definições também em `app/services/analytics_service.py`): ticket médio = faturamento ÷ atendimentos realizados; recorrentes =
clientes com atendimento realizado no período e ao menos 2 realizados até o fim dele.
**Preferências Corporais:** conta projetos (exceto cancelados) por região; mapa SVG com `data-region` pronto para futura interatividade.

## Estrutura
```
app/
  models/    # SQLAlchemy (um arquivo por domínio) + enums.py
  routes/    # blueprints (um por módulo)
  services/  # regras de negócio, sem request/response
  forms/     # Flask-WTF
  utils/     # dinheiro, datas, períodos, formatação, segurança
  seeds/     # dados de demonstração (separados do código)
  templates/ static/{css,js,fonts,vendor}
config.py  wsgi.py  migrations/  tests/  uploads/{projects,clients}/
```
Fontes: Bodoni Moda e Instrument Sans (SIL OFL, em `static/fonts`). Gráficos: Chart.js (MIT, em `static/vendor`).

## Limitações conhecidas
- Uma única profissional (modelo de agenda, permissões e conflito de horário assumem isso); existe o campo `role` para evoluir.
- O sinal é lançado por ação sua (botão no atendimento), não automaticamente; só o sinal tem vínculo com a Agenda (o pagamento do restante é lançado no Financeiro).
- Não há envio de e-mail/WhatsApp nem link público de anamnese (a estrutura de token existe no modelo, sem rota).
- Sem integração com o site público (a separação entre os sistemas foi mantida de propósito).
