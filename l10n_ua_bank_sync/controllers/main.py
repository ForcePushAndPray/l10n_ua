import io
from datetime import datetime

from odoo import http
from odoo.http import request, content_disposition


class BankStatementController(http.Controller):

    @http.route('/l10n_ua_bank_sync/export_statement_xlsx/<int:statement_id>',
                type='http', auth='user')
    def export_statement_xlsx(self, statement_id, **kwargs):
        """Export bank statement to XLSX."""
        try:
            import xlsxwriter
        except ImportError:
            return request.make_response(
                "xlsxwriter library is not installed. Please install it with: pip install xlsxwriter",
                headers=[('Content-Type', 'text/plain')]
            )

        statement = request.env['l10n_ua.bank.statement'].browse(statement_id)
        if not statement.exists():
            return request.not_found()

        # Create XLSX in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Statement')

        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
        })
        money_format = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1,
        })
        money_format_green = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1,
            'font_color': 'green',
        })
        money_format_red = workbook.add_format({
            'num_format': '#,##0.00',
            'border': 1,
            'font_color': 'red',
        })
        date_format = workbook.add_format({
            'num_format': 'dd.mm.yyyy',
            'border': 1,
        })
        text_format = workbook.add_format({
            'border': 1,
            'text_wrap': True,
        })
        bold_format = workbook.add_format({
            'bold': True,
        })

        # Set column widths
        worksheet.set_column('A:A', 12)  # Date
        worksheet.set_column('B:B', 15)  # Reference
        worksheet.set_column('C:C', 40)  # Description
        worksheet.set_column('D:D', 25)  # Partner
        worksheet.set_column('E:E', 30)  # IBAN
        worksheet.set_column('F:F', 15)  # Incoming
        worksheet.set_column('G:G', 15)  # Outgoing
        worksheet.set_column('H:H', 15)  # Balance

        # Title
        row = 0
        company = statement.company_id
        worksheet.write(row, 0, f"Bank Statement: {statement.name}", title_format)
        row += 1
        worksheet.write(row, 0, f"Company: {company.name}")
        row += 1

        if statement.bank_account_id:
            worksheet.write(row, 0, f"Account: {statement.bank_account_id.acc_number}")
            row += 1

        worksheet.write(row, 0, f"Period: {statement.date_from.strftime('%d.%m.%Y')} - {statement.date_to.strftime('%d.%m.%Y')}")
        row += 2

        # Summary
        worksheet.write(row, 0, "Opening Balance:", bold_format)
        worksheet.write(row, 1, statement.opening_balance, money_format)
        row += 1
        worksheet.write(row, 0, "Closing Balance:", bold_format)
        worksheet.write(row, 1, statement.closing_balance, money_format)
        row += 1
        worksheet.write(row, 0, "Total Incoming:", bold_format)
        worksheet.write(row, 1, statement.total_incoming, money_format_green)
        row += 1
        worksheet.write(row, 0, "Total Outgoing:", bold_format)
        worksheet.write(row, 1, statement.total_outgoing, money_format_red)
        row += 2

        # Header
        headers = ['Date', 'Reference', 'Description', 'Partner', 'IBAN', 'Incoming', 'Outgoing', 'Balance']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1

        # Transactions
        running_balance = statement.opening_balance
        for trans in statement.transaction_ids.sorted(key=lambda t: (t.date, t.id)):
            running_balance += trans.amount

            worksheet.write(row, 0, trans.date, date_format)
            worksheet.write(row, 1, trans.payment_ref or '', text_format)
            worksheet.write(row, 2, trans.description or '', text_format)
            worksheet.write(row, 3, trans.partner_name or (trans.partner_id.name if trans.partner_id else ''), text_format)
            worksheet.write(row, 4, trans.partner_iban or '', text_format)

            if trans.amount > 0:
                worksheet.write(row, 5, trans.amount, money_format_green)
                worksheet.write(row, 6, '', text_format)
            else:
                worksheet.write(row, 5, '', text_format)
                worksheet.write(row, 6, abs(trans.amount), money_format_red)

            worksheet.write(row, 7, running_balance, money_format)
            row += 1

        # Totals
        worksheet.write(row, 4, "TOTAL:", bold_format)
        worksheet.write(row, 5, statement.total_incoming, money_format_green)
        worksheet.write(row, 6, statement.total_outgoing, money_format_red)
        worksheet.write(row, 7, statement.closing_balance, money_format)

        workbook.close()

        # Return XLSX file
        output.seek(0)
        filename = f"statement_{statement.date_from}_{statement.date_to}.xlsx"

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )
