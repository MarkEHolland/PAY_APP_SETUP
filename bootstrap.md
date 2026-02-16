# Bootstrap — PAY APP SETUP

## Overview

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary, preparing them for use by PAY-APP.

## How It Works

1. **Country** — The sidebar has a country picker locked to **GBR**. This is used to filter country-specific descriptions and boost country-affinity EntityType matching.
2. **XML Upload** — The user uploads the OData XML metadata dictionary (`veritasp01D-Metadata.xml`, ~9.4 MB, 886 EntityTypes, 14,000+ properties) via the sidebar.
3. **Template Upload** — The user uploads one or more CSV or Excel template files. Each template has two rows: row 1 is the property name headers, row 2 is a freeform description of each field.
4. **Validation** — Files that do not contain exactly 2 rows are flagged with a warning and excluded from processing.
5. **Template Selection** — All uploaded files appear in a multiselect. The user can deselect any they don't want to process.
6. **Transformation** — For each selected template:
   - Property names are normalised (lowercase, hyphens/underscores removed, dotted paths take the last segment) to match XML property keys.
   - The best matching EntityType is detected by scoring how many columns match, with penalties for Permission/FieldControl entities and boosts for country-affinity entities (e.g. `PaymentInformationDetailV3GBR`).
   - Each column's metadata is looked up from the matched EntityType first, then falls back to a global search across all EntityTypes.
   - Country-specific descriptions (pipe-delimited, e.g. `"GBR: County | USA: State/Province"`) are filtered to the selected country segment.
7. **Output** — Each enriched file contains 5 metadata rows (no header row in exports):

   | Row | Content | Source |
   |-----|---------|--------|
   | Column Name | Human-readable label | `sap:label` from XML |
   | Description | What the field contains / valid values | Original template row 2 |
   | Type | `string`, `float`, `date`, `integer`, `boolean`, `picklist` | `Type` attribute mapped from `Edm.*` |
   | Mandatory | `true` / `false` | `sap:required` from XML |
   | Max Length | Character limit | `MaxLength` attribute |

8. **Download** — Files can be downloaded individually or as a ZIP, in either CSV (UTF-8 with BOM) or XLSX format.

## Template Identity Requirements

- Every template must contain at least one of: **User ID** or **Person ID External**.
- The metadata for User ID and Person ID External must be consistent across all templates:
  - Both are always **Mandatory** (`true`).
  - Both are always **Type** `string` with **Max Length** `100`.
- There must always be a **1:1 mapping** between each unique User ID and each unique Person ID External.
- The master source of the User ID ↔ Person ID External mapping is the **BasicUserInfoImportTemplate**.

## Operation Column

- If a column called **Operation** is found in any template, the user should be prompted to confirm it does not require metadata mapping. This column typically contains an allowed database command (e.g. `insert`, `update`, `delete`) rather than a data property.

## Duration / Period Columns

- Columns that refer to a time or date period duration (e.g. length of service, probation period) are typically auto-calculated from other columns and generally do not need to be **Mandatory** — unless the XML definitively says otherwise via `sap:required="true"`.

## Type Mapping

| XML Type | Friendly Name |
|----------|--------------|
| `Edm.String` | string |
| `Edm.Decimal`, `Edm.Double`, `Edm.Single` | float |
| `Edm.DateTime`, `Edm.DateTimeOffset` | date |
| `Edm.Int64`, `Edm.Int32`, `Edm.Int16`, `Edm.Byte` | integer |
| `Edm.Boolean` | boolean |
| `SFOData.*` (navigation/complex types) | picklist |

## Tech Stack

- **Python 3.11+**
- **Streamlit** — Web UI
- **pandas** — DataFrame handling
- **xml.etree.ElementTree** — XML parsing
- **openpyxl** — Reading Excel input files
- **xlsxwriter** — Writing XLSX exports
