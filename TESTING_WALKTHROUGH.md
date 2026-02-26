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

---

### Step-by-Step Guide

**Sidebar**

1. **Select Country** — The country picker is pre-set to **GBR**. This controls EntityType matching — templates are matched to EntityTypes ending with the selected country code (e.g. `EmpJobGBR`) in preference to generic or other-country variants.

2. **Upload XML Metadata** — Click "Browse files" and select your OData XML metadata dictionary (e.g. `veritasp01D-Metadata.xml`). The sidebar confirms how many property definitions and entity types were found. Nothing else in the app renders until this file is uploaded.

3. **Upload Picklist Reference Files** *(optional)* — Upload one or more picklist reference files:
   - **Excel workbooks** (`.xlsx`/`.xls`): sheets ending in `(Data)` are parsed; columns are auto-mapped to picklist tables where possible.
   - **CSV files** (`.csv`): simple 2-column format (Code, Label); the filename becomes the picklist name.
   - Multiple files are merged — same-named tables are unioned by code.
   - The sidebar confirms how many picklist tables were loaded and how many columns were auto-mapped.

4. **Load Configuration** *(optional)* — Upload a `.json` configuration file previously saved from the app. The app will restore the country, skip-operation setting, and all picklist Final Values from that session.

**Main Area**

5. **Upload Template Files** (Step 3) — Select one or more CSV or Excel template files. Each template should have at least one row:
   - **Row 1**: Property name headers (Column Names), e.g. `email-address`, `start-date`, `USERID`
   - **Row 2** *(optional)*: Labels or descriptions for each field
   - **Rows 3+** *(optional)*: Data rows, used for picklist value extraction when no reference files are loaded

6. **Select Templates to Process** (Step 4) — All uploaded files appear in a multiselect. Deselect any you do not want to process. The app warns if any selected template is missing a User ID or Person ID External column. If any template has an `operation` column, a checkbox appears to confirm skipping its metadata mapping (checked by default).

7. **Picklist Assignments** (Step 5) — Shown only when picklist reference files were uploaded. Review and adjust assignments in the interactive editor:
   - **Mand.** — indicates the column is mandatory per the XML metadata.
   - **Assigned Picklist** — the auto-matched picklist table (editable via dropdown).
   - **Reference Values** — first 5 labels from the assigned table (read-only preview).
   - **Template Data** — values found in your uploaded data rows (read-only, up to 8 values).
   - **Final Values** — what goes into the output (editable). Pre-populated from the assigned reference table or template data. Edit freely to add, remove, or correct values.
   - An **error** is shown for any mandatory column with no Final Values.
   - A **warning** is shown for any column with only a single value.
   - Use the **Save configuration** expander to download a JSON file capturing the current settings and assignments.

8. **Generate** (Step 6) — Click **Generate Import Templates**. The app matches each template to the best SAP EntityType and looks up metadata for every column.

9. **Review Results** (Step 7) — Each processed template is displayed as a table with 6 rows. A caption beneath each table shows which EntityType was matched. Columns with no XML match are reported in a warning.

10. **Download** (Step 8) — Choose **CSV** or **XLSX** format:
    - Single file: click the individual download button.
    - Multiple files: click **Download all enriched templates (.zip)**.

    Exported files contain the 6 rows as a plain grid — no row-label column, no file header row.

---

## Test Cases

Use the reference files in `Reference Files/Template/` to verify end-to-end behaviour.

## Test 1 — Single File, Happy Path

**Goal**: Confirm a single template enriches correctly.

1. Run the app: `py -m streamlit run pay_app_setup.py`
2. **Sidebar section 1** — Leave country as **GBR** (default)
3. **Sidebar section 2** — Upload `Reference Files/XML Metadata Dictionary/veritasp01D-Metadata.xml`
   - Confirm the sidebar shows: *"Loaded 14,395 property definitions across 886 entity types."*
4. **Step 3** — Upload `Reference Files/Template/EmailInfoImportTemplate_veritasp01D.csv`
5. **Step 4** — Confirm it appears selected in the multiselect
6. **Step 5 (Picklist Assignments)** — skipped (no reference files uploaded); info message appears
7. **Step 6** — Click **Generate Import Templates**
8. **Step 7** — Check the results table (row labels shown on screen, not in download):

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
9. **Step 8** — Select CSV, click download, open the file and verify:
   - 6 rows, no row-label column A, no file header
   - Row 1: `email-address,email-type,isPrimary,...`
   - Row 6 (Picklist Values): empty fields

## Test 2 — Column Label from XML

**Goal**: Confirm the XML sap:label is correctly mapped to the Column Label row (row 2).

1. Upload `Reference Files/Template/AddressImportTemplate_veritasp01D.csv`
2. Click **Generate Import Templates**
3. In the results, verify the `state` column:
   - Row 1 (Column Name): `state`
   - Row 2 (Column Label): the sap:label value from XML (e.g. `State/Province`)

