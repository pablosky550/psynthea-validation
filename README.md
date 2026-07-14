# 🧬 Psynthea Validation Framework

> **A scientific validation framework for evaluating the fidelity of Psynthea against Synthea through reproducible, statistical and clinical comparisons.**

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pytest](https://img.shields.io/badge/Tested_with-Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-Data_Analysis-150458?style=for-the-badge&logo=pandas)
![SciPy](https://img.shields.io/badge/SciPy-Statistics-8CAAE6?style=for-the-badge&logo=scipy)
![Matplotlib](https://img.shields.io/badge/Matplotlib-Visualization-11557C?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)

---

## Overview

The **Psynthea Validation Framework** is a scientific validation toolkit designed to evaluate the **clinical, statistical and structural fidelity** of **Psynthea** with respect to the original **Synthea** simulator.

Rather than focusing on execution speed or software correctness alone, the framework measures whether both simulation engines generate **equivalent synthetic populations**, preserving demographic distributions, clinical outcomes and epidemiological behaviour.

The project has been developed as part of the **IRYCIS (Instituto Ramón y Cajal de Investigación Sanitaria)** research activities, following scientific software engineering principles with emphasis on:

- reproducibility
- modularity
- statistical rigor
- automated reporting
- extensibility

The framework produces quantitative evidence supporting validation through hypothesis testing, distribution comparisons, cohort analysis and publication-ready reports.

---

# ✨ Features

- Statistical comparison between Psynthea and Synthea outputs
- Demographic validation
- Clinical validation
- Cohort-level comparison
- Observation quality assessment
- Automated HTML reports
- Publication-quality visualizations
- Configurable validation pipeline
- Modular metric architecture
- Reproducible experiments
- Extensive unit testing
- Fully documented codebase

---

# 🏗 Architecture

The validation workflow follows a layered architecture.

```text
                 Synthea
                     │
                     │
          Generated CSV datasets
                     │
                     ▼
          ┌────────────────────┐
          │ Data Loading Layer │
          └────────────────────┘
                     │
                     ▼
          ┌────────────────────┐
          │ Validation Metrics │
          └────────────────────┘
                     │
      ┌──────────────┼───────────────┐
      ▼              ▼               ▼
 Demographic     Clinical       Statistical
 Validation      Validation      Comparison
      │              │               │
      └──────────────┼───────────────┘
                     ▼
          Report & Visualization
                     │
                     ▼
          HTML + Figures + Metrics
```

Every layer follows the **Single Responsibility Principle**, allowing metrics and reports to evolve independently.

---

# ⚙ Technology Stack

| Component | Technology |
|------------|------------|
| Language | Python 3.12 |
| Statistics | SciPy |
| Data Processing | Pandas |
| Numerical Computing | NumPy |
| Visualization | Matplotlib |
| Testing | Pytest |
| Reporting | HTML |
| Configuration | Dataclasses |
| CLI | argparse |

---

# 🔬 Validation Methodology

The framework validates Psynthea across multiple complementary dimensions.

## 1. Demographic Validation

Compares population characteristics including:

- Age distributions
- Gender balance
- Population size
- Birth year distributions

---

## 2. Clinical Validation

Evaluates generated clinical events:

- Conditions
- Medications
- Procedures
- Observations

using frequency and prevalence comparisons.

---

## 3. Cohort Validation

Builds equivalent patient cohorts and compares:

- cohort sizes
- prevalence
- demographic composition
- outcome distributions

---

## 4. Statistical Validation

Uses formal hypothesis testing to determine whether Psynthea reproduces Synthea outputs.

Implemented statistical methods include:

- Kolmogorov–Smirnov Test
- Chi-Square Test
- Jensen-Shannon Distance
- Wasserstein Distance
- Relative Error
- Absolute Error
- Distribution Similarity Metrics

---

## 5. Data Quality Validation

Evaluates:

- missing values
- duplicate records
- invalid timestamps
- inconsistent identifiers
- structural integrity

---

# 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/<your-org>/psynthea-validation.git
cd psynthea-validation
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# ▶ Usage

Basic validation:

```bash
python -m validation.cli \
    --synthea data/synthea \
    --psynthea data/psynthea \
    --output reports
```

Generate report only:

```bash
python -m validation.cli \
    --report-only
```

Generate plots:

```bash
python -m validation.cli \
    --plots
```

Full validation:

```bash
python -m validation.cli \
    --all
```

---

# 📊 Generated Outputs

The framework automatically produces:

```
reports/

├── validation_report.html
├── summary.json
├── metrics.csv
└── figures/

plots/

├── age_distribution.png
├── gender_distribution.png
├── prevalence_comparison.png
├── observations.png
└── ...
```

These outputs are designed for both scientific inspection and publication.

---

# 🧪 Testing

Run the complete test suite:

```bash
pytest
```

Run a specific module:

```bash
pytest tests/test_plots.py
```

Run with coverage:

```bash
pytest --cov=validation
```

The project includes comprehensive unit tests covering:

- statistical metrics
- plotting
- reporting
- configuration
- CLI
- utility functions

---

# 📈 Validation Pipeline

The framework follows three sequential stages.

### Phase 1

Metric computation

- demographics
- clinical entities
- observations
- cohorts
- quality metrics

---

### Phase 2

Statistical validation

- hypothesis testing
- distribution comparison
- similarity metrics

---

### Phase 3

Scientific reporting

- HTML report generation
- visualization
- configurable execution
- command-line interface

---

# 🏛 Design Principles

The framework has been designed following modern software engineering principles.

- Single Responsibility Principle (SRP)
- Open/Closed Principle
- Modular architecture
- Dependency inversion
- Configuration-driven execution
- Reproducible research
- Deterministic statistical analysis

---

# 🤝 Contributing

Contributions are welcome.

Before submitting a pull request:

- follow the existing coding style
- include unit tests
- ensure all tests pass
- document public APIs where appropriate

---

# 📄 License

This project is distributed under the MIT License.

---

# 🙏 Acknowledgements

This work has been developed within the **IRYCIS (Instituto Ramón yCajal de Investigación Sanitaria)** as part of the validation of **Psynthea**, a Python-native implementation compatible with the **Synthea Generic Module Framework**.

Special thanks to:

- the Psynthea development team
- the Synthea project
- the IRYCIS research community

---

## Citation

If you use this framework in academic work, please cite the corresponding publication or repository.
