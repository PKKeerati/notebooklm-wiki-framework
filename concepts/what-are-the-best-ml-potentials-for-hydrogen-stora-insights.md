---
title: 'Insights: What are the best ML potentials for hydrogen storage? Literature
  on phase transition Mg + H2 -> MgH2 via pressure-composition isotherm (PCI). Interest
  in grand canonical Monte Carlo (muNPT) and NPT molecular dynamics. MLIP descriptors
  for studying phase transitions.'
type: crystallized_insight
last_updated: '2026-05-19'
generated_by: Mod
---

# Insights: What are the best ML potentials for hydrogen storage? Literature on phase transition Mg + H2 -> MgH2 via pressure-composition isotherm (PCI). Interest in grand canonical Monte Carlo (muNPT) and NPT molecular dynamics. MLIP descriptors for studying phase transitions.

## Session 2026-05-19 (run: 2026-05-19)

## Mod Handoff

**Insights extracted:** 15
**KB pages to update:** MgH2_phase_transition, MLIP_benchmarking, PCI_curves, hydrogen_storage_dopants, grand_canonical_Monte_Carlo
**KB pages to create:** MgH_MLIP_descriptors, muNPT_vs_NPT_comparison, surface_bulk_phase_transitions, dopant_aware_MLIPs

---

### Atomic Insights

#### Plateau pressure ranges for Mg-H₂ absorption/desorption
- **Fact:** Experimental pressure-composition isotherm (PCI) curves for $Mg + H_2 \rightarrow MgH_2$ exhibit plateau pressures of **0.1–1 bar for absorption** and **0.01–0.1 bar for desorption** at 300–400°C.
- **Detail:** These pressures define the thermodynamic window for hydrogen storage and release. Absorption/desorption hysteresis ($P_{abs}/P_{des} \approx 10$–100) arises from nucleation barriers and lattice strain, with particle size and surface oxides exacerbating the effect. Validated by PCI measurements in [[Q1]].
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #PCI_curves #thermodynamics #experimental_validation

---

#### DFT overestimates Mg-H₂ plateau pressures
- **Fact:** DFT functionals (PBE, PBE-D3, rev-vdW-DF2) predict plateau pressures **2–3× higher** than experimental values for $MgH_2$ formation.
- **Detail:** The overestimation stems from DFT’s inability to fully capture van der Waals interactions and anharmonic lattice vibrations, which stabilize the hydride phase. This discrepancy is consistent across multiple studies [[Q2]][[Q5]] and limits DFT’s utility as a sole reference for MLIP training.
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #DFT_limitations #PCI_curves #thermodynamics

---

#### Hysteresis in Mg-H₂ phase transitions
- **Fact:** Experimental PCI curves show **hysteresis ratios ($P_{abs}/P_{des}$) of 10–100**, with DFT predicting negligible hysteresis.
- **Detail:** Hysteresis originates from kinetic barriers (e.g., nucleation, lattice expansion) and is amplified by particle size reduction (<50 nm) and surface oxides. DFT’s failure to reproduce hysteresis highlights its limitations for non-equilibrium phase transitions [[Q1]][[Q5]].
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #PCI_curves #kinetics #DFT_limitations

---

#### Dopants reduce Mg-H₂ desorption enthalpy
- **Fact:** Dopants (e.g., Ni, Ga) **lower the desorption enthalpy of $MgH_2$ by 20–30 kJ/mol $H_2$** (from ~74–80 kJ/mol to ~50–60 kJ/mol).
- **Detail:** Ni catalyzes $H_2$ dissociation via d-band center tuning, while Ga induces lattice strain, reducing the energy barrier for hydrogen release. This effect is quantified in PCI curves and TPD (temperature-programmed desorption) experiments [[Q4]].
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #dopants #thermodynamics #kinetics

---

#### SOAP-GAP and ACE MLIPs for Mg-H systems
- **Fact:** Smooth Overlap of Atomic Positions (SOAP)-GAP and Atomic Cluster Expansion (ACE) MLIPs **outperform DFT in reproducing Mg-H₂ energetics** by capturing multi-body interactions.
- **Detail:** SOAP-GAP uses spherical harmonics to encode local environments, while ACE leverages polynomial expansions. Both improve upon DFT’s overestimation of plateau pressures but require large training datasets. Benchmarked in [[Q3]] for Mg-H systems.
- **Status:** Ongoing
- **Est. completion:** 2025
- **Confidence:** Medium
- **Topic tags:** #MLIPs #descriptors #PCI_curves

---

#### Equivariant transformers for symmetry preservation
- **Fact:** Equivariant transformer MLIPs **preserve rotational and permutational symmetries** in Mg-H systems, improving accuracy for phase transition predictions.
- **Detail:** These models use irreducible representations to encode atomic environments, reducing the need for data augmentation. Early results show promise for PCI curve reproduction, but computational cost remains high [[Q3]].
- **Status:** Ongoing
- **Est. completion:** 2026
- **Confidence:** Medium
- **Topic tags:** #MLIPs #symmetry #PCI_curves

---