## Test 3 — Multiple Files, Batch Processing

**Goal**: Confirm batch processing and ZIP download.

1. With the XML already loaded, upload all 13 CSV files from `Reference Files/Template/`
2. **Step 4** — All 13 files should appear selected
3. Click **Generate Import Templates**
4. Verify each result table shows a matched EntityType in the caption
5. Select XLSX format, click **Download all enriched templates (.zip)**
6. Extract the ZIP and confirm it contains 13 `_enriched.xlsx` files
7. Open `JobInfoImportTemplate_veritasp01D_enriched.xlsx` and spot-check:
   - `job-code` column: row 1 = "job-code", row 2 = "Job Code", row 3 = "picklist", row 4 = "true", row 5 = "8", row 6 = "" *(no data rows in reference template)*
   - `start-date` column: row 1 = "start-date", row 2 = "Event Date", row 3 = "date", row 4 = "true", row 5 = "10", row 6 = "" *(date type — never a picklist)*

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
2. Process it and check the Step 7 results
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
   - UTF-8 BOM is present (first bytes: `EF BB BF`, or row 1 starts correctly in Excel)
   - 6 rows, no row-label column, no file header
   - Row 1 contains the property names (e.g. `email-address,email-type,...`)
3. Download as **XLSX** — open in Excel and confirm:
   - Sheet name is "Import Template"
   - Same 6-row structure, row 1 = property names, no row-label column
   - No formatting artefacts

## Test 9 — Picklist Reference File (Excel Workbook)

**Goal**: Confirm picklist values are loaded from a `(Data)` sheet workbook and auto-mapped.

1. Load the XML metadata
2. **Sidebar section 3** — Upload `Reference Files/picklists/VP_PeelHunt_SF_EC_EmpDataWBProd.xlsx`
   - Confirm the sidebar success message shows at least 1 picklist table loaded and at least 1 auto-mapped column
3. Upload `Reference Files/Template/JobInfoImportTemplate_veritasp01D.csv`
4. **Step 5 (Picklist Assignments)** — Verify the editor appears and that columns such as `gender` or `country` have an **Assigned Picklist** value pre-set and **Reference Values** showing the first few labels
5. Check **Final Values** for those columns are pre-populated with the full label list from the reference table
6. Click **Generate Import Templates**
7. In **Step 7**, verify row 6 (Picklist Values) for an auto-mapped column contains the reference labels

## Test 10 — Picklist Reference File (CSV)

**Goal**: Confirm a 2-column CSV is accepted as a picklist reference file.

1. Create a file `Gender.csv` with content:
   ```
   Code,Label
   F,Female
   M,Male
   N,Not Specified
   ```
2. Load the XML and at least one template
3. **Sidebar section 3** — Upload `Gender.csv`
   - Confirm the sidebar shows *"Loaded 1 picklist table(s) from 1 file(s)"*
4. **Step 5** — If `gender` is a candidate column, verify it can be assigned to the "Gender" table (named after the filename) in the **Assigned Picklist** dropdown
5. Set **Final Values** for `gender` to the label list and generate templates
6. Verify row 6 for the gender column reflects the values

## Test 11 — Picklist Assignments Manual Override

**Goal**: Confirm Final Values can be edited manually and take priority in the output.

1. Load the XML, a picklist reference file, and a template
2. **Step 5** — In the **Final Values** cell for any picklist column, clear the auto-populated values and type a custom list, e.g. `Alpha, Beta, Gamma`
3. Click **Generate Import Templates**
4. Verify row 6 (Picklist Values) for that column shows `Alpha, Beta, Gamma`

## Test 12 — Mandatory Picklist Validation

**Goal**: Confirm the mandatory-empty error is shown.

1. Load the XML, a picklist reference file, and a template containing a mandatory picklist column
2. **Step 5** — Clear the **Final Values** for a column where **Mand.** is checked
3. Confirm a red error message appears naming the column with no values
4. Fill in a value and confirm the error disappears

## Test 13 — Configuration Save and Load

**Goal**: Confirm picklist assignments and settings round-trip through a saved JSON.

1. Complete Steps 1–5 with at least one picklist reference file and edit some Final Values
2. Open the **Save configuration** expander and click **Download configuration (.json)**
3. Note the country, skip_operation state, and Final Values for two columns
4. Reload the page (or open a new session)
5. Upload the XML and at least one template
6. **Sidebar section 4** — Upload the downloaded JSON file
   - Confirm a sidebar info message appears showing the saved timestamp and number of restored assignments
7. Check **Step 5** — the Picklist Assignments editor should show the restored Final Values
8. Confirm the country selectbox and skip_operation checkbox match the saved values
