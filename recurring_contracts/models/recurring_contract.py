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

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self):
        for contract in self:
            contract.amount_total = sum(contract.line_ids.mapped("price_subtotal"))

    @api.depends("period_ids.invoice_id")
    def _compute_invoice_ids(self):
        for contract in self:
            contract.invoice_ids = contract.period_ids.invoice_id
            contract.invoice_count = len(contract.invoice_ids)

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

    def _generate_invoice(self, run_date):
        """Fatura um período do contrato de forma idempotente.

        A criação do período é protegida pela constraint UNIQUE
        (contract_id, date_start): se o período já foi faturado (cron
        reexecutado ou concorrente), o INSERT falha e o contrato é pulado
        sem duplicar fatura.
        """
        self.ensure_one()
        date_start = self.date_next_invoice or run_date
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

    @api.model
    def _cron_generate_invoices(self):
        today = fields.Date.context_today(self)
        due = self.search(
            [
                ("state", "=", "active"),
                ("date_next_invoice", "<=", today),
            ]
        )
        expired = due.filtered(lambda c: c.date_end and c.date_end < today)
        expired.action_close()
        for contract in due - expired:
            # savepoint por contrato: a falha de um não aborta os demais
            try:
                with self.env.cr.savepoint():
                    contract._generate_invoice(today)
            except Exception:
                _logger.exception(
                    "Falha ao gerar fatura do contrato %s; continuando.",
                    contract.name,
                )
