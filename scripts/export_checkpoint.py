#!/usr/bin/env python3
"""
Export Medical Checkpoint
Generates a human-readable markdown file from Neo4j that can be:
1. Printed and handed to a doctor
2. Used to rebuild the database after a reboot
3. Version controlled for medical history tracking

Usage:
    python scripts/export_checkpoint.py --member-id <id> --output <file.md>
    python scripts/export_checkpoint.py --all --output-dir data/checkpoints/
"""

import argparse
import asyncio
from datetime import datetime, date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from neo4j import AsyncGraphDatabase


async def get_driver():
    """Get Neo4j driver with environment-aware connection."""
    # Try docker internal first, then localhost
    for uri, auth in [
        ("bolt://localhost:7688", ("neo4j", "changeme_secure_password")),
        ("bolt://localhost:7687", ("neo4j", "changeme")),
    ]:
        try:
            driver = AsyncGraphDatabase.driver(uri, auth=auth)
            async with driver.session() as session:
                await session.run("RETURN 1")
            return driver
        except Exception:
            continue
    raise Exception("Could not connect to Neo4j")


async def export_member(driver, member_id: str) -> str:
    """Export a single family member to markdown format."""
    lines = []

    async with driver.session() as session:
        # Get person details
        result = await session.run("""
            MATCH (p:Person {id: $id})
            OPTIONAL MATCH (p)-[:BORN_IN]->(loc:Location)
            OPTIONAL MATCH (p)-[:LIVES_AT]->(addr:Address)
            RETURN p, loc, addr
        """, {"id": member_id})

        record = await result.single()
        if not record:
            raise ValueError(f"Member not found: {member_id}")

        person = dict(record["p"])
        location = dict(record["loc"]) if record["loc"] else None
        address = dict(record["addr"]) if record["addr"] else None

        # Header
        lines.append(f"# Medical Checkpoint: {person.get('preferred_name') or person.get('name')}")
        lines.append(f"")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Member ID:** `{member_id}`")
        lines.append(f"")

        # Personal Information
        lines.append(f"## Personal Information")
        lines.append(f"")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| **Full Legal Name** | {person.get('full_legal_name', person.get('name', 'Unknown'))} |")
        lines.append(f"| **Preferred Name** | {person.get('preferred_name', '-')} |")
        lines.append(f"| **Date of Birth** | {person.get('date_of_birth', '-')} |")
        lines.append(f"| **Gender** | {person.get('gender', '-')} |")
        lines.append(f"| **Blood Type** | {person.get('blood_type', '-')} |")
        lines.append(f"| **Role** | {person.get('role', 'member')} |")

        if location:
            lines.append(f"| **Birth City** | {location.get('city', '-')} |")
            lines.append(f"| **Birth Country** | {location.get('country', '-')} |")
            lines.append(f"| **Country Code** | {location.get('country_code', '-')} |")

        if address:
            addr_parts = [address.get('street', '')]
            if address.get('city') or address.get('state') or address.get('zip'):
                addr_parts.append(f"{address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}")
            lines.append(f"| **Current Address** | {', '.join(p for p in addr_parts if p)} |")

        lines.append(f"")

        # Healthcare Providers & Insurance
        result = await session.run("""
            MATCH (p:Person {id: $id})-[:HAS_INSURANCE]->(ins:Insurance)
            OPTIONAL MATCH (ins)-[:PROVIDED_BY]->(fac:Facility)
            RETURN ins.name as insurance_name, ins.type as insurance_type,
                   ins.member_id as member_id, ins.group_number as group_number,
                   fac.name as facility_name, fac.address as facility_address,
                   fac.city as facility_city, fac.state as facility_state,
                   fac.zip as facility_zip, fac.phone as facility_phone
            ORDER BY ins.name
        """, {"id": member_id})

        insurance_records = [dict(r) async for r in result]
        if insurance_records:
            lines.append(f"## Healthcare Providers & Insurance")
            lines.append(f"")
            for ins in insurance_records:
                lines.append(f"### {ins.get('insurance_name', 'Unknown')}")
                lines.append(f"")
                if ins.get('insurance_type'):
                    lines.append(f"- **Type:** {ins['insurance_type']}")
                if ins.get('member_id'):
                    lines.append(f"- **Member ID:** {ins['member_id']}")
                if ins.get('group_number'):
                    lines.append(f"- **Group Number:** {ins['group_number']}")
                if ins.get('facility_name'):
                    lines.append(f"- **Primary Facility:** {ins['facility_name']}")
                    addr = f"{ins.get('facility_address', '')}"
                    if ins.get('facility_city'):
                        addr += f", {ins['facility_city']}, {ins.get('facility_state', '')} {ins.get('facility_zip', '')}"
                    if addr.strip():
                        lines.append(f"- **Facility Address:** {addr}")
                    if ins.get('facility_phone'):
                        lines.append(f"- **Phone:** {ins['facility_phone']}")
                lines.append(f"")

        # Aliases
        result = await session.run("""
            MATCH (p:Person {id: $id})-[:HAS_ALIAS]->(a:Alias)
            RETURN a.name as name, a.source as source, a.is_primary as is_primary
            ORDER BY a.is_primary DESC, a.name
        """, {"id": member_id})

        aliases = [dict(r) async for r in result]
        if aliases:
            lines.append(f"## Name Aliases")
            lines.append(f"")
            lines.append(f"These names may appear on medical records and should be linked to this person:")
            lines.append(f"")
            lines.append(f"| Alias | Source | Primary |")
            lines.append(f"|-------|--------|---------|")
            for alias in aliases:
                primary = "Yes" if alias.get("is_primary") else "-"
                lines.append(f"| {alias['name']} | {alias.get('source', '-')} | {primary} |")
            lines.append(f"")

        # Allergies
        result = await session.run("""
            MATCH (p:Person {id: $id})-[r:ALLERGIC_TO]->(a:Allergen)
            RETURN a.name as name, r.severity as severity, r.reaction as reaction
            ORDER BY r.severity DESC, a.name
        """, {"id": member_id})

        allergies = [dict(r) async for r in result]
        if allergies:
            lines.append(f"## Allergies")
            lines.append(f"")
            lines.append(f"| Allergen | Severity | Reaction |")
            lines.append(f"|----------|----------|----------|")
            for allergy in allergies:
                lines.append(f"| {allergy['name']} | {allergy.get('severity', '-')} | {allergy.get('reaction', '-')} |")
            lines.append(f"")

        # Current Conditions
        result = await session.run("""
            MATCH (p:Person {id: $id})-[r:HAS_CONDITION]->(c:Condition)
            RETURN c.name as name, c.icd10_code as icd10,
                   r.status as status, r.severity as severity,
                   r.diagnosed_date as diagnosed_date, r.notes as notes
            ORDER BY r.status, c.name
        """, {"id": member_id})

        conditions = [dict(r) async for r in result]
        if conditions:
            lines.append(f"## Current Conditions")
            lines.append(f"")
            lines.append(f"| Condition | ICD-10 | Status | Severity | Diagnosed | Notes |")
            lines.append(f"|-----------|--------|--------|----------|-----------|-------|")
            for cond in conditions:
                lines.append(f"| {cond['name']} | {cond.get('icd10', '-')} | {cond.get('status', '-')} | {cond.get('severity', '-')} | {cond.get('diagnosed_date', '-')} | {cond.get('notes', '-')} |")
            lines.append(f"")

        # Medications (if any)
        result = await session.run("""
            MATCH (p:Person {id: $id})-[r:TAKES]->(m:Medication)
            RETURN m.name as name, m.dosage as dosage, m.frequency as frequency,
                   r.start_date as start_date, r.prescriber as prescriber
            ORDER BY m.name
        """, {"id": member_id})

        medications = [dict(r) async for r in result]
        if medications:
            lines.append(f"## Current Medications")
            lines.append(f"")
            lines.append(f"| Medication | Dosage | Frequency | Started | Prescriber |")
            lines.append(f"|------------|--------|-----------|---------|------------|")
            for med in medications:
                lines.append(f"| {med['name']} | {med.get('dosage', '-')} | {med.get('frequency', '-')} | {med.get('start_date', '-')} | {med.get('prescriber', '-')} |")
            lines.append(f"")

        # Recent Appointments (past year)
        result = await session.run("""
            MATCH (p:Person {id: $id})-[:HAS_APPOINTMENT]->(a:Appointment)
            WHERE a.date >= date() - duration('P1Y')
            RETURN a.date as date, a.time as time, a.appointment_type as type,
                   a.facility as facility, a.clinic as clinic, a.location as location
            ORDER BY a.date DESC
        """, {"id": member_id})

        appointments = [dict(r) async for r in result]
        if appointments:
            lines.append(f"## Recent Appointments (Past Year)")
            lines.append(f"")
            lines.append(f"| Date | Time | Type | Facility | Clinic | Location |")
            lines.append(f"|------|------|------|----------|--------|----------|")
            for appt in appointments:
                appt_date = appt.get('date', '-')
                # Format date as human-readable if it's a date object
                if hasattr(appt_date, 'strftime'):
                    appt_date = appt_date.strftime('%B %d, %Y')
                elif hasattr(appt_date, 'to_native'):
                    appt_date = appt_date.to_native().strftime('%B %d, %Y')
                lines.append(f"| {appt_date} | {appt.get('time', '-')} | {appt.get('type', '-')} | {appt.get('facility', '-')} | {appt.get('clinic', '-')} | {appt.get('location', '-')} |")
            lines.append(f"")

        # Lab Results History (most recent first)
        result = await session.run("""
            MATCH (p:Person {id: $id})-[:HAD_LAB_EVENT]->(le:LabEvent)
            OPTIONAL MATCH (le)-[:INCLUDES]->(lr:LabResult)
            OPTIONAL MATCH (le)-[:PERFORMED_BY]->(prov:Provider)
            RETURN le.date as date, le.document_type as type,
                   prov.name as provider, prov.facility as facility,
                   collect({
                       test: lr.test_name,
                       value: lr.value,
                       unit: lr.unit,
                       reference: lr.reference_range,
                       flag: lr.flag,
                       category: lr.category
                   }) as results
            ORDER BY le.date DESC
        """, {"id": member_id})

        lab_events = [dict(r) async for r in result]
        if lab_events:
            lines.append(f"## Lab Results History")
            lines.append(f"")
            for event in lab_events:
                event_date = event.get('date', 'Unknown date')
                provider_info = ""
                if event.get('facility'):
                    provider_info = f" - {event['facility']}"
                elif event.get('provider'):
                    provider_info = f" - {event['provider']}"

                lines.append(f"### {event_date}{provider_info}")
                lines.append(f"")

                results = [r for r in event.get('results', []) if r.get('test')]
                if results:
                    # Group by category if available
                    lines.append(f"| Test | Result | Reference Range | Status |")
                    lines.append(f"|------|--------|-----------------|--------|")
                    for r in results:
                        value_str = f"{r.get('value', '-')}"
                        if r.get('unit'):
                            value_str += f" {r['unit']}"
                        flag = r.get('flag', 'normal')
                        status = "Normal" if flag == 'normal' else flag.upper() if flag else "-"
                        lines.append(f"| {r.get('test', '-')} | {value_str} | {r.get('reference', '-')} | {status} |")
                    lines.append(f"")

        # Family Relationships
        result = await session.run("""
            MATCH (p:Person {id: $id})-[r]->(other:Person)
            WHERE type(r) IN ['PARENT_OF', 'CHILD_OF', 'SIBLING_OF', 'SPOUSE_OF']
            RETURN type(r) as relationship, other.name as name, other.id as id
            UNION
            MATCH (other:Person)-[r]->(p:Person {id: $id})
            WHERE type(r) IN ['PARENT_OF', 'CHILD_OF', 'SIBLING_OF', 'SPOUSE_OF']
            RETURN type(r) + '_REVERSE' as relationship, other.name as name, other.id as id
        """, {"id": member_id})

        relationships = [dict(r) async for r in result]
        if relationships:
            lines.append(f"## Family Relationships")
            lines.append(f"")
            lines.append(f"| Relationship | Name | Member ID |")
            lines.append(f"|--------------|------|-----------|")
            for rel in relationships:
                lines.append(f"| {rel['relationship'].replace('_', ' ').title()} | {rel['name']} | `{rel['id']}` |")
            lines.append(f"")

        # Footer
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"*Document generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        lines.append(f"")

        # Technical section for reimport
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"<!-- CHECKPOINT_DATA")
        lines.append(f"member_id: {member_id}")
        lines.append(f"export_version: 1.0")
        lines.append(f"exported_at: {datetime.now().isoformat()}")
        lines.append(f"-->")

    return "\n".join(lines)


