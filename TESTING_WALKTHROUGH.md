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

1. **Select Country** (Sidebar) — The country picker is pre-set to **GBR**. This controls EntityType matching — templates are matched to EntityTypes that end with the selected country code (e.g. `EmpJobGBR`) in preference to generic or other-country EntityTypes.

2. **Upload XML Metadata** (Sidebar) — Click "Browse files" and select your OData XML metadata dictionary (e.g. `veritasp01D-Metadata.xml`). Once loaded, the sidebar confirms how many property definitions and entity types were found.

3. **Upload Templates** (Main area, Step 3) — Click "Browse files" and select one or more CSV or Excel template files. Each template should have at least one row:
   - **Row 1**: Property name headers (Column Names), e.g. `email-address`, `start-date`, `USERID`
   - **Row 2** *(optional)*: Labels or descriptions for each field

4. **Select Templates to Process** (Step 4) — All uploaded files appear in a multiselect. Deselect any you don't want to include.

5. **Generate** (Step 5) — Click **Generate Import Templates**. The app will:
   - Match each template to the best SAP EntityType from the XML
   - Look up metadata (label, type, mandatory flag, max length) for every column

6. **Review Results** (Step 6) — Each processed template is displayed as a table with 6 rows:
   - **Column Name** — Property identifier (technical name from the template)
   - **Column Label** — Human-readable label from the XML (`sap:label`)
   - **Type** — `string`, `float`, `date`, `integer`, `boolean`, or `picklist`
   - **Mandatory** — `true` or `false`
   - **Max Length** — Character limit (date/time fields always show `10`)
   - **Picklist Values** — Comma-separated distinct values from template data rows (empty if the template has no data rows)

   A caption beneath each table shows which EntityType was matched.

7. **Download** (Step 7) — Choose **CSV** or **XLSX** format:
   - Single file: click the individual download button
   - Multiple files: click **Download all enriched templates (.zip)**

   Exported files contain the 6 rows with row labels in column A and no file header row.

---

## Test Cases

Use the reference files in `Reference Files/Template/` to verify end-to-end behaviour.

## Test 1 — Single File, Happy Path

**Goal**: Confirm a single template enriches correctly.

1. Run the app: `py -m streamlit run pay_app_setup.py`
2. **Sidebar** — Leave country as **GBR** (default)
3. **Sidebar** — Upload `Reference Files/XML Metadata Dictionary/veritasp01D-Metadata.xml`
   - Confirm the sidebar shows: *"Loaded 14,395 property definitions across 886 entity types."*
4. **Step 3** — Upload `Reference Files/Template/EmailInfoImportTemplate_veritasp01D.csv`
5. **Step 4** — Confirm it appears selected in the multiselect
6. **Step 5** — Click **Generate Import Templates**
7. **Step 6** — Check the results table:

   | | email-address | email-type | isPrimary | personInfo.person-id-external | operation |
   |---|---|---|---|---|---|
   | **Column Name** | email-address | email-type | isPrimary | personInfo.person-id-external | operation |
   | **Column Label** | Email Address | Email Type | Is Primary | Person ID External | Operation |
   | **Type** | string | string | boolean | string | string |
   | **Mandatory** | true | true | true | true | false |
   | **Max Length** | 100 | 38 | | 100 | |
   | **Picklist Values** | | | | | |

   *(Picklist Values are empty because the reference template has no data rows.)*

   - Confirm the caption reads *"Best matching EntityType: PerEmail"*
8. **Step 7** — Select CSV, click download, open the file and verify it has 6 rows (row labels in column A, no file header)

## Test 2 — Column Label from XML

**Goal**: Confirm the XML sap:label is correctly mapped to the Column Label row.

1. Upload `Reference Files/Template/AddressImportTemplate_veritasp01D.csv`
2. Click **Generate Import Templates**
3. In the results, verify the `state` column:
   - **Column Name** row: `state`
   - **Column Label** row: the sap:label value from XML (e.g. `State/Province` or country-specific label)

## Test 3 — Multiple Files, Batch Processing

**Goal**: Confirm batch processing and ZIP download.

1. With the XML already loaded, upload all 13 CSV files from `Reference Files/Template/`
2. **Step 4** — All 13 files should appear selected
3. Click **Generate Import Templates**
4. Verify each result table shows a matched EntityType in the caption
5. Select XLSX format, click **Download all enriched templates (.zip)**
6. Extract the ZIP and confirm it contains 13 `_enriched.xlsx` files
7. Open `JobInfoImportTemplate_veritasp01D_enriched.xlsx` and spot-check:
   - `job-code` column: Column Name = "job-code", Column Label = "Job Code", Type = "picklist", Mandatory = "true", Max Length = "8", Picklist Values = "" *(no data rows in reference template)*
   - `start-date` column: Column Name = "start-date", Column Label = "Event Date", Type = "date", Mandatory = "true", Max Length = "10", Picklist Values = "" *(date type — never a picklist)*

## Test 4 — Interactive File Removal

**Goal**: Confirm deselecting files excludes them from processing.

1. Upload 3 template files (e.g. `PhoneInfoImportTemplate_veritasp01D.csv`, `PersonInfoImportTemplate_veritasp01D.csv`, `CompInfoImportTemplate_veritasp01D.csv`)
2. In **Step 4**, deselect `PhoneInfoImportTemplate_veritasp01D.csv` from the multiselect
3. Click **Generate Import Templates**
4. Verify only 2 result tables appear (PhoneInfo is excluded)

## Test 5 — Invalid File Handling

**Goal**: Confirm unreadable files are flagged and skipped.

1. Create a test file `empty.csv` with no content (0 bytes)
2. Upload it alongside a valid template
3. Confirm a warning appears: *"The following files could not be read and were skipped: empty.csv"*
4. Confirm the valid template still processes normally

## Test 6 — Unmatched Column Warning

**Goal**: Confirm columns with no XML match are reported.

1. Upload `Reference Files/Template/Payment Information .csv`
2. Process it and check the results
3. Verify a warning appears noting that `[OPERATOR]` had no XML match (this is expected — it's a special instruction column, not a data property)

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
   - 6 rows, column A contains: `Column Name`, `Column Label`, `Type`, `Mandatory`, `Max Length`, `Picklist Values`
   - No file header row
3. Download as **XLSX** — open in Excel and confirm:
   - Sheet name is "Import Template"
   - Same 6-row structure with row labels in column A
   - No formatting artefacts
