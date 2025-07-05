# scheduling/pdf_generator.py
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from django.http import HttpResponse
from django.utils import timezone
import io
from .models import PricingSetting
from acquity.utils import get_form_field
import re
from acquity.openai_utils import extract_guest_counts_with_gpt

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
            # Sort appointments by 'datetime' field ascending (earliest to latest)
            def get_dt(appointment):
                from datetime import datetime
                dt_str = appointment.get('datetime', '')
                try:
                    # Support both with and without 'Z' at the end
                    if dt_str.endswith('Z'):
                        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                    return datetime.fromisoformat(dt_str)
                except Exception:
                    return datetime.max
            appointments_data = sorted(appointments_data, key=get_dt)
            
            # Debug: print sorted dates
            print('Sorted appointment dates:')
            for appt in appointments_data:
                print(appt.get('datetime', 'NO DATE'))
            
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
                # The appointments_data is already sorted from most recent to future
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
            # Seating arrangement image path
            image_path = 'seating_arrangement.png'  # Adjust path if needed
            try:
                img = Image(image_path, width=200, height=80)  # Larger for label width
                img.hAlign = 'RIGHT'
            except Exception as img_exc:
                img = None
                import logging
                logging.warning(f"Could not load seating arrangement image: {img_exc}")
            # --- Company Name and Image Row ---
            company_title_style = ParagraphStyle(
                'CompanyTitle', fontSize=22, fontName='Helvetica-Bold', textColor=colors.HexColor('#222222'), alignment=0, spaceAfter=0, spaceBefore=0
            )
            company_title = Paragraph(company_name, company_title_style)
            # Recommended Seating Arrangement label above image
            seating_label_style = ParagraphStyle(
                'SeatingLabel', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#222222'), alignment=1, leading=10, spaceAfter=0, spaceBefore=0, wordWrap='LTR'
            )
            seating_label = Paragraph('Recommended Seating Arrangement', seating_label_style)
            # Compose image cell: label above image (as a mini-table)
            if img:
                img.drawWidth = 200
                img.drawHeight = 80
                image_col = Table([[seating_label], [img]], colWidths=[2.8*inch], hAlign='RIGHT')
                image_col.setStyle(TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                ]))
            else:
                image_col = ''
            header_row = [[company_title, image_col]]
            header_table = Table(header_row, colWidths=[4.0*inch, 2.8*inch], hAlign='RIGHT')
            header_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('ALIGN', (0,0), (0,0), 'LEFT'),
                ('ALIGN', (1,0), (1,0), 'RIGHT'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 8))
            # --- Contact Info Bar ---
            contact_data = [
                [
                    Paragraph(f"<b>Phone:</b> {company_phone}", self.styles['Normal']),
                    Paragraph(f"<b>Website:</b> {company_website}", self.styles['Normal'])
                ]
            ]
            contact_table = Table(contact_data, colWidths=[2.5*inch, 4.5*inch])
            contact_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#888888')),
                ('TEXTCOLOR', (0,0), (-1,-1), colors.white),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                ('TOPPADDING', (0,0), (-1,-1), 2),
            ]))
            elements.append(contact_table)
            elements.append(Spacer(1, 4))
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
            subtotal = 0.0  # Ensure subtotal is always defined
            # Parse form_data for custom fields
            if hasattr(appointment, 'form_data') and appointment.form_data:
                forms = appointment.form_data
                form_fields = {}
                # Build a normalized field dictionary for all possible fields
                for form in forms:
                    for field in form.get('values', []):
                        name = field.get('name', '').strip().upper()
                        value = field.get('value', '')
                        form_fields[name] = value
                # Use robust extraction for key fields
                address = get_form_field(forms, [
                    'full address',
                    'address',
                    'location',
                    'event address',
                    'party address',
                    'venue address',
                    'address of the event',
                ])
                guests = get_form_field(forms, ['order', 'how many adult', '# of guests'])
                # Fetch all relevant values directly from Acuity form data
                num_adult_val = get_form_field(forms, ['how many adult', 'number of adults'])
                num_kid_val = get_form_field(forms, ['how many kid', 'number of children'])
                noodle_rice = get_form_field(forms, ['noodle / rice'])
                gyoza = get_form_field(forms, ['appetizer: pork gyoza'])
                edamame = get_form_field(forms, ['appetizer: edamame'])
                filet_mignon = get_form_field(forms, ['filet mignon (upgraded protein)'])
                lobster_tail = get_form_field(forms, ['lobster tail (upgraded protein)'])
                add_premium_protein = get_form_field(forms, ['additional premium protein ($15)'])
                add_protein = get_form_field(forms, ['additional protein ($10)'])
                travel_fee = get_form_field(forms, ['travel fee'])
                deposit = get_form_field(forms, ['deposit (deducted from total)'])
                processing_fee = get_form_field(forms, ['processing fee (if any)'])
                processing_fee = float(processing_fee) if processing_fee and str(processing_fee).replace('.','',1).isdigit() else 0.0
                # Convert to int/float where appropriate
                num_adult = int(num_adult_val) if num_adult_val and str(num_adult_val).strip().isdigit() else 0
                num_kid = int(num_kid_val) if num_kid_val and str(num_kid_val).strip().isdigit() else 0
                noodle_rice = int(noodle_rice) if noodle_rice and str(noodle_rice).strip().isdigit() else 0
                gyoza = int(gyoza) if gyoza and str(gyoza).strip().isdigit() else 0
                edamame = int(edamame) if edamame and str(edamame).strip().isdigit() else 0
                filet_mignon = int(filet_mignon) if filet_mignon and str(filet_mignon).strip().isdigit() else 0
                lobster_tail = int(lobster_tail) if lobster_tail and str(lobster_tail).strip().isdigit() else 0
                add_premium_protein = int(add_premium_protein) if add_premium_protein and str(add_premium_protein).strip().isdigit() else 0
                add_protein = int(add_protein) if add_protein and str(add_protein).strip().isdigit() else 0
                travel_fee = float(travel_fee) if travel_fee and str(travel_fee).replace('.','',1).isdigit() else 0.0
                deposit = float(deposit) if deposit and str(deposit).replace('.','',1).isdigit() else 0.0
                num_guests = num_adult + num_kid
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
                processing_fee = getattr(appointment, 'processing_fee', 0.0) or 0.0
                # Fetch dynamic prices
                # Optionally, you can use appointment/calendar location if available
                location = getattr(appointment, 'location', None)
                adult_price = self._get_pricing('adult', location)
                kid_price = self._get_pricing('kid', location)
                # --- HEADER TABLE (Address) ---
                header_data = [
                    [Paragraph(f"<b>Address of the Event:</b> {address}", self.styles['Normal'])]
                ]
                address_table = Table(header_data, colWidths=[7*inch])
                address_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2f2f2')),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                    ('TOPPADDING', (0,0), (-1,-1), 2),
                ]))
                elements.append(address_table)
                elements.append(Spacer(1, 4))
                
                # --- EVENT DETAILS ---
                event_details = [
                    [Paragraph(f"<b>When:</b> {appointment.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if getattr(appointment, 'start_time', None) else 'N/A'}", self.styles['Normal'])],
                    [Paragraph(f"<b>Name:</b> {getattr(appointment, 'client_name', 'N/A')}", self.styles['Normal'])],
                    [Paragraph(f"<b>Phone:</b> {getattr(appointment, 'client_phone', 'N/A')}", self.styles['Normal'])],
                ]
                event_table = Table(event_details, colWidths=[7*inch])
                event_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2f2f2')),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                    ('TOPPADDING', (0,0), (-1,-1), 2),
                ]))
                elements.append(event_table)
                elements.append(Spacer(1, 8))
                
                # --- ORDER DETAILS BOX (formatted, one-pager style) ---
                # Add heading for Order Details
                order_details_heading_style = ParagraphStyle('OrderDetailsHeading', fontSize=10, fontName='Helvetica-Bold', alignment=0, spaceAfter=2)
                elements.append(Paragraph('Order Details', order_details_heading_style))
                elements.append(Spacer(1, 4))
                if hasattr(appointment, 'form_data') and appointment.form_data:
                    form_fields = {}
                    for form in appointment.form_data:
                        for field in form.get('values', []):
                            name = field.get('name', '').strip().upper()
                            value = field.get('value', '')
                            form_fields[name] = value
                    order_details_content = []
                    # Only show the 'order' field value in Order Details section
                    order_summary = get_form_field(forms, ['order'])
                    if order_summary:
                        order_details_content.append(f'<font size="10">&#9679; {order_summary}</font>')
                    if order_details_content:
                        order_details_text = '<br/><br/>'.join(order_details_content)
                        order_details_paragraph = Paragraph(order_details_text, self.styles['Normal'])
                        order_details_table = Table([[order_details_paragraph]], colWidths=[7*inch])
                        order_details_table.setStyle(TableStyle([
                            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2f2f2')),
                            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                            ('FONTSIZE', (0,0), (-1,-1), 8),
                            ('GRID', (0,0), (-1,-1), 1, colors.grey),
                            ('TOPPADDING', (0,0), (-1,-1), 2),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                            ('LEFTPADDING', (0,0), (-1,-1), 2),
                            ('RIGHTPADDING', (0,0), (-1,-1), 2),
                        ]))
                        elements.append(order_details_table)
                        elements.append(Spacer(1, 8))
                
                # --- ORDER BREAKDOWN ---
                # Map form field names to PricingSetting categories and display names
                item_fields = [
                    ("Adult", num_adult, "adult"),
                    ("Kid", num_kid, "kid"),
                    ("Noodle / rice", noodle_rice, "noodle_rice"),
                    ("Appetizer: Pork Gyoza", gyoza, "gyoza"),
                    ("Appetizer: Edamame", edamame, "edamame"),
                    ("Filet Mignon (Upgraded Protein)", filet_mignon, "fm"),
                    ("Lobster Tail (Upgraded Protein)", lobster_tail, "lobster"),
                    ("Side", add_protein, "side"),
                ]
                # Add static price items
                item_fields.append(("Additional Premium protein ($15)", add_premium_protein, None))
                item_fields.append(("Additional Protein ($10)", add_protein, None))
                order_table_data = [["Item", "Quantity", "Total ($)"]]
                for label, qty, category in item_fields:
                    if label == "Additional Premium protein ($15)":
                        price = 15.0
                    elif label == "Additional Protein ($10)":
                        price = 10.0
                    else:
                        price = self._get_pricing(category, location) if category else 0.0
                    total = float(qty) * float(price)
                    order_table_data.append([label, str(qty), f"${total}"])
                order_table = Table(order_table_data, colWidths=[2.8*inch, 2.1*inch, 2.1*inch])
                order_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f2f2f2')),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                    ('TOPPADDING', (0,0), (-1,-1), 2),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                    ('LEFTPADDING', (0,0), (-1,-1), 2),
                    ('RIGHTPADDING', (0,0), (-1,-1), 2),
                ]))
                elements.append(order_table)
                elements.append(Spacer(1, 4))
                elements.append(Paragraph("Our meal comes with veggies, fried rice, and salad. Sake is also included.", ParagraphStyle('Normal', fontSize=8)))
                elements.append(Paragraph("Please ensure table, chairs, plates and utensils are also setup prior to the chef's arrival.", ParagraphStyle('Normal', fontSize=8)))
                elements.append(Spacer(1, 4))
                # --- FEES ---
                fees_data = [
                    [Paragraph("<b>Traveling Fee</b>", self.styles['Normal']), travel_fee or ""],
                    [Paragraph("<b>Deposit</b>", self.styles['Normal']), deposit or ""],
                ]
                # Only include processing fee if it is present in the Acuity API response and > 0
                processing_fee_from_api = getattr(appointment, 'processing_fee', None)
                processing_fee_display = None
                processing_fee_percent = 0.0
                if processing_fee_from_api is not None and float(processing_fee_from_api) > 0:
                    pf = float(processing_fee_from_api)
                    if pf >= 1:
                        processing_fee_percent = pf / 100.0
                    else:
                        processing_fee_percent = pf
                    processing_fee_display = (subtotal + travel_fee - deposit) * processing_fee_percent
                    fees_data.append([
                        Paragraph("<b>Processing Fee (If Applicable)</b>", self.styles['Normal']),
                        f"$ {processing_fee_display:.2f}"
                    ])
                fees_table = Table(fees_data, colWidths=[2.5*inch, 4.5*inch])
                fees_table.setStyle(TableStyle([
                    ('ALIGN', (0,0), (0,-1), 'LEFT'),
                    ('ALIGN', (1,0), (1,-1), 'LEFT'),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('TOPPADDING', (0,0), (-1,-1), 2),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                ]))
                elements.append(fees_table)
                elements.append(Spacer(1, 4))
                # --- MENU ---
                # elements.append(Paragraph("<b>****menu</b>", self.styles['Normal']))
                # elements.append(Spacer(1, 16))
                # --- TOTALS ---
                total1 = int(num_adult)*adult_price + int(num_kid)*kid_price
                # Calculate subtotal as the sum of all item totals
                subtotal = 0.0
                for label, qty, category in item_fields:
                    if label == "Additional Premium protein ($15)":
                        price = 15.0
                    elif label == "Additional Protein ($10)":
                        price = 10.0
                    else:
                        price = self._get_pricing(category, location) if category else 0.0
                    total = float(qty) * float(price)
                    subtotal += total
                # Calculate Final Total according to formula
                base_total = subtotal + travel_fee - deposit
                if processing_fee_percent > 0:
                    final_total = base_total * (1 + processing_fee_percent)
                else:
                    final_total = base_total
                elements.append(Paragraph(f"<b>Total ($):</b> {final_total:.2f}", ParagraphStyle('Normal', fontSize=9)))
                elements.append(Paragraph("<b>Note:</b> Payment must be made in cash on the day of the event. If you need to use a different payment method, please let us know as soon as possible.", ParagraphStyle('Normal', fontSize=8)))
                elements.append(Spacer(1, 4))
                # --- ALLERGIES ---
                elements.append(Paragraph(f"<b>Any food allergies?</b> {allergies}", ParagraphStyle('Normal', fontSize=9)))
                elements.append(Spacer(1, 4))
                # --- TIP TABLE ---
                tip_base = subtotal + travel_fee
                tip_20 = round(tip_base * 0.20, 2)
                tip_25 = round(tip_base * 0.25, 2)
                tip_30 = round(tip_base * 0.30, 2)
                tip_table_data = [
                    ["Tip :", "", "Final Total with Gratuity"],
                    ["20% = $", f"{tip_20:.2f}", f"Total: $ {final_total + tip_20:.2f}"],
                    ["25% = $", f"{tip_25:.2f}", f"Total: $ {final_total + tip_25:.2f}"],
                    ["30% = $", f"{tip_30:.2f}", f"Total: $ {final_total + tip_30:.2f}"],
                ]
                tip_table = Table(tip_table_data, colWidths=[2*inch, 2*inch, 3*inch])
                tip_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f2f2f2')),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 9),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                    ('TOPPADDING', (0,0), (-1,-1), 2),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                ]))
                elements.append(tip_table)
                elements.append(Spacer(1, 4))
                # --- FOOTER ---
                elements.append(Paragraph("Thank you for having us. Hope you enjoyed it!", ParagraphStyle('Normal', fontSize=9)))
                elements.append(Paragraph("Follow/tag us on instagram: @mobilehibachi_4u", ParagraphStyle('Normal', fontSize=8)))
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




