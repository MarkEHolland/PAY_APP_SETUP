# Bootstrap — PAY APP SETUP

## Overview

A Streamlit web application that enriches SAP SuccessFactors import template files with metadata from an OData XML dictionary, preparing them for use by PAY-APP.

## UI Flow

The app is a single `main()` function. At the very top of `main()`, before any widgets are rendered, any staged configuration is applied (see **Configuration — Session State Pattern** below).

### Sidebar

**1. Country**
A `st.sidebar.selectbox` with `options=["GBR"]`, `key="country_select"`. Used to boost country-affinity EntityType matching (e.g. `EmpJobGBR` is preferred over the generic `EmpJob`).

**2. XML Metadata Dictionary**
A `st.sidebar.file_uploader` accepting `type=["xml"]`. On upload, parse via `parse_xml_metadata` and show a success message with property and entity type counts. If not yet uploaded, show an info message in the main area and `return` — this blocks the entire rest of the UI.

**3. Picklist Reference Files** *(optional)*
A `st.sidebar.file_uploader` with `accept_multiple_files=True`, accepting `type=["xlsx", "xls", "csv"]`, `key="picklist_ref_uploader"`. For each uploaded file, call `parse_picklist_reference`. Merge results across all files:
- **Tables**: same-named tables have values unioned by code (first file wins per code).
- **Column auto-mappings**: first file wins per normalised column name.

Show success with count of loaded tables and auto-mapped columns, or a warning if no tables were found.

**4. Configuration** *(optional)*
A `st.sidebar.file_uploader` accepting `type=["json"]`, `key="config_uploader"`. On upload, decode the JSON, store it as `st.session_state["_pending_config"]`, and call `st.rerun()`. Show a sidebar info message when a config has been successfully loaded (timestamp and number of restored assignments).

### Main Area

**Step 3: Upload Template Files**
A `st.file_uploader` (in the main area) with `accept_multiple_files=True`, accepting `type=["csv", "xlsx", "xls"]`. For each file, call `read_template`. Files that cannot be read (invalid or empty) are collected and displayed in a single warning.

**Step 4: Select Templates to Process**
A `st.multiselect` with all valid template names pre-selected as default. Filter the templates list to only selected names.
- Warn if any selected template contains no User ID (`userid`) or Person ID External (`personidexternal`) column.
- Show a "Preview uploaded templates" `st.expander` (collapsed by default) containing a DataFrame per template (property_names row + label_row).
- Scan for an `operation` column in any template. If found, show a `st.warning` and a `st.checkbox` (key `"skip_operation"`, default `True`) asking the user to confirm skipping metadata mapping for that column.
- Show an `st.info` box: *"Identity mapping rule: There must be a 1:1 mapping between each unique User ID and Person ID External. The master source of this mapping is BasicUserInfoImportTemplate."*

**Step 5: Picklist Assignments**
Only shown when picklist reference files have been uploaded and returned at least one table.

Call `_get_picklist_candidates(templates, global_lookup, entity_lookup)` to get all picklist-candidate columns (deduplicated by norm_col, one row per unique column, attributed to the first template it appears in; identity and operation columns excluded).

Build editor rows — one per candidate:
- **Mand.** (bool): `meta["required"] == "true"` from XML, or `False` if no metadata.
- **Template** (str): template name.
- **Column** (str): column name as it appears in the template.
- **Assigned Picklist** (str): auto-assigned from `col_to_picklist.get(norm_col, "")`.
- **Reference Values** (str, read-only): first 5 labels from the assigned table (joined by `, `), plus `", ..."` if more. Empty if no assignment.
- **Template Data** (str, read-only): up to 8 unique non-empty values from data rows across all templates for this norm_col (via `_gather_template_data_values`), plus `", ..."` if truncated.
- **Final Values** (str, editable): pre-populated in priority order:
  1. Full label list from the assigned picklist table (all labels, comma-separated).
  2. Else: Template Data values.
  3. Override: if `st.session_state["loaded_config"]["picklist_assignments"]` has an entry for this norm_col, use that value.
- **_norm** (str, hidden via `None` config): the normalised column name.

Render with `st.data_editor`:
- `Mand.`: `CheckboxColumn(disabled=True)`
- `Template`, `Column`, `Reference Values`, `Template Data`: `TextColumn(disabled=True)`
- `Assigned Picklist`: `SelectboxColumn(options=[""] + sorted(picklist_tables.keys()), required=False)`
- `Final Values`: `TextColumn` (editable)
- `_norm`: `None` (hidden)

