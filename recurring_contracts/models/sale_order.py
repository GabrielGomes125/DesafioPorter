from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_recurring_contract_id = fields.Many2one(
        "recurring.contract",
        string="Contrato (Aditivo)",
        copy=False,
        index=True,
        help="Contrato recorrente ao qual este pedido será incorporado "
        "como aditivo ao ser confirmado.",
    )

    def action_confirm(self):
        res = super().action_confirm()
        for order in self.filtered("x_recurring_contract_id"):
            order.x_recurring_contract_id._add_lines_from_sale_order(order)
        return res
