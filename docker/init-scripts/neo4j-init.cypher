// Medical LLM - Neo4j Graph Schema
// Run after Neo4j starts: CALL apoc.cypher.runFile('/var/lib/neo4j/import/init.cypher')

// =============================================================================
// CONSTRAINTS & INDEXES
// =============================================================================

// Unique constraints
CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (c:Condition) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT medication_id IF NOT EXISTS FOR (m:Medication) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (s:Symptom) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT allergy_id IF NOT EXISTS FOR (a:Allergy) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT procedure_id IF NOT EXISTS FOR (p:Procedure) REQUIRE p.id IS UNIQUE;

// Indexes for common lookups
CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name);
CREATE INDEX person_preferred_name IF NOT EXISTS FOR (p:Person) ON (p.preferred_name);
CREATE INDEX alias_name IF NOT EXISTS FOR (a:Alias) ON (a.name);
CREATE INDEX condition_name IF NOT EXISTS FOR (c:Condition) ON (c.name);
CREATE INDEX condition_icd10 IF NOT EXISTS FOR (c:Condition) ON (c.icd10_code);
CREATE INDEX medication_name IF NOT EXISTS FOR (m:Medication) ON (m.name);
CREATE INDEX location_city IF NOT EXISTS FOR (l:Location) ON (l.city);
CREATE INDEX location_country IF NOT EXISTS FOR (l:Location) ON (l.country_code);
CREATE INDEX health_risk_name IF NOT EXISTS FOR (h:HealthRisk) ON (h.name);

// =============================================================================
// NODE LABELS & PROPERTIES DOCUMENTATION
// =============================================================================

// :Person
// - id: UUID (matches PostgreSQL family_members.id)
// - name: String (full legal name)
// - preferred_name: String (name they go by, e.g., middle name)
// - role: String ('parent', 'child', 'grandparent')
// - date_of_birth: Date
// - gender: String
// - blood_type: String

// :Alias (for matching records across systems with name variations)
// - name: String (the alias/variant name)
// - source: String ('va', 'insurance', 'pharmacy', 'form_truncation')
// - is_primary: Boolean (is this their preferred name?)
// Example: "Philip Paran", "Collin Paran", "P. Collin Paran", "Philip C. Paran"

// :Condition
// - id: UUID
// - name: String (e.g., "Type 2 Diabetes")
// - icd10_code: String (e.g., "E11")
// - category: String ('cardiac', 'respiratory', 'endocrine', etc.)
// - description: String
// - onset_age_typical: Integer
// - hereditary: Boolean
// - inheritance_pattern: String ('autosomal_dominant', 'autosomal_recessive', 'x_linked', 'multifactorial', 'none')
// - heritability_percentage: Float (0-100)

// :Medication
// - id: UUID
// - name: String (generic name)
// - brand_names: [String]
// - drug_class: String
// - typical_dosage: String
// - frequency: String

// :Symptom
// - id: UUID
// - name: String
// - body_system: String
// - severity_scale: String ('mild', 'moderate', 'severe')

// :Allergy
// - id: UUID
// - name: String
// - allergen_type: String ('drug', 'food', 'environmental')
// - reaction_type: String ('anaphylaxis', 'rash', 'respiratory', etc.)
// - severity: String

// :Procedure
// - id: UUID
// - name: String
// - cpt_code: String
// - procedure_type: String ('surgery', 'diagnostic', 'therapeutic')

// :GeneticMarker
// - id: UUID
// - name: String (e.g., "BRCA1")
// - chromosome: String
// - associated_conditions: [String]
// - test_available: Boolean

// :Location (for tracking residence history - health relevant)
// - id: UUID or "city-country" key
// - city: String
// - state_province: String (optional)
// - country: String
// - country_code: String (ISO 3166-1 alpha-2)
// - latitude: Float (optional, for mapping)
// - longitude: Float (optional)
// Health relevance: environmental exposures, endemic diseases, air/water quality,
// regional health screening recommendations

// :HealthRisk (regional/environmental health considerations)
// - id: UUID
// - name: String (e.g., "Tuberculosis Exposure", "Air Pollution")
// - category: String ('endemic_disease', 'environmental', 'occupational')
// - description: String
// - screening_recommended: Boolean
// - screening_tests: [String]

// =============================================================================
// RELATIONSHIP TYPES
// =============================================================================

// Family relationships
// (Person)-[:PARENT_OF]->(Person)
// (Person)-[:SIBLING_OF]->(Person)
// (Person)-[:SPOUSE_OF]->(Person)

// Name/Identity relationships
// (Person)-[:HAS_ALIAS]->(Alias)  -- For matching records across systems

