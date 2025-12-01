# LLM Schema Training Examples

## 1. Entity and Relation Extraction (Clinical Text Mapping)

| Clinical Text Segment | Entity 1 | Relation | Entity 2 | Notes |
| :--- | :--- | :--- | :--- | :--- |
| "A 45-year-old male with **Type 2 Diabetes**..." | DISORDER: Type 2 Diabetes | PREDISPOSES | DISORDER: Fungal Foot Ulcer | Diabetes is a significant **RISK_FACTOR** not explicitly modeled as an entity, but its link to complications is important. |
| "**Streptococcus pneumoniae** frequently **causes** **Lobar Pneumonia**." | MICROBE: Streptococcus pneumoniae | CAUSES | DISORDER: Lobar Pneumonia | Direct Etiology. |
| "**Headache** **suggests** a diagnosis of **Meningitis**." | SYMPTOM: Headache | SUGGESTS | DISORDER: Meningitis | Diagnostic clue. |
| "The patient was treated with **Amoxicillin** and his **fever** subsequently **improved**." | DRUG: Amoxicillin | TREATS | SIGN: Fever | Demonstrates treating a sign/symptom (palliative/etiological). |
| "**Echocardiography** is **indicated** to **investigate** murmurs." | INVESTIGATION: Echocardiography | INDICATES | DISORDER: Cardiac Murmur | Investigation planning. |
| "The **appendectomy** was performed **before** the patient received **antibiotics**." | PROCEDURE: Appendectomy | TEMPORAL_ORDER: BEFORE | DRUG: Antibiotics | Crucial for sequencing in vignettes. |
| "The patient was advised **lifestyle modification** for his **hypertension**." | MANAGEMENT_PLAN: Lifestyle Modification | INDICATES | DISORDER: Hypertension | Covers non-procedural/non-drug management. |

## 2. Multiple Choice Question (MCQ) Construction Scenarios

### Scenario A: Pathophysiology and Diagnosis (SUGGESTS & CAUSES)

**Goal:** Create an MCQ asking for the causative agent given a finding and disorder.

* **Schema Path:** $**SIGN** / **SYMPTOM** \xrightarrow{\text{SUGGESTS}} **DISORDER** \xleftarrow{\text{CAUSES}} **MICROBE**$
* **Vignette (Input):** "A 6-year-old child presents with a history of fever, headache, and a stiff neck. CSF tap shows Gram-negative diplococci."
* **Question (Prompt):** What is the most likely **MICROBE** **CAUSING** this **DISORDER**?
* **Correct Answer (Target):** **MICROBE: Neisseria meningitidis**
* **Distractors (Plausibility Check):**
    * *Plausible:* MICROBE: Streptococcus pneumoniae (Another common cause of meningitis).
    * *Plausible:* MICROBE: Haemophilus influenzae (Historical cause of meningitis).
    * *Implausible:* MICROBE: Staphylococcus aureus (Usually not primary meningitis).

### Scenario B: Management and Procedure (INDICATES & TREATS)

**Goal:** Create an MCQ asking for the appropriate next step (Procedure/Investigation) given a disorder.

* **Schema Path:** $**DISORDER** \xrightarrow{\text{INDICATES}} **INVESTIGATION** / **PROCEDURE}$
* **Vignette (Input):** "A 55-year-old obese male presents with recurrent retrosternal pain radiating to his jaw, especially after large meals."
* **Question (Prompt):** Which **INVESTIGATION** is **INDICATED** as the next step to confirm the diagnosis of coronary artery disease?
* **Correct Answer (Target):** **INVESTIGATION: Stress Echocardiography**
* **Distractors (Plausibility Check):**
    * *Plausible:* INVESTIGATION: Upper Endoscopy (Plausible confusion with GERD).
    * *Plausible:* PROCEDURE: Coronary Artery Bypass Grafting (A treatment, not initial investigation).
    * *Implausible:* INVESTIGATION: Colonoscopy (Irrelevant system).

### Scenario C: Management Hierarchy (DISORDER $\to$ MANAGEMENT_PLAN)

**Goal:** Create an MCQ asking for the most appropriate non-drug management.

* **Schema Path:** $**DISORDER** \xrightarrow{\text{INDICATES}} **MANAGEMENT\_PLAN**$
* **Vignette (Input):** "A 30-year-old female is newly diagnosed with mild, uncomplicated Panic Disorder."
* **Question (Prompt):** Which **MANAGEMENT\_PLAN** is most strongly **INDICATED** as the first-line, non-pharmacological treatment?
* **Correct Answer (Target):** **MANAGEMENT\_PLAN: Cognitive Behavioral Therapy (CBT)**
* **Distractors:** Psychodynamic Therapy, Psychoanalysis, Nutritional Supplementation, Observation.
