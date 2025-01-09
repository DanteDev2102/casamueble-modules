from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class AccountGenerateXlsx(models.TransientModel):
    _name = "generate_xlsx"

    date_from = fields.Date()
    date_to = fields.Date()

    def get_payments(self):
        domain = [
            ("partner_type", "=", "customer"),
            ("create_date", ">=", self.date_from),
            ("create_date", "<=", self.date_to),
        ]

        document_ids = list()

        for document in self.env["account.payment"].search(domain):
            document_ids.extend([document.id])

        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": "/account_custom_xlsx_report?document_ids=%s" % document_ids,
        }
