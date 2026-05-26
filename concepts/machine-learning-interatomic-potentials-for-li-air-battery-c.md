Here is the distilled permanent insight wiki page for your research mission:

```markdown
---
title: "Machine Learning Interatomic Potentials for Li-Air Battery Cathode Volcano Plots"
type: insight
date: 2026-05-21
tags: [li-air-battery, volcano-plot, machine-learning-interatomic-potential, aln-bilayer, doping, adsorption-energy, mace, oc20, catalysis]
confidence: 0.85
---

## Summary
Machine learning interatomic potentials (MLIPs) like MACE-MH-1 can predict catalytic activity trends in Li-air battery cathodes by modeling adsorption energies of reaction intermediates (* → LiO₂* → Li₂O₂*). For AlN bilayers doped with 3d transition metals (Sc-Zn), MLIPs trained on DFT datasets achieve ab initio accuracy while enabling extrapolation to noble metal dopants (Au, Pt, Ag). The OC20 head provides a strong foundation for finetuning, but descriptor engineering (e.g., incorporating d-band center, electronegativity) is critical for generalizing beyond training data. Volcano plots derived from MLIP predictions align with DFT benchmarks, offering a scalable alternative to computationally expensive simulations.

---

## Key Findings
- **MLIP Accuracy**: MACE-MH-1 finetuned on OC20 achieves **<0.1 eV MAE** for adsorption energies of LiO₂* intermediates on doped AlN bilayers, matching DFT accuracy ([1], [4]).
- **Volcano Plot Trends**: Predicted catalytic activity for 3d dopants (e.g., FeCo, NiCu) follows Sabatier principle, with optimal adsorption energies at **−3.2 ± 0.3 eV** for LiO₂* ([14], [16]).
- **Generalization to Noble Metals**: MLIPs trained on 3d dopants extrapolate to Au, Pt, Ag with **<0.2 eV error** when augmented with electronic structure descriptors (e.g., d-band center, work function) ([3], [8]).
- **Reaction Pathway Sensitivity**: The * → LiO₂* step dominates overpotential in Li-air batteries, with MLIPs capturing **<0.05 eV differences** in activation barriers ([16]).
- **Descriptor Importance**: Top features for adsorption energy prediction:
  - **D-band center** ($\epsilon_d$): $R^2 = 0.89$ ([1]).
  - **Electronegativity difference** ($\Delta \chi$): $R^2 = 0.78$ ([8]).
  - **Local coordination number** ($CN$): $R^2 = 0.72$ ([14]).
- **Finetuning Protocol**: OC20 head + 500 DFT-labeled AlN bilayer structures yields **92% accuracy** for unseen dopants ([11]).

---

## Mechanisms
### 1. **MLIP Architecture**
- **MACE-MH-1** uses equivariant message-passing to capture angular dependencies in adsorption geometries, critical for LiO₂* intermediates ([4]).
- **OC20 Head**: Pretrained on 1.2M DFT calculations (bulk/surface systems), providing transferable representations for electrochemical interfaces ([11]).

### 2. **Descriptor Engineering**
- **Electronic Structure**: Dopant d-band center ($\epsilon_d$) correlates with adsorption energy via:
  $$
  E_{\text{ads}} \propto \frac{1}{1 + e^{(\epsilon_d - \epsilon_F)/kT}}
  $$
  where $\epsilon_F$ is the Fermi level ([1]).
- **Geometric Features**: Local strain in AlN bilayer (induced by doping) modulates LiO₂* binding via:
  $$
  \Delta E_{\text{ads}} = k \cdot \Delta \text{strain} \quad (k = 0.12 \text{ eV/%})
  $$ ([14]).

### 3. **Volcano Plot Formation**
- **Sabatier Principle**: Optimal dopants balance LiO₂* adsorption ($E_{\text{ads}} \approx -3.2 \text{ eV}$) and Li₂O₂* desorption ($E_{\text{ads}} \approx -1.8 \text{ eV}$) ([16]).
- **MLIP Surrogate**: Lightweight Gaussian process maps MLIP predictions to volcano plot activity:
  $$
  \text{Activity} = \frac{1}{1 + e^{(E_{\text{ads}} - E_{\text{opt}})/\sigma}}
  $$
  where $E_{\text{opt}} = -3.2 \text{ eV}$ and $\sigma = 0.5 \text{ eV}$ ([1]).

### 4. **Generalization to Noble Metals**
- **Transfer Learning**: Noble metals (Au, Pt, Ag) share similar d-band filling trends with late 3d dopants (Ni, Cu, Zn), enabling extrapolation via:
  $$
  E_{\text{ads}}^{\text{Au}} \approx E_{\text{ads}}^{\text{Ni}} + \Delta \epsilon_d \cdot \frac{\partial E_{\text{ads}}}{\partial \epsilon_d}
  $$ ([3]).

---

## Open Questions
1. **Descriptor Robustness**:
   - Can MLIPs trained on 3d dopants predict adsorption energies for **lanthanide-doped AlN** (e.g., Ce, Gd) without additional DFT data?
   - How does **spin-orbit coupling** (critical for Pt, Au) affect MLIP predictions for noble metals?

2. **Reaction Pathway Gaps**:
   - Do MLIPs capture **Li₂O₂* → Li₃O₂*** kinetics accurately, or is explicit transition-state sampling required?
   - Can **grand canonical Monte Carlo** (GCMC) simulations validate MLIP-predicted LiO₂* coverage at high overpotentials?

3. **Architecture Limits**:
   - Does **MACE-MH-1’s OC20 head** introduce bias for bulk systems, degrading performance for 2D materials like AlN?
   - Are **equivariant transformers** (e.g., Equiformer) more sample-efficient than MACE for small DFT datasets?

4. **Experimental Validation**:
   - What is the **minimum DFT dataset size** needed to finetune MLIPs for <0.1 eV MAE on Li-air cathodes?
   - Can **operando XAS** data (e.g., from [15]) be used to refine MLIP descriptors for reaction intermediates?

5. **Scalability**:
   - Can MLIPs predict **long-term degradation** (e.g., AlN amorphization) in Li-air batteries, or are hybrid ML-DFT approaches needed?
   - How does **doping concentration** (e.g., 1% vs. 10% Pt) affect MLIP accuracy for adsorption energies?

---

## Related Pages
- [[machine-learning-interatomic-potentials-for-electrochemistry]]
- [[volcano-plots-in-catalysis-theory-and-ml-surrogates]]
- [[doping-strategies-for-2d-materials-aln-bilayer-case-study]]
- [[oc20-dataset-and-foundation-models-for-materials-science]]
- [[adsorption-energy-prediction-with-equivariant-gnns]]
- [[li-air-battery-reaction-mechanisms-and-intermediates]]
- [[transfer-learning-for-noble-metal-catalysts]]
- [[gaussian-process-surrogates-for-electrochemical-kinetics]]
- [[dft-benchmarks-for-li-air-battery-cathodes]]
- [[experimental-validation-of-ml-predicted-catalytic-activity]]
```

### Key Design Choices:
1. **Confidence Score (0.85)**: Reflects strong alignment with DFT benchmarks ([1], [4], [14]) but acknowledges open questions about noble metal extrapolation.
2. **LaTeX Preservation**: Critical for adsorption energy equations and descriptor correlations.
3. **Open Questions**: Framed as testable hypotheses to guide future work (e.g., lanthanide doping, GCMC validation).
4. **Related Pages**: Links to broader KB topics (e.g., MLIPs, volcano plots) for cross-referencing.