// Location/Residence relationships
// (Person)-[:BORN_IN]->(Location)
// (Person)-[:LIVED_IN {start_date, end_date, is_current}]->(Location)
// (Person)-[:CURRENTLY_RESIDES]->(Location)
// (Location)-[:HAS_HEALTH_RISK {prevalence, notes}]->(HealthRisk)

// Medical relationships
// (Person)-[:HAS_CONDITION {diagnosed_date, status: 'active'|'resolved'|'managed', notes}]->(Condition)
// (Person)-[:TAKES_MEDICATION {start_date, end_date, dosage, frequency, prescriber}]->(Medication)
// (Person)-[:HAS_ALLERGY {discovered_date, reaction_history}]->(Allergy)
// (Person)-[:HAD_PROCEDURE {date, provider, outcome, notes}]->(Procedure)
// (Person)-[:REPORTS_SYMPTOM {first_reported, frequency, triggers}]->(Symptom)
// (Person)-[:HAS_MARKER {test_date, result}]->(GeneticMarker)

// Condition relationships
// (Condition)-[:TREATED_BY]->(Medication)
// (Condition)-[:CAUSES_SYMPTOM]->(Symptom)
// (Condition)-[:CONTRAINDICATES]->(Medication)
// (Condition)-[:ASSOCIATED_WITH {risk_multiplier}]->(Condition)

// Medication interactions
// (Medication)-[:INTERACTS_WITH {severity, description}]->(Medication)
// (Medication)-[:MAY_CAUSE]->(Symptom)

// Privacy-sensitive relationships
// (Person)-[:HAS_SENSITIVE_CONDITION {privacy_level: 'consent_required'}]->(Condition)

// =============================================================================
// SAMPLE HEREDITARY CONDITIONS (Reference Data)
// =============================================================================

// Common hereditary conditions with inheritance patterns
MERGE (c1:Condition {id: 'ref-hypertension', name: 'Essential Hypertension', icd10_code: 'I10', hereditary: true, inheritance_pattern: 'multifactorial', heritability_percentage: 30, category: 'cardiac'})
MERGE (c2:Condition {id: 'ref-t2diabetes', name: 'Type 2 Diabetes', icd10_code: 'E11', hereditary: true, inheritance_pattern: 'multifactorial', heritability_percentage: 40, category: 'endocrine'})
MERGE (c3:Condition {id: 'ref-afib', name: 'Atrial Fibrillation', icd10_code: 'I48', hereditary: true, inheritance_pattern: 'multifactorial', heritability_percentage: 25, category: 'cardiac'})
MERGE (c4:Condition {id: 'ref-asthma', name: 'Asthma', icd10_code: 'J45', hereditary: true, inheritance_pattern: 'multifactorial', heritability_percentage: 60, category: 'respiratory'})
MERGE (c5:Condition {id: 'ref-migraine', name: 'Migraine', icd10_code: 'G43', hereditary: true, inheritance_pattern: 'multifactorial', heritability_percentage: 50, category: 'neurological'})

// Autosomal dominant conditions (50% inheritance risk)
MERGE (c6:Condition {id: 'ref-huntingtons', name: 'Huntington Disease', icd10_code: 'G10', hereditary: true, inheritance_pattern: 'autosomal_dominant', heritability_percentage: 50, category: 'neurological'})
MERGE (c7:Condition {id: 'ref-marfan', name: 'Marfan Syndrome', icd10_code: 'Q87.4', hereditary: true, inheritance_pattern: 'autosomal_dominant', heritability_percentage: 50, category: 'connective_tissue'})

// Autosomal recessive (25% if both parents carriers)
MERGE (c8:Condition {id: 'ref-cf', name: 'Cystic Fibrosis', icd10_code: 'E84', hereditary: true, inheritance_pattern: 'autosomal_recessive', heritability_percentage: 25, category: 'respiratory'})
MERGE (c9:Condition {id: 'ref-sickle', name: 'Sickle Cell Disease', icd10_code: 'D57', hereditary: true, inheritance_pattern: 'autosomal_recessive', heritability_percentage: 25, category: 'hematological'});

// =============================================================================
// REGIONAL HEALTH RISKS (Reference Data)
// =============================================================================

