import os, io, time, json, re, textwrap
from dotenv import load_dotenv
import traceback
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import requests
import io, pdfplumber
from typing import Dict, List, Any

# ────────────────────────── 1) Config ──────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Set GEMINI_API_KEY in env")

MODEL   = "models/gemini-1.5-flash-latest"
API_URL = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"{MODEL}:generateContent?key={GEMINI_API_KEY}")

RATE_DELAY      = 1.25     # seconds between calls
CHUNK_LINES     = 50
REQUEST_TIMEOUT = 60

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

# ────────────────────────── 2) Helpers ──────────────────────────
def extract_text_from_pdf(data: bytes) -> str:

    """
    Returns a single UTF-8 string that contains:
      • page body text (as extracted by pdfplumber)
      • every table, rendered as tab-separated rows
    The blocks appear in natural top-to-bottom order for each page.
    """
    parts: list[str] = []

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pnum, page in enumerate(pdf.pages, 1):
            # ── plain text ────────────────────────────────────────────
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)

            # ── tables (each table → TSV block) ───────────────────────
            for tidx, table in enumerate(page.extract_tables(), 1):
                if not table:
                    continue
                parts.append(f"\n# Page {pnum} – Table {tidx}")
                for row in table:
                    # join cells with TAB; replace None with empty string
                    parts.append("\t".join(cell or "" for cell in row))

    return "\n".join(parts)


def chunk_list(lines, n):
    for i in range(0, len(lines), n):
        yield "\n".join(lines[i:i+n])

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
    """
    Remove leading and trailing Markdown code fences (``````json).
    """
    if text.startswith("```"):
        # kill the opening fence (``` or ```
        text = re.sub(r"^```[\w]*\n?", "", text,  count=1, flags=re.S)
        # kill the closing fence (last line ```
        text = re.sub(r"\n?```$", "", text,  count=1, flags=re.S)
    return text.strip()

def call_gemini(prompt: str) -> Dict[str, Any]:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }

    t0      = time.time()
    resp    = requests.post(API_URL, json=body,
                            headers={"Content-Type": "application/json"},
                            timeout=REQUEST_TIMEOUT)
    elapsed = time.time() - t0

    if not resp.ok:                      # network / HTTP error
        return {
            "ok": False, "status": resp.status_code, "text": resp.text,
            "usage": {"in": 0, "out": 0}, "elapsed": elapsed
        }

    data  = resp.json()
    parts = data.get("candidates", [{}])[0] \
                .get("content", {})      \
                .get("parts",   [])
    
    print(data)

    combined: Dict[str, List[dict]] = {"relevant": [], "irrelevant": []}

    for part in parts:
        raw = part.get("text", "").strip()
        if not raw:
            continue

        clean = _strip_fence(raw)

        try:
            obj = json.loads(clean)
        except json.JSONDecodeError:
            continue                    # skip non-JSON fragments

        combined["relevant"].extend(obj.get("relevant",   []))
        combined["irrelevant"].extend(obj.get("irrelevant", []))

    usage = {
        "in":  data.get("usageMetadata", {}).get("promptTokenCount",      0),
        "out": data.get("usageMetadata", {}).get("candidatesTokenCount",  0),
    }
    
    print({
        "ok": True, "status": 200,
        "json": combined, "usage": usage, "elapsed": elapsed
    })
    
    return {
        "ok": True, "status": 200,
        "json": combined, "usage": usage, "elapsed": elapsed
    }



# ---------- ensure each entry is an object {name,explanation} ----------
def _normalize_list(lst):
    norm = []
    for item in lst:
        if isinstance(item, dict):
            name = item.get("name") or ""
            exp  = item.get("explanation") or ""
            if name: norm.append({"name":name, "explanation":exp})
        elif isinstance(item, str):
            norm.append({"name":item.strip(), "explanation":""})
    return norm

