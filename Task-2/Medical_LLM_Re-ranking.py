from transformers import AutoTokenizer, AutoModel, BitsAndBytesConfig
from sentence_transformers import SentenceTransformer
import torch
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class MedicalLLMCorrector:
    def __init__(self, model_name="emilyalsentzer/Bio_ClinicalBERT"):
        # Load with 4-bit quantization for efficiency
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16
        )
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(
            model_name, 
            quantization_config=bnb_config,
            device_map="auto"
        )
        
        # Preload drug dictionary
        self.drug_dict = self._load_drug_dictionary()
    
    def _load_drug_dictionary(self):
        """Load comprehensive drug dictionary"""
        correct_drugs = [
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
        return [drug.lower() for drug in correct_drugs]
    
    def _get_embedding(self, text):
        """Get contextual embedding for text"""
        inputs = self.tokenizer(text, return_tensors="pt", 
                               truncation=True, max_length=512, 
                               padding=True)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            # Use CLS token embedding
            embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        return embedding
    
    def _generate_candidates(self, misspelled):
        """Generate correction candidates using fuzzy matching"""
        from difflib import get_close_matches
        candidates = get_close_matches(
            misspelled.lower(), 
            self.drug_dict, 
            n=10, 
            cutoff=0.4
        )
        return candidates if candidates else [misspelled.lower()]
    
    def correct_medicine(self, misspelled, context=""):
        """Main correction function"""
        candidates = self._generate_candidates(misspelled)
        
        if len(candidates) == 1:
            return candidates[0]
        
        # If context provided, use it for disambiguation
        if context:
            context_text = f"{context} [DRUG]"
            context_emb = self._get_embedding(context_text)
            
            scores = []
            for candidate in candidates:
                candidate_text = f"{context} {candidate}"
                candidate_emb = self._get_embedding(candidate_text)
                score = cosine_similarity(context_emb, candidate_emb)[0][0]
                scores.append((candidate, score))
            
            # Return highest scoring candidate
            best_candidate = max(scores, key=lambda x: x[1])[0]
            return best_candidate
        
        # Fallback: return closest match by edit distance
        return candidates[0]

# Usage example
corrector = MedicalLLMCorrector()

# Test cases
test_cases = [
    ("Ammoxicillin", "Patient prescribed antibiotics for infection"),
    ("Zolpiden", "Take 10mg tablet at bedtime for insomnia"),
    ("Gabapentain", "300mg three times daily for neuropathic pain"),
    ("Metfornin", "500mg twice daily with meals for diabetes")
]

for misspelled, context in test_cases:
    correction = corrector.correct_medicine(misspelled, context)
    print(f"'{misspelled}' → '{correction}' (Context: {context[:30]}...)")