async def export_all_members(driver, output_dir: Path):
    """Export all family members to separate files."""
    async with driver.session() as session:
        result = await session.run("MATCH (p:Person) RETURN p.id as id, p.name as name")
        members = [dict(r) async for r in result]

    output_dir.mkdir(parents=True, exist_ok=True)

    for member in members:
        content = await export_member(driver, member["id"])
        filename = f"{member['name'].lower().replace(' ', '_')}_checkpoint.md"
        filepath = output_dir / filename
        filepath.write_text(content)
        print(f"Exported: {filepath}")


async def main():
    parser = argparse.ArgumentParser(description="Export medical checkpoint to markdown")
    parser.add_argument("--member-id", type=str, help="Specific member ID to export")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--all", action="store_true", help="Export all members")
    parser.add_argument("--output-dir", type=str, default="data/checkpoints", help="Output directory for --all")

    args = parser.parse_args()

    driver = await get_driver()

    try:
        if args.all:
            await export_all_members(driver, Path(args.output_dir))
        elif args.member_id:
            content = await export_member(driver, args.member_id)
            if args.output:
                Path(args.output).write_text(content)
                print(f"Exported to: {args.output}")
            else:
                print(content)
        else:
            # Default: export first member found
            async with driver.session() as session:
                result = await session.run("MATCH (p:Person) RETURN p.id as id LIMIT 1")
                record = await result.single()
                if record:
                    content = await export_member(driver, record["id"])
                    print(content)
                else:
                    print("No members found in database")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
