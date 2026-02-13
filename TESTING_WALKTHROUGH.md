# Testing Walkthrough

## How to Use the App

### Option A — Docker (Recommended)

```bash
cd PAY_APP_SETUP
docker build -t pay-app-setup .
docker run -p 8501:8501 pay-app-setup
```

### Option B — Local Python

- Python 3.11+
- Install dependencies:
  ```bash
  cd PAY_APP_SETUP
  pip install .
  ```
- Start the app:
  ```bash
  py -m streamlit run pay_app_setup.py
  ```

### Access

The app opens in your browser at [http://localhost:8501](http://localhost:8501).

### Step-by-Step Guide

1. **Select Country** (Sidebar) — The country picker is pre-set to **GBR**. This controls how country-specific descriptions are filtered in the output.

2. **Upload XML Metadata** (Sidebar) — Click "Browse files" and select your OData XML metadata dictionary (e.g. `veritasp01D-Metadata.xml`). Once loaded, the sidebar confirms how many property definitions and entity types were found.

3. **Upload Templates** (Main area, Step 3) — Click "Browse files" and select one or more CSV or Excel template files. Each template should have exactly 2 rows:
   - **Row 1**: Property name headers (e.g. `email-address`, `start-date`, `USERID`)
   - **Row 2**: Freeform descriptions of each field

   Files with fewer or more than 2 rows will be flagged with a warning.

4. **Select Templates to Process** (Step 4) — All uploaded files appear in a multiselect. Deselect any you don't want to include.

5. **Generate** (Step 5) — Click **Generate Import Templates**. The app will:
   - Match each template to the best SAP EntityType from the XML
   - Look up metadata (label, type, mandatory flag, max length) for every column
   - Filter country-specific descriptions to the selected country

6. **Review Results** (Step 6) — Each processed template is displayed as a table with 5 metadata rows:
   - **Column Name** — Human-readable label from the XML
   - **Description** — Original description from the template (country-filtered if applicable)
   - **Type** — `string`, `float`, `date`, `integer`, `boolean`, or `picklist`
   - **Mandatory** — `true` or `false`
   - **Max Length** — Character limit

   A caption beneath each table shows which EntityType was matched.

7. **Download** (Step 7) — Choose **CSV** or **XLSX** format:
   - Single file: click the individual download button
   - Multiple files: click **Download all enriched templates (.zip)**

   Exported files contain the 5 metadata rows without the property name header row.

---

## Test Cases

Use the reference files in `Reference Files/Template/` to verify end-to-end behaviour.

## Test 1 — Single File, Happy Path

**Goal**: Confirm a single template enriches correctly.

1. Run the app: `py -m streamlit run pay_app_setup.py`
2. **Sidebar** — Leave country as **GBR** (default)
3. **Sidebar** — Upload `Reference Files/Template/veritasp01D-Metadata.xml`
   - Confirm the sidebar shows: *"Loaded 14,395 property definitions across 886 entity types."*
4. **Step 3** — Upload `Reference Files/Template/EmailInfoImportTemplate_veritasp01D.csv`
5. **Step 4** — Confirm it appears selected in the multiselect
6. **Step 5** — Click **Generate Import Templates**
7. **Step 6** — Check the results table:

   | | email-address | email-type | isPrimary | personInfo.person-id-external | operation |
   |---|---|---|---|---|---|
   | **Column Name** | Email Address | Email Type | Is Primary | Person ID External | Operation |
   | **Description** | Email Address | Email Type | Is Primary | Person ID External | Operation |
   | **Type** | string | string | string | string | string |
   | **Mandatory** | true | true | false | true | false |
   | **Max Length** | 100 | 38 | | 100 | |

   - Confirm the caption reads *"Best matching EntityType: PerEmail"*
8. **Step 7** — Select CSV, click download, open the file and verify it has 5 rows (5 metadata rows, no header)

## Test 2 — Country Description Filtering (GBR)

**Goal**: Confirm the GBR country setting filters pipe-delimited descriptions.

1. **Sidebar** — Confirm country is **GBR**
2. Upload `Reference Files/Template/AddressImportTemplate_veritasp01D.csv`
3. Click **Generate Import Templates**
4. In the results, check the `state` column:
   - The original template description is `"GBR: County | JPN: State | PER: State/Province | USA: State/Province"`
   - With GBR selected, the **Description** row should show just: **County**
5. Repeat with `EmergencyContactImportTemplate_veritasp01D.csv` — the `homeAddress.state` description should filter the same way

## Test 3 — Multiple Files, Batch Processing

**Goal**: Confirm batch processing and ZIP download.

1. With the XML already loaded, upload all 14 CSV files from `Reference Files/Template/` (excluding the XML)
2. **Step 4** — All 14 files should appear selected
3. Click **Generate Import Templates**
4. Verify each result table shows a matched EntityType in the caption
5. Select XLSX format, click **Download all enriched templates (.zip)**
6. Extract the ZIP and confirm it contains 14 `_enriched.xlsx` files
7. Open `JobInfoImportTemplate_veritasp01D_enriched.xlsx` and spot-check:
   - `job-code` column should show: Column Name = "Job Code", Type = "string", Mandatory = "true", Max Length = "8"
   - `start-date` column should show: Column Name = "Event Date", Type = "date", Mandatory = "true"

## Test 4 — Interactive File Removal

**Goal**: Confirm deselecting files excludes them from processing.

1. Upload 3 template files (e.g. `Bank.csv`, `PersonInfoImportTemplate_veritasp01D.csv`, `CompInfoImportTemplate_veritasp01D.csv`)
2. In **Step 4**, deselect `Bank.csv` from the multiselect
3. Click **Generate Import Templates**
4. Verify only 2 result tables appear (no Bank output)

## Test 5 — Invalid File Handling

**Goal**: Confirm files with fewer than 2 rows are flagged.

1. Create a test file `single_row.csv` with only one row of headers:
   ```
   col-a,col-b,col-c
   ```
2. Upload it alongside a valid template
3. Confirm a warning appears: *"The following files do not contain exactly 2 rows and were flagged: single_row.csv"*
4. Confirm the valid template still processes normally

## Test 6 — Unmatched Column Warning

**Goal**: Confirm columns with no XML match are reported.

1. Upload `Bank.csv`
2. Process it and check the results
3. Verify a warning appears noting that `[OPERATOR]` had no XML match (this is expected — it's a special instruction column, not a property)

## Test 7 — Excel Template Input

**Goal**: Confirm `.xlsx` input files work.

1. Open any reference CSV template in Excel and save it as `.xlsx`
2. Upload the `.xlsx` file to the app
3. Process it and confirm the results match the CSV version

## Test 8 — Download Format Comparison

**Goal**: Verify both export formats produce valid files.

1. Process any template
2. Download as **CSV** — open in a text editor and confirm:
   - UTF-8 BOM is present (for Excel compatibility)
   - 5 rows (5 metadata rows, no header)
3. Download as **XLSX** — open in Excel and confirm:
   - Sheet name is "Import Template"
   - Same 5-row structure
   - No formatting artefacts
