from odoo import api, fields, models


class RecurringContractPeriod(models.Model):
    _name = "recurring.contract.period"
    _description = "Período Faturado de Contrato Recorrente"
    _order = "date_start desc, id desc"

    _uniq_contract_period = models.Constraint(
        "UNIQUE(contract_id, date_start)",
        "Já existe faturamento para este contrato neste período.",
    )

    contract_id = fields.Many2one(
        "recurring.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_start = fields.Date(string="Início do Período", required=True)
    date_end = fields.Date(string="Fim do Período", required=True)
    invoice_id = fields.Many2one(
        "account.move",
        string="Fatura",
        ondelete="set null",
        index=True,
    )
    name = fields.Char(string="Período", compute="_compute_name")

    @api.depends("date_start")
    def _compute_name(self):
        for period in self:
            period.name = (
                period.date_start.strftime("%m/%Y") if period.date_start else ""
            )
