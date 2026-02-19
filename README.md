# PAY APP SETUP — Template Metadata Enrichment Tool

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary, preparing them for use by PAY-APP.

## What It Does

Takes a set of **Template files** (CSV/Excel) — each with a property-name header row and an optional label row — and an **XML metadata dictionary**, then:

1. Country is set to **GBR** (additional countries can be added to the picker later) — used to prefer country-specific EntityTypes (e.g. `EmpJobGBR`)
2. Auto-detects the best matching SAP EntityType for each template
3. Looks up each column's metadata (label, data type, mandatory flag, max length)
4. Outputs enriched Import Template files with 6 rows (no file header row)

### Output Format

Each enriched file contains 6 rows. Column A holds the row label; remaining columns hold the values for each property.

| Row (Column A) | Content | Source |
|----------------|---------|--------|
| **Column Name** | Property identifier (technical name) | Template row 1 |
| **Column Label** | Human-readable label | `sap:label` from XML (falls back to property name) |
| **Type** | `string`, `float`, `date`, `integer`, `boolean`, `picklist` | `Type` attribute mapped from `Edm.*` |
| **Mandatory** | `true` / `false` | `sap:required` from XML |
| **Max Length** | Character limit (date/time fields capped at 10) | `MaxLength` attribute |
| **Picklist Values** | Comma-separated distinct values (empty when no data rows present) | Template rows 3+ |

> **Note:** The XML metadata dictionary does not contain actual picklist option values. Picklist Values are extracted from any data rows (rows 3+) in the uploaded template. Templates with only header rows will have an empty Picklist Values row.

### Type Mapping

| XML Type | Friendly Name |
|----------|--------------|
| `Edm.String` | string |
| `Edm.Decimal`, `Edm.Double`, `Edm.Single` | float |
| `Edm.DateTime`, `Edm.DateTimeOffset` | date |
| `Edm.Int64`, `Edm.Int32`, `Edm.Int16`, `Edm.Byte` | integer |
| `Edm.Boolean` | boolean |
| `SFOData.*` (navigation/complex types) | picklist |

## Running the App

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

The app opens at [http://localhost:8501](http://localhost:8501).

## Project Structure

```
PAY_APP_SETUP/
  pay_app_setup.py                  # Main Streamlit application
  pyproject.toml                    # Project metadata and dependencies
  Dockerfile                        # Container build definition
  .dockerignore                     # Files excluded from Docker build
  README.md                         # This file
  TESTING_WALKTHROUGH.md            # How-to guide and test cases
  bootstrap.md                      # App specification
  Reference Files/
    XML Metadata Dictionary/
      veritasp01D-Metadata.xml      # XML metadata dictionary (9.4 MB, 886 EntityTypes)
    Template/
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
      Payment Information .csv
    Source Payment data/             # Reference payroll data (not used by script)
  skills/                            # Bootstrap optimizer skill files
```

## How the Matching Works

The XML contains **886 EntityTypes** with **14,000+ property definitions**. Many property names (e.g. `userId`, `startDate`) appear in multiple EntityTypes. The script uses a two-tier matching strategy:

1. **EntityType detection** — For each template, it normalises all column names and scores every EntityType by how many columns match. The EntityType with the highest match count wins. Permission/FieldControl mirror entities are penalised to avoid false matches. EntityTypes ending with the selected country code (e.g. `PaymentInformationDetailV3GBR`) are boosted, while those ending with a different country code are penalised.

2. **Property lookup** — Each column is first looked up in the matched EntityType's properties. If not found there, it falls back to a global search across all EntityTypes.

### Property Name Normalisation

Template columns come in varied formats. The normaliser handles all of them:

| Template Format | Example | Normalised Key |
|----------------|---------|---------------|
| UPPERCASE | `USERID` | `userid` |
| kebab-case | `start-date` | `startdate` |
| Space-separated | `LAST REVIEW DATE` | `lastreviewdate` |
| Dotted path | `personInfo.person-id-external` | `personidexternal` |
| Mixed | `custom_string1` | `customstring1` |

### Verified Template-to-EntityType Mapping

| Template File | Matched EntityType | Columns Matched |
|--------------|-------------------|----------------|
| BasicUserInfoImportTemplate | User | 19/19 |
| CompInfoImportTemplate | EmpCompensation | 6/6 |
| JobInfoImportTemplate | EmpJob | 15/15 |
| PersonInfoImportTemplate | PerPerson | 4/4 |
| EmploymentInfoImportTemplate | EmpEmployment | 8/8 |
| AddressImportTemplate | PerAddressDEFLT | 7/7 |
| EmailInfoImportTemplate | PerEmail | 5/5 |
| PhoneInfoImportTemplate | PerPhone | 5/5 |
| EmergencyContactImportTemplate | PerEmergencyContacts | 9/9 |
| NationalIdCardImportTemplate | PerNationalId | 6/6 |
| PayComponentRecurringImportTemplate | EmpPayCompRecurring | 8/8 |
| PayComponentNonRecurringImportTemplate | EmpPayCompNonRecurring | 6/6 |
| Payment Information | PaymentInformationV3 | 3/4* |

*Unmatched column is `[OPERATOR]` — square brackets are not stripped by the normaliser, so it never matches an XML property name. It is an instruction marker, not a data property.

## Silent Failure Modes

The following situations produce incorrect or incomplete output **without raising a warning in the UI**. They are distinct from columns with no XML match at all, which *are* explicitly flagged in the Step 6 results.

### 1. No EntityType matched

If the template columns share no overlap with any EntityType, `find_best_entity_type` returns nothing. All columns fall back entirely to the global property lookup. No warning is shown — the EntityType caption beneath the results table is simply absent.

### 2. Global fallback returns the wrong EntityType's definition

When a column is not found in the matched EntityType, the app takes the **first** matching entry from the global property list (14,000+ properties across 886 EntityTypes, in XML document order). Common property names such as `startDate`, `endDate`, `status`, and `currency` appear in dozens of EntityTypes with different types, mandatory flags, and max lengths. The wrong definition may be used silently — because a match *is* found, the unmatched-column warning does not fire.

> **This is the most dangerous failure mode.** Always verify the matched EntityType shown in the results caption. Columns that relied on the global fallback are not individually identified.

### 3. `friendly_type` returns a raw Edm type string

Any XML property type that is not in the type map and does not start with `SFOData.` is returned verbatim (e.g. `Edm.Guid`). This raw string appears in the Type row without warning.

### 4. Undocumented mapped types (`binary`, `time`)

`Edm.Binary` → `binary` and `Edm.Time` → `time` are handled by the type map but are not part of the documented output format (`string`, `float`, `date`, `integer`, `boolean`, `picklist`). They appear in the Type row without warning.

---

**What does NOT silently fail:** a column with no XML match at all. This is caught and shown as a warning — the unmatched-column detection fires when the Column Label falls back to the property name *and* the Type row is empty.
