from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
