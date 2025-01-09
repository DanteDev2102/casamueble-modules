from odoo import http, _
from odoo.http import request, content_disposition

from .basic_controller import BasicControllerXlsxReport

import logging
import ast

_logger = logging.getLogger(__name__)


class AccountCustomXlsxReport(BasicControllerXlsxReport):
    @http.route(
        ["/account_custom_xlsx_report"],
        auth="user",
        csrf=False,
        type="http",
    )
    def generate_xlsx_report(self, **kw):
        return request.make_response(
            self.get_report(
                kw,
                request,
                kw.get("document_ids"),
            ),
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                (
                    "Content-Disposition",
                    content_disposition(_("interval_payment_report.xlsx")),
                ),
            ],
        )

    def _prepare_data_table(self, data, kw):
        final_sheet = list()

        data = ast.literal_eval(data)

        for record_id in data:
            record = request.env["account.payment"].search([("id", "=", record_id)])

            final_sheet.append(
                [
                    self._format_date_str(str(record.date)),
                    record.ref,
                    record.display_name,
                    record.amount,
                ]
            )

        return [*final_sheet]

    def _prepare_table_headers(self, kw, wb):
        table_header_format = wb.add_format({"bold": True})

        return [
            {
                "header": _("Date"),
                "header_format": table_header_format,
            },
            {
                "header": _("Reference Code"),
                "header_format": table_header_format,
            },
            {
                "header": _("Document Name"),
                "header_format": table_header_format,
            },
            {
                "header": _("Amount"),
                "header_format": table_header_format,
            },
        ]

    def _prepare_header_report(self, wb, ws, kw, req):
        header_format = wb.add_format(
            {"bold": True, "align": "center", "bg_color": "#ffffff"}
        )

        ws.merge_range("B2:F2", req.env.company.name, header_format)
