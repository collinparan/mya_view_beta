#!/usr/bin/env python3
"""
Import Medical Checkpoint
Restores Neo4j database from a human-readable markdown checkpoint file.

Usage:
    python scripts/import_checkpoint.py data/checkpoints/collin_checkpoint.md
    python scripts/import_checkpoint.py --dir data/checkpoints/
"""

import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from neo4j import AsyncGraphDatabase


async def get_driver():
    """Get Neo4j driver with environment-aware connection."""
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


def parse_table(lines: list, start_idx: int) -> list:
    """Parse a markdown table starting at given index."""
    rows = []
    headers = None

    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        if "---" in line:
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if headers is None:
            headers = [h.lower().replace(" ", "_").replace("**", "") for h in cells]
        else:
            row = dict(zip(headers, cells))
            rows.append(row)

    return rows


def parse_checkpoint(content: str) -> dict:
    """Parse a checkpoint markdown file into structured data."""
    data = {
        "member_id": None,
        "personal_info": {},
        "aliases": [],
        "health_risks": [],
        "conditions": [],
        "medications": [],
        "lab_events": [],
        "relationships": [],
    }

    lines = content.split("\n")

    # Extract member ID from metadata
    match = re.search(r"member_id:\s*([a-f0-9-]+)", content)
    if match:
        data["member_id"] = match.group(1)

    # Also check the header for member ID
    match = re.search(r"\*\*Member ID:\*\*\s*`([a-f0-9-]+)`", content)
    if match:
        data["member_id"] = match.group(1)

    current_section = None

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Track sections
        if line_stripped.startswith("## "):
            current_section = line_stripped[3:].lower()
            continue

        # Parse Personal Information table
        if current_section == "personal information" and line_stripped.startswith("| **"):
            match = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|", line_stripped)
            if match:
                key = match.group(1).lower().replace(" ", "_")
                value = match.group(2).strip()
                if value and value != "-":
                    data["personal_info"][key] = value

        # Parse Aliases table
        if current_section == "name aliases" and line_stripped.startswith("|") and "---" not in line_stripped:
            if "Alias" not in line_stripped and "alias" not in line_stripped.lower():
                cells = [c.strip() for c in line_stripped.split("|")[1:-1]]
                if len(cells) >= 2:
                    data["aliases"].append({
                        "name": cells[0],
                        "source": cells[1] if len(cells) > 1 and cells[1] != "-" else "unknown",
                        "is_primary": len(cells) > 2 and cells[2].lower() == "yes"
                    })

        # Parse Health Risks
        if current_section and "health risks" in current_section:
            if line_stripped.startswith("### "):
                risk_name = line_stripped[4:]
                data["health_risks"].append({"name": risk_name, "reason": None, "screening": None})
            elif line_stripped.startswith("- **Reason:**"):
                if data["health_risks"]:
                    data["health_risks"][-1]["reason"] = line_stripped.split(":**")[1].strip()
            elif line_stripped.startswith("- **Screening:**"):
                if data["health_risks"]:
                    data["health_risks"][-1]["screening"] = line_stripped.split(":**")[1].strip()

        # Parse Conditions table
        if current_section == "current conditions" and line_stripped.startswith("|") and "---" not in line_stripped:
            if "Condition" not in line_stripped:
                cells = [c.strip() for c in line_stripped.split("|")[1:-1]]
                if len(cells) >= 4:
                    data["conditions"].append({
                        "name": cells[0],
                        "icd10": cells[1] if cells[1] != "-" else None,
                        "status": cells[2] if cells[2] != "-" else "active",
                        "severity": cells[3] if len(cells) > 3 and cells[3] != "-" else "mild",
                        "diagnosed_date": cells[4] if len(cells) > 4 and cells[4] != "-" else None,
                        "notes": cells[5] if len(cells) > 5 and cells[5] != "-" else None,
                    })

        # Parse Medications table
        if current_section == "current medications" and line_stripped.startswith("|") and "---" not in line_stripped:
            if "Medication" not in line_stripped:
                cells = [c.strip() for c in line_stripped.split("|")[1:-1]]
                if len(cells) >= 3:
                    data["medications"].append({
                        "name": cells[0],
                        "dosage": cells[1] if cells[1] != "-" else None,
                        "frequency": cells[2] if cells[2] != "-" else None,
                        "start_date": cells[3] if len(cells) > 3 and cells[3] != "-" else None,
                        "prescriber": cells[4] if len(cells) > 4 and cells[4] != "-" else None,
                    })

        # Parse Relationships table
        if current_section == "family relationships" and line_stripped.startswith("|") and "---" not in line_stripped:
            if "Relationship" not in line_stripped:
                cells = [c.strip() for c in line_stripped.split("|")[1:-1]]
                if len(cells) >= 3:
                    # Extract member ID from backticks
                    member_id_match = re.search(r"`([a-f0-9-]+)`", cells[2])
                    data["relationships"].append({
                        "type": cells[0].upper().replace(" ", "_"),
                        "name": cells[1],
                        "member_id": member_id_match.group(1) if member_id_match else cells[2],
                    })

    return data


