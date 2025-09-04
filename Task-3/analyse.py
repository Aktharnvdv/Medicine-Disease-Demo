# core_logic.py  ─────────────────────────────────────────────────────────
import os, io, time, json, re, textwrap
from typing import Dict, List, Any, Iterator

import pdfplumber
from dotenv import load_dotenv
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM

# ── 1. Config ───────────────────────────────────────────────────────────
load_dotenv()
HF_MODEL         = os.getenv("HF_MODEL",  "HuggingFaceH4/zephyr-7b-beta")
DEVICE           = int(os.getenv("CUDA_DEVICE", 0)) if os.getenv("CUDA_VISIBLE_DEVICES") else -1
RATE_DELAY       = 1.25        # seconds between LLM calls
CHUNK_LINES      = 50

# Single pipeline object reused across calls
_text_gen = pipeline(
    task="text-generation",
    model=HF_MODEL,
    tokenizer=AutoTokenizer.from_pretrained(HF_MODEL),
    model_kwargs={"device_map": "auto"},
    device=DEVICE,
    max_new_tokens=512,
    temperature=0.2,
)

# ── 2. Helper utilities (unchanged) ─────────────────────────────────────
def extract_text_from_pdf(data: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pnum, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt)
            for tidx, tbl in enumerate(page.extract_tables(), 1):
                if tbl:
                    parts.append(f"\n# Page {pnum} – Table {tidx}")
                    parts.extend("\t".join(c or "" for c in row) for row in tbl)
    return "\n".join(parts)

def chunk_list(lines: List[str], n: int) -> Iterator[str]:
    for i in range(0, len(lines), n):
        yield "\n".join(lines[i : i + n])

def build_prompt(disease: str, block: str) -> str:
    return textwrap.dedent(f"""
        You are an experienced clinical pharmacist so first extract medicine details only from below prompt.

        For every medicine (one per line) in the list below, classify it as
        RELEVANT for treating or managing "{disease}" or IRRELEVANT
        (unrelated/contraindicated).  Return strictly valid JSON:

        {{
          "relevant": [
            {{"name":"<Med A>","explanation":"<15-30 word reason it helps {disease}>"}}
          ],
          "irrelevant": [
            {{"name":"<Med X>","explanation":"<brief reason it is not used / risky>"}}
          ]
        }}

        • Keep keys exactly as shown.
        • Do not add any explanations outside the JSON block.

        List:
        {block}
    """).strip()

def _strip_fence(text: str) -> str:
    if text.startswith("```
        text = re.sub(r"^```[\w]*\n?", "", text, count=1, flags=re.S)
        text = re.sub(r"\n?```
    return text.strip()

# ── 3. LLM call (Hugging Face) ──────────────────────────────────────────
def call_hf_llm(prompt: str) -> Dict[str, Any]:
    """
    Send prompt to Hugging Face pipeline and return parsed JSON plus timings.
    """
    t0   = time.time()
    raw  = _text_gen(prompt, return_full_text=False)["generated_text"]
    elapsed = time.time() - t0

    combined: Dict[str, List[dict]] = {"relevant": [], "irrelevant": []}
    try:
        obj = json.loads(_strip_fence(raw))
        combined["relevant"].extend(obj.get("relevant",   []))
        combined["irrelevant"].extend(obj.get("irrelevant", []))
    except json.JSONDecodeError:
        pass  # model returned malformed JSON -> handled downstream

    return {
        "ok":    True,
        "status": 200,
        "json": combined,
        "usage": {"in": 0, "out": 0},  # local model: no token accounting
        "elapsed": elapsed,
    }

def _normalize_list(lst):
    out = []
    for item in lst:
        if isinstance(item, dict):
            name = item.get("name") or ""
            exp  = item.get("explanation") or ""
            if name:
                out.append({"name": name, "explanation": exp})
        elif isinstance(item, str):
            out.append({"name": item.strip(), "explanation": ""})
    return out

# ── 4. Public API ───────────────────────────────────────────────────────
def analyse_pdf(pdf_bytes: bytes, disease: str) -> Dict[str, Any]:
    text = extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        raise ValueError("No extractable text in PDF")

    lines  = [ln.strip() for ln in text.splitlines() if ln.strip()]
    chunks = list(chunk_list(lines, CHUNK_LINES))
    if not chunks:
        raise ValueError("No text chunks generated")

    agg_rel, agg_irr, results = {}, {}, []
    for idx, block in enumerate(chunks, 1):
        r = call_hf_llm(build_prompt(disease, block))

        rel = _normalize_list(r["json"].get("relevant",   []))
        irr = _normalize_list(r["json"].get("irrelevant", []))

        for obj in rel:
            agg_rel.setdefault(obj["name"], obj)
        for obj in irr:
            agg_irr.setdefault(obj["name"], obj)

        results.append({"idx": idx, "elapsed": r["elapsed"],
                        "relevant": rel, "irrelevant": irr})

        time.sleep(RATE_DELAY)

    return {
        "relevant":   sorted(agg_rel.values(), key=lambda d: d["name"].lower()),
        "irrelevant": sorted(agg_irr.values(), key=lambda d: d["name"].lower()),
        "results":    results,
        "summary":    {"calls": len(chunks)},
    }

def analyse_uploaded_file(file_storage, disease: str) -> Dict[str, Any]:
    data = file_storage.read()
    if not data:
        raise ValueError("Empty upload")
    return analyse_pdf(data, disease)
