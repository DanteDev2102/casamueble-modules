from odoo import models, fields, api


class Product(models.Model):
    _inherit = "product.product"

    manpower_amount = fields.Float("Mano de Obra")

    margin = fields.Float("Margen de ganancia")

    @api.constrains("standard_price", "margin", "manpower_amount")
    def _check_sale_price(self):
        for product in self:
            product.lst_price = round(
                product.standard_price
                + product.manpower_amount
                + (product.lst_price * (product.margin / 100)),
                2,
            )
