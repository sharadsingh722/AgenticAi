"""Profile engine for computing deterministic derived profiles."""
from typing import Dict, Any

def compute_derived_profile(resume_json: Dict[str, Any]) -> Dict[str, Any]:
    """Compute deterministic flags and metrics from the parsed resume JSON."""
    profile = {
        "has_railway_experience": False,
        "has_epc_experience": False,
        "has_electrification_experience": False,
        "has_signalling_experience": False,
        "has_bridge_or_structure_experience": False,
        "max_project_value_cr": 0.0,
        "railway_project_count": 0
    }
    
    experience = resume_json.get("experience", [])
    if not experience:
        return profile
    
    domains_and_sectors = []
    domains_and_sectors.extend([d.lower() for d in resume_json.get("domain_expertise", [])])
    
    for exp in experience:
        sector_str = (exp.get("sector") or "").lower()
        subsector_str = (exp.get("subsector") or "").lower()
        desc_str = (exp.get("description") or "").lower()
        components = [c.lower() for c in exp.get("components", [])]
        
        all_text = f"{sector_str} {subsector_str} {desc_str} " + " ".join(components)
        
        # Railway Experience
        if "railway" in all_text or "railway" in sector_str or "metro" in all_text:
            profile["has_railway_experience"] = True
            profile["railway_project_count"] += 1
            
        # EPC Experience
        if "epc" in all_text or "epc" in domains_and_sectors:
            profile["has_epc_experience"] = True
            
        # Electrification
        if "electrification" in all_text or "ohe" in all_text or "traction" in all_text:
            profile["has_electrification_experience"] = True
            
        # Signalling
        if "signalling" in all_text or "telecom" in all_text or "s&t" in all_text:
            profile["has_signalling_experience"] = True
            
        # Bridge or Structure
        if "bridge" in all_text or "viaduct" in all_text or "flyover" in all_text or "structure" in all_text:
            profile["has_bridge_or_structure_experience"] = True
            
        # Max Project Value
        try:
            val = float(exp.get("project_value_cr", 0.0))
            if val > profile["max_project_value_cr"]:
                profile["max_project_value_cr"] = val
        except (ValueError, TypeError):
            pass
            
    return profile
