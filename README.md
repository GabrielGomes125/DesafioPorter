# DesafioPorter — Odoo 19

Ambiente de desenvolvimento Docker para o desafio técnico em Odoo 19 e os
módulos customizados (a começar por **`recurring_contracts`**). Todo o ambiente
sobe com um único comando — não é necessário instalar Odoo, Python ou
PostgreSQL na máquina.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose v2
  (no Windows, Docker Desktop com backend WSL 2; no Linux, Docker Engine).

> A imagem oficial `odoo:19` já traz todo o código-fonte do Odoo. Este
> repositório agrupa o ambiente Docker e os módulos: cada subpasta com
> `__manifest__.py` é um addon, e a pasta inteira é montada como `addons_path`
> em `/mnt/extra-addons`.

## Subir o ambiente

```bash
# 1. Copie o modelo de variáveis de ambiente
cp .env.example .env

# 2. Suba os containers (baixa as imagens na primeira vez)
docker compose up -d

# 3. Acompanhe a inicialização do Odoo
docker compose logs -f odoo
```

Quando aparecer `HTTP service (werkzeug) running`, acesse:

**http://localhost:8069**

Na primeira vez, o Odoo pede para criar uma base de dados:

- **Master Password:** `admin` (definida em `odoo.conf` → `admin_passwd`)
- Defina nome da base, e-mail e senha do usuário administrador.

### Instalar o módulo

Pela interface: ative o **modo desenvolvedor** (Configurações → Ativar modo
desenvolvedor), vá em **Apps → Atualizar lista de aplicativos**, procure por
_Recurring Contracts_ e clique em **Instalar**.

Ou por linha de comando (troque `<base>` pelo nome do seu banco):

```bash
docker compose run --rm odoo odoo -d <base> -i recurring_contracts --stop-after-init
```

### Para avaliar rápido: base com dados de demonstração

```bash
docker compose run --rm odoo odoo -d demo_db -i recurring_contracts \
  --with-demo --stop-after-init
```

O `--with-demo` é obrigatório: **desde a 19.0 o Odoo não instala dados de
demonstração por padrão**. Pela interface, equivale a marcar _"Carregar dados de
demonstração"_ ao criar a base.

Isso traz quatro contratos que cobrem o que a rotina precisa decidir — um em
dia, um com dois ciclos em atraso, um vencido e um em rascunho. Rodando a ação
agendada (Configurações → Técnico → Ações Agendadas → _Contratos Recorrentes:
gerar faturas_ → **Executar manualmente**), dá para ver de uma vez o
faturamento, a recuperação do atraso e o encerramento automático, sem cadastrar
nada à mão.

## O módulo `recurring_contracts`

Sistema de assinaturas para a CondoTech: clientes contratam produtos/serviços
de forma recorrente e o sistema fatura automaticamente a cada período,
reutilizando as estruturas nativas do Odoo (`res.partner`, `product.product`,
`sale.order`, `account.move`).

### Fluxo de uso

1. **Criar o contrato** — menu **Contratos Recorrentes → Contratos → Novo**:
   informe o cliente, a periodicidade (mensal, trimestral, semestral ou anual),
   a data de início e, opcionalmente, a data de término (vazio = sem prazo).
   Na aba **Itens**, adicione os produtos/serviços com quantidade e preço.
2. **Ativar** — botão **Ativar** no topo do formulário (exige ao menos um
   item). O contrato ganha o número sequencial `CTR/xxxxx` na criação e pode
   ser **Suspenso** (pausa o faturamento) ou **Encerrado** a qualquer momento.
3. **Faturamento automático** — a ação agendada
   _“Contratos Recorrentes: gerar faturas”_ roda diariamente e:
   - **encerra os contratos vencidos** (Data de Término no passado), sem
     faturar — mesmo que a próxima cobrança deles ainda estivesse no futuro;
   - para cada contrato **ativo** com **Próxima Fatura ≤ hoje**, gera uma
     **fatura de cliente postada** (`account.move`) com os itens do contrato,
     a descrição de cada linha trazendo o período coberto, e avança a Próxima
     Fatura conforme a periodicidade;
   - **se o contrato estiver atrasado**, fatura todos os períodos em aberto na
     mesma execução (um contrato ativado com início retroativo, ou que ficou
     sem cron por alguns dias, se acerta de uma vez);
   - registra cada período na aba **Períodos Faturados** — uma restrição UNIQUE
     no banco garante **idempotência** (reexecutar o cron não duplica fatura).

   Para disparar manualmente: Configurações → Técnico → Ações Agendadas →
   _Contratos Recorrentes: gerar faturas_ → **Executar manualmente**.
