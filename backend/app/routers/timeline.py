"""
Timeline router - REST endpoints for chronological health event visualization.

Provides timeline data for:
- Lab events and results
- Appointments (past and future)
- Condition diagnoses
- Medication start/stop events
- Procedures
- Genetic marker tests
"""

from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog
import csv
import io

from app.models.database import run_cypher

router = APIRouter()
logger = structlog.get_logger()


class TimelineEvent(BaseModel):
    """A single event on the health timeline."""
    id: str
    event_type: str  # 'lab_event', 'appointment', 'condition', 'medication_start', 'medication_stop', 'procedure', 'genetic_test'
    date: str  # ISO format
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None  # 'normal', 'warning', 'critical'
    metadata: Dict[str, Any] = {}


class TimelineResponse(BaseModel):
    """Timeline data response."""
    family_member_id: str
    family_member_name: str
    events: List[TimelineEvent]
    total_events: int
    date_range: Dict[str, Optional[str]]  # 'start' and 'end'
    event_type_counts: Dict[str, int]


@router.get("/{family_member_id}")
async def get_timeline(
    family_member_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types to include"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum events to return")
):
    """
    Get chronological timeline of health events for a family member.

    Args:
        family_member_id: ID of the family member
        start_date: Optional filter for events after this date
        end_date: Optional filter for events before this date
        event_types: Optional comma-separated list (lab_event,appointment,condition,etc.)
        limit: Maximum number of events to return

    Returns:
        Timeline with all health events in chronological order
    """
    try:
        logger.info("Fetching timeline", member_id=family_member_id,
                   start=start_date, end=end_date)

        # Parse event types filter
        allowed_types = None
        if event_types:
            allowed_types = [t.strip() for t in event_types.split(',')]

        # Build Cypher query to get all timeline events
        query = """
        MATCH (p:Person {id: $member_id})

        // Get all possible timeline events
        OPTIONAL MATCH (p)-[:HAD_LAB_EVENT]->(le:LabEvent)
        OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(appt:Appointment)
        OPTIONAL MATCH (p)-[cond_rel:HAS_CONDITION]->(c:Condition)
        OPTIONAL MATCH (p)-[med_rel:TAKES_MEDICATION]->(m:Medication)
        OPTIONAL MATCH (p)-[proc_rel:HAD_PROCEDURE]->(proc:Procedure)
        OPTIONAL MATCH (p)-[marker_rel:HAS_MARKER]->(gm:GeneticMarker)

        WITH p,
             // Lab events
             CASE WHEN le IS NOT NULL THEN {
                 id: le.id,
                 type: 'lab_event',
                 date: le.date,
                 title: COALESCE(le.document_type, 'Lab Result'),
                 description: le.summary,
                 category: le.document_type,
                 metadata: {summary: le.summary}
             } END as lab_event,

             // Appointments
             CASE WHEN appt IS NOT NULL THEN {
                 id: appt.id,
                 type: 'appointment',
                 date: appt.date,
                 title: appt.appointment_type,
                 description: COALESCE(appt.facility, '') + COALESCE(' - ' + appt.clinic, ''),
                 category: 'appointment',
                 metadata: {
                     time: appt.time,
                     facility: appt.facility,
                     clinic: appt.clinic,
                     location: appt.location
                 }
             } END as appointment,

             // Condition diagnoses
             CASE WHEN c IS NOT NULL AND cond_rel.diagnosed_date IS NOT NULL THEN {
                 id: c.id,
                 type: 'condition',
                 date: cond_rel.diagnosed_date,
                 title: 'Diagnosed: ' + c.name,
                 description: cond_rel.notes,
                 category: c.category,
                 severity: cond_rel.severity,
                 metadata: {
                     icd10: c.icd10_code,
                     status: cond_rel.status,
                     severity: cond_rel.severity,
                     hereditary: c.hereditary
                 }
             } END as condition,

             // Medication starts
             CASE WHEN m IS NOT NULL AND med_rel.start_date IS NOT NULL THEN {
                 id: m.id + '_start',
                 type: 'medication_start',
                 date: med_rel.start_date,
                 title: 'Started: ' + m.name,
                 description: COALESCE(med_rel.dosage, '') + COALESCE(' ' + med_rel.frequency, ''),
                 category: m.drug_class,
                 metadata: {
                     dosage: med_rel.dosage,
                     frequency: med_rel.frequency,
                     prescriber: med_rel.prescriber,
                     brand_names: m.brand_names
                 }
             } END as medication_start,

             // Medication stops
             CASE WHEN m IS NOT NULL AND med_rel.end_date IS NOT NULL THEN {
                 id: m.id + '_stop',
                 type: 'medication_stop',
                 date: med_rel.end_date,
                 title: 'Stopped: ' + m.name,
                 description: 'Discontinued medication',
                 category: m.drug_class,
                 metadata: {
                     started: med_rel.start_date
                 }
             } END as medication_stop,

             // Procedures
             CASE WHEN proc IS NOT NULL AND proc_rel.date IS NOT NULL THEN {
                 id: proc.id,
                 type: 'procedure',
                 date: proc_rel.date,
                 title: proc.name,
                 description: proc_rel.notes,
                 category: proc.procedure_type,
                 metadata: {
                     cpt_code: proc.cpt_code,
                     provider: proc_rel.provider,
                     outcome: proc_rel.outcome
                 }
             } END as procedure,

             // Genetic marker tests
             CASE WHEN gm IS NOT NULL AND marker_rel.test_date IS NOT NULL THEN {
                 id: gm.id,
                 type: 'genetic_test',
                 date: marker_rel.test_date,
                 title: 'Genetic Test: ' + gm.name,
                 description: marker_rel.result,
                 category: 'genetics',
                 metadata: {
                     chromosome: gm.chromosome,
                     result: marker_rel.result,
                     associated_conditions: gm.associated_conditions
                 }
             } END as genetic_test

        // Collect all events
        WITH p, [lab_event, appointment, condition, medication_start, medication_stop, procedure, genetic_test] as all_events

        UNWIND all_events as event
        WITH p, event
        WHERE event IS NOT NULL
        """

        # Add date range filters
        params = {"member_id": family_member_id}

        if start_date:
            query += " AND event.date >= date($start_date)"
            params["start_date"] = start_date

        if end_date:
            query += " AND event.date <= date($end_date)"
            params["end_date"] = end_date

        # Add event type filter
        if allowed_types:
            query += " AND event.type IN $allowed_types"
            params["allowed_types"] = allowed_types

        # Return sorted events
        query += """
        WITH p, event
        ORDER BY event.date DESC
        """

        if limit:
            query += " LIMIT $limit"
            params["limit"] = limit

        query += """
        RETURN p.name as member_name,
               p.preferred_name as preferred_name,
               collect(event) as events
        """

        results = await run_cypher(query, params)

        if not results or not results[0]:
            raise HTTPException(status_code=404, detail="Family member not found")

        result = results[0]
        events = result.get('events', [])

        # Format events
        formatted_events = []
        event_type_counts = {}

        for event in events:
            if not event:
                continue

            # Skip events with missing required fields
            if not event.get('id') or not event.get('type') or not event.get('date'):
                continue

            # Convert Neo4j date to ISO string
            event_date = event['date']
            if hasattr(event_date, 'isoformat'):
                date_str = event_date.isoformat()
            elif hasattr(event_date, 'iso_format'):
                date_str = event_date.iso_format()
            else:
                date_str = str(event_date)

            # Determine severity for visual coding
            severity = 'normal'
            if event['type'] == 'condition' and event.get('severity') in ['severe', 'critical']:
                severity = 'critical'
            elif event['type'] == 'lab_event':
                # Check if summary mentions abnormal results
                summary = (event.get('description') or '').lower()
                if any(word in summary for word in ['high', 'elevated', 'abnormal', 'critical']):
                    severity = 'warning'

            formatted_event = TimelineEvent(
                id=event['id'],
                event_type=event['type'],
                date=date_str,
                title=event['title'],
                description=event.get('description'),
                category=event.get('category'),
                severity=event.get('severity', severity),
                metadata=event.get('metadata', {})
            )

            formatted_events.append(formatted_event)

            # Count by type
            event_type_counts[event['type']] = event_type_counts.get(event['type'], 0) + 1

        # Calculate date range
        date_range = {
            'start': None,
            'end': None
        }

        if formatted_events:
            dates = [e.date for e in formatted_events]
            date_range['start'] = min(dates)
            date_range['end'] = max(dates)

        member_name = result.get('preferred_name') or result.get('member_name')

        return TimelineResponse(
            family_member_id=family_member_id,
            family_member_name=member_name,
            events=formatted_events,
            total_events=len(formatted_events),
            date_range=date_range,
            event_type_counts=event_type_counts
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get timeline", member_id=family_member_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{family_member_id}/medications")
async def get_medication_timeline(family_member_id: str):
    """
    Get detailed medication timeline showing all starts/stops.

    Returns medication periods with start and end dates for visualization.
    """
    try:
        query = """
        MATCH (p:Person {id: $member_id})-[rel:TAKES_MEDICATION]->(m:Medication)
        WHERE rel.start_date IS NOT NULL

        RETURN m.id as medication_id,
               m.name as medication_name,
               m.drug_class as drug_class,
               m.brand_names as brand_names,
               rel.start_date as start_date,
               rel.end_date as end_date,
               rel.dosage as dosage,
               rel.frequency as frequency,
               rel.prescriber as prescriber,
               CASE
                   WHEN rel.end_date IS NULL THEN true
                   ELSE false
               END as is_current
        ORDER BY rel.start_date DESC
        """

        results = await run_cypher(query, {"member_id": family_member_id})

        medications = []
        for record in results or []:
            med = {
                "medication_id": record['medication_id'],
                "medication_name": record['medication_name'],
                "drug_class": record['drug_class'],
                "brand_names": record.get('brand_names', []),
                "start_date": record['start_date'].isoformat() if hasattr(record['start_date'], 'isoformat') else str(record['start_date']),
                "end_date": record['end_date'].isoformat() if record['end_date'] and hasattr(record['end_date'], 'isoformat') else None,
                "dosage": record.get('dosage'),
                "frequency": record.get('frequency'),
                "prescriber": record.get('prescriber'),
                "is_current": record['is_current'],
            }

            # Calculate duration if ended
            if med['end_date']:
                start = datetime.fromisoformat(med['start_date'])
                end = datetime.fromisoformat(med['end_date'])
                duration_days = (end - start).days
                med['duration_days'] = duration_days

            medications.append(med)

        return {
            "family_member_id": family_member_id,
            "medications": medications,
            "total": len(medications),
            "current_count": sum(1 for m in medications if m['is_current'])
        }

    except Exception as e:
        logger.error("Failed to get medication timeline", member_id=family_member_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{family_member_id}/stats")
async def get_timeline_stats(family_member_id: str):
    """Get statistics about the timeline (event counts, trends, etc.)."""
    try:
        query = """
        MATCH (p:Person {id: $member_id})

        OPTIONAL MATCH (p)-[:HAD_LAB_EVENT]->(le:LabEvent)
        OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(appt:Appointment)
        OPTIONAL MATCH (p)-[cond_rel:HAS_CONDITION]->(c:Condition)
        WHERE cond_rel.diagnosed_date IS NOT NULL
        OPTIONAL MATCH (p)-[med_rel:TAKES_MEDICATION]->(m:Medication)
        WHERE med_rel.start_date IS NOT NULL
        OPTIONAL MATCH (p)-[proc_rel:HAD_PROCEDURE]->(proc:Procedure)
        WHERE proc_rel.date IS NOT NULL

        WITH p,
             count(DISTINCT le) as lab_count,
             count(DISTINCT appt) as appointment_count,
             count(DISTINCT c) as condition_count,
             count(DISTINCT m) as medication_count,
             count(DISTINCT proc) as procedure_count,
             [le in collect(DISTINCT le) WHERE le.date IS NOT NULL | le.date] as lab_dates,
             [appt in collect(DISTINCT appt) WHERE appt.date IS NOT NULL | appt.date] as appt_dates,
             [cond_rel in collect(DISTINCT cond_rel) WHERE cond_rel.diagnosed_date IS NOT NULL | cond_rel.diagnosed_date] as cond_dates

        // Get date range
        WITH p, lab_count, appointment_count, condition_count, medication_count, procedure_count,
             lab_dates + appt_dates + cond_dates as all_dates

        RETURN lab_count, appointment_count, condition_count, medication_count, procedure_count,
               CASE WHEN size(all_dates) > 0 THEN reduce(min_date = all_dates[0], d IN all_dates | CASE WHEN d < min_date THEN d ELSE min_date END) ELSE null END as earliest_date,
               CASE WHEN size(all_dates) > 0 THEN reduce(max_date = all_dates[0], d IN all_dates | CASE WHEN d > max_date THEN d ELSE max_date END) ELSE null END as latest_date
        """

        results = await run_cypher(query, {"member_id": family_member_id})

        if not results:
            return {
                "total_events": 0,
                "event_counts": {},
                "date_range": {}
            }

        result = results[0]

        return {
            "family_member_id": family_member_id,
            "total_events": (
                result['lab_count'] +
                result['appointment_count'] +
                result['condition_count'] +
                result['medication_count'] +
                result['procedure_count']
            ),
            "event_counts": {
                "lab_events": result['lab_count'],
                "appointments": result['appointment_count'],
                "conditions": result['condition_count'],
                "medications": result['medication_count'],
                "procedures": result['procedure_count']
            },
            "date_range": {
                "earliest": result['earliest_date'].isoformat() if result['earliest_date'] else None,
                "latest": result['latest_date'].isoformat() if result['latest_date'] else None
            }
        }

    except Exception as e:
        logger.error("Failed to get timeline stats", member_id=family_member_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{family_member_id}/export/csv")
async def export_timeline_csv(
    family_member_id: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types")
):
    """
    Export timeline to CSV format.

    Returns a CSV file with all timeline events.
    """
    try:
        # Get timeline data using the existing endpoint logic
        params = {"member_id": family_member_id}
        query = """
        MATCH (p:Person {id: $member_id})

        OPTIONAL MATCH (p)-[:HAD_LAB_EVENT]->(le:LabEvent)
        OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(appt:Appointment)
        OPTIONAL MATCH (p)-[cond_rel:HAS_CONDITION]->(c:Condition)
        OPTIONAL MATCH (p)-[med_rel:TAKES_MEDICATION]->(m:Medication)
        OPTIONAL MATCH (p)-[proc_rel:HAD_PROCEDURE]->(proc:Procedure)

        WITH p,
             CASE WHEN le IS NOT NULL THEN {
                 id: le.id,
                 type: 'lab_event',
                 date: le.date,
                 title: COALESCE(le.document_type, 'Lab Result'),
                 description: le.summary,
                 category: le.document_type
             } END as lab_event,
             CASE WHEN appt IS NOT NULL THEN {
                 id: appt.id,
                 type: 'appointment',
                 date: appt.date,
                 title: appt.appointment_type,
                 description: COALESCE(appt.facility, '') + COALESCE(' - ' + appt.clinic, ''),
                 category: 'appointment'
             } END as appointment,
             CASE WHEN c IS NOT NULL AND cond_rel.diagnosed_date IS NOT NULL THEN {
                 id: c.id,
                 type: 'condition',
                 date: cond_rel.diagnosed_date,
                 title: 'Diagnosed: ' + c.name,
                 description: cond_rel.notes,
                 category: c.category
             } END as condition,
             CASE WHEN m IS NOT NULL AND med_rel.start_date IS NOT NULL THEN {
                 id: m.id + '_start',
                 type: 'medication_start',
                 date: med_rel.start_date,
                 title: 'Started: ' + m.name,
                 description: COALESCE(med_rel.dosage, '') + COALESCE(' ' + med_rel.frequency, ''),
                 category: m.drug_class
             } END as medication_start,
             CASE WHEN m IS NOT NULL AND med_rel.end_date IS NOT NULL THEN {
                 id: m.id + '_stop',
                 type: 'medication_stop',
                 date: med_rel.end_date,
                 title: 'Stopped: ' + m.name,
                 description: 'Discontinued medication',
                 category: m.drug_class
             } END as medication_stop,
             CASE WHEN proc IS NOT NULL AND proc_rel.date IS NOT NULL THEN {
                 id: proc.id,
                 type: 'procedure',
                 date: proc_rel.date,
                 title: proc.name,
                 description: proc_rel.notes,
                 category: proc.procedure_type
             } END as procedure

        WITH p, [lab_event, appointment, condition, medication_start, medication_stop, procedure] as all_events

        UNWIND all_events as event
        WITH p, event
        WHERE event IS NOT NULL
        """

        if start_date:
            query += " AND event.date >= date($start_date)"
            params["start_date"] = start_date

        if end_date:
            query += " AND event.date <= date($end_date)"
            params["end_date"] = end_date

        if event_types:
            allowed_types = [t.strip() for t in event_types.split(',')]
            query += " AND event.type IN $allowed_types"
            params["allowed_types"] = allowed_types

        query += """
        WITH p, event
        ORDER BY event.date DESC
        RETURN p.name as member_name,
               p.preferred_name as preferred_name,
               collect(event) as events
        """

        results = await run_cypher(query, params)

        if not results or not results[0]:
            raise HTTPException(status_code=404, detail="Family member not found")

        result = results[0]
        events = result.get('events', [])
        member_name = result.get('preferred_name') or result.get('member_name')

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Date', 'Event Type', 'Title', 'Description', 'Category'])

        # Write events
        for event in events:
            if not event:
                continue

            event_date = event['date']
            if hasattr(event_date, 'isoformat'):
                date_str = event_date.isoformat()
            elif hasattr(event_date, 'iso_format'):
                date_str = event_date.iso_format()
            else:
                date_str = str(event_date)

            writer.writerow([
                date_str,
                event['type'].replace('_', ' ').title(),
                event['title'],
                event.get('description', ''),
                event.get('category', '')
            ])

        # Prepare response
        output.seek(0)
        filename = f"health_timeline_{member_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to export timeline CSV", member_id=family_member_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
