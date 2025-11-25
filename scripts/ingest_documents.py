#!/usr/bin/env python3
"""
Document Ingestion Script
Load medical documents into Mya View databases.

Usage:
    python scripts/ingest_documents.py <file_or_directory> --member-id <id> [options]

Options:
    --full-name        Full legal name for alias generation
    --preferred-name   Preferred name (e.g., middle name they go by)
    --dob              Date of birth (YYYY-MM-DD)
    --birth-city       City of birth (for regional health considerations)
    --birth-country    Country of birth
    --birth-country-code  ISO country code (e.g., PH, US)
    --alias            Additional nickname/alias (can use multiple times)
    --dry-run          Parse only, don't load to database
    --date             Document date (YYYY-MM-DD)

Example:
    python scripts/ingest_documents.py data/uploads/collin/ --member-id collin-paran-001 \\
        --full-name "Philip Collin Richard Navarro Paran" --preferred-name "Collin" \\
        --dob 1985-09-02 --birth-city "Manila" --birth-country "Philippines" --birth-country-code PH \\
        --alias "Cole" --alias "Cole Paran"
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.ingestion import MedicalDocumentParser, generate_neo4j_queries, MedicalDocument, BirthInfo
from neo4j import AsyncGraphDatabase

# PDF support
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: pypdf not installed. PDF support disabled.")


def extract_text_from_pdf(filepath: Path) -> str:
    """Extract text content from a PDF file."""
    if not PDF_SUPPORT:
        raise Exception("PDF support not available. Install pypdf: pip install pypdf")

    reader = PdfReader(filepath)
    text_parts = []

    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text()
        if page_text:
            text_parts.append(f"--- Page {page_num} ---\n{page_text}")

    return "\n\n".join(text_parts)


async def get_neo4j_driver():
    """Get Neo4j driver with environment-aware connection (local or docker)."""
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


async def ingest_file(filepath: Path, member_id: str, parser: MedicalDocumentParser) -> MedicalDocument:
    """Ingest a single medical document file."""
    print(f"\n{'='*60}")
    print(f"Processing: {filepath.name}")
    print(f"{'='*60}")

    # Read file content based on file type
    suffix = filepath.suffix.lower()
    if suffix == '.pdf':
        print("  Extracting text from PDF...")
        content = extract_text_from_pdf(filepath)
        print(f"  Extracted {len(content)} characters from {len(PdfReader(filepath).pages)} pages")
    else:
        content = filepath.read_text(encoding='utf-8')

    # Parse the document
    doc = parser.parse_markdown(content, filepath.name)

    # Display extracted information
    print(f"\nDocument Type: {doc.document_type}")
    print(f"Patient: {doc.patient_name or 'Not found'}")

    if doc.provider:
        print(f"Provider: {doc.provider.name} ({doc.provider.facility or 'Unknown facility'})")

    print(f"\nLab Results: {len(doc.lab_results)}")
    for result in doc.lab_results[:5]:  # Show first 5
        flag_icon = "✅" if result.flag.value == "normal" else "⚠️"
        print(f"  {flag_icon} {result.test_name}: {result.value} {result.unit or ''} ({result.reference_range or 'N/A'})")
    if len(doc.lab_results) > 5:
        print(f"  ... and {len(doc.lab_results) - 5} more")

    print(f"\nConditions Identified: {len(doc.conditions)}")
    for condition in doc.conditions:
        print(f"  - {condition.name} ({condition.status}, {condition.severity})")
        if condition.icd10_code:
            print(f"    ICD-10: {condition.icd10_code}")

    print(f"\nFollow-up Items: {len(doc.followup_items)}")
    for item in doc.followup_items[:3]:
        print(f"  - {item[:80]}{'...' if len(item) > 80 else ''}")

    if doc.summary:
        print(f"\nSummary: {doc.summary[:200]}...")

    return doc


async def load_to_neo4j(
    doc: MedicalDocument,
    member_id: str,
    full_legal_name: str = None,
    preferred_name: str = None,
    birth_info: BirthInfo = None,
    additional_aliases: list = None,
):
    """Load parsed document into Neo4j."""
    queries = generate_neo4j_queries(doc, member_id, full_legal_name, preferred_name, birth_info, additional_aliases)

    print(f"\nLoading into Neo4j ({len(queries)} operations)...")

    try:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            for i, query_data in enumerate(queries):
                try:
                    await session.run(query_data["query"], query_data["params"])
                    print(f"  [{i+1}/{len(queries)}] ✓")
                except Exception as e:
                    print(f"  [{i+1}/{len(queries)}] ✗ Error: {e}")

        print("Neo4j load complete!")
        return True

    except Exception as e:
        print(f"Failed to connect to Neo4j: {e}")
        print("Make sure Neo4j is running: docker-compose up -d neo4j")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Ingest medical documents into Assist Health")
    parser.add_argument("path", type=str, help="File or directory path to ingest")
    parser.add_argument("--member-id", type=str, required=True, help="Family member ID")
    parser.add_argument("--full-name", type=str, help="Full legal name (for alias generation)")
    parser.add_argument("--preferred-name", type=str, help="Preferred name (e.g., middle name they go by)")
    parser.add_argument("--dob", type=str, help="Date of birth (YYYY-MM-DD)")
    parser.add_argument("--birth-city", type=str, help="City of birth")
    parser.add_argument("--birth-country", type=str, help="Country of birth")
    parser.add_argument("--birth-country-code", type=str, help="ISO country code (e.g., PH, US)")
    parser.add_argument("--alias", type=str, action="append", help="Additional name alias (can be used multiple times)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't load to database")
    parser.add_argument("--date", type=str, help="Document date (YYYY-MM-DD)")

    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: Path not found: {path}")
        sys.exit(1)

    # Get list of files to process
    if path.is_file():
        files = [path]
    else:
        files = list(path.glob("*.md")) + list(path.glob("*.txt")) + list(path.glob("*.pdf"))

    if not files:
        print(f"No markdown, text, or PDF files found in: {path}")
        sys.exit(1)

    print(f"Found {len(files)} file(s) to process")
    print(f"Family Member ID: {args.member_id}")

    # Build birth info if provided
    birth_info = None
    if args.dob or args.birth_city:
        from datetime import datetime
        birth_info = BirthInfo(
            date_of_birth=datetime.strptime(args.dob, "%Y-%m-%d").date() if args.dob else None,
            birth_city=args.birth_city,
            birth_country=args.birth_country,
            birth_country_code=args.birth_country_code,
        )
        if args.dob:
            print(f"Date of Birth: {args.dob}")
        if args.birth_city:
            print(f"Birth Location: {args.birth_city}, {args.birth_country or ''}")

    # Initialize parser
    doc_parser = MedicalDocumentParser()

    # Process each file
    documents = []
    for filepath in files:
        doc = await ingest_file(filepath, args.member_id, doc_parser)
        documents.append(doc)

        if not args.dry_run:
            await load_to_neo4j(
                doc,
                args.member_id,
                full_legal_name=args.full_name,
                preferred_name=args.preferred_name,
                birth_info=birth_info,
                additional_aliases=args.alias,
            )

    # Summary
    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {len(documents)}")
    print(f"Total lab results: {sum(len(d.lab_results) for d in documents)}")
    print(f"Total conditions: {sum(len(d.conditions) for d in documents)}")
    print(f"Total appointments: {sum(len(d.appointments) for d in documents)}")
    print(f"Total follow-up items: {sum(len(d.followup_items) for d in documents)}")

    if args.dry_run:
        print("\n[DRY RUN] No data was loaded to databases")


if __name__ == "__main__":
    asyncio.run(main())
