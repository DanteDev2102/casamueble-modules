from odoo import models, fields
from bs4 import BeautifulSoup
from datetime import datetime
import requests
import logging

_logger = logging.getLogger(__name__)


class ResCurrencyRate(models.Model):
    _inherit = "res.currency"

    sync_rate = fields.Boolean()

    def get_bcv_rate(self):
        url = "https://www.bcv.org.ve/"
        req = requests.get(url, verify=False)

        status_code = req.status_code

        if status_code == 200:
            html = BeautifulSoup(req.text, "html.parser")
            dolar = html.find("div", {"id": "dolar"})
            dolar = str(dolar.find("strong")).split()
            dolar = str.replace(dolar[1], ".", "")
            dolar = float(str.replace(dolar, ",", "."))

            return dolar

        return False

    def update_rate(self):
        for currency in self:
            rate = currency.get_bcv_rate()

            if not rate:
                return

            currency.env["res.currency.rate"].sudo().create(
                {
                    "currency_id": currency.id,
                    "name": datetime.now(),
                    "company_rate": rate,
                    "company_id": currency.env.company.id,
                }
            )

    def cron_update_rate(self):
        currencies = self.search([("sync_rate", "=", True)])

        for currency in currencies:
            currency.update_rate()
