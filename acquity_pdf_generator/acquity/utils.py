def get_form_field(forms, possible_names):
    """
    Extracts the value for any of the possible field names from Acuity form data.
    - forms: list of form dicts (from Acuity API or DB)
    - possible_names: list of str, possible field names (case-insensitive, partial match allowed)
    """
    for form in forms or []:
        for field in form.get('values', []):
            field_name = field.get('name', '').strip().lower()
            for name in possible_names:
                if name.lower() in field_name:
                    return field.get('value')
    return None 