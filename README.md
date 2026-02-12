# PAY APP SETUP — Template Metadata Enrichment Tool

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary. Designed to support data migration by converting bare two-row templates into fully annotated Import Templates.

## What It Does

Takes a set of **Template files** (CSV/Excel) — each containing a property-name header row and a description row — and an **XML metadata dictionary**, then:

1. Country is set to **GBR** (additional countries can be added to the picker later)
2. Auto-detects the best matching SAP EntityType for each template
3. Looks up each column's metadata (label, data type, mandatory flag, max length)
4. Filters country-specific descriptions (e.g. `"GBR: County | USA: State/Province"` becomes `"County"` when GBR is selected)
5. Outputs enriched Import Template files with 5 metadata rows

### Output Format

Each enriched file keeps the original column headers across the top and adds:

| Row | Content | Source |
|-----|---------|--------|
| **Column Name** | Human-readable label | `sap:label` from XML |
| **Description** | What the field contains / valid values | Original template row 2 |
| **Type** | `string`, `float`, `date`, `integer`, `boolean`, `picklist` | `Type` attribute mapped from `Edm.*` |
| **Mandatory** | `true` / `false` | `sap:required` from XML |
| **Max Length** | Character limit | `MaxLength` attribute |

### Type Mapping

| XML Type | Friendly Name |
|----------|--------------|
| `Edm.String` | string |
| `Edm.Decimal`, `Edm.Double`, `Edm.Single` | float |
| `Edm.DateTime`, `Edm.DateTimeOffset` | date |
| `Edm.Int64`, `Edm.Int32`, `Edm.Int16`, `Edm.Byte` | integer |
| `Edm.Boolean` | boolean |
| `SFOData.*` (navigation/complex types) | picklist |

## Prerequisites

- Python 3.11+
- Required packages:

```
pip install streamlit pandas openpyxl xlsxwriter
```

## Running the App

```bash
cd PAY_APP_SETUP
py -m streamlit run pay_app_setup.py
```

