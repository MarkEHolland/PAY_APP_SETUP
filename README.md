# PAY APP SETUP — Template Metadata Enrichment Tool

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary, preparing them for use by PAY-APP.

## What It Does

Takes a set of **Template files** (CSV/Excel) — each containing a property-name header row and a description row — and an **XML metadata dictionary**, then:

1. Country is set to **GBR** (additional countries can be added to the picker later)
2. Auto-detects the best matching SAP EntityType for each template
3. Looks up each column's metadata (label, data type, mandatory flag, max length)
4. Filters country-specific descriptions (e.g. `"GBR: County | USA: State/Province"` becomes `"County"` when GBR is selected)
5. Outputs enriched Import Template files with 5 metadata rows (no header row)

### Output Format

Each enriched file contains 5 metadata rows without the property name header:

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
