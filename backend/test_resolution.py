import os
import json
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

class CommonValueSelection(BaseModel):
    selected_common_values: list[str] = Field(default_factory=list)
    reasoning: str = ""

def test_resolution():
    llm = ChatOpenAI(model="gpt-4o").with_structured_output(CommonValueSelection)
    
    category = "education"
    user_query = "PhD vs Master candidates in Civil Eng"
    
    # Represent the catalog I saw in DB
    catalog = [
        {"name": "btech_civil", "label": "btech civil", "level": "graduate", "aliases": []},
        {"name": "mtech_civil", "label": "mtech civil", "level": "postgraduate", "aliases": []},
        {"name": "phd_civil_engineering", "label": "phd civil engineering", "level": "phd", "aliases": ["Doctor of Philosophy..."]},
        {"name": "mtech_structural", "label": "mtech structural", "level": "postgraduate", "aliases": []},
    ]
    
    catalog_lines = []
    for item in catalog:
        catalog_lines.append(f"- {item['name']} | label: {item['label']} | level: {item['level']} | aliases: {item['aliases']}")
    
    catalog_text = "\n".join(catalog_lines)
    
    prompt = (
        "You are an expert at matching a user's search filter against a catalog of standardized values.\n\n"
        f"Category: {category}\n"
        f'User filter: "{user_query}"\n\n'
        f"Catalog of available values:\n{catalog_text}\n\n"
        "Instructions:\n"
        "1. Understand the full semantic intent of the user's filter using your world knowledge.\n"
        "2. Select EVERY catalog entry that matches that intent - and ONLY those entries.\n"
        "3. Do NOT select entries from a different level, domain, or category.\n\n"
        "Catalog note:\n"
        "- Some catalog names may be technical keys or may include noisy details from old data. Use the label, concepts, and aliases to understand the real reusable concept.\n\n"
        "How to interpret common filter types:\n"
        '- A qualification LEVEL filter (e.g. "Graduate", "Post Graduate", "PhD", "Diploma") - match by academic level only.\n'
        '  * SEARCH PROTOCOL for Levels: If the user asks for a level (like "Masters"), you MUST select ALL catalog entries where the `level` metadata matches that intent (e.g., all "postgraduate" entries).\n'
        '  * "Graduate" = undergraduate/Bachelor\'s level degrees (B.E., B.Tech, BCA, BSc, BA, AMIE, etc.) - NOT Masters, NOT Diploma.\n'
        '  * "Post Graduate" = Master\'s level (M.Tech, M.E., MSc, MBA, etc.) - NOT Bachelor\'s.\n'
        '  * "PhD" = Doctorate only.\n'
        '  * "Diploma" = Diploma/Polytechnic certificates only.\n'
        '- A SUBJECT/DOMAIN filter (e.g. "Civil Engineering", "Python") - match by subject across all levels.\n'
        '- A SPECIFIC DEGREE filter (e.g. "B.Tech Computer Science" or "Bachelor of Science") - match that exact degree family/variant.\n\n'
        "Equivalence Logic:\n"
        "- Use your broad world knowledge to identify degrees that are semantically identical.\n"
        "- STRICTNESS RULE: If the user asks for 'Science' (e.g. Bachelor of Science, BSc, MSc), do NOT match 'Engineering' (B.E., B.Tech, M.E.) unless the engineering degree explicitly calls itself a 'B.Sc. (Engineering)' or similar.\n"
        "- STRICTNESS RULE: Conversely, if the user asks for 'Engineering', do NOT match pure 'Science' degrees (BSc, MSc).\n"
        "- If a user filter corresponds to a standard professional qualification like AMIE, match it to the equivalent degree level when appropriate.\n\n"
        "Rules:\n"
        "- Use your own world knowledge - do NOT rely on name patterns or prefixes in the catalog entries.\n"
        "- Use the `label`, `level`, and `concepts` metadata to make high-fidelity decisions.\n"
        "- If the user filter already exactly matches a catalog degree label or alias, prefer that exact catalog match instead of broad expansion.\n"
        "- For education, treat equivalent degree families as matches when the catalog concepts support it.\n"
        "- Return values exactly as they appear in the catalog.\n"
        "- If nothing in the catalog matches, return an empty list.\n"
        "- If the user asks for multiple things (e.g. 'PhD vs Masters'), select BOTH categories."
    )
    
    res = llm.invoke(prompt)
    print(f"Selected: {res.selected_common_values}")
    print(f"Reasoning: {res.reasoning}")

if __name__ == "__main__":
    test_resolution()
