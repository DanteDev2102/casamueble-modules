from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    fabric_id = fields.Many2one(
        "product.product", string="Tela", domain=[("fabric_ok", "=", True)]
    )

    bom_id = fields.Many2one("mrp.bom", string="Lista de Materiales")

    @api.constrains("product_id")
    def _check_bom_id(self):
        for line in self:
            if line.product_id.bom_ids:
                line.bom_id = line.product_id.bom_ids[0].id
                continue
            elif line.product_template_id.bom_ids:
                line.bom_id = line.product_template_id.bom_ids[0].id
                continue
