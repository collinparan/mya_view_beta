"""
Family router - REST endpoints for family member management.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.database import get_db, run_cypher

router = APIRouter()


class FamilyMemberCreate(BaseModel):
    """Family member creation model."""
    name: str
    role: str  # 'parent', 'child', 'grandparent', etc.
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    blood_type: Optional[str] = None


class FamilyMember(FamilyMemberCreate):
    """Family member response model."""
    id: str
    adapter_name: Optional[str] = None
    created_at: str


class FamilyRelationship(BaseModel):
    """Family relationship model."""
    from_member_id: str
    to_member_id: str
    relationship_type: str  # 'PARENT_OF', 'SIBLING_OF', 'SPOUSE_OF'


class HereditaryRisk(BaseModel):
    """Hereditary risk assessment."""
    condition_name: str
    parent_name: str
    inheritance_pattern: str
    risk_percentage: float
    notes: Optional[str] = None


@router.post("/members", response_model=FamilyMember)
async def create_family_member(
    member: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new family member."""
    member_id = str(uuid.uuid4())

    # TODO: Create in PostgreSQL
    # TODO: Create node in Neo4j

    # Create Neo4j node
    try:
        await run_cypher(
            """
            CREATE (p:Person {
                id: $id,
                name: $name,
                role: $role,
                date_of_birth: $dob,
                gender: $gender,
                blood_type: $blood_type
            })
            RETURN p
            """,
            {
                "id": member_id,
                "name": member.name,
                "role": member.role,
                "dob": member.date_of_birth,
                "gender": member.gender,
                "blood_type": member.blood_type,
            }
        )
    except Exception as e:
        # Log but don't fail - Neo4j is optional for basic functionality
        pass

    return FamilyMember(
        id=member_id,
        name=member.name,
        role=member.role,
        date_of_birth=member.date_of_birth,
        gender=member.gender,
        blood_type=member.blood_type,
        adapter_name=None,
        created_at="2024-01-01T00:00:00Z",  # TODO: Use actual timestamp
    )


@router.get("/members", response_model=List[FamilyMember])
async def list_family_members(
    db: AsyncSession = Depends(get_db),
):
    """List all family members from Neo4j."""
    members = []

    # Always include Demo User first
    members.append(FamilyMember(
        id="demo",
        name="Demo User",
        role="demo",
        date_of_birth=None,
        gender=None,
        blood_type=None,
        adapter_name=None,
        created_at="2024-01-01T00:00:00Z",
    ))

    try:
        results = await run_cypher(
            """
            MATCH (p:Person)
            RETURN p.id as id, p.name as name, p.preferred_name as preferred_name,
                   p.role as role, p.date_of_birth as date_of_birth,
                   p.gender as gender, p.blood_type as blood_type
            ORDER BY p.preferred_name, p.name
            """,
            {}
        )
        for r in results:
            # Convert Neo4j date objects to strings
            dob = r.get("date_of_birth")
            if dob is not None:
                dob = str(dob)

            # Use preferred name if available, otherwise full name
            display_name = r.get("preferred_name") or r["name"]

            members.append(FamilyMember(
                id=r["id"],
                name=display_name,
                role=r["role"] or "member",
                date_of_birth=dob,
                gender=r.get("gender"),
                blood_type=r.get("blood_type"),
                adapter_name=None,
                created_at="2024-01-01T00:00:00Z",
            ))
    except Exception as e:
        # Log but continue - Demo User is still available
        import logging
        logging.error(f"Failed to list family members from Neo4j: {e}")

    return members


@router.get("/members/{member_id}", response_model=FamilyMember)
async def get_family_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific family member."""
    # TODO: Implement retrieval
    raise HTTPException(status_code=404, detail="Family member not found")


@router.post("/relationships")
async def create_relationship(
    relationship: FamilyRelationship,
):
    """Create a family relationship in the graph."""
    try:
        await run_cypher(
            f"""
            MATCH (a:Person {{id: $from_id}})
            MATCH (b:Person {{id: $to_id}})
            CREATE (a)-[:{relationship.relationship_type}]->(b)
            RETURN a, b
            """,
            {
                "from_id": relationship.from_member_id,
                "to_id": relationship.to_member_id,
            }
        )
        return {"status": "created", "relationship": relationship}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/members/{member_id}/hereditary-risks", response_model=List[HereditaryRisk])
async def get_hereditary_risks(
    member_id: str,
):
    """
    Get hereditary risks for a family member based on parent conditions.

    This queries the Neo4j graph to find conditions that parents have
    and calculates inheritance risk.
    """
    try:
        results = await run_cypher(
            """
            MATCH (parent:Person)-[:PARENT_OF]->(child:Person {id: $child_id})
            MATCH (parent)-[:HAS_CONDITION]->(cond:Condition)
            WHERE cond.hereditary = true
            RETURN
                parent.name as parent_name,
                cond.name as condition_name,
                cond.inheritance_pattern as inheritance_pattern,
                cond.heritability_percentage as risk_percentage
            """,
            {"child_id": member_id}
        )

        return [
            HereditaryRisk(
                condition_name=r["condition_name"],
                parent_name=r["parent_name"],
                inheritance_pattern=r["inheritance_pattern"] or "unknown",
                risk_percentage=r["risk_percentage"] or 0,
            )
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/members/{member_id}/timeline")
async def get_health_timeline(
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get chronological health timeline for a family member."""
    # TODO: Implement timeline aggregation from documents and chat history
    return {"timeline": [], "member_id": member_id}
