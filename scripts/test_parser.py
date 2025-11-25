#!/usr/bin/env python3
"""
Quick test of the document parser - standalone, no dependencies needed.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class LabFlag(Enum):
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"


@dataclass
class LabResult:
    test_name: str
    value: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: LabFlag = LabFlag.NORMAL
    category: Optional[str] = None


@dataclass
class Condition:
    name: str
    status: str = "active"
    severity: str = "mild"
    icd10_code: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Provider:
    name: str
    facility: Optional[str] = None


def parse_lab_row(line: str, category: Optional[str]) -> Optional[LabResult]:
    """Parse a single lab result row from markdown table."""
    parts = [p.strip() for p in line.split('|') if p.strip()]
    if len(parts) < 3:
        return None

    test_name = None
    value = None
    unit = None
    reference = None
    flag = LabFlag.NORMAL

    for part in parts:
        clean = re.sub(r'\*+', '', part).strip()

        # Test name
        if not test_name and re.match(r'^[A-Za-z]', clean) and not re.match(r'^[<>]?\d', clean):
            test_name = clean
            continue

        # Value with optional unit
        value_match = re.match(r'^([<>]?\d+\.?\d*)\s*([a-zA-Z/%°₂]+)?', clean)
        if value_match and not value:
            value = value_match.group(1)
            unit = value_match.group(2)
            continue

        # Reference range
        if re.search(r'\d+\s*[-–]\s*\d+|[<>]\s*\d+', clean) and not reference:
            reference = clean
            continue

        # Flags
        if '✅' in part or 'Normal' in part:
            flag = LabFlag.NORMAL
        elif '⚠️' in part or 'High' in part or 'Elevated' in part:
            flag = LabFlag.HIGH

    if test_name and value:
        return LabResult(test_name=test_name, value=value, unit=unit,
                        reference_range=reference, flag=flag, category=category)
    return None


def parse_document(content: str, filename: str):
    """Parse a medical document."""
    results = {
        "filename": filename,
        "patient_name": None,
        "provider": None,
        "lab_results": [],
        "conditions": [],
        "followups": [],
        "summary": None,
    }

    # Extract patient name
    name_match = re.search(r'#\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–—]', content)
    if name_match:
        results["patient_name"] = name_match.group(1)

    # Extract provider
    provider_match = re.search(r'(?:Physician|Doctor)[:\s]+(?:Dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)', content)
    if provider_match:
        facility_match = re.search(r'(VA\s+Hospital|VA\s+Medical)', content, re.IGNORECASE)
        results["provider"] = Provider(
            name=provider_match.group(1),
            facility=facility_match.group(1) if facility_match else None
        )

    # Extract lab results from tables
    current_category = None
    for line in content.split('\n'):
        # Category headers
        cat_match = re.search(r'\|\s*\*\*([A-Za-z\s]+)\*\*', line)
        if cat_match:
            potential_cat = cat_match.group(1).strip()
            if potential_cat.lower() not in ['test', 'result', 'reference', 'interpretation', 'category']:
                current_category = potential_cat

        # Lab rows
        if '|' in line and re.search(r'\d', line):
            result = parse_lab_row(line, current_category)
            if result:
                results["lab_results"].append(result)

    # Identify conditions
    content_lower = content.lower()
    condition_map = {
        "Prediabetes": {"keywords": ["prediabetes", "prediabetic", "a1c 5.8"], "icd10": "R73.03"},
        "Fatty Liver": {"keywords": ["fatty liver", "nafld", "liver inflammation"], "icd10": "K76.0"},
        "Elevated LDL": {"keywords": ["ldl 130", "high ldl", "elevated ldl"], "icd10": "E78.0"},
        "Elevated Liver Enzymes": {"keywords": ["elevated alt", "alt 94", "ast 52"], "icd10": "R74.01"},
    }

    for name, config in condition_map.items():
        for kw in config["keywords"]:
            if kw in content_lower:
                results["conditions"].append(Condition(
                    name=name,
                    status="suspected",
                    severity="mild",
                    icd10_code=config["icd10"]
                ))
                break

    # Extract follow-up items
    followup_match = re.search(r'Discussion Points[^\n]*\n((?:.*?\n)*?)(?=\n##|\n---|\Z)', content, re.IGNORECASE)
    if followup_match:
        items = re.findall(r'(?:^\s*[-•*]|\d+\.)\s*\*\*([^*]+)\*\*', followup_match.group(1), re.MULTILINE)
        results["followups"] = items

    # Extract summary
    summary_match = re.search(r'TL;DR\s*\n+(.+?)(?=\n##|\n---|\Z)', content, re.IGNORECASE | re.DOTALL)
    if summary_match:
        results["summary"] = re.sub(r'\*+', '', summary_match.group(1)).strip()[:300]

    return results


def main():
    docs_path = Path(__file__).parent.parent / "data" / "uploads" / "collin"

    for filepath in sorted(docs_path.glob("*.md")):
        print(f"\n{'='*70}")
        print(f"FILE: {filepath.name}")
        print(f"{'='*70}")

        content = filepath.read_text()
        doc = parse_document(content, filepath.name)

        print(f"\nPatient: {doc['patient_name'] or 'Not found'}")
        if doc['provider']:
            print(f"Provider: {doc['provider'].name} @ {doc['provider'].facility}")

        print(f"\n--- LAB RESULTS ({len(doc['lab_results'])}) ---")

        # Group by category
        categories = {}
        for r in doc['lab_results']:
            cat = r.category or "Other"
            categories.setdefault(cat, []).append(r)

        for cat, results in categories.items():
            print(f"\n  [{cat}]")
            for r in results:
                flag = "✅" if r.flag == LabFlag.NORMAL else "⚠️ "
                unit = r.unit or ""
                ref = f"(ref: {r.reference_range})" if r.reference_range else ""
                print(f"    {flag} {r.test_name}: {r.value} {unit} {ref}")

        print(f"\n--- CONDITIONS IDENTIFIED ({len(doc['conditions'])}) ---")
        for c in doc['conditions']:
            print(f"  • {c.name} [{c.icd10_code}] - {c.status}, {c.severity}")

        print(f"\n--- FOLLOW-UP ITEMS ({len(doc['followups'])}) ---")
        for i, item in enumerate(doc['followups'], 1):
            print(f"  {i}. {item}")

        if doc['summary']:
            print(f"\n--- SUMMARY ---")
            print(f"  {doc['summary']}")

        # Neo4j queries preview
        num_queries = 2 + len(doc['lab_results']) + len(doc['conditions'])
        print(f"\n--- NEO4J LOAD PREVIEW ---")
        print(f"  Would execute {num_queries} queries:")
        print(f"    - 1 Person node (merge)")
        print(f"    - 1 LabEvent node")
        print(f"    - {len(doc['lab_results'])} LabResult nodes")
        print(f"    - {len(doc['conditions'])} Condition nodes with HAS_CONDITION relationships")


if __name__ == "__main__":
    main()
