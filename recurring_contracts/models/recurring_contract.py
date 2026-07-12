import logging

from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

_PERIODICITY_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
}


class RecurringContract(models.Model):
    _name = "recurring.contract"
    _description = "Contrato Recorrente"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Número",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("Novo"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
    )
    date_start = fields.Date(
        string="Data de Início",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    periodicity = fields.Selection(
        [
            ("monthly", "Mensal"),
            ("quarterly", "Trimestral"),
            ("semiannual", "Semestral"),
            ("annual", "Anual"),
        ],
        string="Periodicidade",
        required=True,
        default="monthly",
        tracking=True,
    )
    date_next_invoice = fields.Date(
        string="Próxima Fatura",
        tracking=True,
    )
    date_end = fields.Date(
        string="Data de Término",
        help="Vazio significa contrato sem prazo determinado.",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Rascunho"),
            ("active", "Ativo"),
            ("suspended", "Suspenso"),
            ("closed", "Encerrado"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "recurring.contract.line",
        "contract_id",
        string="Itens",
    )
    period_ids = fields.One2many(
        "recurring.contract.period",
        "contract_id",
        string="Períodos Faturados",
    )
    amount_total = fields.Monetary(
        string="Valor Total",
        compute="_compute_amount_total",
        store=True,
        currency_field="currency_id",
    )
    invoice_ids = fields.Many2many(
        "account.move",
        string="Faturas",
        compute="_compute_invoice_ids",
    )
    invoice_count = fields.Integer(
        string="Qtde. de Faturas",
        compute="_compute_invoice_ids",
    )
    sale_order_ids = fields.One2many(
        "sale.order",
        "x_recurring_contract_id",
        string="Pedidos (Aditivos)",
    )
    sale_order_count = fields.Integer(
        string="Qtde. de Aditivos",
        compute="_compute_sale_order_count",
    )

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self):
        for contract in self:
            contract.amount_total = sum(contract.line_ids.mapped("price_subtotal"))

    @api.depends("period_ids.invoice_id")
    def _compute_invoice_ids(self):
        for contract in self:
            contract.invoice_ids = contract.period_ids.invoice_id
            contract.invoice_count = len(contract.invoice_ids)

    @api.depends("sale_order_ids")
    def _compute_sale_order_count(self):
        for contract in self:
            contract.sale_order_count = len(contract.sale_order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("Novo"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("recurring.contract")
                    or _("Novo")
                )
            if not vals.get("date_next_invoice"):
                vals["date_next_invoice"] = vals.get(
                    "date_start", fields.Date.context_today(self)
                )
        return super().create(vals_list)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for contract in self:
            if contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError(
                    _("A data de término não pode ser anterior à data de início.")
                )

    @api.constrains("state", "line_ids")
    def _check_active_has_lines(self):
        for contract in self:
            if contract.state == "active" and not contract.line_ids:
                raise ValidationError(
                    _("Não é possível ativar um contrato sem itens.")
                )

    def action_activate(self):
        self.write({"state": "active"})

    def action_suspend(self):
        self.write({"state": "suspended"})

    def action_close(self):
        self.write({"state": "closed"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    def action_create_addendum(self):
        self.ensure_one()
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_id.id,
                "company_id": self.company_id.id,
                "origin": self.name,
                "x_recurring_contract_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Aditivo"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
        }

    def _add_lines_from_sale_order(self, order):
        """Incorpora as linhas do pedido confirmado como itens do contrato.

        Idempotente: linhas de pedido já incorporadas (sale_line_id presente)
        e linhas de seção/nota (display_type) são ignoradas.
        """
        self.ensure_one()
        incorporated = self.line_ids.sale_line_id
        new_lines = order.order_line.filtered(
            lambda line: not line.display_type and line not in incorporated
        )
        return self.env["recurring.contract.line"].create(
            [
                {
                    "contract_id": self.id,
                    "product_id": line.product_id.id,
                    "name": line.name,
                    "quantity": line.product_uom_qty,
                    "price_unit": line.price_unit,
                    "product_uom_id": line.product_uom_id.id,
                    "order_id": order.id,
                    "sale_line_id": line.id,
                }
                for line in new_lines
            ]
        )

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Faturas"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "context": {"create": False},
        }

    def action_view_sale_orders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aditivos"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("x_recurring_contract_id", "=", self.id)],
            "context": {"create": False},
        }

    def _get_next_invoice_date(self, from_date):
        self.ensure_one()
        return from_date + relativedelta(months=_PERIODICITY_MONTHS[self.periodicity])

    def _prepare_invoice_vals(self, date_start, date_end):
        self.ensure_one()
        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "invoice_date": date_start,
            "invoice_origin": self.name,
            "invoice_line_ids": [
                Command.create(line._prepare_invoice_line_vals())
                for line in self.line_ids
            ],
        }

    def _generate_invoice(self):
        """Fatura o período corrente do contrato, de forma idempotente.

        A criação do período é protegida pela constraint UNIQUE
        (contract_id, date_start): se o período já foi faturado (cron
        reexecutado ou concorrente), o INSERT falha e o contrato é pulado
        sem duplicar fatura.
        """
        self.ensure_one()
        date_start = self.date_next_invoice
        next_date = self._get_next_invoice_date(date_start)
        date_end = next_date - relativedelta(days=1)
        try:
            with self.env.cr.savepoint():
                period = self.env["recurring.contract.period"].create(
                    {
                        "contract_id": self.id,
                        "date_start": date_start,
                        "date_end": date_end,
                    }
                )
        except IntegrityError:
            _logger.info(
                "Contrato %s já faturado para o período iniciado em %s; pulando.",
                self.name,
                date_start,
            )
            return self.env["account.move"]
        move = self.env["account.move"].create(
            self._prepare_invoice_vals(date_start, date_end)
        )
        move.action_post()
        period.invoice_id = move
        self.date_next_invoice = next_date
        return move

    def _generate_invoices_until(self, run_date):
        """Fatura todos os períodos em aberto até run_date.

        Um contrato pode acumular mais de um período pendente (ativado com data
        de início retroativa, cron parado por alguns dias, contrato reativado),
        então uma execução pode gerar mais de uma fatura.
        """
        self.ensure_one()
        moves = self.env["account.move"]
        while self.date_next_invoice <= run_date:
            move = self._generate_invoice()
            if not move:
                # Período já faturado: a próxima data não avança, e parar aqui
                # é o que impede o laço de girar para sempre.
                break
            moves |= move
        return moves

    @api.model
    def _cron_generate_invoices(self):
        today = fields.Date.context_today(self)
        active_domain = [("state", "=", "active")]
        # Encerrar os vencidos antes de faturar: um contrato que passou da data
        # de término não gera fatura, e precisa ser encerrado mesmo que a
        # próxima cobrança ainda esteja no futuro.
        self.search(active_domain + [("date_end", "<", today)]).action_close()
        for contract in self.search(
            active_domain + [("date_next_invoice", "<=", today)]
        ):
            # savepoint por contrato: a falha de um não aborta os demais
            try:
                with self.env.cr.savepoint():
                    contract._generate_invoices_until(today)
            except Exception:
                _logger.exception(
                    "Falha ao gerar fatura do contrato %s; continuando.",
                    contract.name,
                )
