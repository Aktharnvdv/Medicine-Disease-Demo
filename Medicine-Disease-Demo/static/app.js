/* ---------- helpers ---------- */
const $ = (sel) => document.querySelector(sel);

/* ---------- elements ---------- */
const diseaseEl  = $("#disease");
const pdfEl      = $("#pdf");
const previewBtn = $("#preview");
const pdfViewer  = $("#pdf-viewer");
const pdfEmbed   = $("#pdf-embed");
const analyzeBtn = $("#analyze");
const spinnerEl  = $("#spinner");
const summaryEl  = $("#summary");
const chunksEl   = $("#chunks");
const emptyEl    = $("#empty");
const outputCard = $("#output");          // NEW

/* ---------- preview state ---------- */
let previewURL = null;

/* ---------- button management ---------- */
function updateButtons(){
  const hasDisease = diseaseEl.value.trim().length > 0;
  const f          = pdfEl.files?.[0];
  const hasPDF     = f && f.type === "application/pdf";

  previewBtn.disabled = !hasPDF;
  analyzeBtn.disabled = !(hasDisease && hasPDF);
  if (!hasPDF) hidePreview();
}
updateButtons();
diseaseEl.addEventListener("input", updateButtons);
pdfEl.addEventListener("change", () => { hidePreview(); updateButtons(); });

/* ---------- preview toggle ---------- */
previewBtn.addEventListener("click",
  () => pdfViewer.hidden ? showPreview() : hidePreview());

function showPreview(){
  const f = pdfEl.files?.[0];
  if (!f || f.type !== "application/pdf") return;
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL        = URL.createObjectURL(f);
  pdfEmbed.src      = previewURL;
  pdfViewer.hidden  = false;
  previewBtn.textContent = "Hide PDF";
}
function hidePreview(){
  pdfViewer.hidden = true;
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = null;
  pdfEmbed.removeAttribute("src");
  previewBtn.textContent = "Preview PDF";
}
window.addEventListener("beforeunload", hidePreview);

/* ---------- UI helpers ---------- */
function clearOutput(){
  chunksEl.innerHTML = "";
  summaryEl.textContent = "";
  emptyEl.hidden = false;
}
function splitBullets(t=""){
  return t.split(/\r?\n/)
          .map(s => s.trim())
          .filter(Boolean)
          .map(s => s.replace(/^[-*•]\s+/, ""));
}

/* render a single medicine card */
function renderItem(grid, obj){
  const card  = document.createElement("div");
  card.className = "medicine-card";

  const title = document.createElement("div");
  title.className = "med-name";
  title.textContent = obj.name || "–";
  card.appendChild(title);

  if (obj.explanation){
    const body = document.createElement("div");
    body.className = "med-desc";
    body.textContent = obj.explanation;
    card.appendChild(body);
  }
  grid.appendChild(card);
}

/* ---------- grouped blocks ---------- */
function buildGroup(title, items){
  const wrap = document.createElement("div");

  const h3 = document.createElement("div");
  h3.className = "group-title med-name";
  h3.textContent = title;
  wrap.appendChild(h3);

  const grid = document.createElement("div");
  grid.className = "med-grid";
  items.forEach(obj => renderItem(grid, obj));
  wrap.appendChild(grid);

  return wrap;
}

function appendChunk(res){
  const chunk  = document.createElement("section");
  chunk.className = "chunk";

  const groups = document.createElement("div");
  groups.className = "groups";

  const rel = res.relevant   ?? [];
  const irr = res.irrelevant ?? [];

  if (rel.length) groups.appendChild(buildGroup("Relevant",   rel));
  if (irr.length) groups.appendChild(buildGroup("Irrelevant", irr));

  /* fallback: plain-text parsing if LLM didn't give JSON */
  if (!rel.length && !irr.length){
    const grid = document.createElement("div");
    grid.className = "med-grid";
    const raw = splitBullets(res.text);
    (raw.length ? raw : [res.text])
      .map(name => ({ name, explanation: "" }))
      .forEach(obj => renderItem(grid, obj));
    groups.appendChild(grid);
  }

  chunk.appendChild(groups);
  chunksEl.appendChild(chunk);
}

/* ---------- optional smooth scroll ---------- */
function scrollLastChunkIntoView(){
  const last = chunksEl.lastElementChild;
  if (last) last.scrollIntoView({behavior:"smooth", block:"end"});
}

/* ---------- main action ---------- */
analyzeBtn.addEventListener("click", async () => {
  clearOutput();
  spinnerEl.hidden = false;
  analyzeBtn.disabled = true;

  const disease = diseaseEl.value.trim();
  const file    = pdfEl.files?.[0];
  if (!disease || !file){
    spinnerEl.hidden = true;
    updateButtons();
    return;
  }

  try{
    const form = new FormData();
    form.append("disease", disease);
    form.append("pdf", file);

    const r = await fetch("/api/analyze", { method: "POST", body: form });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);

    const p = await r.json();

    emptyEl.hidden = p.results.length > 0;
    p.results.forEach(res => { appendChunk(res); scrollLastChunkIntoView(); });

    const s = p.summary || { calls: 0, tokens_in: 0, tokens_out: 0 };
    summaryEl.textContent =
      `Processed ${s.calls} chunks • tokens in/out: ` +
      `${s.tokens_in}/${s.tokens_out} • ` +
      `relevant: ${p.relevant?.length || 0} • ` +
      `irrelevant: ${p.irrelevant?.length || 0}`;

  }catch(e){
    emptyEl.hidden = false;
    emptyEl.textContent = `Error: ${e.message || e}`;
    emptyEl.classList.add("error");
  }finally{
    spinnerEl.hidden = true;
    updateButtons();
  }
});