#### Lack of PCI-relevant ab initio datasets
- **Fact:** No curated ab initio datasets exist for **Mg-H systems at PCI-relevant conditions (300–400°C, 0.01–1 bar)**.
- **Detail:** Current datasets focus on 0 K or high-pressure regimes, missing critical temperature/pressure windows for hydrogen storage. This gap limits MLIP training for PCI curve prediction [[Q5]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #training_data #MLIPs #PCI_curves

---

#### μNPT vs. NPT for phase coexistence
- **Fact:** Grand canonical Monte Carlo (μNPT) **explicitly models hydrogen chemical potential**, unlike NPT MD, which may misrepresent phase coexistence in Mg-H systems.
- **Detail:** μNPT allows for variable hydrogen content, better capturing PCI curves where $H_2$ pressure drives phase transitions. However, no direct comparisons exist for Mg-H systems [[Q6]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** Medium
- **Topic tags:** #muNPT #phase_coexistence #PCI_curves

---

#### Descriptor transferability challenges
- **Fact:** Descriptors (e.g., SOAP, ACSF) **show moderate transferability to Mg-H systems** but struggle with hydrogen’s light mass and quantum effects.
- **Detail:** SOAP’s spherical harmonics and ACSF’s geometric features are less effective for hydrogen due to its high mobility and zero-point energy. This limits μNPT accuracy for Mg-H phase transitions [[Q6]].
- **Status:** Ongoing
- **Est. completion:** 2025
- **Confidence:** Medium
- **Topic tags:** #descriptors #muNPT #quantum_effects

---

#### Dopant-aware MLIPs do not exist
- **Fact:** No MLIPs **explicitly incorporate dopant-specific descriptors** (e.g., d-band centers, vacancy formation energies) for Mg-H systems.
- **Detail:** Current MLIPs treat dopants as generic atoms, ignoring their catalytic effects on $H_2$ dissociation and lattice strain. This gap explains their poor performance for doped Mg-H PCI curves [[Q4]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #dopants #MLIPs #descriptors

---

#### Surface vs. bulk phase transition kinetics
- **Fact:** Surface-mediated Mg-H phase transitions **exhibit faster kinetics** than bulk transitions, with PCI curves shifting for nanoscale Mg particles.
- **Detail:** Surface oxides and reduced coordination numbers lower nucleation barriers, but no MLIPs differentiate surface and bulk effects. Experimental PCI curves for <50 nm particles show distinct plateaus [[Q7]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #surface_effects #nanoscale #PCI_curves

---

#### Non-equilibrium pathways are unmodeled
- **Fact:** No MLIPs or descriptors **address non-equilibrium Mg-H phase transitions** (e.g., ball-milling, high-pressure cycling).
- **Detail:** Real-world hydrogen storage involves dynamic conditions, but current models assume equilibrium. This gap limits their applicability to industrial processes [[Q7]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #non_equilibrium #kinetics #MLIPs

---

#### DFT fails to capture hysteresis mechanisms
- **Fact:** DFT **underestimates hysteresis in Mg-H₂ phase transitions** due to its inability to model nucleation barriers and lattice strain.
- **Detail:** Hysteresis arises from kinetic limitations (e.g., hydride nucleation, lattice expansion), which DFT’s harmonic approximations cannot capture. This is evident in PCI curve comparisons [[Q5]].
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #DFT_limitations #hysteresis #kinetics

---

#### Training data gaps for PCI conditions
- **Fact:** Ab initio datasets for MLIP training **lack coverage of PCI-relevant temperatures (300–400°C) and pressures (0.01–1 bar)**.
- **Detail:** Existing datasets focus on 0 K or high-pressure regimes, missing the thermodynamic window critical for hydrogen storage. This limits MLIP accuracy for PCI curve prediction [[Q5]].
- **Status:** Not done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #training_data #MLIPs #PCI_curves

---

#### Dopant electronegativity alters phase transitions
- **Fact:** Dopant electronegativity **correlates with Mg-H₂ desorption enthalpy**, with more electronegative dopants (e.g., Ni) reducing barriers.
- **Detail:** Ni’s high electronegativity (1.91) weakens Mg-H bonds, while Ga’s lower electronegativity (1.81) induces lattice strain. This effect is quantified in TPD experiments [[Q4]].
- **Status:** Done
- **Est. completion:** N/A
- **Confidence:** High
- **Topic tags:** #dopants #thermodynamics #electronegativity

---

### Conflicts with existing KB
- None. All insights align with or expand upon existing KB entries without contradictions.

---

### Top 5 Tactical Choices

| # | Direction | Status | Effort | Why now |
|---|-----------|--------|--------|---------|
| 1 | **Benchmark MLIPs for PCI curve accuracy** | Ongoing | High | Directly addresses the core gap: no prior MLIP benchmarks for Mg-H PCI curves. Validates architectures (SOAP-GAP, ACE, equivariant transformers) against experimental plateaus, hysteresis, and enthalpies. Critical for identifying the best MLIP for hydrogen storage modeling. |
| 2 | **Curate ab initio datasets for PCI-relevant conditions** | Not done | Medium | Enables MLIP training at 300–400°C and 0.01–1 bar, where current datasets are lacking. Foundational for all subsequent MLIP development (e.g., μNPT, dopant-aware models). High-impact, tractable effort. |
| 3 | **Develop dopant-aware MLIP descriptors** | Not done | High | Captures experimentally validated dopant effects (e.g., Ni, Ga) missing in current MLIPs. Incorporates d-band centers, electronegativity, and vacancy formation energies to model catalytic mechanisms. Essential for industrial applications. |
| 4 | **Compare μNPT vs. NPT for phase coexistence** | Not done | Medium | Tests whether μNPT’s explicit hydrogen chemical potential improves PCI curve accuracy over NPT MD. Low-hanging fruit with potential to redefine MLIP validation protocols for hydrogen storage. |
| 5 | **Model surface vs. bulk phase transitions** | Not done | High | Addresses the blind spot of surface effects, which dominate in nanoscale Mg particles. Validates MLIPs against experimental PCI curves for <50 nm particles. Critical for bridging lab-scale and industrial hydrogen storage. |