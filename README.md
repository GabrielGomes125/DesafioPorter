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

👉 **http://localhost:8069**

Na primeira vez, o Odoo pede para criar uma base de dados:

- **Master Password:** `admin` (definida em `odoo.conf` → `admin_passwd`)
- Defina nome da base, e-mail e senha do usuário administrador.

### Instalar o módulo

Pela interface: ative o **modo desenvolvedor** (Configurações → Ativar modo
desenvolvedor), vá em **Apps → Atualizar lista de aplicativos**, procure por
_Recurring Contracts_ e clique em **Instalar**.

Ou por linha de comando (troque `<base>` pelo nome do seu banco):

```bash
docker compose exec odoo odoo -d <base> -i recurring_contracts --stop-after-init
```

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
    ├── models/
    ├── security/
    │   └── ir.model.access.csv
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
docker compose exec odoo odoo -d <base> -u recurring_contracts --stop-after-init

# Rodar os testes do módulo
docker compose exec odoo odoo -d <base> -u recurring_contracts \
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
