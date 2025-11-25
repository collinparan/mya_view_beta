"""
CCD (Continuity of Care Document) Parser

Parses C-CDA XML files (HL7 standard) to extract structured health data.
Supports selective import with review before adding to Neo4j.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
import structlog

logger = structlog.get_logger()

# HL7 C-CDA namespaces
NAMESPACES = {
    'hl7': 'urn:hl7-org:v3',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'sdtc': 'urn:hl7-org:sdtc'
}


class CCDParser:
    """Parser for C-CDA (Consolidated Clinical Document Architecture) files."""

    def __init__(self):
        self.tree = None
        self.root = None

    def parse_file(self, file_content: bytes) -> Dict[str, Any]:
        """
        Parse a CCD XML file and extract structured health data.

        Returns a dictionary with sections:
        - demographics: patient info
        - medications: current and past medications
        - allergies: allergies and intolerances
        - problems: conditions and diagnoses
        - procedures: medical procedures
        - lab_results: laboratory results
        - immunizations: vaccination history
        - vital_signs: vital sign measurements
        """
        try:
            self.tree = ET.fromstring(file_content)
            self.root = self.tree

            result = {
                'demographics': self._parse_demographics(),
                'medications': self._parse_medications(),
                'allergies': self._parse_allergies(),
                'problems': self._parse_problems(),
                'procedures': self._parse_procedures(),
                'lab_results': self._parse_lab_results(),
                'immunizations': self._parse_immunizations(),
                'vital_signs': self._parse_vital_signs(),
                'metadata': self._parse_metadata()
            }

            logger.info("CCD file parsed successfully",
                       sections=len([k for k, v in result.items() if v]))
            return result

        except ET.ParseError as e:
            logger.error("Failed to parse XML", error=str(e))
            raise ValueError(f"Invalid XML format: {str(e)}")
        except Exception as e:
            logger.error("Failed to parse CCD", error=str(e))
            raise

    def _parse_demographics(self) -> Optional[Dict[str, Any]]:
        """Extract patient demographics."""
        try:
            patient_role = self.root.find('.//hl7:recordTarget/hl7:patientRole', NAMESPACES)
            if not patient_role:
                return None

            patient = patient_role.find('hl7:patient', NAMESPACES)
            if not patient:
                return None

            # Name
            name_elem = patient.find('hl7:name', NAMESPACES)
            given_name = self._get_text(name_elem, 'hl7:given')
            family_name = self._get_text(name_elem, 'hl7:family')

            # Birth date
            birth_time = patient.find('hl7:birthTime', NAMESPACES)
            birth_date = birth_time.get('value') if birth_time is not None else None

            # Gender
            gender = patient.find('hl7:administrativeGenderCode', NAMESPACES)
            gender_code = gender.get('displayName') if gender is not None else None

            # Address
            addr = patient_role.find('hl7:addr', NAMESPACES)
            address_parts = []
            if addr is not None:
                street = self._get_text(addr, 'hl7:streetAddressLine')
                city = self._get_text(addr, 'hl7:city')
                state = self._get_text(addr, 'hl7:state')
                zip_code = self._get_text(addr, 'hl7:postalCode')
                if street:
                    address_parts.append(street)
                if city and state:
                    address_parts.append(f"{city}, {state} {zip_code or ''}")

            return {
                'given_name': given_name,
                'family_name': family_name,
                'full_name': f"{given_name} {family_name}" if given_name and family_name else None,
                'birth_date': self._format_hl7_date(birth_date),
                'gender': gender_code,
                'address': ' '.join(address_parts) if address_parts else None
            }

        except Exception as e:
            logger.warning("Failed to parse demographics", error=str(e))
            return None

    def _parse_medications(self) -> List[Dict[str, Any]]:
        """Extract medications."""
        medications = []

        try:
            # Find medications section
            section = self._find_section('2.16.840.1.113883.10.20.22.2.1.1')  # Medications section
            if not section:
                return medications

            entries = section.findall('.//hl7:entry', NAMESPACES)

            for entry in entries:
                try:
                    med_activity = entry.find('.//hl7:substanceAdministration', NAMESPACES)
                    if med_activity is None:
                        continue

                    # Medication name and code
                    consumable = med_activity.find('.//hl7:consumable/hl7:manufacturedProduct/hl7:manufacturedMaterial', NAMESPACES)
                    if consumable is None:
                        continue

                    code_elem = consumable.find('hl7:code', NAMESPACES)
                    name = code_elem.get('displayName') if code_elem is not None else 'Unknown Medication'
                    rxnorm_code = code_elem.get('code') if code_elem is not None else None

                    # Dosage
                    dose_quantity = med_activity.find('.//hl7:doseQuantity', NAMESPACES)
                    dose_value = dose_quantity.get('value') if dose_quantity is not None else None
                    dose_unit = dose_quantity.get('unit') if dose_quantity is not None else None
                    dosage = f"{dose_value} {dose_unit}" if dose_value and dose_unit else None

                    # Frequency
                    frequency = None
                    period = med_activity.find('.//hl7:effectiveTime[@operator="A"]/hl7:period', NAMESPACES)
                    if period is not None:
                        period_value = period.get('value')
                        period_unit = period.get('unit')
                        if period_value and period_unit:
                            frequency = f"Every {period_value} {period_unit}"

                    # Start/end dates
                    effective_time = med_activity.find('.//hl7:effectiveTime[not(@operator)]', NAMESPACES)
                    start_date = None
                    end_date = None
                    if effective_time is not None:
                        low = effective_time.find('hl7:low', NAMESPACES)
                        high = effective_time.find('hl7:high', NAMESPACES)
                        start_date = self._format_hl7_date(low.get('value')) if low is not None else None
                        end_date = self._format_hl7_date(high.get('value')) if high is not None else None

                    # Status
                    status_code = med_activity.find('hl7:statusCode', NAMESPACES)
                    status = status_code.get('code') if status_code is not None else 'active'

                    medications.append({
                        'name': name,
                        'rxnorm_code': rxnorm_code,
                        'dosage': dosage,
                        'frequency': frequency,
                        'start_date': start_date,
                        'end_date': end_date,
                        'status': status
                    })

                except Exception as e:
                    logger.warning("Failed to parse medication entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse medications section", error=str(e))

        return medications

    def _parse_allergies(self) -> List[Dict[str, Any]]:
        """Extract allergies and adverse reactions."""
        allergies = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.6.1')  # Allergies section
            if not section:
                return allergies

            entries = section.findall('.//hl7:entry', NAMESPACES)

            for entry in entries:
                try:
                    obs = entry.find('.//hl7:observation', NAMESPACES)
                    if obs is None:
                        continue

                    # Allergen
                    participant = obs.find('.//hl7:participant/hl7:participantRole/hl7:playingEntity', NAMESPACES)
                    if participant is None:
                        continue

                    code_elem = participant.find('hl7:code', NAMESPACES)
                    allergen = code_elem.get('displayName') if code_elem is not None else 'Unknown Allergen'
                    allergen_code = code_elem.get('code') if code_elem is not None else None

                    # Reaction
                    reaction_obs = obs.find('.//hl7:entryRelationship/hl7:observation', NAMESPACES)
                    reaction = None
                    if reaction_obs is not None:
                        reaction_value = reaction_obs.find('hl7:value', NAMESPACES)
                        reaction = reaction_value.get('displayName') if reaction_value is not None else None

                    # Severity
                    severity_obs = obs.find('.//hl7:entryRelationship[@typeCode="SUBJ"]/hl7:observation', NAMESPACES)
                    severity = None
                    if severity_obs is not None:
                        severity_value = severity_obs.find('hl7:value', NAMESPACES)
                        severity = severity_value.get('displayName') if severity_value is not None else None

                    allergies.append({
                        'allergen': allergen,
                        'allergen_code': allergen_code,
                        'reaction': reaction,
                        'severity': severity
                    })

                except Exception as e:
                    logger.warning("Failed to parse allergy entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse allergies section", error=str(e))

        return allergies

    def _parse_problems(self) -> List[Dict[str, Any]]:
        """Extract problems/conditions."""
        problems = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.5.1')  # Problems section
            if not section:
                return problems

            entries = section.findall('.//hl7:entry', NAMESPACES)

            for entry in entries:
                try:
                    obs = entry.find('.//hl7:observation', NAMESPACES)
                    if obs is None:
                        continue

                    # Condition name and code
                    value_elem = obs.find('hl7:value', NAMESPACES)
                    if value_elem is None:
                        continue

                    name = value_elem.get('displayName', 'Unknown Condition')
                    icd10_code = value_elem.get('code')

                    # Dates
                    effective_time = obs.find('hl7:effectiveTime', NAMESPACES)
                    start_date = None
                    end_date = None
                    if effective_time is not None:
                        low = effective_time.find('hl7:low', NAMESPACES)
                        high = effective_time.find('hl7:high', NAMESPACES)
                        start_date = self._format_hl7_date(low.get('value')) if low is not None else None
                        end_date = self._format_hl7_date(high.get('value')) if high is not None else None

                    # Status
                    status_code = obs.find('hl7:statusCode', NAMESPACES)
                    status = status_code.get('code') if status_code is not None else 'active'

                    problems.append({
                        'name': name,
                        'icd10_code': icd10_code,
                        'diagnosed_date': start_date,
                        'resolved_date': end_date,
                        'status': status
                    })

                except Exception as e:
                    logger.warning("Failed to parse problem entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse problems section", error=str(e))

        return problems

    def _parse_procedures(self) -> List[Dict[str, Any]]:
        """Extract procedures."""
        procedures = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.7.1')  # Procedures section
            if not section:
                return procedures

            entries = section.findall('.//hl7:entry', NAMESPACES)

            for entry in entries:
                try:
                    procedure = entry.find('.//hl7:procedure', NAMESPACES)
                    if procedure is None:
                        continue

                    # Procedure name and code
                    code_elem = procedure.find('hl7:code', NAMESPACES)
                    if code_elem is None:
                        continue

                    name = code_elem.get('displayName', 'Unknown Procedure')
                    cpt_code = code_elem.get('code')

                    # Date
                    effective_time = procedure.find('hl7:effectiveTime', NAMESPACES)
                    procedure_date = None
                    if effective_time is not None:
                        date_value = effective_time.get('value')
                        procedure_date = self._format_hl7_date(date_value)

                    procedures.append({
                        'name': name,
                        'cpt_code': cpt_code,
                        'date': procedure_date
                    })

                except Exception as e:
                    logger.warning("Failed to parse procedure entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse procedures section", error=str(e))

        return procedures

    def _parse_lab_results(self) -> List[Dict[str, Any]]:
        """Extract laboratory results."""
        labs = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.3.1')  # Results section
            if not section:
                return labs

            organizers = section.findall('.//hl7:organizer', NAMESPACES)

            for organizer in organizers:
                try:
                    # Panel name
                    code_elem = organizer.find('hl7:code', NAMESPACES)
                    panel_name = code_elem.get('displayName') if code_elem is not None else 'Lab Panel'

                    # Date
                    effective_time = organizer.find('hl7:effectiveTime', NAMESPACES)
                    test_date = None
                    if effective_time is not None:
                        date_value = effective_time.get('value')
                        test_date = self._format_hl7_date(date_value)

                    # Individual results
                    observations = organizer.findall('.//hl7:observation', NAMESPACES)
                    results = []

                    for obs in observations:
                        code = obs.find('hl7:code', NAMESPACES)
                        value = obs.find('hl7:value', NAMESPACES)

                        if code is not None and value is not None:
                            test_name = code.get('displayName', 'Unknown Test')
                            test_value = value.get('value')
                            test_unit = value.get('unit')

                            # Reference range
                            ref_range = obs.find('hl7:referenceRange/hl7:observationRange/hl7:value', NAMESPACES)
                            reference = None
                            if ref_range is not None:
                                low = ref_range.find('hl7:low', NAMESPACES)
                                high = ref_range.find('hl7:high', NAMESPACES)
                                if low is not None and high is not None:
                                    reference = f"{low.get('value')}-{high.get('value')} {test_unit or ''}"

                            results.append({
                                'test': test_name,
                                'value': test_value,
                                'unit': test_unit,
                                'reference_range': reference
                            })

                    if results:
                        labs.append({
                            'panel': panel_name,
                            'date': test_date,
                            'results': results
                        })

                except Exception as e:
                    logger.warning("Failed to parse lab organizer", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse lab results section", error=str(e))

        return labs

    def _parse_immunizations(self) -> List[Dict[str, Any]]:
        """Extract immunizations."""
        immunizations = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.2.1')  # Immunizations section
            if not section:
                return immunizations

            entries = section.findall('.//hl7:entry', NAMESPACES)

            for entry in entries:
                try:
                    substance = entry.find('.//hl7:substanceAdministration', NAMESPACES)
                    if substance is None:
                        continue

                    # Vaccine name
                    material = substance.find('.//hl7:manufacturedMaterial', NAMESPACES)
                    if material is None:
                        continue

                    code_elem = material.find('hl7:code', NAMESPACES)
                    vaccine = code_elem.get('displayName', 'Unknown Vaccine') if code_elem is not None else 'Unknown Vaccine'
                    cvx_code = code_elem.get('code') if code_elem is not None else None

                    # Date
                    effective_time = substance.find('hl7:effectiveTime', NAMESPACES)
                    admin_date = None
                    if effective_time is not None:
                        date_value = effective_time.get('value')
                        admin_date = self._format_hl7_date(date_value)

                    immunizations.append({
                        'vaccine': vaccine,
                        'cvx_code': cvx_code,
                        'date': admin_date
                    })

                except Exception as e:
                    logger.warning("Failed to parse immunization entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse immunizations section", error=str(e))

        return immunizations

    def _parse_vital_signs(self) -> List[Dict[str, Any]]:
        """Extract vital signs."""
        vitals = []

        try:
            section = self._find_section('2.16.840.1.113883.10.20.22.2.4.1')  # Vital signs section
            if not section:
                return vitals

            organizers = section.findall('.//hl7:organizer', NAMESPACES)

            for organizer in organizers:
                try:
                    # Date
                    effective_time = organizer.find('hl7:effectiveTime', NAMESPACES)
                    vital_date = None
                    if effective_time is not None:
                        date_value = effective_time.get('value')
                        vital_date = self._format_hl7_date(date_value)

                    # Measurements
                    observations = organizer.findall('.//hl7:observation', NAMESPACES)
                    measurements = {}

                    for obs in observations:
                        code = obs.find('hl7:code', NAMESPACES)
                        value = obs.find('hl7:value', NAMESPACES)

                        if code is not None and value is not None:
                            vital_type = code.get('displayName', 'Unknown')
                            vital_value = value.get('value')
                            vital_unit = value.get('unit')

                            measurements[vital_type] = f"{vital_value} {vital_unit}" if vital_unit else vital_value

                    if measurements:
                        vitals.append({
                            'date': vital_date,
                            'measurements': measurements
                        })

                except Exception as e:
                    logger.warning("Failed to parse vital signs entry", error=str(e))
                    continue

        except Exception as e:
            logger.warning("Failed to parse vital signs section", error=str(e))

        return vitals

    def _parse_metadata(self) -> Dict[str, Any]:
        """Extract document metadata."""
        try:
            # Document ID
            id_elem = self.root.find('hl7:id', NAMESPACES)
            doc_id = id_elem.get('root') if id_elem is not None else None

            # Document title
            title_elem = self.root.find('hl7:title', NAMESPACES)
            title = title_elem.text if title_elem is not None else None

            # Effective time (document date)
            time_elem = self.root.find('hl7:effectiveTime', NAMESPACES)
            doc_date = self._format_hl7_date(time_elem.get('value')) if time_elem is not None else None

            # Author organization
            author = self.root.find('.//hl7:author/hl7:assignedAuthor', NAMESPACES)
            org_name = None
            if author is not None:
                org = author.find('.//hl7:representedOrganization/hl7:name', NAMESPACES)
                org_name = org.text if org is not None else None

            return {
                'document_id': doc_id,
                'title': title,
                'date': doc_date,
                'source_organization': org_name
            }

        except Exception as e:
            logger.warning("Failed to parse metadata", error=str(e))
            return {}

    def _find_section(self, template_id: str):
        """Find a section by its template ID."""
        sections = self.root.findall('.//hl7:section', NAMESPACES)
        for section in sections:
            template = section.find(f'hl7:templateId[@root="{template_id}"]', NAMESPACES)
            if template is not None:
                return section
        return None

    def _get_text(self, parent, tag: str) -> Optional[str]:
        """Safely extract text from an element."""
        if parent is None:
            return None
        elem = parent.find(tag, NAMESPACES)
        return elem.text if elem is not None and elem.text else None

    def _format_hl7_date(self, date_str: Optional[str]) -> Optional[str]:
        """Convert HL7 date format (YYYYMMDD or YYYYMMDDHHMMSS) to ISO format."""
        if not date_str:
            return None

        try:
            # Remove timezone if present
            date_str = date_str.split('+')[0].split('-')[0]

            if len(date_str) >= 8:
                year = date_str[0:4]
                month = date_str[4:6]
                day = date_str[6:8]
                return f"{year}-{month}-{day}"

        except Exception as e:
            logger.warning("Failed to format date", date=date_str, error=str(e))

        return None
