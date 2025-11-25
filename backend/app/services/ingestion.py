"""
Data Ingestion Service - Parse medical documents and load into databases.
Handles lab results, interpretations, and medical records.
"""

import re
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger()


class LabFlag(Enum):
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"
    CRITICAL_HIGH = "critical_high"
    CRITICAL_LOW = "critical_low"


@dataclass
class LabResult:
    """Individual lab test result."""
    test_name: str
    value: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: LabFlag = LabFlag.NORMAL
    category: Optional[str] = None
    interpretation: Optional[str] = None


@dataclass
class Condition:
    """Medical condition or finding."""
    name: str
    status: str = "active"  # active, resolved, suspected
    severity: str = "mild"  # mild, moderate, severe
    icd10_code: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Provider:
    """Healthcare provider."""
    name: str
    facility: Optional[str] = None
    specialty: Optional[str] = None


@dataclass
class Appointment:
    """Medical appointment record."""
    date: date
    time: Optional[str] = None
    appointment_type: str = "VA appointment"
    facility: Optional[str] = None
    clinic: Optional[str] = None
    location: Optional[str] = None


@dataclass
class MedicalDocument:
    """Parsed medical document with extracted entities."""
    id: str
    document_type: str  # lab_result, interpretation, medical_record
    document_date: Optional[date] = None
    patient_name: Optional[str] = None
    provider: Optional[Provider] = None
    raw_text: str = ""

    lab_results: List[LabResult] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)
    followup_items: List[str] = field(default_factory=list)
    appointments: List[Appointment] = field(default_factory=list)
    summary: Optional[str] = None