# ---------- robust JSON extractor ---------------------------------
def safe_parse(reply: str) -> dict[str, list[dict]]:
    """
    Always return
        {"relevant":[{"name":..,"explanation":..}, …],
         "irrelevant":[{…}, …]}
    even if Gemini surrounds the JSON with markdown, commentary,
    trailing commas, or extra keys.
    """
    # 1) isolate the first {...} block (ignores ```json fences etc.)
    m = re.search(r"\{.*\}", reply, flags=re.S)
    if m:
        raw = m.group(0)

        # 2) strip trailing commas that break json.loads
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)

        try:
            data = json.loads(raw)
            return {
                "relevant":   _normalize_list(data.get("relevant",   [])),
                "irrelevant": _normalize_list(data.get("irrelevant", [])),
            }
        except Exception:
            pass  # fall through to bullet fallback below

    # 3) fallback: split “Relevant: … / Irrelevant: …” sections
    rel = irr = []
    m = re.search(r"[Rr]elevant[^:\n]*[:\n](.+?)(?:\n\s*[Ii]rrelevant|$)",
                  reply, flags=re.S)
    if m:
        rel = [ln.strip(" -*•\t") for ln in m.group(1).splitlines() if ln.strip()]
    m = re.search(r"[Ii]rrelevant[^:\n]*[:\n](.+)$", reply, flags=re.S)
    if m:
        irr = [ln.strip(" -*•\t") for ln in m.group(1).splitlines() if ln.strip()]

    return {
        "relevant":   _normalize_list(rel),
        "irrelevant": _normalize_list(irr),
    }

# ────────────────────────── 3) Routes ──────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    try:
        # ── 1. validate form ---------------------------------------------------
        disease = (request.form.get("disease") or "").strip()
        pdf_file = request.files.get("pdf")

        if not disease or not pdf_file:
            return jsonify(error="Missing disease or PDF"), 400

        data = pdf_file.read()
        if not data:
            return jsonify(error="Empty file"), 400

        # ── 2. extract text & build chunks ------------------------------------
        text = extract_text_from_pdf(data)
        if not text.strip():
            return jsonify(error="No extractable text"), 200

        lines   = [ln.strip() for ln in text.splitlines() if ln.strip()]
        chunks  = list(chunk_list(lines, CHUNK_LINES))
        if not chunks:
            return jsonify(error="No chunks"), 200

        # ── 3. init accumulators ---------------------------------------------
        agg_rel, agg_irr = {}, {}
        results          = []
        tot_in = tot_out = 0

        # ── 4. loop over chunks ----------------------------------------------
        for idx, block in enumerate(chunks, 1):
            r = call_gemini(build_prompt(disease, block))
            print("chunk", idx, "→", r)      # debug

            if not r["ok"]:
                results.append({"idx": idx, **r})  # capture error details
                continue

            # Prefer structured JSON; fall back to safe_parse() if missing
            parsed_raw = r.get("json") or safe_parse(r.get("text", ""))

            # normalise (remove empties, ensure dict shape)
            relevant   = _normalize_list(parsed_raw.get("relevant",   []))
            irrelevant = _normalize_list(parsed_raw.get("irrelevant", []))

            if not relevant and not irrelevant:
                continue  # nothing useful in this chunk

            # ── 4a. aggregate uniques ---------------------------------------
            for obj in relevant:
                agg_rel.setdefault(obj["name"], obj)
            for obj in irrelevant:
                agg_irr.setdefault(obj["name"], obj)

            # ── 4b. store per-chunk result -----------------------------------
            results.append({
                "idx":         idx,
                "elapsed":     r["elapsed"],
                "usage":       r["usage"],
                "relevant":    relevant,
                "irrelevant":  irrelevant,
                "status":      r["status"],
            })

            tot_in  += r["usage"]["in"]
            tot_out += r["usage"]["out"]
            time.sleep(RATE_DELAY)

        # ── 5. final JSON response -------------------------------------------
        return jsonify(
            relevant   = sorted(agg_rel.values(), key=lambda d: d["name"].lower()),
            irrelevant = sorted(agg_irr.values(), key=lambda d: d["name"].lower()),
            results    = results,
            summary    = {
                "calls":      len(chunks),
                "tokens_in":  tot_in,
                "tokens_out": tot_out,
            },
        )

    except Exception as exc:
        traceback.print_exc()
        return jsonify(error=str(exc)), 500



# ────────────────────────── Main ──────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
