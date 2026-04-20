import sys
import os
import asyncio
import json
import hashlib
from datetime import datetime

# Add backend to path
sys.path.append(os.path.abspath('d:/agentic project/resume_tender_match_agent/backend'))

from app.database import SessionLocal
from app.models import Tender
from app.services.embedding import embed_texts, store_tender_role_embedding
from app.services.ingestion import process_rag_indexing

async def create_simulated_software_tender():
    print("Creating Simulated Software Tender...")
    
    tender_data = {
        "project_name": "Enterprise AI & Data Analytics Platform",
        "client": "TechInnovate Solutions Corp",
        "document_reference": "RFP-2026-IT-001",
        "document_date": datetime.now().strftime("%Y-%m-%d"),
        "key_technologies": ["Python", "React", "Machine Learning", "FastAPI", "PostgreSQL", "OpenAI API", "Langchain"],
        "project_duration": "12 Months",
        "eligibility_criteria": [
            "Minimum 3 years of experience in Software Development",
            "Expertise in Data Engineering or AI/ML",
            "Proven track right of delivering enterprise-grade web applications"
        ]
    }

    roles = [
        {
            "role_title": "Full Stack Developer",
            "min_experience": 3,
            "required_skills": ["Python", "React", "FastAPI", "SQL", "Git"],
            "required_certifications": [],
            "required_domain": ["Web Development", "Backend Services"],
            "preferred_components": ["API Integration", "Microservices"]
        },
        {
            "role_title": "Data Scientist / ML Engineer",
            "min_experience": 2,
            "required_skills": ["Python", "Machine Learning", "NLP", "Statistical Data Analysis", "OpenAI"],
            "required_certifications": [],
            "required_domain": ["Artificial Intelligence", "Data Science"],
            "preferred_components": ["Generative AI", "Vector Databases"]
        },
        {
            "role_title": "Digital Marketing & SEO Specialist",
            "min_experience": 2,
            "required_skills": ["SEO", "Google Analytics", "Keyword Research", "Content Strategy"],
            "required_certifications": [],
            "required_domain": ["Digital Commerce", "Marketing Strategy"],
            "preferred_components": ["Performance Analysis"]
        }
    ]

    raw_text = """
    Request for Proposal: Enterprise AI & Data Analytics Platform (RFP-2026-IT-001)
    
    Overview:
    TechInnovate Solutions is seeking a qualified team of software engineers and data scientists to build an Enterprise-grade AI platform. 
    The platform will involve heavy backend development using Python and FastAPI, with a reactive frontend built in React.
    
    Roles Required:
    1. Full Stack Developer: Must be proficient in Python, React, and SQL. Experience with FastAPI is preferred.
    2. Data Scientist: Focused on Machine Learning, NLP, and Statistical Analysis. Familiarity with OpenAI and Langchain is a plus.
    3. Digital Marketing Specialist: To handle SEO and performance analysis for the platform launch.
    
    Project Duration: 12 months.
    Location: Remote / Flexible.
    """

    db = SessionLocal()
    try:
        db_tender = Tender(
            project_name=tender_data["project_name"],
            client=tender_data["client"],
            document_reference=tender_data["document_reference"],
            document_date=tender_data["document_date"],
            required_roles=json.dumps(roles),
            eligibility_criteria=json.dumps(tender_data["eligibility_criteria"]),
            project_duration=tender_data["project_duration"],
            key_technologies=json.dumps(tender_data["key_technologies"]),
            raw_text=raw_text,
            file_name="simulated_it_tender.pdf",
            pdf_filename="simulated_it_tender.pdf",
            parsed_data=json.dumps({**tender_data, "required_roles": roles}),
            parse_status="success",
        )
        db.add(db_tender)
        db.commit()
        db.refresh(db_tender)

        print(f"Tender ID {db_tender.id} created: {db_tender.project_name}")

        # Generate embeddings for roles
        for i, role in enumerate(roles):
            role_text = f"{role['role_title']}. Skills: {', '.join(role['required_skills'])}. Domain: {', '.join(role['required_domain'])}."
            print(f"Embedding role: {role['role_title']}...")
            embeddings = await embed_texts([role_text])
            metadata = {"tender_id": db_tender.id, "role_title": role["role_title"]}
            store_tender_role_embedding(db_tender.id, i, embeddings[0], metadata)

        # Index for RAG
        print("Indexing for RAG...")
        process_rag_indexing(db_tender.id, "tender", raw_text)
        
        print("\nSUCCESS! The IT Tender is now live.")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(create_simulated_software_tender())