The app opens at [http://localhost:8501](http://localhost:8501).

## Project Structure

```
PAY_APP_SETUP/
  pay_app_setup.py                  # Main Streamlit application
  README.md                         # This file
  bootstap.md                       # Original requirements
  Reference Files/
    Template/
      veritasp01D-Metadata.xml      # XML metadata dictionary (9.4 MB, 886 EntityTypes)
      BasicUserInfoImportTemplate_veritasp01D.csv
      CompInfoImportTemplate_veritasp01D.csv
      JobInfoImportTemplate_veritasp01D.csv
      PersonInfoImportTemplate_veritasp01D.csv
      EmploymentInfoImportTemplate_veritasp01D.csv
      AddressImportTemplate_veritasp01D.csv
      EmailInfoImportTemplate_veritasp01D.csv
      PhoneInfoImportTemplate_veritasp01D.csv
      EmergencyContactImportTemplate_veritasp01D.csv
      NationalIdCardImportTemplate_veritasp01D.csv
      PayComponentRecurringImportTemplate_veritasp01D.csv
      PayComponentNonRecurringImportTemplate_veritasp01D.csv
      Bank.csv                        # Not required for import — reference only
      Payment Information .csv
    Source Payment data/             # Reference payroll data (not used by script)
    testing notes/                   # Historical testing notes
  skills/                            # Bootstrap optimizer skill files
```

## How the Matching Works

The XML contains **886 EntityTypes** with **14,000+ property definitions**. Many property names (e.g. `userId`, `startDate`) appear in multiple EntityTypes. The script uses a two-tier matching strategy:

1. **EntityType detection** — For each template, it normalises all column names and scores every EntityType by how many columns match. The EntityType with the highest match count wins. Permission/FieldControl mirror entities are penalised to avoid false matches. EntityTypes ending with the selected country code (currently GBR, e.g. `PaymentInformationDetailV3GBR`) are boosted, while those ending with a different country code are penalised.

2. **Property lookup** — Each column is first looked up in the matched EntityType's properties. If not found there, it falls back to a global search across all EntityTypes.

3. **Description filtering** — Template descriptions that contain pipe-delimited country variants (e.g. `"GBR: County | JPN: State | USA: State/Province"`) are filtered down to the segment matching the selected country. Non-country descriptions are left unchanged.

### Property Name Normalisation

Template columns come in varied formats. The normaliser handles all of them:

| Template Format | Example | Normalised Key |
|----------------|---------|---------------|
| UPPERCASE | `USERID` | `userid` |
| kebab-case | `start-date` | `startdate` |
| Dotted path | `personInfo.person-id-external` | `personidexternal` |
| Mixed | `custom_string1` | `customstring1` |

### Verified Template-to-EntityType Mapping

| Template File | Matched EntityType | Columns Matched |
|--------------|-------------------|----------------|
| BasicUserInfoImportTemplate | User | 19/19 |
| CompInfoImportTemplate | EmpCompensation | 6/6 |
| JobInfoImportTemplate | EmpJob | 15/15 |
| PersonInfoImportTemplate | PerPerson | 4/4 |
| EmploymentInfoImportTemplate | EmpEmployment* | 8/8 |
| AddressImportTemplate | PerAddressDEFLT | 7/7 |
| EmailInfoImportTemplate | PerEmail | 5/5 |
| PhoneInfoImportTemplate | PerPhone | 5/5 |
| EmergencyContactImportTemplate | PerEmergencyContacts | 9/9 |
| NationalIdCardImportTemplate | PerNationalId | 6/6 |
| PayComponentRecurringImportTemplate | EmpPayCompRecurring | 8/8 |
| PayComponentNonRecurringImportTemplate | EmpPayCompNonRecurring | 6/6 |
| Bank | Bank | 10/11 |
| Payment Information | PaymentInformationV3 | 3/4 |

*Unmatched columns are typically special fields like `[OPERATOR]` which is an instruction marker, not a data property.

---

## Testing Walkthrough

Use the reference files in `Reference Files/Template/` to verify end-to-end behaviour.

### Test 1 — Single File, Happy Path

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
8. **Step 7** — Select CSV, click download, open the file and verify it has 6 rows (header + 5 metadata rows)

### Test 2 — Country Description Filtering (GBR)

**Goal**: Confirm the GBR country setting filters pipe-delimited descriptions.

1. **Sidebar** — Confirm country is **GBR**
2. Upload `Reference Files/Template/AddressImportTemplate_veritasp01D.csv`
3. Click **Generate Import Templates**
4. In the results, check the `state` column:
   - The original template description is `"GBR: County | JPN: State | PER: State/Province | USA: State/Province"`
   - With GBR selected, the **Description** row should show just: **County**
5. Repeat with `EmergencyContactImportTemplate_veritasp01D.csv` — the `homeAddress.state` description should filter the same way

### Test 3 — Multiple Files, Batch Processing

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

### Test 4 — Interactive File Removal

**Goal**: Confirm deselecting files excludes them from processing.

1. Upload 3 template files (e.g. `Bank.csv`, `PersonInfoImportTemplate_veritasp01D.csv`, `CompInfoImportTemplate_veritasp01D.csv`)
2. In **Step 4**, deselect `Bank.csv` from the multiselect
3. Click **Generate Import Templates**
4. Verify only 2 result tables appear (no Bank output)

### Test 5 — Invalid File Handling

**Goal**: Confirm files with fewer than 2 rows are flagged.

1. Create a test file `single_row.csv` with only one row of headers:
   ```
   col-a,col-b,col-c
   ```
2. Upload it alongside a valid template
3. Confirm a warning appears: *"The following files do not contain exactly 2 rows and were flagged: single_row.csv"*
4. Confirm the valid template still processes normally

### Test 6 — Unmatched Column Warning

**Goal**: Confirm columns with no XML match are reported.

1. Upload `Bank.csv`
2. Process it and check the results
3. Verify a warning appears noting that `[OPERATOR]` had no XML match (this is expected — it's a special instruction column, not a property)

### Test 7 — Excel Template Input

**Goal**: Confirm `.xlsx` input files work.

1. Open any reference CSV template in Excel and save it as `.xlsx`
2. Upload the `.xlsx` file to the app
3. Process it and confirm the results match the CSV version

### Test 8 — Download Format Comparison

**Goal**: Verify both export formats produce valid files.

1. Process any template
2. Download as **CSV** — open in a text editor and confirm:
   - UTF-8 BOM is present (for Excel compatibility)
   - 6 lines: header row + 5 metadata rows
3. Download as **XLSX** — open in Excel and confirm:
   - Sheet name is "Import Template"
   - Same 6-row structure
   - No formatting artefacts