**Validation** (after the editor):
- **Error** if any row has `Mand. == True` and empty `Final Values` → list affected column names.
- **Warning** if any row has `Final Values` containing exactly one comma-split item → list column name and the single value.

Build `resolved_picklists: dict[str, str]` = `{_norm: Final Values}` for all rows where Final Values is non-empty.

Show a "Save configuration" `st.expander` (collapsed) with a `st.download_button` that downloads a JSON file in this format:
```json
{
  "saved_at": "2026-01-15T14:32:00",
  "country": "GBR",
  "skip_operation": true,
  "files_used": {
    "xml_metadata": "veritasp01D-Metadata.xml",
    "picklist_references": ["VP_PeelHunt_SF_EC_EmpDataWBProd.xlsx"],
    "templates": ["JobInfoImportTemplate.csv"]
  },
  "picklist_assignments": {
    "gender": "Female, Male, Not Specified",
    "country": "GBR, USA, DEU"
  }
}
```

If no picklist reference files are uploaded, show `st.info` noting picklist values will be extracted from template data rows. `resolved_picklists` remains empty.

**Step 6: Run Transformation**
A primary `st.button("Generate Import Templates", type="primary")`. On click:
- Show `st.progress` bar.
- For each selected template, call `transform_template(...)` and collect results.
- Store results in `st.session_state["results"]`.
- Show success message with count of processed templates.

**Step 7: Results**
For each result:
- Warn about unmatched columns: a column is unmatched when its Column Label row equals the raw property name (label fell back) **and** its Type row is empty.
- Show `st.subheader` with filename, `st.caption` with matched EntityType, `st.dataframe` with the result DataFrame.

The result DataFrame is displayed with its index visible (showing "Column Name", "Column Label", etc. as row labels in the on-screen table). These labels are only for display — they are not written to downloaded files.

**Step 8: Download**
`st.radio("Output format:", ["CSV", "XLSX"], horizontal=True)`.
- **1 result**: individual download button.
- **Multiple results**: ZIP download button + "Or download individually" `st.expander` with per-file buttons.

---

## Parsing

### `_normalise_property_name(col: str) -> str`
- If `col` contains `.`: take the segment after the last `.`.
- Remove `-`, `_`, and spaces.
- Lowercase.

### `parse_xml_metadata(xml_file) -> (global_lookup, entity_lookup)`
Iterates all `EntityType` elements in the XML using `EDM_NS = "{http://schemas.microsoft.com/ado/2008/09/edm}"`. For each `Property` child, reads:
- `Name`, `Type`, `MaxLength`, `sap:required` (using `SAP_NS = "{http://www.successfactors.com/edm/sap}"`), `sap:label`.

Returns:
- `global_lookup: dict[str, list[dict]]` — normalised name → list of all matching entries across all EntityTypes.
- `entity_lookup: dict[str, dict[str, dict]]` — EntityType name → {normalised name → entry}.

### `parse_picklist_reference(file) -> (picklist_tables, col_to_picklist)`

**CSV files** (`.csv` extension on `file.name`):
- Picklist name = `os.path.splitext(os.path.basename(fname))[0]`.
- Read bytes from `file.getvalue()`, decode UTF-8-sig then latin-1 as fallback.
- Parse with `pd.read_csv(header=None, dtype=str)`.
- Skip row 0 if `str(df.iloc[0, 0]).strip().lower()` is one of: `code`, `id`, `value`, `key`, `externalcode`.
- Column 0 = code, column 1 = label. Skip rows where code is empty or `"nan"`.
- Returns one picklist table keyed by filename; `col_to_picklist` is empty (no auto-mapping).

**Excel files** (all other accepted extensions):
- Only sheets whose name **ends with** `(Data)` are processed.
- **Row 0**: technical column names on the LEFT side; picklist display names at each "Code" column position on the RIGHT side.
- **Row 1**: human-readable labels on the LEFT; literal `"Code"` / `"Label"` on the RIGHT.
- **Row 2+**: data values on the LEFT; picklist code/label pairs on the RIGHT.
- A "Code" column is identified when `row1[col_idx].strip().lower() == "code"`. Its display name is `row0[col_idx]`.
- The LEFT side spans columns `0` to `first_code_col - 1`. Each LEFT column is mapped: tech name (row0) → normalised → auto-mapped picklist name (matched by comparing row1 human label to picklist display name, case-insensitive).
- For each picklist table, data is extracted from rows 2+ at `code_col` and `code_col + 1`. Empty or `"nan"` codes are skipped.
- `picklist_tables.setdefault(display_name, values)` — first occurrence per display name across all sheets wins.

