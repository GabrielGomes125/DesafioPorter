from odoo import api, fields, models


class RecurringContractLine(models.Model):
    _name = "recurring.contract.line"
    _description = "Item de Contrato Recorrente"

    contract_id = fields.Many2one(
        "recurring.contract",
        string="Contrato",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Produto",
        required=True,
    )
    name = fields.Char(
        string="Descrição",
        compute="_compute_name",
        store=True,
        readonly=False,
    )
    quantity = fields.Float(
        string="Quantidade",
        required=True,
        default=1.0,
        digits="Product Unit of Measure",
    )
    price_unit = fields.Float(
        string="Preço Unitário",
        compute="_compute_price_unit",
        store=True,
        readonly=False,
        digits="Product Price",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        compute="_compute_product_uom_id",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        related="contract_id.currency_id",
        store=True,
    )
    price_subtotal = fields.Monetary(
        string="Subtotal",
        compute="_compute_price_subtotal",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("product_id")
    def _compute_name(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.display_name

    @api.depends("product_id")
    def _compute_price_unit(self):
        for line in self:
            if line.product_id:
                line.price_unit = line.product_id.list_price

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id

    @api.depends("quantity", "price_unit")
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit
