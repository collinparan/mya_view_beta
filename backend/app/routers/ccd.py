"""
CCD (Continuity of Care Document) Router

Handles upload, parsing, review, and import of C-CDA files from EHR systems.
"""

from typing import Dict, List, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Body
from pydantic import BaseModel, Field
import uuid
import structlog
from neo4j import AsyncGraphDatabase

from app.config import settings
from app.services.ccd_parser import CCDParser

logger = structlog.get_logger()
router = APIRouter()


class CCDPreview(BaseModel):
    """Preview of parsed CCD data for review."""
    upload_id: str
    demographics: Dict[str, Any] | None
    medications: List[Dict[str, Any]]
    allergies: List[Dict[str, Any]]
    problems: List[Dict[str, Any]]
    procedures: List[Dict[str, Any]]
    lab_results: List[Dict[str, Any]]
    immunizations: List[Dict[str, Any]]
    vital_signs: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    summary: Dict[str, int] = Field(default_factory=dict)


class CCDImportRequest(BaseModel):
    """Request to import selected CCD data."""
    upload_id: str
    family_member_id: str
    selected_sections: List[str]  # e.g., ['medications', 'problems', 'allergies']
    selected_items: Dict[str, List[int]] = Field(default_factory=dict)  # section -> indices


class CCDImportResponse(BaseModel):
    """Response after importing CCD data."""
    success: bool
    imported_counts: Dict[str, int]
    errors: List[str] = Field(default_factory=list)


# Temporary storage for uploaded CCD files (in production, use Redis or DB)
_ccd_storage: Dict[str, Dict[str, Any]] = {}


@router.post("/upload", response_model=CCDPreview)
async def upload_ccd(file: UploadFile = File(...)):
    """
    Upload and parse a CCD XML file.

    Returns a preview of all extracted data for user review.
    User can then selectively choose what to import.
    """
    logger.info("CCD upload started", filename=file.filename)

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(('.xml', '.ccd', '.ccda')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a CCD/C-CDA XML file (.xml, .ccd, or .ccda)"
        )

    try:
        # Read file content
        content = await file.read()

        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=400,
                detail="File too large. Maximum size is 10MB"
            )

        # Parse CCD
        parser = CCDParser()
        parsed_data = parser.parse_file(content)

        # Generate upload ID
        upload_id = str(uuid.uuid4())

        # Store parsed data temporarily
        _ccd_storage[upload_id] = parsed_data

        # Build summary
        summary = {
            'medications': len(parsed_data.get('medications', [])),
            'allergies': len(parsed_data.get('allergies', [])),
            'problems': len(parsed_data.get('problems', [])),
            'procedures': len(parsed_data.get('procedures', [])),
            'lab_results': len(parsed_data.get('lab_results', [])),
            'immunizations': len(parsed_data.get('immunizations', [])),
            'vital_signs': len(parsed_data.get('vital_signs', []))
        }

        logger.info("CCD parsed successfully", upload_id=upload_id, summary=summary)

        return CCDPreview(
            upload_id=upload_id,
            demographics=parsed_data.get('demographics'),
            medications=parsed_data.get('medications', []),
            allergies=parsed_data.get('allergies', []),
            problems=parsed_data.get('problems', []),
            procedures=parsed_data.get('procedures', []),
            lab_results=parsed_data.get('lab_results', []),
            immunizations=parsed_data.get('immunizations', []),
            vital_signs=parsed_data.get('vital_signs', []),
            metadata=parsed_data.get('metadata', {}),
            summary=summary
        )

    except ValueError as e:
        logger.error("Invalid CCD format", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to parse CCD", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse CCD file")


@router.post("/import", response_model=CCDImportResponse)
async def import_ccd(request: CCDImportRequest = Body(...)):
    """
    Import selected CCD data into Neo4j for a specific family member.

    Only imports the sections and items explicitly selected by the user.
    """
    logger.info("CCD import started",
               upload_id=request.upload_id,
               member=request.family_member_id,
               sections=request.selected_sections)

    # Retrieve parsed data
    parsed_data = _ccd_storage.get(request.upload_id)
    if not parsed_data:
        raise HTTPException(
            status_code=404,
            detail="Upload not found. Please re-upload the CCD file."
        )

    try:
        # Connect to Neo4j
        user, password = settings.neo4j_credentials
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_url,
            auth=(user, password)
        )

        imported_counts = {}
        errors = []

        async with driver.session() as session:
            # Verify family member exists
            result = await session.run(
                "MATCH (p:Person {id: $id}) RETURN p",
                id=request.family_member_id
            )
            person = await result.single()
            if not person:
                raise HTTPException(
                    status_code=404,
                    detail=f"Family member {request.family_member_id} not found"
                )

            # Import selected sections
            if 'medications' in request.selected_sections:
                count = await _import_medications(
                    session,
                    request.family_member_id,
                    parsed_data.get('medications', []),
                    request.selected_items.get('medications', [])
                )
                imported_counts['medications'] = count

            if 'allergies' in request.selected_sections:
                count = await _import_allergies(
                    session,
                    request.family_member_id,
                    parsed_data.get('allergies', []),
                    request.selected_items.get('allergies', [])
                )
                imported_counts['allergies'] = count

            if 'problems' in request.selected_sections:
                count = await _import_problems(
                    session,
                    request.family_member_id,
                    parsed_data.get('problems', []),
                    request.selected_items.get('problems', [])
                )
                imported_counts['problems'] = count

            if 'procedures' in request.selected_sections:
                count = await _import_procedures(
                    session,
                    request.family_member_id,
                    parsed_data.get('procedures', []),
                    request.selected_items.get('procedures', [])
                )
                imported_counts['procedures'] = count

            if 'lab_results' in request.selected_sections:
                count = await _import_lab_results(
                    session,
                    request.family_member_id,
                    parsed_data.get('lab_results', []),
                    request.selected_items.get('lab_results', [])
                )
                imported_counts['lab_results'] = count

        await driver.close()

        # Clean up stored data
        del _ccd_storage[request.upload_id]

        logger.info("CCD import completed", imported_counts=imported_counts)

        return CCDImportResponse(
            success=True,
            imported_counts=imported_counts,
            errors=errors
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to import CCD", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to import CCD data")


async def _import_medications(session, member_id: str, medications: List[Dict], selected_indices: List[int]) -> int:
    """Import medications into Neo4j."""
    if not selected_indices:
        selected_indices = list(range(len(medications)))

    count = 0
    for idx in selected_indices:
        if idx >= len(medications):
            continue

        med = medications[idx]
        try:
            med_id = f"med_{uuid.uuid4()}"

            await session.run("""
                MATCH (p:Person {id: $member_id})
                MERGE (m:Medication {name: $name})
                ON CREATE SET
                    m.id = $med_id,
                    m.rxnorm_code = $rxnorm_code
                MERGE (p)-[r:TAKES_MEDICATION]->(m)
                ON CREATE SET
                    r.dosage = $dosage,
                    r.frequency = $frequency,
                    r.start_date = date($start_date),
                    r.end_date = CASE WHEN $end_date IS NOT NULL THEN date($end_date) ELSE null END,
                    r.status = $status,
                    r.source = 'ccd_import'
            """,
                member_id=member_id,
                med_id=med_id,
                name=med['name'],
                rxnorm_code=med.get('rxnorm_code'),
                dosage=med.get('dosage'),
                frequency=med.get('frequency'),
                start_date=med.get('start_date'),
                end_date=med.get('end_date'),
                status=med.get('status', 'active')
            )
            count += 1

        except Exception as e:
            logger.warning("Failed to import medication", medication=med['name'], error=str(e))

    return count


async def _import_allergies(session, member_id: str, allergies: List[Dict], selected_indices: List[int]) -> int:
    """Import allergies into Neo4j."""
    if not selected_indices:
        selected_indices = list(range(len(allergies)))

    count = 0
    for idx in selected_indices:
        if idx >= len(allergies):
            continue

        allergy = allergies[idx]
        try:
            allergy_id = f"allergy_{uuid.uuid4()}"

            await session.run("""
                MATCH (p:Person {id: $member_id})
                MERGE (a:Allergy {allergen: $allergen})
                ON CREATE SET
                    a.id = $allergy_id,
                    a.allergen_code = $allergen_code
                MERGE (p)-[r:HAS_ALLERGY]->(a)
                ON CREATE SET
                    r.reaction = $reaction,
                    r.severity = $severity,
                    r.source = 'ccd_import'
            """,
                member_id=member_id,
                allergy_id=allergy_id,
                allergen=allergy['allergen'],
                allergen_code=allergy.get('allergen_code'),
                reaction=allergy.get('reaction'),
                severity=allergy.get('severity')
            )
            count += 1

        except Exception as e:
            logger.warning("Failed to import allergy", allergen=allergy['allergen'], error=str(e))

    return count


async def _import_problems(session, member_id: str, problems: List[Dict], selected_indices: List[int]) -> int:
    """Import conditions/problems into Neo4j."""
    if not selected_indices:
        selected_indices = list(range(len(problems)))

    count = 0
    for idx in selected_indices:
        if idx >= len(problems):
            continue

        problem = problems[idx]
        try:
            condition_id = f"cond_{uuid.uuid4()}"

            await session.run("""
                MATCH (p:Person {id: $member_id})
                MERGE (c:Condition {name: $name})
                ON CREATE SET
                    c.id = $condition_id,
                    c.icd10_code = $icd10_code
                MERGE (p)-[r:HAS_CONDITION]->(c)
                ON CREATE SET
                    r.diagnosed_date = CASE WHEN $diagnosed_date IS NOT NULL THEN date($diagnosed_date) ELSE null END,
                    r.resolved_date = CASE WHEN $resolved_date IS NOT NULL THEN date($resolved_date) ELSE null END,
                    r.status = $status,
                    r.source = 'ccd_import'
            """,
                member_id=member_id,
                condition_id=condition_id,
                name=problem['name'],
                icd10_code=problem.get('icd10_code'),
                diagnosed_date=problem.get('diagnosed_date'),
                resolved_date=problem.get('resolved_date'),
                status=problem.get('status', 'active')
            )
            count += 1

        except Exception as e:
            logger.warning("Failed to import problem", problem=problem['name'], error=str(e))

    return count


async def _import_procedures(session, member_id: str, procedures: List[Dict], selected_indices: List[int]) -> int:
    """Import procedures into Neo4j."""
    if not selected_indices:
        selected_indices = list(range(len(procedures)))

    count = 0
    for idx in selected_indices:
        if idx >= len(procedures):
            continue

        procedure = procedures[idx]
        try:
            proc_id = f"proc_{uuid.uuid4()}"

            await session.run("""
                MATCH (p:Person {id: $member_id})
                MERGE (proc:Procedure {name: $name})
                ON CREATE SET
                    proc.id = $proc_id,
                    proc.cpt_code = $cpt_code
                MERGE (p)-[r:HAD_PROCEDURE]->(proc)
                ON CREATE SET
                    r.date = CASE WHEN $date IS NOT NULL THEN date($date) ELSE null END,
                    r.source = 'ccd_import'
            """,
                member_id=member_id,
                proc_id=proc_id,
                name=procedure['name'],
                cpt_code=procedure.get('cpt_code'),
                date=procedure.get('date')
            )
            count += 1

        except Exception as e:
            logger.warning("Failed to import procedure", procedure=procedure['name'], error=str(e))

    return count


async def _import_lab_results(session, member_id: str, lab_results: List[Dict], selected_indices: List[int]) -> int:
    """Import lab results into Neo4j."""
    if not selected_indices:
        selected_indices = list(range(len(lab_results)))

    count = 0
    for idx in selected_indices:
        if idx >= len(lab_results):
            continue

        lab = lab_results[idx]
        try:
            lab_id = f"lab_{uuid.uuid4()}"

            # Create summary from results
            results_summary = []
            for result in lab.get('results', []):
                results_summary.append(
                    f"{result['test']}: {result['value']} {result.get('unit', '')}"
                )
            summary = '; '.join(results_summary)

            await session.run("""
                MATCH (p:Person {id: $member_id})
                CREATE (le:LabEvent {
                    id: $lab_id,
                    document_type: $panel,
                    date: CASE WHEN $date IS NOT NULL THEN date($date) ELSE date() END,
                    summary: $summary,
                    source: 'ccd_import'
                })
                CREATE (p)-[:HAD_LAB_EVENT]->(le)
            """,
                member_id=member_id,
                lab_id=lab_id,
                panel=lab.get('panel', 'Lab Results'),
                date=lab.get('date'),
                summary=summary
            )
            count += 1

        except Exception as e:
            logger.warning("Failed to import lab result", lab=lab.get('panel'), error=str(e))

    return count


@router.get("/uploads/{upload_id}")
async def get_upload_preview(upload_id: str):
    """Retrieve a previously uploaded CCD preview."""
    parsed_data = _ccd_storage.get(upload_id)
    if not parsed_data:
        raise HTTPException(
            status_code=404,
            detail="Upload not found. It may have expired or been imported."
        )

    summary = {
        'medications': len(parsed_data.get('medications', [])),
        'allergies': len(parsed_data.get('allergies', [])),
        'problems': len(parsed_data.get('problems', [])),
        'procedures': len(parsed_data.get('procedures', [])),
        'lab_results': len(parsed_data.get('lab_results', [])),
        'immunizations': len(parsed_data.get('immunizations', [])),
        'vital_signs': len(parsed_data.get('vital_signs', []))
    }

    return CCDPreview(
        upload_id=upload_id,
        demographics=parsed_data.get('demographics'),
        medications=parsed_data.get('medications', []),
        allergies=parsed_data.get('allergies', []),
        problems=parsed_data.get('problems', []),
        procedures=parsed_data.get('procedures', []),
        lab_results=parsed_data.get('lab_results', []),
        immunizations=parsed_data.get('immunizations', []),
        vital_signs=parsed_data.get('vital_signs', []),
        metadata=parsed_data.get('metadata', {}),
        summary=summary
    )
