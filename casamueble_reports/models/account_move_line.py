from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_cm_new_sale = fields.Boolean(
        string='Es Venta Nueva (Casamueble)',
        compute='_compute_is_cm_new_sale',
        store=True,
        compute_sudo=True,
        help="Clasificación automática: Verdadero si el pago se realizó el mismo día que la factura."
    )

    @api.depends('payment_id', 'payment_id.reconciled_invoice_ids', 'payment_id.reconciled_invoice_ids.date', 'payment_id.date')
    def _compute_is_cm_new_sale(self):
        for line in self:
            is_new = False
            if line.payment_id:
                payment = line.payment_id
                # Lógica: Es venta nueva si alguna de las facturas conciliadas tiene la misma fecha que el pago
                if any(inv.date == payment.date for inv in payment.reconciled_invoice_ids):
                    is_new = True
            line.is_cm_new_sale = is_new
