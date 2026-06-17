# IEEMS — Intelligent Employee Expense Management System

A multi-agent pipeline that processes employee expense bundles (receipts, card exports, policy) and outputs per-expense decisions with full audit trails.

**Pipeline order:** `A (Intake) → B (Extraction) → D (Normalization) → C (Policy) → E (Duplicates) → H (Decision)`

---

## Prerequisites

- Python 3.10+
- An OpenAI API key (used by Agent B for receipt extraction)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/valeragashi/IEEMS-Project
cd IEEMS-Project-main
```

### 2. Create a virtual environment

**Windows**
```cmd
python -m venv venv
```

**Linux / macOS**
```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

**Windows**
```cmd
venv\Scripts\activate
```

**Linux / macOS**
```bash
source venv/bin/activate
```

You should see `(venv)` appear in your terminal prompt.

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Set your OpenAI API key

Create a `.env` file in the project root:

**Windows**
```cmd
echo OPENAI_API_KEY=your-key-here > .env
```

**Linux / macOS**
```bash
echo "OPENAI_API_KEY=your-key-here" > .env
```

Or just create the file manually and add:
```
OPENAI_API_KEY=your-key-here
```

---

## Generating Test Data

Before running the pipeline, generate the 9 test bundles:

```bash
cd tools
python generate_test_data.py
cd ..
```

This creates `input_bundles/s01_clean` through `s09_fast_track`.

---

## Running the Pipeline

Run a single bundle:

```bash
python run.py input_bundles/s01_clean
```

Output is written to `runs/<bundle_id>_<run_number>/`.

---

## Running the Test Harness

Run all 9 bundles and check results against expected outcomes:

```bash
python demo.py
```

Run a single bundle through the harness:

```bash
python demo.py --bundle s01_clean
```

Verbose output (shows per-expense detail):

```bash
python demo.py --verbose
```

---

## Deactivating the Virtual Environment

When you're done:

```bash
deactivate
```