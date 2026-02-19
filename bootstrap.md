# Bootstrap — PAY APP SETUP

## Overview

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary, preparing them for use by PAY-APP.

## How It Works

1. **Country** — The sidebar has a country picker locked to **GBR**. This is used to boost country-affinity EntityType matching (e.g. `PaymentInformationDetailV3GBR` is preferred over the generic equivalent).
2. **XML Upload** — The user uploads the OData XML metadata dictionary (`veritasp01D-Metadata.xml`, ~9.4 MB, 886 EntityTypes, 14,000+ properties) via the sidebar.
3. **Template Upload** — The user uploads one or more CSV or Excel template files. Each template has at least one row: row 1 is the property name headers (Column Names), and an optional row 2 is a label/description for each field.
4. **Validation** — Files that cannot be read are flagged with a warning and excluded from processing.
5. **Template Selection** — All uploaded files appear in a multiselect. The user can deselect any they don't want to process.
6. **Transformation** — For each selected template:
   - Property names are normalised (lowercase, hyphens/underscores/spaces removed, dotted paths take the last segment) to match XML property keys.
   - The best matching EntityType is detected by scoring how many columns match, with penalties for Permission/FieldControl entities and boosts for country-affinity entities (e.g. `PaymentInformationDetailV3GBR`).
   - Each column's metadata is looked up from the matched EntityType first, then falls back to a global search across all EntityTypes.
   - Date and time fields always have Max Length set to `10`.
   - If the XML defines a column as `string` but its normalised name matches a picklist keyword, the Type is upgraded to `picklist`.
7. **Output** — Each enriched file contains 6 rows (no file header row). Column A holds the row label:

   | Row (Column A) | Content | Source |
   |----------------|---------|--------|
   | Column Name | Property identifier (technical name) | Template row 1 |
   | Column Label | Human-readable label | `sap:label` from XML (falls back to property name) |
   | Type | `string`, `float`, `date`, `integer`, `boolean`, `picklist` | `Type` attribute mapped from `Edm.*` |
   | Mandatory | `true` / `false` | `sap:required` from XML |
   | Max Length | Character limit (date/time capped at 10) | `MaxLength` attribute |
   | Picklist Values | Comma-separated distinct values (empty when no data rows present) | Template rows 3+ |

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

## Picklist Values

The OData XML metadata dictionary does **not** contain actual picklist option values. It only defines the schema of `PicklistOption` / `PickListValueV2` entities; the real values live in the SAP SuccessFactors database. Picklist values are therefore derived from any data rows present in the uploaded template (rows 3+).

### What IS a picklist

A column is treated as a picklist when:

- Its XML type is `SFOData.*` (navigation/complex types) — these always map to `picklist`.
- Its XML type is `Edm.String` **and** its normalised column name contains one of the following keywords (in this case the **Type row is upgraded from `string` to `picklist`**):
  `gender`, `salutation`, `marital`, `legalentity`, `employmenttype`, `employeeclass`,
  `employeetype`, `contingent` (isContingentWorker), `timezone`, `country`, `nationality`,
  `addresstype`, `isprimary`, `currency`, `frequency`, `paygroup`, `holidaycalendar`,
  `eventreason`, `eventtype`, `contracttype`, `costcenter`, `division`, `department`,
  `businessunit`, `location`, `jobcode`, `jobtitle`, `jobfamily`, `joblevel`, `timetype`,
  `workschedule`, `payscale`, `locale`, `status`.

### What is NOT a picklist

- Any column with type `date`, `time`, `float`, `integer`, or `boolean`.
- String columns whose normalised name contains: `firstname`, `lastname`, `middlename`,
  `preferredname`, `formalname`, `address1/2/3`, `addressline`, `street`, `city`, `postcode`,
  `postalcode`, `zipcode`, `emailaddress`, `phone`, `fax`, `nationalid`, `nino`, `passport`,
  `sequencenumber`, `description`, `comments`, `remark`.
- By rule: dates, floats, integers, IDs, free-text names, addresses, and postcodes are never picklists.

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