// Common health considerations by region
MERGE (hr1:HealthRisk {id: 'risk-tb', name: 'Tuberculosis Exposure', category: 'endemic_disease', description: 'Higher TB prevalence in Southeast Asia, testing recommended', screening_recommended: true, screening_tests: ['TST', 'IGRA', 'Chest X-ray']})
MERGE (hr2:HealthRisk {id: 'risk-hepb', name: 'Hepatitis B', category: 'endemic_disease', description: 'Endemic in parts of Asia, vaccination and screening recommended', screening_recommended: true, screening_tests: ['HBsAg', 'Anti-HBs', 'Anti-HBc']})
MERGE (hr3:HealthRisk {id: 'risk-dengue', name: 'Dengue Fever History', category: 'endemic_disease', description: 'Previous dengue exposure affects future infection risk', screening_recommended: false, screening_tests: ['Dengue IgG']})
MERGE (hr4:HealthRisk {id: 'risk-parasitic', name: 'Parasitic Infection History', category: 'endemic_disease', description: 'Soil-transmitted helminths common in tropical regions', screening_recommended: true, screening_tests: ['Stool O&P', 'CBC for eosinophilia']})
MERGE (hr5:HealthRisk {id: 'risk-air-pollution', name: 'Air Pollution Exposure', category: 'environmental', description: 'Long-term exposure increases respiratory and cardiovascular risk', screening_recommended: true, screening_tests: ['Spirometry', 'Chest X-ray']});

// Reference locations with health risk associations
MERGE (loc1:Location {id: 'manila-ph', city: 'Manila', country: 'Philippines', country_code: 'PH'})
MERGE (loc1)-[:HAS_HEALTH_RISK {prevalence: 'high', notes: 'WHO high-burden country'}]->(hr1)
MERGE (loc1)-[:HAS_HEALTH_RISK {prevalence: 'intermediate', notes: '~5% chronic carrier rate'}]->(hr2)
MERGE (loc1)-[:HAS_HEALTH_RISK {prevalence: 'endemic', notes: 'Year-round transmission'}]->(hr3)
MERGE (loc1)-[:HAS_HEALTH_RISK {prevalence: 'high', notes: 'Urban air quality concerns'}]->(hr5);

// =============================================================================
// CYPHER QUERY TEMPLATES (For Application Use)
// =============================================================================

// Template: Get hereditary risk for a child
// MATCH (parent:Person)-[:PARENT_OF]->(child:Person {id: $childId})
// MATCH (parent)-[:HAS_CONDITION]->(cond:Condition)
// WHERE cond.hereditary = true
// RETURN parent.name, cond.name, cond.inheritance_pattern, cond.heritability_percentage

// Template: Get all conditions in family tree
// MATCH (p:Person)-[:HAS_CONDITION]->(c:Condition)
// WHERE p.id IN $familyMemberIds
// RETURN p.name, collect(c.name) as conditions

// Template: Check medication interactions
// MATCH (p:Person {id: $personId})-[:TAKES_MEDICATION]->(m1:Medication)
// MATCH (m1)-[i:INTERACTS_WITH]->(m2:Medication)<-[:TAKES_MEDICATION]-(p)
// RETURN m1.name, m2.name, i.severity, i.description

// Template: Get sexual health conditions (requires consent)
// MATCH (p:Person {id: $personId})-[r:HAS_SENSITIVE_CONDITION]->(c:Condition)
// WHERE r.privacy_level = 'consent_required'
// RETURN c.name, r.notes
// -- Application must verify consent before running this query

// Template: Find person by any name alias
// MATCH (a:Alias)<-[:HAS_ALIAS]-(p:Person)
// WHERE toLower(a.name) CONTAINS toLower($searchName)
//    OR toLower(p.name) CONTAINS toLower($searchName)
//    OR toLower(p.preferred_name) CONTAINS toLower($searchName)
// RETURN DISTINCT p

// Template: Get all aliases for a person
// MATCH (p:Person {id: $personId})-[:HAS_ALIAS]->(a:Alias)
// RETURN a.name, a.source, a.is_primary

// Template: Get health risks based on residence history
// MATCH (p:Person {id: $personId})-[:LIVED_IN|BORN_IN]->(loc:Location)
// MATCH (loc)-[r:HAS_HEALTH_RISK]->(hr:HealthRisk)
// WHERE hr.screening_recommended = true
// RETURN loc.city, loc.country, hr.name, hr.screening_tests, r.prevalence

// Template: Get full residence history for a person
// MATCH (p:Person {id: $personId})
// OPTIONAL MATCH (p)-[:BORN_IN]->(birth:Location)
// OPTIONAL MATCH (p)-[lived:LIVED_IN]->(residence:Location)
// OPTIONAL MATCH (p)-[:CURRENTLY_RESIDES]->(current:Location)
// RETURN birth, collect({location: residence, start: lived.start_date, end: lived.end_date}) as history, current

// Template: Get recommended screenings based on birthplace
// MATCH (p:Person {id: $personId})-[:BORN_IN]->(loc:Location)
// MATCH (loc)-[:HAS_HEALTH_RISK]->(hr:HealthRisk)
// WHERE hr.screening_recommended = true
// RETURN hr.name, hr.description, hr.screening_tests
