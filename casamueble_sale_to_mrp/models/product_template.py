from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fabric_ok = fields.Boolean(default=False)

    legs_ok = fields.Boolean(default=False)
