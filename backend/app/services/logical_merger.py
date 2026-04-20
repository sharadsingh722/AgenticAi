import re
import collections
import logging
from app.config import settings

logger = logging.getLogger(__name__)

from enum import Enum
class DocumentType(Enum):
    RESUME = "resume"
    RFP = "tender"

class LogicalMerger:
    """
    Advanced Surgical Document Cleaner & Structural Healer.
    Orchestrates deep cleaning, semantic deduplication, and markdown hierarchy restoration.
    """
    
    @classmethod
    def merge_and_clean(cls, markdown_text: str, doc_type: DocumentType = DocumentType.RFP) -> str:
        """Full Structural cleanup pipeline."""
        logger.info(f"Surgical Consensus Cleaning for {doc_type.value}...")

        # PHASE 1: Broken Word & Symbol Repair
        text = cls._stitch_words(markdown_text)

        # PHASE 2: Scanner Noise (Headers/Footers/Page Numbers)
        cleaned = cls._clean_scanner_noise(text, doc_type)

        # PHASE 3: Global Placeholder Stripping
        stripped = cls._strip_placeholders(cleaned)

        # PHASE 4: Paragraph Healing (Joining split sentences/lines)
        healed = cls._heal_paragraphs(stripped)

        # PHASE 5: Deep Table Cleaning (Deduplication & Consolidation)
        table_fixed = cls._fix_tables_and_repetition(healed)

        # PHASE 6: Symbol & Header Sanitization
        sanitized = cls._sanitize_headers_and_symbols(table_fixed)

        # PHASE 7: Header Healing (Join multi-line headers)
        header_healed = cls._heal_headers(sanitized)

        # PHASE 8: Structural Promotion (Enhanced for Resumes)
        promoted = cls._promote_to_headers(header_healed, doc_type)

        # PHASE 9: Final Global Pipe Fix
        final_doc = re.sub(r'\|{2,}', '|', promoted)

        return final_doc.strip()

    @staticmethod
    def _stitch_words(text: str) -> str:
        """Joins words split mid-way by pipes, markers, or br tags."""
        text = re.sub(r'([a-zA-Z])\|([a-zA-Z])', r'\1\2', text)
        text = re.sub(r'([a-zA-Z])\s*\**\s*\|\s*\**\s*([a-zA-Z])', r'\1\2', text)
        text = re.sub(r'([a-zA-Z])<br>([a-zA-Z])', r'\1\2', text)
        return text

    @staticmethod
    def _strip_placeholders(text: str) -> str:
        """Strips URLs and parser-specific breadcrumbs."""
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\*\*==> picture.*?intentionally omitted <==\*\*', '', text, flags=re.I)
        text = re.sub(r'^\s*\d+/\d+\s*$', '', text, flags=re.M)
        return text

    @staticmethod
    def _clean_scanner_noise(text: str, doc_type: DocumentType) -> str:
        """Heuristic noise removal for recurring patterns."""
        page_blocks = re.split(r'(<!-- PAGE_START_\d+ -->)', text)
        candidates = collections.Counter()
        
        # 1. Build Consensus
        for block in page_blocks:
            if "<!-- PAGE_START" in block or not block.strip(): continue
            page_lines = [l.strip() for l in block.split('\n') if l.strip() and "<!-- PAGE_END" not in l]
            if len(page_lines) < 2: continue
            
            if doc_type == DocumentType.RESUME:
                for line in page_lines[:3] + page_lines[-3:]:
                    skeleton = re.sub(r'[\d\W_]+', '', line).lower()
                    if len(skeleton) >= 5: candidates[skeleton] += 1
            else:
                # RFP specific noise detection for TOP/BTM
                for idx, pos in [(0, "TOP"), (-1, "BTM")]:
                    if idx < len(page_lines):
                        line = page_lines[idx]
                        match = re.search(r'^(.*?)(Page|Pg\.?)\s+[\*_]*\d+[\*_]*(\s+of\s+[\*_]*\d+[\*_]*)?$', line, re.IGNORECASE)
                        if match:
                            candidates[(pos, match.group(1).strip())] += 1
        
        verified_noise = {skel for skel, count in candidates.items() if count >= 3}
        
        # 2. Filter
        filtered_lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped or "<!-- PAGE_" in line:
                filtered_lines.append(line); continue
            
            skeleton = re.sub(r'[\d\W_]+', '', stripped).lower()
            if doc_type == DocumentType.RESUME and skeleton in verified_noise: continue
            
            filtered_lines.append(line)
        return '\n'.join(filtered_lines)

    @staticmethod
    def _heal_paragraphs(text: str) -> str:
        """Join mid-sentence breaks."""
        lines = text.split('\n')
        healed = []; buffer = ""
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith('|') and stripped.endswith('|')) or not stripped or "<!-- PAGE_" in line or re.match(r'^([#\-\d\*\+\|])', stripped):
                if buffer: healed.append(buffer); buffer = ""
                healed.append(line); continue
            
            if buffer:
                if not re.search(r'[\.\!\?\:\;]$', buffer.strip()): buffer += " " + stripped
                else: healed.append(buffer); buffer = line
            else: buffer = line
        if buffer: healed.append(buffer)
        return '\n'.join(healed)

    @classmethod
    def _fix_tables_and_repetition(cls, text: str) -> str:
        """Deep Table Cleaning with Semantic Deduplication and Col Trimming."""
        lines = text.split('\n')
        processed = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith('|'):
                table_block = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    row = re.sub(r'\|{2,}', '|', lines[i])
                    table_block.append(row); i += 1
                
                # A. Semantic Vertical Dedupe (ID-Blind)
                deduped_rows = []
                registry = set()
                for row in table_block:
                    if '---' in row: deduped_rows.append(row); continue
                    content_skel = re.sub(r'^\|\s*[\d\.\-]+\s*\|', '|', row) 
                    content_skel = re.sub(r'[^a-zA-Z0-9]', '', content_skel).lower()
                    if len(content_skel) > 10 and content_skel in registry: continue
                    registry.add(content_skel); deduped_rows.append(row)

                # B. Normalization & Column Trimming
                if deduped_rows:
                    if not any('---|' in r for r in deduped_rows) and len(deduped_rows) > 1:
                        deduped_rows.insert(1, "| --- " * (deduped_rows[0].count('|') - 1) + "|")

                    matrix = [r.split('|') for r in deduped_rows]
                    # matrix might be uneven
                    max_cells = max(len(r) for r in matrix)
                    used_idxs = {0, max_cells - 1}
                    for row_cells in matrix:
                        for idx, cell in enumerate(row_cells):
                            c_strip = cell.strip()
                            if c_strip and c_strip != "---" and not re.match(r'^Col\d+$', c_strip):
                                used_idxs.add(idx)
                    
                    sorted_idxs = sorted(list(used_idxs))
                    for row_cells in matrix:
                        row_content = "|".join([row_cells[idx].strip() if idx < len(row_cells) else "" for idx in sorted_idxs])
                        if row_content:
                            if not row_content.startswith('|'): row_content = '|' + row_content
                            if not row_content.endswith('|'): row_content = row_content + '|'
                            processed.append(row_content)
            else:
                processed.append(line); i += 1
        return '\n'.join(processed)

    @staticmethod
    def _sanitize_headers_and_symbols(text: str) -> str:
        """Crush noise artifacts and excessive symbols."""
        text = re.sub(r'[.\u2026\u00b7\u2022\u25cf\u22ef\u2010-\u2015_\-\=]{3,}', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text

    @staticmethod
    def _heal_headers(text: str) -> str:
        """Join multi-line headers split by parser."""
        temp = text.split('\n')
        healed = []; i = 0
        while i < len(temp):
            line = temp[i]; stripped = line.strip()
            if re.match(r'^###\s+', stripped) and i + 1 < len(temp):
                nxt = temp[i+1].strip()
                if nxt and not nxt.startswith('#') and not nxt.startswith('|') and len(nxt) < 80:
                    joined = f"{stripped} {nxt}"
                    if len(joined) < 150: healed.append(joined); i += 2; continue
            healed.append(line); i += 1
        return '\n'.join(healed)

    @staticmethod
    def _promote_to_headers(text: str, doc_type: DocumentType) -> str:
        """Promote bold labels to Markdown headers."""
        # Triggers for section identification
        triggers = ["Experience", "Education", "Skills", "Certifications", "Projects", "Summary", "Personal Details", "Eligibility", "Role", "Project Name"]
        noise = {"S. No. Contents Page No.", "Dated:"}

        lines = text.split('\n'); final = []
        for line in lines:
            stripped = line.strip()
            content = stripped.strip('| ').strip()
            is_bold = re.match(r'^\*\*([^\n\*]{2,70})\*\*\s*$', content)
            is_trigger = any(t.upper() in content.upper() for t in triggers) and len(content.split()) < 15
            
            if (is_bold or is_trigger) and content not in noise and len(content) > 3:
                if not re.match(r'^[\d\W]+$', content):
                    header = content.replace("**", "").strip()
                    final.append(f"### {header}"); continue
            final.append(line)
        return '\n'.join(final)
