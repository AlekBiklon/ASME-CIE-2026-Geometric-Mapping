<p align="center">
  <img src="assets/logo.png" alt="ASME CIE 2026 Student Hackathon" width="500">
</p>


# ASME CIE 2026 — Geometric Mapping for Deterministic 3D CAD Editing
This repository contains the **Geometric Mapping** method developed for the
**ASME CIE 2026 Student Hackathon — Autodesk Challenge: 3D CAD Model Editing with Visual Language Models**.

## Novelty

A **Geometric Mapping** method for editing 3D CAD models is proposed, featuring
deterministic and geometrically controlled execution of CAD operations based on
semi-automatic geometric grounding.

The proposed approach provides four key advantages:

1. **Faster execution** compared with neuralCAD-Edit.
2. **No additional VLM inference cost.**
3. **Geometric controllability** of CAD operations.
4. **Robustness to topological issues.**

## Overview

The project investigates an alternative approach to iterative VLM-based CAD editing.

Instead of repeatedly asking a vision-language model to generate and refine CAD code,

the proposed method converts a natural-language editing request into an engineering

operation and uses minimal user-provided geometric grounding to identify the relevant

B-Rep geometry.

The CAD modification is then performed deterministically.

The general pipeline is:

**Natural-language instruction → Engineering intent → Geometric grounding → B-Rep feature recognition → Deterministic CAD edit → Geometry validation**

## Motivation

VLM-based CAD editing can require multiple inference iterations, visual renders,

and repeated code generation before producing a valid result.

The proposed Geometric Mapping approach separates:

- semantic understanding of the requested operation;

- geometric identification of the target;

- deterministic execution of the CAD modification.

This allows the geometry modification itself to be performed without iterative

VLM inference.

## Supported Operations

The experimental implementation currently supports several common CAD editing operations:

- `ADD_HOLE`

- `FILLET`

- `CHAMFER`

Different grounding strategies are used depending on the instruction, including:

- point-based grounding;

- edge selection;

- multiple-edge selection;

- reference-feature selection;

- geometric parameter extraction from existing B-Rep features.


## Experimental Evaluation

Ten paired experiments (`B01`–`B10`) were conducted using editing requests from
the neuralCAD-Edit experimental data.
For each task, the proposed **Geometric Mapping** method was compared with the
Autodesk/neuralCAD-Edit VLM-based baseline.

The evaluation records include:

- runtime;
- STEP generation success;
- B-Rep validity;
- STEP re-import validity;
- solid preservation;
- face and edge counts;
- volume change;
- VLM response count;
- visual render count;
- estimated inference cost where available.

## Installation

This repository contains the custom `geometry_map` harness developed for the
Geometric Mapping method.

To integrate the method with the original neuralCAD-Edit framework, copy the
`geometry_map` directory into:

```text
neuralCAD-Edit/
└── src/
    └── harnesses/
        └── geometry_map/
```
The resulting path should be:
`neuralCAD-Edit/src/harnesses/geometry_map/`
The upstream neuralCAD-Edit source code and dataset are not redistributed in this repository.

## Upstream Project and Attribution

This project builds upon the **neuralCAD-Edit** benchmark and experimental
framework developed by Toby Perrett, Matthew Bouchard, and William McCarthy.

The original Autodesk Hackathon repository is available here:

**[IDETC26-Hackathon-Autodesk-neuralCAD-Edit](https://github.com/grndnl/IDETC26-Hackathon-Autodesk-neuralCAD-Edit)**

The neuralCAD-Edit framework was used as the VLM-based baseline and as part of
the experimental infrastructure for the CAD editing tasks evaluated in this
repository.

The **Geometric Mapping** method presented in this repository is an alternative
CAD-editing approach developed for the ASME CIE 2026 Student Hackathon. It uses
geometric grounding, B-Rep feature recognition, and deterministic CAD operations
instead of iterative VLM-based CAD code generation and refinement.

### Citation

If you use the neuralCAD-Edit benchmark or framework, please cite the original work:

```bibtex
@inproceedings{perrett2026neuralcadedit,
  title={neuralCAD-Edit: An Expert Benchmark for Multimodal-Instructed 3D CAD Model Editing},
  author={Perrett, Toby and Bouchard, Matthew and McCarthy, William},
  booktitle={arXiv preprint arXiv:2604.16170},
  year={2026}
}
```
