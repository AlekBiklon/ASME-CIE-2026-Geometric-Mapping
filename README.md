\# ASME CIE 2026 — Geometric Mapping for Deterministic 3D CAD Editing



This repository contains the \*\*Geometric Mapping\*\* method developed for the

\*\*ASME CIE 2026 Student Hackathon — Autodesk Challenge: 3D CAD Model Editing with Visual Language Models\*\*.



\## Overview



The project investigates an alternative approach to iterative VLM-based CAD editing.



Instead of repeatedly asking a vision-language model to generate and refine CAD code,

the proposed method converts a natural-language editing request into an engineering

operation and uses minimal user-provided geometric grounding to identify the relevant

B-Rep geometry.



The CAD modification is then performed deterministically.



The general pipeline is:



\*\*Natural-language instruction → Engineering intent → Geometric grounding → B-Rep feature recognition → Deterministic CAD edit → Geometry validation\*\*



\## Motivation



VLM-based CAD editing can require multiple inference iterations, visual renders,

and repeated code generation before producing a valid result.



The proposed Geometric Mapping approach separates:



\- semantic understanding of the requested operation;

\- geometric identification of the target;

\- deterministic execution of the CAD modification.



This allows the geometry modification itself to be performed without iterative

VLM inference.



\## Supported Operations



The experimental implementation currently supports several common CAD editing operations:



\- `ADD\_HOLE`

\- `FILLET`

\- `CHAMFER`



Different grounding strategies are used depending on the instruction, including:



\- point-based grounding;

\- edge selection;

\- multiple-edge selection;

\- reference-feature selection;

\- geometric parameter extraction from existing B-Rep features.



\## Experimental Evaluation



Ten paired experiments (`B01`–`B10`) were conducted using editing requests from

the neuralCAD-Edit experimental data.



For each task, the proposed \*\*Geometric Mapping\*\* method was compared with the

Autodesk/neuralCAD-Edit VLM-based baseline.



The evaluation records include:



\- runtime;

\- STEP generation success;

\- B-Rep validity;

\- STEP re-import validity;

\- solid preservation;

\- face and edge counts;

\- volume change;

\- VLM response count;

\- visual render count;

\- estimated inference cost where available.



The proposed method performs the CAD edit with:



\- \*\*0 VLM responses during deterministic editing\*\*

\- \*\*0 iterative visual renders\*\*

\- \*\*0 inference tokens\*\*

\- \*\*$0 inference cost during deterministic editing\*\*



Runtime improvements vary by task and are reported individually in the experimental results.



\## Ground-Truth Limitation



The experiments contain the original CAD models and editing instructions.



However, an official human-created target STEP model was not available for the

evaluated cases in the local experimental data.



Therefore, ground-truth-dependent metrics such as:



\- Voxel IoU

\- Volumetric F1

\- Difference F1

\- Added F1

\- Removed F1

\- Chamfer Distance to target geometry



are not reported as confirmed accuracy metrics.



The comparison therefore focuses on directly measurable properties of the generated

CAD models and execution process.



\## Repository Structure



```text

ASME-CIE-2026-Geometric-Mapping/

│

├── 1\_MAIN.py

├── 2\_COMPARE\_EXPERIMENTS.py

├── main.json

│

├── geometry\_map/

│   ├── deterministic\_edit.py

│   ├── feature\_recognition.py

│   ├── geometry\_picker.py

│   ├── instruction\_grounding.py

│   ├── point\_grounding.py

│   └── step\_geometry\_map.py

│

├── pipeline/

│   ├── autodesk.py

│   ├── autodesk\_metrics.py

│   ├── cad\_edit.py

│   ├── geometry\_benchmark.py

│   ├── ground\_truth.py

│   ├── input\_viewer.py

│   └── metrics.py

│

├── experiments/

│   ├── B01/

│   ├── B02/

│   ├── ...

│   └── B10/

│

├── comparison/

│   └── ASME\_method\_comparison.xlsx

│

└── tools/