### `read_template(uploaded_file) -> (name, property_names, label_row, data_rows, is_valid)`
- `.xlsx` / `.xls`: `pd.read_excel(header=None, dtype=str)`.
- All others: read bytes, decode UTF-8-sig then latin-1 fallback, `pd.read_csv(header=None, dtype=str)`.
- Row 0 → `property_names`, Row 1 → `label_row`, Rows 2+ → `data_rows`.
- `is_valid = len(df) >= 1`.

### `find_best_entity_type(property_names, entity_lookup, country) -> str | None`
Scores every EntityType: `match_count = |normalised_columns ∩ entity_type_keys|`. Tiebreakers (lexicographic score tuple `(match_count, match_ratio, country_bonus)`):
1. EntityTypes ending with `Permissions`, `Permission`, or `FieldControls`: `match_count //= 2`.
2. `country_bonus = +1` if EntityType ends with `country`; `-1` if it ends with a different country code from `COUNTRY_CODES`.
3. `match_ratio = match_count / max(len(et_props), 1)`.

Returns the EntityType name with the highest score, or `None` if no EntityType matched.

### `lookup_property(column_name, entity_props, global_lookup) -> dict | None`
1. Check `entity_props` (matched EntityType) first.
2. Fall back to `global_lookup[norm_key][0]` (first entry across all EntityTypes).

### `_get_picklist_candidates(templates, global_lookup, entity_lookup) -> list[(tmpl_name, col_name, norm_col)]`
Iterates all selected templates and their columns. For each column not yet seen (`seen_norms`), not an identity column, and not the operation column:
- Look up metadata, compute `friendly_type`.
- If XML says `string` and `_is_picklist_column(norm_col, "string")` → upgrade to `picklist`.
- If `_is_picklist_column(norm_col, type)` → include in results.
Each unique norm_col appears once (attributed to the first template).

### `_gather_template_data_values(norm_col, templates, max_values=8) -> str`
Collects up to 8 unique non-empty values for `norm_col` across data rows of all templates. Returns comma-separated string; appends `", ..."` if `max_values` was reached.

### `transform_template(..., resolved_picklists=None) -> (DataFrame, matched_entity_type)`
Builds a 6-row DataFrame with columns = `property_names` and index = `["Column Name", "Column Label", "Type", "Mandatory", "Max Length", "Picklist Values"]`.

For each column:
- **Identity columns** (`userid`, `personidexternal`): hardcoded — Label from `_IDENTITY_LABELS`, Type=`string`, Mandatory=`true`, MaxLength=`100`, Picklist=`""`.
- **Operation column** (when `skip_operation=True`): Label=`"Operation"`, Type=`string`, Mandatory=`false`, MaxLength=`""`, Picklist=`""`.
- **All others**: look up metadata, map type via `TYPE_MAP`, upgrade `string` → `picklist` if `_is_picklist_column`, enforce duration-column mandatory rules, force MaxLength=`"10"` for date/time types.
- **Picklist Values priority**: `resolved_picklists[norm_col]` → `_extract_picklist_values(data_rows)` → `""`.

### `_is_picklist_column(norm_key, friendly_type_val) -> bool`
- `picklist` type → always True.
- `date`, `time`, `float`, `integer`, `boolean` → always False.
- `string` → True if `norm_key` contains any `_PICKLIST_SUBSTRINGS` keyword **and** does not contain any `_NON_PICKLIST_SUBSTRINGS` keyword.

### `_is_duration_column(norm_key) -> bool`
Returns True if `norm_key` contains any keyword from `_DURATION_KEYWORDS`: `duration`, `period`, `lengthofservice`, `tenure`, `probation`, `probationperiod`, `noticperiod`, `noticeperiod`, `servicedate`.

### Export helpers

`to_csv_bytes(df)`: `df.to_csv(index=False, header=False)` + UTF-8 BOM prefix `\ufeff`.
`to_xlsx_bytes(df)`: `df.to_excel(index=False, header=False, sheet_name="Import Template")` via xlsxwriter.

Both omit the DataFrame index (row labels) and the column-name header, producing a plain 6-row grid.

---

## Configuration — Session State Pattern

Loading a config JSON triggers `st.rerun()` so the restored values are applied before any widgets render. The staging flow:

1. User uploads a JSON file in sidebar section 4.
2. Handler decodes the JSON, stores it as `st.session_state["_pending_config"]`, calls `st.rerun()`.
3. At the **very top of `main()`** (before any widgets): `_pending = st.session_state.pop("_pending_config", None)`.
4. If `_pending` is set:
   - `st.session_state["country_select"] = _pending["country"]` (if key present).
   - `st.session_state["skip_operation"] = _pending["skip_operation"]` (if key present).
   - `st.session_state["loaded_config"] = _pending` — the picklist assignments editor reads this to override Final Values pre-population.

