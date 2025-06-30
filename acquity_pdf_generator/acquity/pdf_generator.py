# scheduling/pdf_generator.py
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from django.http import HttpResponse
from django.utils import timezone
import io
from .models import PricingSetting

class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.darkblue,
            alignment=1  # Center alignment
        )

    def generate_appointment_pdf(self, appointments_data, calendar_name):
        """Generate PDF for multiple appointments in a calendar"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, 
                              topMargin=72, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        elements = []
        try:
            # Title
            title = Paragraph(f"Appointments Report - {calendar_name}", self.title_style)
            elements.append(title)
            elements.append(Spacer(1, 20))
            
            # Summary
            summary_text = f"Total Appointments: {len(appointments_data)}"
            summary = Paragraph(summary_text, self.styles['Heading2'])
            elements.append(summary)
            elements.append(Spacer(1, 20))
            
            if appointments_data:
                # Appointments Table
                table_data = [['Client', 'Service', 'Date & Time', 'Duration', 'Status', 'Price']]
                
                for appointment in appointments_data:
                    # Get appointment details from API data
                    client_name = f"{appointment.get('firstName', '')} {appointment.get('lastName', '')}".strip()
                    if not client_name:
                        client_name = 'N/A'
                    
                    service_name = appointment.get('appointmentType', {}).get('name', 'N/A')
                    duration = f"{appointment.get('appointmentType', {}).get('duration', 'N/A')} min"
                    price = f"${appointment.get('price', 'N/A')}"
                    
                    # Format date and time
                    datetime_str = appointment.get('datetime', '')
                    if datetime_str:
                        try:
                            # Parse ISO datetime string
                            from datetime import datetime
                            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                            date_time = dt.strftime('%m/%d/%Y %I:%M %p')
                        except:
                            date_time = 'N/A'
                    else:
                        date_time = 'N/A'
                    
                    # Get status
                    status = appointment.get('status', 'N/A').title()
                    
                    table_data.append([client_name, service_name, date_time, duration, status, price])
                
                # Create table
                table = Table(table_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 0.8*inch, 0.8*inch, 0.8*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTNAME', (0, 1), (0, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.beige, colors.white]),
                ]))
                
                elements.append(table)
            else:
                # No appointments message
                no_appointments = Paragraph("No appointments found for the selected date range.", self.styles['Normal'])
                elements.append(no_appointments)
            
            elements.append(Spacer(1, 30))
            
            # Footer
            footer_text = f"Generated on {timezone.now().strftime('%B %d, %Y at %I:%M %p')}"
            footer = Paragraph(footer_text, self.styles['Normal'])
            elements.append(footer)
            
            # Build PDF
            doc.build(elements)
            
            # Get PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            return pdf_content
        except Exception as e:
            import logging
            logging.exception('Error generating appointments PDF')
            buffer.close()
            raise e

    def _get_pricing(self, category, location=None):
        try:
            if location:
                setting = PricingSetting.objects.filter(category=category, location=location).first()
                if setting:
                    return float(setting.price)
            # fallback to default (no location)
            setting = PricingSetting.objects.filter(category=category, location="").first()
            if setting:
                return float(setting.price)
        except Exception:
            pass
        # fallback default if not found
        return 0.0

    def generate_appointment_confirmation(self, appointment):
        """Generate PDF confirmation for an appointment (custom layout for Hibachi)"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=18)
        elements = []
        try:
            # --- HEADER ---
            company_name = "Mobile Hibachi 4U"
            company_phone = "(555) 123-4567"  # Replace with real value if available
            company_website = "www.mobilehibachi4u.com"
            # Address of the event (from form_data or appointment)
            address = None
            num_adult = num_kid = num_guests = None
            seating = ""
            allergies = ""
            menu = ""
            traveling_fee = deposit = protein = fee = None
            order_breakdown = {
                'Adult': {'count': 0, 'total': 0},
                'Kid': {'count': 0, 'total': 0},
                'Noodle / rice': {'count': 0, 'total': 0},
                'Gyoza': {'count': 0, 'total': 0},
                'Edamame': {'count': 0, 'total': 0},
                'FM': {'count': 0, 'total': 0},
                'Lobster': {'count': 0, 'total': 0},
                'Side': {'count': 0, 'total': 0},
                'Protein': {'count': 0, 'total': 0},
            }
            # Parse form_data for custom fields
            if hasattr(appointment, 'form_data') and appointment.form_data:
                for form in appointment.form_data:
                    for field in form.get('values', []):
                        name = field.get('name', '').lower()
                        value = field.get('value', '')
                        if 'address' in name:
                            address = value
                        elif 'seating' in name:
                            seating = value
                        elif 'adult' in name and 'number' in name:
                            try: num_adult = int(value)
                            except: num_adult = value
                        elif 'kid' in name and 'number' in name:
                            try: num_kid = int(value)
                            except: num_kid = value
                        elif 'guest' in name and ('how many' in name or 'number' in name):
                            try: num_guests = int(value)
                            except: num_guests = value
                        elif 'allerg' in name:
                            allergies = value
                        elif 'menu' in name:
                            menu = value
                        elif 'travel' in name:
                            traveling_fee = value
                        elif 'deposit' in name:
                            deposit = value
                        elif 'protein' in name:
                            try: protein = int(value)
                            except: protein = value
                        elif 'fee:' in name:
                            try:
                                fee = float(value)
                            except:
                                fee = 0.0
                        # Order breakdown
                        for key in order_breakdown.keys():
                            if key.lower() in name:
                                try:
                                    order_breakdown[key]['count'] = int(value)
                                except:
                                    order_breakdown[key]['count'] = value
            # Fallbacks
            if not address:
                address = getattr(appointment, 'notes', '')
            if not num_adult:
                num_adult = 0
            if not num_kid:
                num_kid = 0
            # Ensure num_adult and num_kid are always integers
            try:
                num_adult = int(num_adult)
            except Exception:
                num_adult = 0
            try:
                num_kid = int(num_kid)
            except Exception:
                num_kid = 0
            if not num_guests:
                try:
                    num_guests = int(num_adult) + int(num_kid)
                except Exception:
                    num_guests = 0
            # Extra type safety for fee
            if fee is None:
                fee = 0.0
            if not isinstance(fee, (int, float)):
                try:
                    fee = float(fee)
                except Exception as e:
                    import logging
                    logging.error(f"Could not convert fee to float: {fee} ({type(fee)}) - {e}")
                    fee = 0.0
            # Debug log for fee
            import logging
            logging.debug(f"Fee value before calculations: {fee} (type: {type(fee)})")
            # Use processing_fee from appointment model (default 1.0)
            processing_fee = getattr(appointment, 'processing_fee', 1.0) or 1.0
            # Fetch dynamic prices
            # Optionally, you can use appointment/calendar location if available
            location = getattr(appointment, 'location', None)
            adult_price = self._get_pricing('adult', location)
            kid_price = self._get_pricing('kid', location)
            # --- HEADER TABLE ---
            header_data = [
                [Paragraph(f"<b>Company Name:</b> {company_name}", self.styles['Normal']),
                 Paragraph(f"<b>Phone:</b> {company_phone}", self.styles['Normal']),
                 Paragraph(f"<b>Website:</b> {company_website}", self.styles['Normal'])],
                [Paragraph(f"<b>Address of the Event:</b> {address}", self.styles['Normal']), '', '']
            ]
            header_table = Table(header_data, colWidths=[2.5*inch, 2*inch, 2*inch])
            header_table.setStyle(TableStyle([
                ('SPAN', (0,1), (2,1)),
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
                ('BOTTOMPADDING', (0,1), (-1,1), 8),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 10))
            
            # --- EVENT DETAILS ---
            event_details = [
                [Paragraph(f"<b>Recommended Seating Arrangement:</b> {seating}", self.styles['Normal'])],
                [Paragraph(f"<b>When:</b> {appointment.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if getattr(appointment, 'start_time', None) else 'N/A'}", self.styles['Normal'])],
                [Paragraph(f"<b>Name:</b> {getattr(appointment, 'client_name', 'N/A')}", self.styles['Normal'])],
                [Paragraph(f"<b>Phone:</b> {getattr(appointment, 'client_phone', 'N/A')}", self.styles['Normal'])],
                [Paragraph(f"<b>Address of the Event:</b> {address}", self.styles['Normal'])],
                [Paragraph(f"<b>Number of Adult:</b> {num_adult}", self.styles['Normal'])],
                [Paragraph(f"<b>Number of Kids:</b> {num_kid}", self.styles['Normal'])],
                [Paragraph(f"<b>How many guests will you have:</b> {num_guests}", self.styles['Normal'])],
            ]
            event_table = Table(event_details, colWidths=[7*inch])
            event_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
            ]))
            elements.append(event_table)
            elements.append(Spacer(1, 10))
            
            # --- ORDER DETAILS BOX (formatted, one-pager style) ---
            order_fields = [
                'ORDER',
                'TRAVEL FEE',
                'TIPS',
                'TOTAL',
                'HOW MANY ADULT?',
                'HOW MANY KID?',
                'NOODLE / RICE',
                'GYOZA',
                'EDAMAME',
                'FILET MIGNON',
                'LOBSTER TAIL',
                'ADDITIONAL SIDE ($15)',
                'ADDITIONAL SIDE ($10)',
                'TRAVEL FEE',
                'DEPOSIT',
            ]
            # Grouping for proteins and sides
            protein_fields = ['CHICKEN', 'STEAK', 'SHRIMP', 'SCALLOPS', 'SALMON', 'FILET MIGNON', 'LOBSTER TAIL']
            side_fields = ['NOODLE / RICE', 'GYOZA', 'EDAMAME', 'ADDITIONAL SIDE ($15)', 'ADDITIONAL SIDE ($10)']
            if hasattr(appointment, 'form_data') and appointment.form_data:
                form_fields = {}
                for form in appointment.form_data:
                    for field in form.get('values', []):
                        name = field.get('name', '').strip().upper()
                        value = field.get('value', '')
                        form_fields[name] = value
                order_details_content = []
                # Heading
                order_details_content.append('<b>Order Details:</b>')
                # Guests/party size
                guests = form_fields.get('ORDER') or form_fields.get('HOW MANY ADULT?')
                if guests:
                    order_details_content.append(f'<font size="10">&#9679; {guests}</font>')
                # Total Protein
                total_protein = form_fields.get('TOTAL PROTEIN')
                if total_protein:
                    order_details_content.append(f'<font size="10">&#9679; Total Protein: {total_protein}</font>')
                # Proteins
                protein_lines = []
                for pf in protein_fields:
                    val = form_fields.get(pf)
                    if val:
                        protein_lines.append(f'{val} {pf.title()}')
                if protein_lines:
                    order_details_content.append(f'<font size="10">&#9679; ' + ' / '.join(protein_lines) + '</font>')
                # Sides
                side_lines = []
                for sf in side_fields:
                    val = form_fields.get(sf)
                    if val:
                        side_lines.append(f'{val} {sf.title()}')
                if side_lines:
                    order_details_content.append(f'<font size="10">&#9679; Sides:</font>')
                    for s in side_lines:
                        order_details_content.append(f'<font size="10">&#9679; {s}</font>')
                # Travel Fee, Tips, Total, Deposit
                for label in ['TRAVEL FEE', 'TIPS', 'TOTAL', 'DEPOSIT']:
                    val = form_fields.get(label)
                    if val:
                        order_details_content.append(f'<font size="10">&#9679; {label.title()}: {val}</font>')
                # Allergies (if present)
                allergy = form_fields.get('ALLERGIES') or form_fields.get('ALLERGY')
                if allergy:
                    order_details_content.append(f'allergies: {allergy}')
                if order_details_content:
                    order_details_text = '<br/><br/>'.join(order_details_content)
                    order_details_paragraph = Paragraph(order_details_text, self.styles['Normal'])
                    order_details_table = Table([[order_details_paragraph]], colWidths=[7*inch])
                    order_details_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                        ('FONTSIZE', (0,0), (-1,-1), 9),
                        ('GRID', (0,0), (-1,-1), 1, colors.grey),
                        ('TOPPADDING', (0,0), (-1,-1), 10),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                        ('LEFTPADDING', (0,0), (-1,-1), 10),
                        ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ]))
                    elements.append(order_details_table)
                    elements.append(Spacer(1, 10))
            
            # --- ORDER BREAKDOWN ---
            order_table_data = [
                ["", "Quantity", "Total ($)"]
            ]
            # Adult, Kid rows
            order_table_data.append(["Adult", str(num_adult), f"${int(num_adult)*adult_price}"])
            order_table_data.append(["Kid", str(num_kid), f"${int(num_kid)*kid_price}"])
            # Other items
            for key in ["Noodle / rice", "Gyoza", "Edamame", "FM", "Lobster", "Side"]:
                order_table_data.append([key, str(order_breakdown[key]['count']), f"${order_breakdown[key]['total']}"])
            order_table = Table(order_table_data, colWidths=[2.8*inch, 2.1*inch, 2.1*inch])
            order_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))
            elements.append(order_table)
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("Our meal comes with veggies, fried rice, and salad. Sake is also included.", self.styles['Normal']))
            elements.append(Paragraph("Please ensure table, chairs, plates and utensils are also setup prior to the chef's arrival.", self.styles['Normal']))
            elements.append(Spacer(1, 8))
            # --- FEES ---
            fees_data = [
                ["Traveling Fee", traveling_fee or ""],
                ["Deposit", deposit or ""],
            ]
            if fee is not None:
                fees_data.append(["Processing Fee", f"${fee:.2f}"])
            fees_table = Table(fees_data, colWidths=[2.5*inch, 4.5*inch])
            fees_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
            ]))
            elements.append(fees_table)
            elements.append(Spacer(1, 8))
            # --- MENU ---
            # elements.append(Paragraph("<b>****menu</b>", self.styles['Normal']))
            # elements.append(Spacer(1, 16))
            # --- TOTALS ---
            total1 = int(num_adult)*adult_price + int(num_kid)*kid_price
            subtotal = total1 * processing_fee
            elements.append(Paragraph(f"<b>Subtotal ($):</b> {total1} (Cash Payment only day of, tip is not included. Other payment method, let us know ASAP.)", self.styles['Normal']))
            # Show the processing fee as a dollar amount (difference due to multiplier)
            processing_fee_amount = subtotal - total1
            if processing_fee_amount > 0:
                elements.append(Paragraph(f"<b>Processing Fee ($):</b> {processing_fee_amount:.2f}", self.styles['Normal']))
            elements.append(Paragraph(f"<b>Total (Deposit deducted) ($):</b> {subtotal:.2f}", self.styles['Normal']))
            elements.append(Spacer(1, 8))
            # --- ALLERGIES ---
            elements.append(Paragraph(f"<b>Any food allergies?</b> {allergies}", self.styles['Normal']))
            elements.append(Spacer(1, 8))
            # --- TIP TABLE ---
            tip_20 = round(subtotal * 0.20, 2)
            tip_25 = round(subtotal * 0.25, 2)
            tip_30 = round(subtotal * 0.30, 2)
            tip_table_data = [
                ["Tip :", "", "Final Total with Gratuity"],
                ["20% = $", f"{tip_20:.2f}", f"Total: $ {subtotal + tip_20:.2f}"],
                ["25% = $", f"{tip_25:.2f}", f"Total: $ {subtotal + tip_25:.2f}"],
                ["30% = $", f"{tip_30:.2f}", f"Total: $ {subtotal + tip_30:.2f}"],
            ]
            tip_table = Table(tip_table_data, colWidths=[2*inch, 2*inch, 3*inch])
            tip_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE', (0,0), (-1,-1), 10),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ]))
            elements.append(tip_table)
            elements.append(Spacer(1, 8))
            # --- FOOTER ---
            elements.append(Paragraph("Thank you for having us. Hope you enjoyed it!", self.styles['Normal']))
            elements.append(Paragraph("Follow/tag us on instagram: @mobilehibachi_4u", self.styles['Normal']))
            # Build PDF
            doc.build(elements)
            pdf_content = buffer.getvalue()
            buffer.close()
            return pdf_content
        except Exception as e:
            import logging
            logging.exception('Error generating appointment confirmation PDF')
            buffer.close()
            raise e