class MedicalDocumentParser:
    """Parse medical documents and extract structured data."""

    def __init__(self):
        # Common lab test patterns
        self.lab_patterns = {
            # Pattern: test_name value unit reference_range
            "table_row": re.compile(
                r'\|\s*(?:\*\*)?([^|*]+?)(?:\*\*)?\s*\|\s*'  # Test name
                r'(?:\*\*)?([0-9.,]+)\s*([a-zA-Z/%°₂]+)?(?:\*\*)?\s*\|\s*'  # Value + unit
                r'([^|]+)\s*\|',  # Reference range
                re.IGNORECASE
            ),
            "inline": re.compile(
                r'(?:\*\*)?([A-Za-z0-9\s]+?)\s+'
                r'([0-9.,]+)\s*([a-zA-Z/%°]+)?\s*'
                r'\(([^)]+)\)',
                re.IGNORECASE
            ),
        }

        # Flag indicators
        self.flag_indicators = {
            "high": ["⚠️", "high", "elevated", "above", ">"],
            "low": ["low", "below", "<", "decreased"],
            "normal": ["✅", "normal", "within", "optimal"],
        }

        # Common condition patterns
        self.condition_keywords = {
            "prediabetes": {"icd10": "R73.03", "keywords": ["prediabetes", "prediabetic", "a1c 5.7-6.4"]},
            "fatty_liver": {"icd10": "K76.0", "keywords": ["fatty liver", "nafld", "hepatic steatosis"]},
            "hyperlipidemia": {"icd10": "E78.5", "keywords": ["high ldl", "elevated ldl", "hyperlipidemia", "high cholesterol"]},
            "elevated_liver_enzymes": {"icd10": "R74.01", "keywords": ["elevated alt", "elevated ast", "liver enzymes"]},
        }

    def parse_markdown(self, content: str, filename: str) -> MedicalDocument:
        """Parse a markdown medical document."""
        doc = MedicalDocument(
            id=str(uuid.uuid4()),
            document_type=self._detect_document_type(filename, content),
            raw_text=content,
        )

        # Extract patient name
        doc.patient_name = self._extract_patient_name(content)

        # Extract provider
        doc.provider = self._extract_provider(content)

        # Extract lab results from tables
        doc.lab_results = self._extract_lab_results(content)

        # Identify conditions based on content
        doc.conditions = self._identify_conditions(content, doc.lab_results)

        # Extract follow-up items
        doc.followup_items = self._extract_followup_items(content)

        # Extract appointments
        doc.appointments = self._extract_appointments(content)

        # Extract summary
        doc.summary = self._extract_summary(content)

        logger.info(
            "Parsed medical document",
            filename=filename,
            lab_results=len(doc.lab_results),
            conditions=len(doc.conditions),
            followup_items=len(doc.followup_items),
            appointments=len(doc.appointments),
        )

        return doc

    def _detect_document_type(self, filename: str, content: str) -> str:
        """Detect the type of medical document."""
        filename_lower = filename.lower()
        content_lower = content.lower()

        if "lab" in filename_lower or "result" in content_lower[:500]:
            return "lab_result"
        if "interpretation" in filename_lower or "interpretation" in content_lower[:500]:
            return "interpretation"
        if "prescription" in filename_lower or "rx" in filename_lower:
            return "prescription"
        return "medical_record"

    def _extract_patient_name(self, content: str) -> Optional[str]:
        """Extract patient name from document."""
        patterns = [
            r'#\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–—]',  # # Name -
            r'(?:Patient|Name|Prepared for)[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'(?:for|of)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_provider(self, content: str) -> Optional[Provider]:
        """Extract healthcare provider information."""
        # Look for "Dr." or "Physician:" patterns
        patterns = [
            r'(?:Physician|Doctor|Provider)[:\s]+(?:Dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
            r'Dr\.?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
        ]

        name = None
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                name = match.group(1).strip()
                break

        if not name:
            return None

        # Look for facility
        facility = None
        facility_match = re.search(r'(VA\s+Hospital|VA\s+Medical|Hospital|Clinic)', content, re.IGNORECASE)
        if facility_match:
            facility = facility_match.group(1)

        return Provider(name=name, facility=facility)

    def _extract_lab_results(self, content: str) -> List[LabResult]:
        """Extract lab results from markdown tables."""
        results = []
        current_category = None

        # Split by lines and process table rows
        lines = content.split('\n')

        for line in lines:
            # Check for category headers
            category_match = re.search(r'\*\*([A-Za-z\s]+)\*\*', line)
            if category_match and '|' in line:
                potential_category = category_match.group(1).strip()
                if potential_category.lower() not in ['test', 'result', 'reference', 'interpretation']:
                    current_category = potential_category

            # Parse table rows with lab values
            if '|' in line and re.search(r'\d', line):
                result = self._parse_lab_row(line, current_category)
                if result:
                    results.append(result)

        return results

    def _parse_lab_row(self, line: str, category: Optional[str]) -> Optional[LabResult]:
        """Parse a single lab result row."""
        # Clean the line
        line = line.strip()

        # Split by pipe and clean
        parts = [p.strip() for p in line.split('|') if p.strip()]

        if len(parts) < 3:
            return None

        # Try to extract test name, value, reference range
        test_name = None
        value = None
        unit = None
        reference = None
        flag = LabFlag.NORMAL
        interpretation = None

        for i, part in enumerate(parts):
            # Clean markdown formatting
            clean_part = re.sub(r'\*+', '', part).strip()

            # Check if this looks like a test name (starts with letter, not a number)
            if not test_name and re.match(r'^[A-Za-z]', clean_part) and not re.match(r'^[<>]?\d', clean_part):
                test_name = clean_part
                continue

            # Check if this looks like a value (number)
            value_match = re.match(r'^([<>]?\d+\.?\d*)\s*([a-zA-Z/%°₂]+)?', clean_part)
            if value_match and not value:
                value = value_match.group(1)
                unit = value_match.group(2)
                continue

            # Check if this looks like a reference range
            if re.search(r'\d+\s*[-–]\s*\d+|[<>]\s*\d+', clean_part) and not reference:
                reference = clean_part
                continue

            # Check for flag indicators
            if '✅' in part or 'Normal' in part:
                flag = LabFlag.NORMAL
                interpretation = clean_part
            elif '⚠️' in part or 'High' in part or 'Elevated' in part:
                flag = LabFlag.HIGH
                interpretation = clean_part
            elif 'Low' in part:
                flag = LabFlag.LOW
                interpretation = clean_part

        if test_name and value:
            return LabResult(
                test_name=test_name,
                value=value,
                unit=unit,
                reference_range=reference,
                flag=flag,
                category=category,
                interpretation=interpretation,
            )

        return None

    def _identify_conditions(self, content: str, lab_results: List[LabResult]) -> List[Condition]:
        """Identify medical conditions from content and lab results."""
        conditions = []
        content_lower = content.lower()

        for condition_key, config in self.condition_keywords.items():
            for keyword in config["keywords"]:
                if keyword in content_lower:
                    conditions.append(Condition(
                        name=condition_key.replace("_", " ").title(),
                        status="suspected" if "suspected" in content_lower or "possible" in content_lower else "active",
                        severity="mild",
                        icd10_code=config["icd10"],
                    ))
                    break

        # Check lab results for specific conditions
        for result in lab_results:
            if result.flag in [LabFlag.HIGH, LabFlag.LOW]:
                test_lower = result.test_name.lower()

                # A1C prediabetes check
                if "a1c" in test_lower:
                    try:
                        a1c_value = float(result.value.replace('%', ''))
                        if 5.7 <= a1c_value < 6.5:
                            if not any(c.name == "Prediabetes" for c in conditions):
                                conditions.append(Condition(
                                    name="Prediabetes",
                                    status="active",
                                    severity="mild",
                                    icd10_code="R73.03",
                                    notes=f"A1C {result.value}%",
                                ))
                    except ValueError:
                        pass

        return conditions

    def _extract_followup_items(self, content: str) -> List[str]:
        """Extract follow-up recommendations."""
        items = []

        # Look for numbered lists under "Discussion Points" or "Follow-up"
        followup_section = re.search(
            r'(?:Discussion Points|Follow-up|Recommendations|Plan)[^\n]*\n((?:.*?\n)*?)(?=\n##|\n---|\Z)',
            content,
            re.IGNORECASE
        )

        if followup_section:
            section_text = followup_section.group(1)
            # Extract numbered or bulleted items
            item_matches = re.findall(r'(?:^\s*[-•*]|\d+\.)\s*(.+?)(?=\n|$)', section_text, re.MULTILINE)
            items.extend([item.strip() for item in item_matches if item.strip()])

        return items

    def _extract_summary(self, content: str) -> Optional[str]:
        """Extract summary or TL;DR section."""
        patterns = [
            r'(?:TL;DR|Summary|Impression)[^\n]*\n+(.+?)(?=\n##|\n---|\Z)',
            r'\*\*Impression:\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                summary = match.group(1).strip()
                # Clean up markdown
                summary = re.sub(r'\*+', '', summary)
                summary = re.sub(r'\n+', ' ', summary)
                return summary[:500]  # Limit length

        return None

    def _extract_appointments(self, content: str) -> List[Appointment]:
        """Extract appointment records from content."""
        appointments = []

        # Month name to number mapping
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

        # Look for VA-style appointment patterns
        # Pattern: "4 Tue 9:00 a.m. MT VA appointment" under "November 2025"
        current_month = None
        current_year = None

        lines = content.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()

            # Check for month header (e.g., "November 2025")
            month_match = re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$', line, re.IGNORECASE)
            if month_match:
                current_month = months.get(month_match.group(1).lower())
                current_year = int(month_match.group(2))
                continue

            # Check for appointment line pattern
            # "4 Tue 9:00 a.m. MT VA appointment" or "17 Fri 8:30 a.m. MT Primary care"
            appt_match = re.match(r'^(\d{1,2})\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*(\d{1,2}:\d{2}\s*[ap]\.?m\.?)\s*(?:MT|ET|CT|PT)?\s*(.+?)$', line, re.IGNORECASE)
            if appt_match and current_month and current_year:
                day = int(appt_match.group(1))
                time_str = appt_match.group(2)
                appt_type = appt_match.group(3).strip()

                try:
                    appt_date = date(current_year, current_month, day)
                except ValueError:
                    continue

                # Look for facility and clinic info in subsequent lines
                facility = None
                clinic = None
                location = None

                for j in range(i + 1, min(i + 6, len(lines))):
                    next_line = lines[j].strip()
                    if re.match(r'^At\s+', next_line):
                        facility = re.sub(r'^At\s+', '', next_line)
                    elif re.match(r'^Clinic:', next_line):
                        clinic = re.sub(r'^Clinic:\s*', '', next_line)
                    elif re.match(r'^Location:', next_line):
                        location = re.sub(r'^Location:\s*', '', next_line)
                    elif re.match(r'^\d{1,2}\s', next_line) or re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)', next_line, re.IGNORECASE):
                        break

                appointments.append(Appointment(
                    date=appt_date,
                    time=time_str,
                    appointment_type=appt_type,
                    facility=facility,
                    clinic=clinic,
                    location=location,
                ))

        return appointments


def generate_name_aliases(full_name: str, preferred_name: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Generate common name aliases from a full name.

    Example: "Philip Collin Richard Navarro Paran" with preferred "Collin"
    Returns aliases like: "Philip Paran", "Collin Paran", "P. Collin Paran", etc.
    """
    if not full_name:
        return []

    aliases = []
    parts = full_name.split()

    if len(parts) < 2:
        return []

    first_name = parts[0]
    last_name = parts[-1]
    middle_names = parts[1:-1] if len(parts) > 2 else []

    # Standard aliases
    aliases.append({"name": f"{first_name} {last_name}", "source": "form_truncation"})

    # First initial + last name
    aliases.append({"name": f"{first_name[0]}. {last_name}", "source": "form_truncation"})

    # If preferred name exists and is different from first name
    if preferred_name and preferred_name.lower() != first_name.lower():
        aliases.append({"name": f"{preferred_name} {last_name}", "source": "preferred", "is_primary": True})
        aliases.append({"name": f"{first_name[0]}. {preferred_name} {last_name}", "source": "formal"})

    # Middle name variations
    for i, middle in enumerate(middle_names):
        if middle != preferred_name:  # Don't duplicate preferred name
            aliases.append({"name": f"{first_name} {middle[0]}. {last_name}", "source": "form_truncation"})
            aliases.append({"name": f"{middle} {last_name}", "source": "middle_name_used"})

    return aliases


@dataclass
class BirthInfo:
    """Birth information for a person."""
    date_of_birth: Optional[date] = None
    birth_city: Optional[str] = None
    birth_country: Optional[str] = None
    birth_country_code: Optional[str] = None  # ISO 3166-1 alpha-2


def generate_neo4j_queries(
    doc: MedicalDocument,
    family_member_id: str,
    full_legal_name: Optional[str] = None,
    preferred_name: Optional[str] = None,
    birth_info: Optional[BirthInfo] = None,
    additional_aliases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Generate Neo4j Cypher queries to insert document data."""
    queries = []
    doc_date = doc.document_date or date.today()

    # Create or match person node with preferred name and DOB support
    person_query = """
        MERGE (p:Person {id: $person_id})
        SET p.name = COALESCE($full_name, p.name, $extracted_name),
            p.preferred_name = COALESCE($preferred_name, p.preferred_name)
    """
    person_params = {
        "person_id": family_member_id,
        "full_name": full_legal_name,
        "extracted_name": doc.patient_name or "Unknown",
        "preferred_name": preferred_name,
    }

    # Add DOB if provided
    if birth_info and birth_info.date_of_birth:
        person_query += ",\n            p.date_of_birth = date($dob)"
        person_params["dob"] = birth_info.date_of_birth.isoformat()

    person_query += "\n        RETURN p"
    queries.append({"query": person_query, "params": person_params})

    # Create birth location and relationship if provided
    if birth_info and birth_info.birth_city and birth_info.birth_country:
        location_id = f"{birth_info.birth_city.lower().replace(' ', '-')}-{birth_info.birth_country_code or birth_info.birth_country[:2].lower()}"
        queries.append({
            "query": """
                MATCH (p:Person {id: $person_id})
                MERGE (loc:Location {id: $loc_id})
                SET loc.city = $city,
                    loc.country = $country,
                    loc.country_code = $country_code
                MERGE (p)-[:BORN_IN]->(loc)
                RETURN loc
            """,
            "params": {
                "person_id": family_member_id,
                "loc_id": location_id,
                "city": birth_info.birth_city,
                "country": birth_info.birth_country,
                "country_code": birth_info.birth_country_code,
            }
        })

    # Generate and create aliases if full name provided
    if full_legal_name:
        aliases = generate_name_aliases(full_legal_name, preferred_name)
        for alias in aliases:
            queries.append({
                "query": """
                    MATCH (p:Person {id: $person_id})
                    MERGE (a:Alias {name: $alias_name})
                    SET a.source = $source,
                        a.is_primary = $is_primary
                    MERGE (p)-[:HAS_ALIAS]->(a)
                    RETURN a
                """,
                "params": {
                    "person_id": family_member_id,
                    "alias_name": alias["name"],
                    "source": alias.get("source", "unknown"),
                    "is_primary": alias.get("is_primary", False),
                }
            })

    # Add any additional manual aliases (nicknames, etc.)
    if additional_aliases:
        for alias_name in additional_aliases:
            queries.append({
                "query": """
                    MATCH (p:Person {id: $person_id})
                    MERGE (a:Alias {name: $alias_name})
                    SET a.source = 'nickname'
                    MERGE (p)-[:HAS_ALIAS]->(a)
                    RETURN a
                """,
                "params": {
                    "person_id": family_member_id,
                    "alias_name": alias_name,
                }
            })

    # Create provider if exists
    if doc.provider:
        queries.append({
            "query": """
                MERGE (prov:Provider {name: $name})
                SET prov.facility = $facility
                RETURN prov
            """,
            "params": {
                "name": doc.provider.name,
                "facility": doc.provider.facility,
            }
        })

    # Create lab event node
    lab_event_id = f"lab_{doc.id}"
    queries.append({
        "query": """
            MATCH (p:Person {id: $person_id})
            CREATE (le:LabEvent {
                id: $event_id,
                date: date($date),
                document_type: $doc_type,
                summary: $summary
            })
            CREATE (p)-[:HAD_LAB_EVENT]->(le)
            RETURN le
        """,
        "params": {
            "person_id": family_member_id,
            "event_id": lab_event_id,
            "date": doc_date.isoformat(),
            "doc_type": doc.document_type,
            "summary": doc.summary,
        }
    })

    # Create lab result nodes
    for result in doc.lab_results:
        queries.append({
            "query": """
                MATCH (le:LabEvent {id: $event_id})
                CREATE (lr:LabResult {
                    test_name: $test_name,
                    value: $value,
                    unit: $unit,
                    reference_range: $reference,
                    flag: $flag,
                    category: $category
                })
                CREATE (le)-[:INCLUDES]->(lr)
                RETURN lr
            """,
            "params": {
                "event_id": lab_event_id,
                "test_name": result.test_name,
                "value": result.value,
                "unit": result.unit,
                "reference": result.reference_range,
                "flag": result.flag.value,
                "category": result.category,
            }
        })

    # Create condition nodes and relationships
    for condition in doc.conditions:
        queries.append({
            "query": """
                MATCH (p:Person {id: $person_id})
                MERGE (c:Condition {name: $name})
                SET c.icd10_code = $icd10
                MERGE (p)-[r:HAS_CONDITION]->(c)
                SET r.status = $status,
                    r.severity = $severity,
                    r.diagnosed_date = date($date),
                    r.notes = $notes
                RETURN c
            """,
            "params": {
                "person_id": family_member_id,
                "name": condition.name,
                "icd10": condition.icd10_code,
                "status": condition.status,
                "severity": condition.severity,
                "date": doc_date.isoformat(),
                "notes": condition.notes,
            }
        })

    # Create appointment nodes and relationships
    for appt in doc.appointments:
        appt_id = f"appt_{appt.date.isoformat()}_{appt.time.replace(' ', '').replace('.', '').replace(':', '') if appt.time else 'unknown'}"
        queries.append({
            "query": """
                MATCH (p:Person {id: $person_id})
                MERGE (a:Appointment {id: $appt_id})
                SET a.date = date($date),
                    a.time = $time,
                    a.appointment_type = $appt_type,
                    a.facility = $facility,
                    a.clinic = $clinic,
                    a.location = $location
                MERGE (p)-[:HAS_APPOINTMENT]->(a)
                RETURN a
            """,
            "params": {
                "person_id": family_member_id,
                "appt_id": appt_id,
                "date": appt.date.isoformat(),
                "time": appt.time,
                "appt_type": appt.appointment_type,
                "facility": appt.facility,
                "clinic": appt.clinic,
                "location": appt.location,
            }
        })

    return queries
