from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()

        for order in self:
            if not order.mrp_production_ids:
                return res

            lines = order.order_line.filtered(lambda x: x.product_id.type == "product")

            for mrp in order.mrp_production_ids:
                line = lines.filtered(lambda x: x.product_id.id == mrp.product_id.id)
                for move in mrp.move_raw_ids:
                    move.quantity_done = move.product_uom_qty
                    move._action_done()

        return res
