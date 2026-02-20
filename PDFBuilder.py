from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from datetime import datetime

class PDFBuilder:
    def __init__(self, filename):
        self.filename = filename
        self.canvas = canvas.Canvas(filename, pagesize=letter)
        self.width, self.height = letter
        self.margin = inch
        self.y_position = self.height - self.margin
        self.min_y = self.margin
        self.section_gap = 0.25 * inch

    def check_page_space(self, needed_height):
        """Check if there is enough space on the current page, otherwise create a new page."""
        if self.y_position - needed_height < self.min_y:
            self.canvas.showPage()
            self.y_position = self.height - self.margin
        return self.y_position

    def draw_section_header(self, label):
        """Draw a section header."""
        self.canvas.setFillColor(colors.lightgrey)
        self.canvas.rect(self.margin, self.y_position - 0.3 * inch, self.width - 2 * self.margin, 0.3 * inch, fill=1)
        self.canvas.setFillColor(colors.black)
        self.canvas.setFont("Helvetica-Bold", 12)
        self.canvas.drawString(self.margin + 0.1 * inch, self.y_position - 0.2 * inch, label)
        self.y_position -= 0.4 * inch

    def draw_table(self, data, col_widths):
        """Draw a table."""
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        w, h = table.wrap(self.width - 2 * self.margin, self.y_position)
        self.y_position = self.check_page_space(h)
        table.drawOn(self.canvas, self.margin, self.y_position - h)
        self.y_position -= h + self.section_gap

    def add_footer(self):
        """Add a footer to the PDF."""
        self.y_position = max(self.y_position, self.min_y + 0.5 * inch)
        self.canvas.setFont("Helvetica", 8)
        self.canvas.setFillColor(colors.grey)
        self.canvas.drawString(self.margin, self.y_position, "This is a computer-generated form created by AI Medical Coding Assistant.")
        self.y_position -= 0.2 * inch
        self.canvas.drawString(self.margin, self.y_position, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def save(self):
        """Save the PDF."""
        self.canvas.save()