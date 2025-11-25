"""
LLM Service - Handles all LLM interactions via Ollama.
Includes model routing, streaming, and RAG integration.
"""

import base64
from typing import AsyncGenerator, Optional, Dict, Any
import structlog
import ollama
from ollama import AsyncClient

from app.config import settings

logger = structlog.get_logger()


class LLMService:
    """
    Service for LLM interactions.

    Handles:
    - Model routing (text vs vision vs coordinator)
    - Streaming responses
    - RAG context injection
    - Family member context loading
    """

    def __init__(self):
        self.client = AsyncClient(host=settings.OLLAMA_HOST)
        self.models_loaded: Dict[str, bool] = {}

    async def initialize(self):
        """Initialize the LLM service and verify model availability."""
        logger.info("Initializing LLM service", ollama_host=settings.OLLAMA_HOST)

        # Check which models are available
        try:
            models_response = await self.client.list()
            # Handle both old dict-style and new object-style responses
            models_list = getattr(models_response, 'models', models_response.get('models', []) if isinstance(models_response, dict) else [])
            available_models = [getattr(m, 'model', m.get('model', m.get('name', ''))) if hasattr(m, 'model') or isinstance(m, dict) else str(m) for m in models_list]

            for model in [settings.PRIMARY_VLM, settings.MEDICAL_TEXT_MODEL, settings.COORDINATOR_MODEL]:
                # Check partial match (ollama uses various naming conventions)
                base_name = model.split(':')[0]
                is_available = any(base_name in m for m in available_models)
                self.models_loaded[model] = is_available

                if is_available:
                    logger.info(f"Model available: {model}")
                else:
                    logger.warning(f"Model not found: {model}. Run: ollama pull {model}")

        except Exception as e:
            logger.error("Failed to connect to Ollama", error=str(e))
            logger.warning("Continuing without Ollama - some features will be unavailable")

        # Initialize GraphRAG service
        try:
            from app.services.graphrag import get_graphrag_service
            graphrag = get_graphrag_service()
            await graphrag.initialize()
            logger.info("GraphRAG service initialized")
        except Exception as e:
            logger.warning("Failed to initialize GraphRAG", error=str(e))
            logger.warning("Continuing without GraphRAG - context retrieval will be limited")

    def _select_model(self, has_image: bool = False, query_type: str = "general") -> str:
        """
        Select the appropriate model based on the query type.

        Args:
            has_image: Whether the query includes an image
            query_type: Type of query ('general', 'medical', 'coordinator')

        Returns:
            Model name to use
        """
        if has_image:
            return settings.PRIMARY_VLM

        if query_type == "medical":
            return settings.MEDICAL_TEXT_MODEL

        if query_type == "coordinator":
            return settings.COORDINATOR_MODEL

        # Default to medical model for text queries
        return settings.MEDICAL_TEXT_MODEL

    async def _get_member_context(self, member_id: str) -> Optional[str]:
        """Fetch member's health context from Neo4j."""
        try:
            from neo4j import AsyncGraphDatabase

            # Try different connection options
            for uri, auth in [
                ("bolt://localhost:7688", ("neo4j", "changeme_secure_password")),
                ("bolt://neo4j:7687", ("neo4j", "changeme_secure_password")),
                ("bolt://localhost:7687", ("neo4j", "changeme")),
            ]:
                try:
                    driver = AsyncGraphDatabase.driver(uri, auth=auth)
                    async with driver.session() as session:
                        await session.run("RETURN 1")

                        # Get person details with aliases
                        result = await session.run("""
                            MATCH (p:Person {id: $id})
                            OPTIONAL MATCH (p)-[:HAS_ALIAS]->(a:Alias)
                            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
                            OPTIONAL MATCH (p)-[:TAKES]->(m:Medication)
                            OPTIONAL MATCH (p)-[:ALLERGIC_TO]->(al:Allergen)
                            OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(apt:Appointment)
                            RETURN p.name as name, p.full_legal_name as full_name,
                                   p.preferred_name as preferred,
                                   p.date_of_birth as dob, p.gender as gender,
                                   collect(DISTINCT a.name) as aliases,
                                   collect(DISTINCT {name: c.name, status: c.icd10_code}) as conditions,
                                   collect(DISTINCT m.name) as medications,
                                   collect(DISTINCT {name: al.name, reaction: al.reaction}) as allergies,
                                   collect(DISTINCT {date: apt.date, time: apt.time, type: apt.appointment_type, facility: apt.facility, clinic: apt.clinic}) as appointments
                        """, {"id": member_id})

                        record = await result.single()
                        if not record:
                            return None

                        context_parts = []
                        context_parts.append(f"Current user: {record['preferred'] or record['name']}")
                        if record['full_name']:
                            context_parts.append(f"Full legal name: {record['full_name']}")
                        if record['dob']:
                            context_parts.append(f"Date of birth: {record['dob']}")

                        aliases = [a for a in record['aliases'] if a]
                        if aliases:
                            context_parts.append(f"Name aliases (may appear on medical records): {', '.join(aliases)}")

                        conditions = [c['name'] for c in record['conditions'] if c.get('name')]
                        if conditions:
                            context_parts.append(f"Current conditions: {', '.join(conditions)}")

                        medications = [m for m in record['medications'] if m]
                        if medications:
                            context_parts.append(f"Current medications: {', '.join(medications)}")

                        allergies = [f"{a['name']} ({a.get('reaction', 'unknown reaction')})" for a in record['allergies'] if a.get('name')]
                        if allergies:
                            context_parts.append(f"Allergies: {', '.join(allergies)}")

                        # Format appointments with dates
                        appointments = []
                        for apt in record['appointments']:
                            if apt.get('date'):
                                apt_date = apt['date']
                                # Format date as human-readable
                                if hasattr(apt_date, 'to_native'):
                                    apt_date = apt_date.to_native()
                                date_str = apt_date.strftime("%B %d, %Y") if hasattr(apt_date, 'strftime') else str(apt_date)
                                time_str = f" at {apt['time']}" if apt.get('time') else ""
                                type_str = apt.get('type', 'appointment')
                                facility_str = f" ({apt['facility']})" if apt.get('facility') else ""
                                appointments.append(f"{date_str}{time_str}: {type_str}{facility_str}")
                        if appointments:
                            # Sort by date (most recent first)
                            context_parts.append(f"Recent appointments: {'; '.join(appointments[:5])}")

                        await driver.close()
                        return "\n".join(context_parts)

                except Exception:
                    continue
            return None
        except Exception as e:
            logger.warning("Failed to load member context", error=str(e))
            return None

    async def _build_system_prompt(self, family_member_id: Optional[str] = None) -> str:
        """Build the system prompt with family context."""
        base_prompt = """You are Mya, a warm and caring health companion. You help people and their families manage health information and prepare for doctor visits.

YOUR PERSONALITY:
- Warm, supportive, and reassuring - like a knowledgeable friend who genuinely cares
- Patient and thorough - take time to understand their concerns
- Encouraging - help them feel confident about discussing health matters with their doctors

When the user says "my" or "I" - they are referring to THEMSELVES and their personal health data stored in this system.

HOW YOU HELP:
1. PREPARE FOR DOCTOR VISITS - Help organize thoughts, recall dates, and list symptoms to discuss
2. FRAME BETTER QUESTIONS - Suggest clear, specific questions to ask healthcare providers
3. TRACK HEALTH HISTORY - Help organize conditions, medications, and family health patterns
4. UNDERSTAND DOCUMENTS - Explain prescriptions, lab results, and medical records in plain language

YOUR APPROACH:
- Be reassuring when things seem normal: "That sounds like it's within the normal range, but it's always good to mention it to your doctor."
- Be gentle when something needs attention: "It might be worth bringing this up with your doctor so they can take a closer look."
- Help them feel prepared, not anxious
- When discussing symptoms, help them note: when it started, frequency, severity, what helps or makes it worse
- For urgent symptoms (chest pain, difficulty breathing, severe bleeding), calmly but clearly recommend seeking immediate medical care

DATE FORMAT:
- ALWAYS format dates in a human-readable way: "Month Day, Year" (e.g., "November 4, 2025", "March 21, 2023")
- NEVER use ISO format like "2023-03-21" or "2025-11-04" when speaking to the user
- Convert any dates you see in the data to this friendly format

IMPORTANT:
- You are a health companion, not a doctor. Never diagnose or prescribe.
- Always encourage professional medical consultation
- When referencing their data below, help them understand how it connects to their current question
- Be specific with dates and details - doctors appreciate precise timelines"""

        # Add family member specific context from Neo4j
        if family_member_id:
            member_context = await self._get_member_context(family_member_id)
            if member_context:
                base_prompt += f"\n\n--- USER'S HEALTH PROFILE ---\n{member_context}\n--- END PROFILE ---"

        return base_prompt

    async def stream_chat(
        self,
        message: str,
        family_member_id: Optional[str] = None,
        session_id: Optional[str] = None,
        include_rag: bool = True,
        history: Optional[list] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a chat response.

        Args:
            message: User's message
            family_member_id: ID of the family member making the query
            session_id: Chat session ID for context
            include_rag: Whether to include RAG context
            history: Previous conversation messages [{"role": "user"|"assistant", "content": "..."}]

        Yields:
            Dict with type ('token', 'done', 'error', 'context') and content
        """
        model = self._select_model(has_image=False, query_type="medical")
        logger.info("Starting chat stream", model=model, family_member_id=family_member_id,
                    history_length=len(history) if history else 0)

        # Build messages with user context
        system_prompt = await self._build_system_prompt(family_member_id)
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add GraphRAG context
        if include_rag and family_member_id:
            try:
                from app.services.graphrag import get_graphrag_service
                graphrag = get_graphrag_service()
                rag_context = await graphrag.get_medical_context(
                    query=message,
                    family_member_id=family_member_id,
                    top_k=3
                )
                if rag_context:
                    logger.info("Retrieved GraphRAG context", context_length=len(rag_context))
                    yield {"type": "context", "content": rag_context}
                    messages.append({
                        "role": "system",
                        "content": f"\n\n--- RELEVANT MEDICAL HISTORY ---\n{rag_context}\n--- END MEDICAL HISTORY ---\n\nUse this context to provide informed, specific answers."
                    })
            except Exception as e:
                logger.warning("Failed to retrieve GraphRAG context", error=str(e))
                # Continue without RAG context

        # Add conversation history (excluding the current message which will be added separately)
        if history:
            # Skip the last message if it matches current message (it's the one we're about to add)
            history_to_add = history[:-1] if history and history[-1].get("content") == message else history
            for msg in history_to_add:
                if msg.get("role") in ["user", "assistant"] and msg.get("content"):
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

        messages.append({"role": "user", "content": message})

        try:
            # Stream response from Ollama
            response = await self.client.chat(
                model=model,
                messages=messages,
                stream=True,
            )

            full_response = ""
            async for chunk in response:
                if chunk.get("message", {}).get("content"):
                    token = chunk["message"]["content"]
                    full_response += token
                    yield {
                        "type": "token",
                        "content": token,
                        "full": full_response,
                    }

            # Signal completion
            yield {
                "type": "done",
                "content": full_response,
                "model": model,
            }

        except Exception as e:
            logger.error("Chat stream error", error=str(e))
            yield {
                "type": "error",
                "content": f"Error generating response: {str(e)}",
            }

    async def stream_vision(
        self,
        image_b64: str,
        prompt: str = "Describe what you see in this image.",
        family_member_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a vision/image analysis response.

        Args:
            image_b64: Base64 encoded image
            prompt: User's prompt about the image
            family_member_id: ID of the family member

        Yields:
            Dict with type and content
        """
        model = settings.PRIMARY_VLM
        logger.info("Starting vision stream", model=model)

        # Build medical vision prompt - gentle, reassuring health assistant
        system_prompt = """You are Mya, a caring health observation assistant helping someone prepare for their doctor visit.

YOUR APPROACH:
- Be warm, reassuring, and supportive in your tone
- Help the person document what they're experiencing so they can discuss it with their doctor
- If something looks normal, say so clearly and reassuringly
- If you notice something that may need attention, mention it gently without causing alarm

WHEN THINGS LOOK NORMAL:
- Clearly state that what you see appears normal/healthy
- Example: "This area looks healthy - the skin tone is even and there's no visible irritation. When you see your doctor, you can mention you wanted to have them take a look just to be sure."

WHEN SOMETHING MAY NEED ATTENTION:
- Describe observations factually but gently
- Frame it as something worth discussing with a doctor, not as a diagnosis
- Example: "I notice some redness in this area. It's worth mentioning to your doctor so they can take a closer look. They'll be able to tell you more about what might be causing it."

FOR MEDICATIONS/DOCUMENTS:
- Read labels clearly and accurately
- Note dosages, instructions, and any important warnings
- Help organize information to discuss with healthcare providers

IMPORTANT GUIDELINES:
- Never diagnose - you are helping document observations for their doctor
- Always encourage professional medical consultation
- Be specific about location, size, color when describing anything
- If you can't see something clearly, ask for better lighting or angle
- End with a supportive note when appropriate"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            },
        ]

        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
                stream=True,
            )

            full_response = ""
            async for chunk in response:
                if chunk.get("message", {}).get("content"):
                    token = chunk["message"]["content"]
                    full_response += token
                    yield {
                        "type": "token",
                        "content": token,
                        "full": full_response,
                    }

            yield {
                "type": "done",
                "content": full_response,
                "model": model,
            }

        except Exception as e:
            logger.error("Vision stream error", error=str(e))
            yield {
                "type": "error",
                "content": f"Error analyzing image: {str(e)}",
            }

    async def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Classify a query to determine routing and privacy requirements.

        Returns:
            Dict with:
            - query_type: 'simple', 'medical', 'cross_member', 'hereditary'
            - requires_consent: bool
            - entities: extracted entities (family members, conditions, etc.)
        """
        # Use coordinator model for classification
        model = settings.COORDINATOR_MODEL

        classification_prompt = f"""Classify this medical query and extract entities.

Query: "{query}"

Respond in JSON format:
{{
    "query_type": "simple|medical|cross_member|hereditary",
    "involves_members": ["list of family members mentioned"],
    "medical_topics": ["conditions, symptoms, or medications mentioned"],
    "requires_consent": false,
    "sensitive_category": null or "sexual_health|reproductive|mental_health"
}}

Rules:
- "cross_member" if query involves comparing or relating multiple family members
- "hereditary" if asking about genetic conditions or inheritance
- "requires_consent" if involves: sexual_health, reproductive, std_history
- Extract all family member references (mom, dad, child, names, etc.)"""

        try:
            response = await self.client.chat(
                model=model,
                messages=[{"role": "user", "content": classification_prompt}],
                format="json",
            )

            import json
            return json.loads(response["message"]["content"])

        except Exception as e:
            logger.error("Query classification failed", error=str(e))
            return {
                "query_type": "simple",
                "involves_members": [],
                "medical_topics": [],
                "requires_consent": False,
                "sensitive_category": None,
            }