async def import_checkpoint(driver, data: dict):
    """Import parsed checkpoint data into Neo4j."""
    if not data["member_id"]:
        raise ValueError("No member_id found in checkpoint")

    member_id = data["member_id"]
    info = data["personal_info"]

    queries_executed = 0

    async with driver.session() as session:
        # Create/update Person node
        await session.run("""
            MERGE (p:Person {id: $id})
            SET p.name = $name,
                p.full_legal_name = $full_name,
                p.preferred_name = $preferred,
                p.gender = $gender,
                p.blood_type = $blood_type,
                p.role = $role
            WITH p
            WHERE $dob IS NOT NULL
            SET p.date_of_birth = date($dob)
            RETURN p
        """, {
            "id": member_id,
            "name": info.get("preferred_name") or info.get("full_legal_name", "Unknown").split()[0],
            "full_name": info.get("full_legal_name"),
            "preferred": info.get("preferred_name"),
            "dob": info.get("date_of_birth"),
            "gender": info.get("gender"),
            "blood_type": info.get("blood_type"),
            "role": info.get("role", "member"),
        })
        queries_executed += 1
        print(f"[{queries_executed}] Created/updated Person node")

        # Create birth location if provided
        if info.get("birth_city") and info.get("birth_country"):
            loc_id = f"{info['birth_city'].lower().replace(' ', '-')}-{info.get('country_code', info['birth_country'][:2]).lower()}"
            await session.run("""
                MATCH (p:Person {id: $person_id})
                MERGE (loc:Location {id: $loc_id})
                SET loc.city = $city,
                    loc.country = $country,
                    loc.country_code = $code
                MERGE (p)-[:BORN_IN]->(loc)
            """, {
                "person_id": member_id,
                "loc_id": loc_id,
                "city": info["birth_city"],
                "country": info["birth_country"],
                "code": info.get("country_code"),
            })
            queries_executed += 1
            print(f"[{queries_executed}] Created birth location: {info['birth_city']}")

        # Create aliases
        for alias in data["aliases"]:
            await session.run("""
                MATCH (p:Person {id: $person_id})
                MERGE (a:Alias {name: $name})
                SET a.source = $source, a.is_primary = $is_primary
                MERGE (p)-[:HAS_ALIAS]->(a)
            """, {
                "person_id": member_id,
                "name": alias["name"],
                "source": alias.get("source", "unknown"),
                "is_primary": alias.get("is_primary", False),
            })
            queries_executed += 1
        if data["aliases"]:
            print(f"[{queries_executed}] Created {len(data['aliases'])} aliases")

        # Create health risks
        for risk in data["health_risks"]:
            await session.run("""
                MATCH (p:Person {id: $person_id})
                MERGE (hr:HealthRisk {name: $name})
                SET hr.screening = $screening
                MERGE (p)-[:AT_RISK_FOR {reason: $reason}]->(hr)
            """, {
                "person_id": member_id,
                "name": risk["name"],
                "screening": risk.get("screening"),
                "reason": risk.get("reason"),
            })
            queries_executed += 1
        if data["health_risks"]:
            print(f"[{queries_executed}] Created {len(data['health_risks'])} health risks")

        # Create conditions
        for cond in data["conditions"]:
            await session.run("""
                MATCH (p:Person {id: $person_id})
                MERGE (c:Condition {name: $name})
                SET c.icd10_code = $icd10
                MERGE (p)-[r:HAS_CONDITION]->(c)
                SET r.status = $status,
                    r.severity = $severity,
                    r.notes = $notes
            """, {
                "person_id": member_id,
                "name": cond["name"],
                "icd10": cond.get("icd10"),
                "status": cond.get("status", "active"),
                "severity": cond.get("severity", "mild"),
                "notes": cond.get("notes"),
            })
            queries_executed += 1
        if data["conditions"]:
            print(f"[{queries_executed}] Created {len(data['conditions'])} conditions")

        # Create medications
        for med in data["medications"]:
            await session.run("""
                MATCH (p:Person {id: $person_id})
                MERGE (m:Medication {name: $name})
                SET m.dosage = $dosage, m.frequency = $frequency
                MERGE (p)-[r:TAKES]->(m)
                SET r.prescriber = $prescriber
            """, {
                "person_id": member_id,
                "name": med["name"],
                "dosage": med.get("dosage"),
                "frequency": med.get("frequency"),
                "prescriber": med.get("prescriber"),
            })
            queries_executed += 1
        if data["medications"]:
            print(f"[{queries_executed}] Created {len(data['medications'])} medications")

    print(f"\nImport complete: {queries_executed} operations")
    return queries_executed


async def main():
    parser = argparse.ArgumentParser(description="Import medical checkpoint from markdown")
    parser.add_argument("file", type=str, nargs="?", help="Checkpoint markdown file to import")
    parser.add_argument("--dir", type=str, help="Import all checkpoints from directory")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't import")

    args = parser.parse_args()

    if args.dir:
        files = list(Path(args.dir).glob("*_checkpoint.md"))
    elif args.file:
        files = [Path(args.file)]
    else:
        parser.print_help()
        return

    driver = await get_driver() if not args.dry_run else None

    try:
        for filepath in files:
            print(f"\n{'='*60}")
            print(f"Processing: {filepath}")
            print(f"{'='*60}")

            content = filepath.read_text()
            data = parse_checkpoint(content)

            print(f"Member ID: {data['member_id']}")
            print(f"Personal Info: {data['personal_info'].get('full_legal_name', 'Unknown')}")
            print(f"Aliases: {len(data['aliases'])}")
            print(f"Health Risks: {len(data['health_risks'])}")
            print(f"Conditions: {len(data['conditions'])}")
            print(f"Medications: {len(data['medications'])}")

            if not args.dry_run and driver:
                await import_checkpoint(driver, data)
    finally:
        if driver:
            await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
