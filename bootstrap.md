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