---

## Output Format

Exported files contain **6 rows**, no row-label column, no file header:

| Row | Content | Source |
|-----|---------|--------|
| 1 | Property names (Column Names) | Template row 1 |
| 2 | Human-readable labels | `sap:label` from XML (falls back to property name) |
| 3 | Type | `Edm.*` mapped to `string`/`float`/`date`/`integer`/`boolean`/`picklist` |
| 4 | Mandatory | `sap:required` from XML (`true`/`false`) |
| 5 | Max Length | `MaxLength` from XML (date/time capped at `10`) |
| 6 | Picklist Values | Comma-separated. Priority: Final Values from Step 5 → template data rows 3+ → empty |

> The in-app preview (`st.dataframe`) shows row labels ("Column Name", "Column Label", etc.) because the DataFrame index is displayed on screen. The downloaded file does not include those labels.

---

## Template Identity Requirements

- Every template must contain at least one of: **User ID** (`userid`) or **Person ID External** (`personidexternal`).
- These columns always get hardcoded metadata: Type=`string`, Mandatory=`true`, MaxLength=`100`.
- There must be a 1:1 mapping between each unique User ID and Person ID External.
- The master source of the User ID ↔ Person ID External mapping is the **BasicUserInfoImportTemplate**.

## Operation Column

If a column called `operation` (normalised) is found in any template, the user is prompted to confirm it does not require metadata mapping. This column typically contains a database command (`insert`, `update`, `delete`), not a data property. When the checkbox is checked (`skip_operation=True`), the column gets hardcoded metadata: Label=`"Operation"`, Type=`string`, Mandatory=`false`, MaxLength=`""`.

## Duration / Period Columns

Columns whose normalised name contains a duration keyword (`_DURATION_KEYWORDS`) are generally auto-calculated and should not be forced Mandatory — unless the XML explicitly states `sap:required="true"`. All other columns inherit the XML `sap:required` value, defaulting to `false` if absent.

## Picklist Rules

The OData XML metadata dictionary does **not** contain actual picklist option values — it only defines the schema of `PicklistOption` / `PickListValueV2` entities. Picklist values come from:
1. The **Picklist Assignments editor** (Step 5) — Final Values column, pre-populated from reference files or template data.
2. **Template data rows** (rows 3+) — extracted automatically when no reference files are uploaded.

### What IS a picklist

- XML type is `SFOData.*` → always `picklist`.
- XML type is `Edm.String` **and** normalised column name contains one of these keywords (type is upgraded from `string` to `picklist`):
  `gender`, `salutation`, `marital`, `legalentity`, `employmenttype`, `employeeclass`,
  `employeetype`, `contingent`, `timezone`, `country`, `nationality`, `addresstype`,
  `isprimary`, `currency`, `frequency`, `paygroup`, `holidaycalendar`, `eventreason`,
  `eventtype`, `contracttype`, `costcenter`, `division`, `department`, `businessunit`,
  `location`, `jobcode`, `jobtitle`, `jobfamily`, `joblevel`, `timetype`, `workschedule`,
  `payscale`, `locale`, `status`.

### What is NOT a picklist

- Any column with type `date`, `time`, `float`, `integer`, or `boolean`.
- String columns whose normalised name contains any of: `firstname`, `lastname`, `middlename`,
  `preferredname`, `formalname`, `suffixname`, `address1`, `address2`, `address3`,
  `addressline`, `street`, `city`, `postcode`, `postalcode`, `zipcode`, `emailaddress`,
  `phone`, `fax`, `nationalid`, `nino`, `passport`, `sequencenumber`, `description`,
  `comments`, `remark`.

## Type Mapping

| XML Type | Friendly Name |
|----------|--------------|
| `Edm.String` | string |
| `Edm.Decimal`, `Edm.Double`, `Edm.Single` | float |
| `Edm.DateTime`, `Edm.DateTimeOffset` | date |
| `Edm.Int64`, `Edm.Int32`, `Edm.Int16`, `Edm.Byte` | integer |
| `Edm.Boolean` | boolean |
| `Edm.Binary` | binary |
| `Edm.Time` | time |
| `SFOData.*` (navigation/complex types) | picklist |

## Tech Stack

- **Python 3.11+**
- **Streamlit** — Web UI
- **pandas** — DataFrame handling
- **xml.etree.ElementTree** — XML parsing
- **openpyxl** — Reading Excel input files
- **xlsxwriter** — Writing XLSX exports
