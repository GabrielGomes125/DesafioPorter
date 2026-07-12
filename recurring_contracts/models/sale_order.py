from odoo import api, fields, models


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

    def _action_cancel(self):
        res = super()._action_cancel()
        # Aditivo cancelado deixa de valer: os itens que ele trouxe saem do
        # contrato e param de ser cobrados nos próximos ciclos. As faturas já
        # emitidas não são afetadas.
        self.env["recurring.contract.line"].search(
            [("order_id", "in", self.ids)]
        ).unlink()
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("order_id.x_recurring_contract_id")
    def _compute_qty_to_invoice(self):
        """Linhas de aditivo são cobradas pelo contrato, nunca pelo pedido.

        Zerar a quantidade a faturar tira o pedido da fila "A Faturar" e fecha
        o caminho de cobrança em dobro (uma vez pelo pedido, outra pelo cron da
        recorrência).
        """
        addendum = self.filtered(lambda line: line.order_id.x_recurring_contract_id)
        addendum.qty_to_invoice = 0
        super(SaleOrderLine, self - addendum)._compute_qty_to_invoice()
