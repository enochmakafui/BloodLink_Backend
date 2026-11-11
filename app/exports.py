"""Build downloadable documents (PDF / Word / Excel) from tabular data."""
from datetime import datetime, timezone
from io import BytesIO

from flask import Response

def _now():
    return datetime.now(timezone.utc)


FORMATS = {
    "pdf": ("application/pdf", "pdf"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
}
# friendly aliases
ALIASES = {"word": "docx", "excel": "xlsx", "doc": "docx", "xls": "xlsx"}


def normalize_format(value):
    value = (value or "pdf").strip().lower()
    value = ALIASES.get(value, value)
    return value if value in FORMATS else None


def _cell(v):
    return "" if v is None else str(v)


def table_pdf(title, headers, rows):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=title,
                            leftMargin=24, rightMargin=24, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("cell", fontSize=8, leading=10)
    data = [[Paragraph(f"<b>{h}</b>", small) for h in headers]]
    data += [[Paragraph(_escape(_cell(c)), small) for c in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3c6c6")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    doc.build([
        Paragraph(title, styles["Title"]),
        Paragraph(f"Generated {_now():%Y-%m-%d %H:%M} UTC &middot; {len(rows)} record(s)",
                  styles["Normal"]),
        Spacer(1, 12), table,
    ])
    return buf.getvalue()


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table_docx(title, headers, rows):
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Pt

    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    doc.add_heading(title, 0)
    doc.add_paragraph(f"Generated {_now():%Y-%m-%d %H:%M} UTC · {len(rows)} record(s)")
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    for row in rows:
        cells = table.add_row().cells
        for i, c in enumerate(row):
            cells[i].text = _cell(c)
    for r in table.rows:
        for c in r.cells:
            for p in c.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(8)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def table_xlsx(title, headers, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F3C6C6")
    for row in rows:
        ws.append([c if isinstance(c, (int, float)) else _cell(c) for c in row])
    for i, h in enumerate(headers, 1):
        width = max([len(h)] + [len(_cell(r[i - 1])) for r in rows]) + 2
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(width, 50)
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


_BUILDERS = {"pdf": table_pdf, "docx": table_docx, "xlsx": table_xlsx}


def table_response(fmt, filename, title, headers, rows):
    body = _BUILDERS[fmt](title, headers, rows)
    mime, ext = FORMATS[fmt]
    return download(body, mime, f"{filename}.{ext}")


def download(body, mime, filename, inline=False):
    disposition = "inline" if inline else "attachment"
    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    })


def donor_form_pdf(donor):
    """A one-page printable copy of the donor's registration details."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="BloodLink Donor Registration Form")
    styles = getSampleStyleSheet()
    fields = [
        ("Full name", donor.full_name),
        ("Email", donor.user.email),
        ("Phone", donor.phone),
        ("Blood type", donor.blood_type),
        ("City", donor.city),
        ("Region", donor.region),
        ("GPS address", donor.gps_address or "-"),
        ("Currently available to donate", "Yes" if donor.is_available else "No"),
        ("Last donation date", donor.last_donation_date.isoformat() if donor.last_donation_date else "-"),
        ("Registered on", f"{donor.user.created_at:%Y-%m-%d}" if donor.user.created_at else "-"),
    ]
    table = Table([[Paragraph(f"<b>{k}</b>", styles["Normal"]), Paragraph(_escape(_cell(v)), styles["Normal"])]
                   for k, v in fields], colWidths=[190, 300])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9e4e4")),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    doc.build([
        Paragraph("BloodLink", styles["Title"]),
        Paragraph("Donor Registration Form", styles["Heading2"]),
        Paragraph(f"Printed {_now():%Y-%m-%d %H:%M} UTC", styles["Normal"]),
        Spacer(1, 16), table, Spacer(1, 40),
        Paragraph("Donor signature: ______________________________ &nbsp;&nbsp; Date: ______________",
                  styles["Normal"]),
    ])
    return buf.getvalue()
