"""
PDF export service for generating printable route sheets.
Uses ReportLab to create professional route documents for techs.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class PDFExportService:
    """Service for generating PDF route sheets."""

    def __init__(self):
        """Initialize PDF export service."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Set up custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            alignment=TA_CENTER
        ))

        self.styles.add(ParagraphStyle(
            name='RouteHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#3498db'),
            spaceAfter=6,
        ))

        self.styles.add(ParagraphStyle(
            name='StopInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=4,
        ))

    def generate_route_sheet(
        self,
        route_data: Dict,
        tech_info: Dict
    ) -> BytesIO:
        """
        Generate a PDF route sheet for a single route.

        Args:
            route_data: Route information with stops
            tech_info: Tech information

        Returns:
            BytesIO buffer containing the PDF
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.5*inch
        )

        story = []

        # Title
        title = Paragraph("Route Sheet", self.styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 0.2*inch))

        # Tech and route information
        info_data = [
            ['Tech:', tech_info.get('name', 'N/A')],
            ['Service Day:', route_data.get('service_day', 'N/A').title()],
            ['Date:', datetime.now().strftime('%B %d, %Y')],
            ['Total Stops:', str(route_data.get('total_customers', 0))],
            ['Total Distance:', f"{route_data.get('total_distance_miles', 0):.1f} miles"],
            ['Estimated Time:', f"{route_data.get('total_duration_minutes', 0)} minutes"],
        ]

        info_table = Table(info_data, colWidths=[1.5*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ]))

        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Route header
        route_header = Paragraph("Route Stops (In Order)", self.styles['RouteHeader'])
        story.append(route_header)
        story.append(Spacer(1, 0.1*inch))

        # Stops table
        stops = route_data.get('stops', [])

        if stops:
            # Table header
            table_data = [['#', 'Customer', 'Address', 'Type', 'Time (min)']]

            # Add stops
            for stop in stops:
                table_data.append([
                    str(stop.get('sequence', '')),
                    stop.get('customer_name', ''),
                    stop.get('address', ''),
                    stop.get('service_type', 'residential').title(),
                    str(stop.get('service_duration', ''))
                ])

            stops_table = Table(
                table_data,
                colWidths=[0.4*inch, 1.8*inch, 2.8*inch, 0.8*inch, 0.7*inch]
            )

            stops_table.setStyle(TableStyle([
                # Header row
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

                # Data rows
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Sequence number
                ('ALIGN', (-1, 1), (-1, -1), 'CENTER'),  # Time
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),

                # Borders and grid
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2980b9')),

                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ]))

            story.append(stops_table)

        else:
            no_stops = Paragraph("No stops on this route.", self.styles['Normal'])
            story.append(no_stops)

        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = (
            f"Generated by RouteOptimizer on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        )
        footer = Paragraph(footer_text, self.styles['Normal'])
        story.append(footer)

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def generate_multi_route_pdf(
        self,
        routes: List[Dict],
        techs: Dict[str, Dict]
    ) -> BytesIO:
        """
        Generate a PDF with multiple routes (one page per route).

        Args:
            routes: List of route data
            techs: Dictionary mapping tech_id to tech info

        Returns:
            BytesIO buffer containing the PDF
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.5*inch
        )

        story = []

        for idx, route in enumerate(routes):
            tech_id = route.get('tech_id', '')
            tech_info = techs.get(tech_id, {'name': 'Unknown Tech'})

            # Generate route page
            route_story = self._build_route_page(route, tech_info)
            story.extend(route_story)

            # Add page break between routes (except last one)
            if idx < len(routes) - 1:
                story.append(PageBreak())

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def _build_route_page(self, route_data: Dict, tech_info: Dict) -> List:
        """Build story elements for a single route page."""
        story = []

        # Title
        title = Paragraph("Route Sheet", self.styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 0.2*inch))

        # Tech and route information
        info_data = [
            ['Tech:', tech_info.get('name', 'N/A')],
            ['Service Day:', route_data.get('service_day', 'N/A').title()],
            ['Date:', datetime.now().strftime('%B %d, %Y')],
            ['Total Stops:', str(route_data.get('total_customers', 0))],
            ['Total Distance:', f"{route_data.get('total_distance_miles', 0):.1f} miles"],
            ['Estimated Time:', f"{route_data.get('total_duration_minutes', 0)} minutes"],
        ]

        info_table = Table(info_data, colWidths=[1.5*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ]))

        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Route header
        route_header = Paragraph("Route Stops (In Order)", self.styles['RouteHeader'])
        story.append(route_header)
        story.append(Spacer(1, 0.1*inch))

        # Stops table
        stops = route_data.get('stops', [])

        if stops:
            # Table header
            table_data = [['#', 'Customer', 'Address', 'Type', 'Time (min)']]

            # Add stops
            for stop in stops:
                table_data.append([
                    str(stop.get('sequence', '')),
                    stop.get('customer_name', ''),
                    stop.get('address', ''),
                    stop.get('service_type', 'residential').title(),
                    str(stop.get('service_duration', ''))
                ])

            stops_table = Table(
                table_data,
                colWidths=[0.4*inch, 1.8*inch, 2.8*inch, 0.8*inch, 0.7*inch]
            )

            stops_table.setStyle(TableStyle([
                # Header row
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

                # Data rows
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
                ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Sequence number
                ('ALIGN', (-1, 1), (-1, -1), 'CENTER'),  # Time
                ('VALIGN', (0, 1), (-1, -1), 'TOP'),

                # Borders and grid
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2980b9')),

                # Alternating row colors
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ]))

            story.append(stops_table)

        else:
            no_stops = Paragraph("No stops on this route.", self.styles['Normal'])
            story.append(no_stops)

        # Footer
        story.append(Spacer(1, 0.3*inch))
        footer_text = (
            f"Generated by RouteOptimizer on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        )
        footer = Paragraph(footer_text, self.styles['Normal'])
        story.append(footer)

        return story


# Global PDF export service instance
pdf_export_service = PDFExportService()
