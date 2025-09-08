MedicalLLMCorrector fixes misspelled drug names using Bio-ClinicalBERT embeddings plus fuzzy search.
Features:

Loads Bio_ClinicalBERT in 4-bit with bitsandbytes, saving VRAM.

Generates candidates via difflib edit distance against a built-in list of 100+ common medications.

Ranks candidates by cosine similarity to prescription context, selecting the most semantically plausible drug.