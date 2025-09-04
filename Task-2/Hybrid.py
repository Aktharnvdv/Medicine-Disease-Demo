from symspellpy import SymSpell, Verbosity
from transformers import pipeline
import torch          # ← ADD THIS LINE
import numpy as np     # needed later for np.linalg.norm
import time


class HybridMedicineCorrector:
    def __init__(self, 
                 medical_model="emilyalsentzer/Bio_ClinicalBERT",
                 max_edit_distance=2):
        
        # Initialize SymSpell for fast candidate generation
        self.symspell = SymSpell(
            max_dictionary_edit_distance=max_edit_distance,
            prefix_length=7
        )
        
        # Load medical LLM for re-ranking
        self.medical_pipeline = pipeline(
            "feature-extraction",
            model=medical_model,
            device=0 if torch.cuda.is_available() else -1
        )
        
        # Build dictionary
        self._build_dictionary()
    
    def _build_dictionary(self):
        """Build SymSpell dictionary with drug names"""
        drug_names = [
            "Acetaminophen","Adderall","Amlodipine","Amoxicillin","Aripiprazole",
            "Atorvastatin","Azithromycin","Baclofen","Benadryl","Bupropion",
            "Buspirone","Celecoxib","Cephalexin","Ciprofloxacin","Citalopram",
            "Clindamycin","Clonazepam","Cyclobenzaprine","Cymbalta","Doxycycline",
            "Duloxetine","Escitalopram","Fentanyl","Fluoxetine","Gabapentin",
            "Hydrocodone","Hydrochlorothiazide","Ibuprofen","Imodium","Lisinopril",
            "Levothyroxine","Loratadine","Losartan","Meloxicam","Metformin",
            "Methadone","Metoprolol","Methylprednisolone","Naproxen","Nortriptyline",
            "Omeprazole","Ondansetron","Oxycodone","Pantoprazole","Prednisone",
            "Propranolol","Quetiapine","Ranitidine","Risperidone","Rosuvastatin",
            "Sertraline","Simvastatin","Spironolactone","Sumatriptan","Tamoxifen",
            "Tamsulosin","Tramadol","Trazodone","Valacyclovir","Valproic acid",
            "Venlafaxine","Warfarin","Alprazolam","Zolpidem","Apixaban",
            "Insulin glargine","Ezetimibe","Liraglutide","Clopidogrel","Dabigatran",
            "Ticagrelor","Ustekinumab","Vedolizumab","Secukinumab","Infliximab",
            "Etanercept","Abatacept","Tocilizumab","Teriparatide","Denosumab",
            "Alendronate","Zoledronic acid","Filgrastim","Rituximab","Pembrolizumab",
            "Nivolumab","Atezolizumab","Olaparib","Ibrutinib","Imatinib",
            "Sunitinib","Sorafenib","Bevacizumab","Trastuzumab","Cetuximab",
            "Erlotinib","Lapatinib","Osimertinib","Palbociclib","Crizotinib"
        ]
        
        for drug in drug_names:
            # Add both original case and lowercase
            self.symspell.create_dictionary_entry(drug.lower(), 1)
            self.symspell.create_dictionary_entry(drug, 1)
    
    def _get_symspell_candidates(self, misspelled, max_suggestions=5):
        """Fast candidate generation using SymSpell"""
        raw_suggestions = self.symspell.lookup(
            misspelled,
            Verbosity.CLOSEST,
            max_edit_distance=2
        )
        # convert SuggestItem objects → strings and truncate
        suggestions = [s.term for s in raw_suggestions][:max_suggestions]

        return suggestions          # ← just return the list of strings

        
    def _llm_rerank(self, candidates, context):
        """Use LLM to re-rank candidates based on context"""
        if not context or len(candidates) <= 1:
            return candidates[0] if candidates else None
        
        scores = []
        base_context = f"Medical context: {context}"
        
        for candidate in candidates:
            # Create contextual prompt
            text = f"{base_context} Medicine: {candidate}"
            
            # Get embedding
            embedding = self.medical_pipeline(text)[0]
            # Simple scoring based on embedding magnitude
            score = np.linalg.norm(embedding)
            scores.append((candidate, score))
        
        # Return highest scoring candidate
        return max(scores, key=lambda x: x[1])[0]
    
    def correct_with_timing(self, misspelled, context=""):
        """Correct with detailed timing information"""
        start_time = time.time()
        
        # Step 1: Fast candidate generation
        candidates_start = time.time()
        candidates = self._get_symspell_candidates(misspelled)
        candidates_time = time.time() - candidates_start
        
        if not candidates:
            return {
                'original': misspelled,
                'corrected': misspelled,
                'confidence': 0.0,
                'symspell_time': candidates_time,
                'llm_time': 0.0,
                'total_time': time.time() - start_time
            }
        
        # Step 2: LLM re-ranking
        llm_start = time.time()
        best_correction = self._llm_rerank(candidates, context)
        llm_time = time.time() - llm_start
        
        total_time = time.time() - start_time
        
        return {
            'original': misspelled,
            'corrected': best_correction,
            'candidates': candidates,
            'context': context,
            'symspell_time': candidates_time * 1000,  # ms
            'llm_time': llm_time * 1000,              # ms
            'total_time': total_time * 1000           # ms
        }

# Usage and benchmarking
hybrid_corrector = HybridMedicineCorrector()

test_cases = [
    ("Ammoxicillin", "Patient needs antibiotic treatment"),
    ("Zolpiden", "Sleep aid medication for insomnia"),
    ("Gabapentain", "Nerve pain medication"),
    ("Atrovastatin", "Cholesterol lowering medication")
]

print("=== Hybrid Method Performance ===")
for misspelled, context in test_cases:
    result = hybrid_corrector.correct_with_timing(misspelled, context)
    print(f"\nOriginal: {result['original']}")
    print(f"Corrected: {result['corrected']}")
    print(f"Candidates: {result['candidates']}")
    print(f"SymSpell Time: {result['symspell_time']:.1f}ms")
    print(f"LLM Time: {result['llm_time']:.1f}ms")
    print(f"Total Time: {result['total_time']:.1f}ms")