4. **Aditivos** — no contrato ativo, o botão **Criar Aditivo** abre um pedido
   de venda vinculado. Ao **confirmar** o pedido, as linhas são incorporadas
   aos itens do contrato (com o pedido de origem rastreado) e passam a ser
   cobradas nos próximos ciclos. O pedido em si fica como **“Nada a Faturar”**:
   quem cobra aquelas linhas é o contrato, então não há como faturá-las duas
   vezes. **Cancelar** o aditivo remove do contrato os itens que ele trouxe
   (as faturas já emitidas não são afetadas).
5. **Rastreabilidade** — smart buttons **Faturas** e **Aditivos** no topo do
   formulário; alterações de status/datas ficam no chatter (`mail.thread`).

> **Impostos:** o contrato mostra o **Valor por Ciclo** sem impostos. Eles são
> calculados na emissão da fatura, a partir do produto e da posição fiscal do
> cliente — assim uma mudança de alíquota vale já na próxima cobrança, em vez
> de ficar congelada no contrato.

### Rodar os testes do módulo

```bash
docker compose run --rm odoo odoo -d <base> -u recurring_contracts \
  --test-enable --test-tags /recurring_contracts --stop-after-init
```

Saída esperada: `0 failed, 0 error(s) of 16 tests`.

> Os comandos de linha usam `docker compose run --rm` (e não `exec`) de
> propósito: `run` passa pelo entrypoint da imagem, que injeta as credenciais
> do banco vindas do `.env`. Um `docker compose exec` executa o binário direto,
> sem entrypoint, e o Odoo tentaria o socket local em vez do serviço `db`.

## Estrutura do repositório

```
DesafioPorter/                  # raiz do repositório (ambiente + módulos)
├── docker-compose.yml          # ambiente: odoo (odoo:19) + db (postgres:16)
├── odoo.conf                   # addons_path, conexão ao banco, dev mode
├── .env.example                # modelo de variáveis (copie para .env)
├── README.md
└── recurring_contracts/        # módulo (sem nada de Docker dentro)
    ├── __manifest__.py
    ├── __init__.py
    ├── models/                 # contrato, itens, períodos e sale.order
    ├── data/                   # sequência CTR/ e ação agendada (cron)
    ├── views/                  # contrato (form/list/search/menu) e pedido
    ├── security/               # acessos (csv) e regras multiempresa (ir.rule)
    ├── demo/                   # contratos de exemplo para avaliar o fluxo
    ├── static/description/     # ícone do app
    └── tests/
```

> Módulos futuros entram como novas subpastas ao lado de `recurring_contracts/`
> — nenhuma configuração Docker vive dentro de um módulo.

## Comandos úteis

```bash
# Ver logs em tempo real (Ctrl+C sai sem parar o Odoo)
docker compose logs -f odoo

# Reiniciar o Odoo (após mexer em Python)
docker compose restart odoo

# Atualizar o módulo após mudanças (dados/estrutura/views)
docker compose run --rm odoo odoo -d <base> -u recurring_contracts --stop-after-init

# Rodar os testes do módulo
docker compose run --rm odoo odoo -d <base> -u recurring_contracts \
  --test-enable --stop-after-init

# Parar (mantém os dados)
docker compose stop

# Remover containers (mantém volumes/dados)
docker compose down

# Zerar TUDO, inclusive banco e filestore
docker compose down -v
```

## Desenvolvimento

- O `odoo.conf` está com `dev_mode = reload,qweb,xml`: alterações em Python
  (reload) e em views XML/QWeb são recarregadas sem rebuild da imagem. Mudanças
  de estrutura de dados/menu ainda pedem um `-u recurring_contracts`.
- A pasta do repositório é montada como volume no container (em
  `/mnt/extra-addons`), então editar os módulos no host reflete direto no Odoo.

## Portas

| Serviço            | Porta host | Porta container |
|--------------------|-----------|-----------------|
| Odoo (web)         | 8069      | 8069            |
| Odoo (longpolling) | 8072      | 8072            |
| PostgreSQL         | —         | 5432 (interno)  |

As portas do host podem ser ajustadas no `.env`.
