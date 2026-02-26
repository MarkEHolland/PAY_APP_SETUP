"""
PAY APP SETUP - Template Metadata Enrichment Tool

Reads a set of CSV/Excel template files and an XML metadata dictionary,
looks up metadata for each column header (Property Name), and produces
enriched Import Template files with additional metadata rows.
"""

import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EDM_NS = "{http://schemas.microsoft.com/ado/2008/09/edm}"
SAP_NS = "{http://www.successfactors.com/edm/sap}"

TYPE_MAP = {
    "Edm.String": "string",
    "Edm.Decimal": "float",
    "Edm.DateTime": "date",
    "Edm.DateTimeOffset": "date",
    "Edm.Int64": "integer",
    "Edm.Int32": "integer",
    "Edm.Int16": "integer",
    "Edm.Byte": "integer",
    "Edm.Boolean": "boolean",
    "Edm.Double": "float",
    "Edm.Single": "float",
    "Edm.Binary": "binary",
    "Edm.Time": "time",
}


# ---------------------------------------------------------------------------
# XML Parsing
# ---------------------------------------------------------------------------
def _normalise_property_name(col: str) -> str:
    """
    Normalise a CSV column header to a canonical key for lookup.
    Handles UPPERCASE, kebab-case, space-separated, dotted navigation paths,
    and underscores.
    """
    if "." in col:
        col = col.rsplit(".", 1)[-1]
    return col.replace("-", "").replace("_", "").replace(" ", "").lower()


def parse_xml_metadata(xml_file) -> tuple[dict, dict]:
    """
    Parse the SAP SuccessFactors OData metadata XML.

    Returns:
        global_lookup  – normalised_name -> list[property_entry]
        entity_lookup  – entity_type_name -> {normalised_name -> property_entry}
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()

    global_lookup: dict[str, list[dict]] = {}
    entity_lookup: dict[str, dict[str, dict]] = {}

    for entity_type in root.iter(f"{EDM_NS}EntityType"):
        et_name = entity_type.attrib.get("Name", "")
        et_props: dict[str, dict] = {}

        for prop in entity_type.iter(f"{EDM_NS}Property"):
            attr = prop.attrib
            name = attr.get("Name", "")
            entry = {
                "entity_type": et_name,
                "name": name,
                "type": attr.get("Type", ""),
                "required": attr.get(f"{SAP_NS}required", ""),
                "max_length": attr.get("MaxLength", ""),
                "label": attr.get(f"{SAP_NS}label", ""),
            }
            norm_key = _normalise_property_name(name)
            global_lookup.setdefault(norm_key, []).append(entry)
            et_props[norm_key] = entry

        entity_lookup[et_name] = et_props

    return global_lookup, entity_lookup


# ---------------------------------------------------------------------------
# Picklist Reference File Parsing
# ---------------------------------------------------------------------------
def parse_picklist_reference(
    xl_file,
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """
    Parse a picklist reference file (Excel workbook or CSV).

    Excel workbooks: parses all `(Data)` sheets.
    CSV files: treated as a two-column (Code, Label) table; the filename
               (without extension) is used as the picklist name.

    Sheet layout for Excel (0-indexed rows):
      Row 0 — technical column names (LEFT side); picklist table display names
              at the 'Code' column positions (RIGHT side).
      Row 1 — human-readable labels (LEFT); literal 'Code'/'Label' (RIGHT).
      Row 2+ — data / picklist values.

    Returns:
        picklist_tables  — {display_name: [(code, label), ...]}
        col_to_picklist  — {normalised_col_name: display_name}  (auto-mapped)
    """
    picklist_tables: dict[str, list[tuple[str, str]]] = {}
    col_to_picklist: dict[str, str] = {}

    fname = getattr(xl_file, "name", "") or ""
    ext = os.path.splitext(fname)[1].lower()

    # --- CSV path ---
    if ext == ".csv":
        picklist_name = os.path.splitext(os.path.basename(fname))[0].strip() or "Picklist"
        try:
            content = xl_file.getvalue()
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            df = pd.read_csv(io.StringIO(text), header=None, dtype=str)
        except Exception as e:
            st.error(f"Could not read CSV picklist reference '{fname}': {e}")
            return picklist_tables, col_to_picklist

        if len(df) < 1:
            return picklist_tables, col_to_picklist

        # Skip a header row if the first cell looks like a column label
        first_cell = str(df.iloc[0, 0]).strip().lower()
        start_row = 1 if first_cell in ("code", "id", "value", "key", "externalcode") else 0

        values: list[tuple[str, str]] = []
        for r_idx in range(start_row, len(df)):
            code_val = str(df.iloc[r_idx, 0]).strip() if df.shape[1] >= 1 else ""
            label_val = str(df.iloc[r_idx, 1]).strip() if df.shape[1] >= 2 else ""
            if code_val and code_val.lower() != "nan":
                label_clean = label_val if label_val and label_val.lower() != "nan" else ""
                values.append((code_val, label_clean))

        if values:
            picklist_tables[picklist_name] = values

        return picklist_tables, col_to_picklist

    # --- Excel path ---
    try:
        xl = pd.ExcelFile(xl_file)
    except Exception as e:
        st.error(f"Could not open picklist reference file: {e}")
        return picklist_tables, col_to_picklist

    data_sheets = [s for s in xl.sheet_names if s.endswith("(Data)")]

    for sheet_name in data_sheets:
        try:
            df = xl.parse(sheet_name, header=None, dtype=str)
        except Exception:
            continue

        if len(df) < 2:
            continue

        row0 = list(df.iloc[0].fillna(""))
        row1 = list(df.iloc[1].fillna(""))

        # --- RIGHT side: locate picklist table start columns (row1 == "Code") ---
        table_positions: list[tuple[int, str]] = []
        for c_idx, r1_val in enumerate(row1):
            if str(r1_val).strip().lower() == "code":
                display_name = str(row0[c_idx]).strip() if c_idx < len(row0) else ""
                if display_name and display_name.lower() != "nan":
                    table_positions.append((c_idx, display_name))

        if not table_positions:
            continue

        # --- LEFT side: data column labels (row1), before the first Code col ---
        first_code_col = table_positions[0][0]
        left_labels: dict[int, str] = {}  # col_index -> human label
        for c_idx in range(first_code_col):
            r0s = str(row0[c_idx]).strip() if c_idx < len(row0) else ""
            r1s = str(row1[c_idx]).strip() if c_idx < len(row1) else ""
            if r0s and r0s.lower() != "nan" and r1s and r1s.lower() != "nan":
                left_labels[c_idx] = r1s

        # --- Extract picklist tables (first occurrence across sheets wins) ---
        sheet_tables: dict[str, list[tuple[str, str]]] = {}
        for code_col, display_name in table_positions:
            label_col = code_col + 1
            values: list[tuple[str, str]] = []
            for r_idx in range(2, len(df)):
                code_val = str(df.iloc[r_idx, code_col]).strip() if code_col < df.shape[1] else ""
                label_val = (
                    str(df.iloc[r_idx, label_col]).strip()
                    if label_col < df.shape[1]
                    else ""
                )
                if code_val and code_val.lower() != "nan":
                    label_clean = label_val if label_val and label_val.lower() != "nan" else ""
                    values.append((code_val, label_clean))
            if values:
                sheet_tables[display_name] = values
                picklist_tables.setdefault(display_name, values)

        # --- Auto-map LEFT labels to RIGHT picklist display names ---
        table_name_lower: dict[str, str] = {
            name.lower(): name for name in sheet_tables
        }
        for c_idx, human_label in left_labels.items():
            tech_name = str(row0[c_idx]).strip() if c_idx < len(row0) else ""
            if not tech_name or tech_name.lower() == "nan":
                continue
            norm_tech = _normalise_property_name(tech_name)
            matched_table = table_name_lower.get(human_label.lower())
            if matched_table and norm_tech:
                col_to_picklist.setdefault(norm_tech, matched_table)

    return picklist_tables, col_to_picklist


# EntityType name patterns that represent permission/metadata mirrors,
# not actual data entities — deprioritised during matching.
_METADATA_ENTITY_SUFFIXES = ("Permissions", "Permission", "FieldControls")

# Country codes that appear as EntityType suffixes in SAP SF metadata.
COUNTRY_CODES = [
    "GBR", "USA", "DEU", "FRA", "AUS", "CAN", "JPN", "NLD", "ESP", "ITA",
    "BRA", "MEX", "IND", "SGP", "ZAF", "NZL", "ARE", "KWT", "PER", "SAU",
    "CHN", "HKG", "KOR", "MYS", "THA", "PHL", "IDN", "COL", "CHL", "ARG",
    "POL", "CZE", "TUN", "EGY", "ISR", "RUS", "SVK", "SVN",
]

# Identity columns — every template must have at least one of these.
# Metadata for these columns is enforced to be consistent across templates.
_IDENTITY_USERID_NORM = "userid"
_IDENTITY_PERSONID_NORM = "personidexternal"
_IDENTITY_NORMS = {_IDENTITY_USERID_NORM, _IDENTITY_PERSONID_NORM}
_IDENTITY_LABELS = {
    _IDENTITY_USERID_NORM: "User ID",
    _IDENTITY_PERSONID_NORM: "Person ID External",
}

# Operation column — typically a DB command, not a data property.
_OPERATION_NORM = "operation"

# Duration / period column keywords — these are usually auto-calculated
# and should not be forced to Mandatory unless XML explicitly requires it.
_DURATION_KEYWORDS = {
    "duration", "period", "lengthofservice", "tenure", "probation",
    "probationperiod", "noticperiod", "noticeperiod", "servicedate",
}

# ---------------------------------------------------------------------------
# Picklist rules
# The XML metadata dictionary does NOT contain actual picklist option values —
# it only defines the schema of PicklistOption / PickListValueV2 entities.
# Picklist values must therefore be derived from data rows in the uploaded
# template (rows 3+) using the rules below.
# ---------------------------------------------------------------------------
_MAX_PICKLIST_VALUES = 20

# Normalised column-name substrings that indicate a string column is likely
# a picklist.  SFOData.* (XML-typed) columns are always picklists regardless
# of these keywords.
_PICKLIST_SUBSTRINGS = frozenset({
    "gender", "salutation", "marital", "legalentity",
    "employmenttype", "employeeclass", "employeetype", "contingent",
    "timezone", "country", "nationality", "addresstype", "isprimary",
    "currency", "frequency", "paygroup", "holidaycalendar",
    "eventreason", "eventtype", "contracttype",
    "costcenter", "division", "department", "businessunit",
    "location", "jobcode", "jobtitle", "jobfamily", "joblevel",
    "timetype", "workschedule", "payscale",
    "locale", "status",
})

# Normalised column-name substrings that override the above and mark a column
# as NOT a picklist (names, free-text fields, IDs, addresses, etc.).
_NON_PICKLIST_SUBSTRINGS = frozenset({
    "firstname", "lastname", "middlename", "preferredname",
    "formalname", "suffixname",
    "address1", "address2", "address3", "addressline", "street",
    "city", "postcode", "postalcode", "zipcode",
    "emailaddress", "phone", "fax",
    "nationalid", "nino", "passport",
    "sequencenumber", "description", "comments", "remark",
})


def find_best_entity_type(
    property_names: list[str],
    entity_lookup: dict[str, dict[str, dict]],
    country: str = "",
) -> str | None:
    """
    Given a list of template column names, find the EntityType that has
    the most matching properties.  Returns the EntityType name or None.

    Scoring: raw match count, with a tiebreaker that penalises
    permission/field-control mirror entities and prefers entities with
    a higher match *ratio* (matched / total props).

    When *country* is provided (e.g. "GBR"), EntityTypes ending with that
    code are boosted, while those ending with a *different* country code
    are penalised.
    """
    norm_cols = {_normalise_property_name(c) for c in property_names}
    other_countries = {c for c in COUNTRY_CODES if c != country} if country else set()

    best_name = None
    best_score = (0, 0.0, 0)  # (match_count, match_ratio, country_bonus)

    for et_name, et_props in entity_lookup.items():
        match_count = len(norm_cols & et_props.keys())
        if match_count == 0:
            continue

        # Penalise metadata mirror entities
        if et_name.endswith(_METADATA_ENTITY_SUFFIXES):
            match_count = match_count // 2

        # Country affinity: boost matching country, penalise others
        country_bonus = 0
        if country and et_name.endswith(country):
            country_bonus = 1
        elif other_countries and any(et_name.endswith(oc) for oc in other_countries):
            country_bonus = -1

        ratio = match_count / max(len(et_props), 1)
        score = (match_count, ratio, country_bonus)

        if score > best_score:
            best_score = score
            best_name = et_name

    return best_name if best_score[0] > 0 else None


def lookup_property(
    column_name: str,
    entity_props: dict[str, dict] | None,
    global_lookup: dict[str, list[dict]],
) -> dict | None:
    """
    Look up a column's metadata.  Prefers the matched EntityType's own
    properties, falls back to the global lookup across all EntityTypes.
    """
    key = _normalise_property_name(column_name)

    # Prefer the entity-specific match
    if entity_props and key in entity_props:
        return entity_props[key]

    # Fall back to global (first match)
    if key in global_lookup:
        return global_lookup[key][0]

    return None


def friendly_type(edm_type: str) -> str:
    """Map an Edm.* type string to a friendly name."""
    if edm_type in TYPE_MAP:
        return TYPE_MAP[edm_type]
    if edm_type.startswith("SFOData."):
        return "picklist"
    return edm_type


# ---------------------------------------------------------------------------
# Template file reading
# ---------------------------------------------------------------------------
def read_template(uploaded_file) -> tuple[str, list[str], list[str], list[list[str]], bool]:
    """
    Read a template file (CSV or Excel).
    Returns (filename, property_names, descriptions, data_rows, is_valid).
    A valid template has at least 1 row.  Rows 3+ are treated as data rows
    and used for picklist value extraction.
    """
    name = uploaded_file.name
    ext = os.path.splitext(name)[1].lower()

    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(uploaded_file, header=None, dtype=str)
        else:
            # Try reading as CSV
            content = uploaded_file.getvalue()
            # Detect encoding
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            df = pd.read_csv(io.StringIO(text), header=None, dtype=str)
    except Exception as e:
        st.error(f"Could not read **{name}**: {e}")
        return name, [], [], [], False

    if len(df) < 1:
        return name, [], [], [], False

    row1 = list(df.iloc[0].fillna(""))  # Property Names
    row2 = list(df.iloc[1].fillna("")) if len(df) >= 2 else []
    data_rows = [list(df.iloc[i].fillna("")) for i in range(2, len(df))] if len(df) > 2 else []
    return name, row1, row2, data_rows, True


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------
def _is_duration_column(norm_key: str) -> bool:
    """Return True if the normalised column name suggests a duration/period field."""
    return any(kw in norm_key for kw in _DURATION_KEYWORDS)


def _is_picklist_column(norm_key: str, friendly_type_val: str) -> bool:
    """
    Return True if this column should have a Picklist Values entry.

    Rules:
    - XML type 'picklist' (SFOData.*) → always a picklist.
    - date, time, float, integer, boolean → never a picklist.
    - string → picklist if norm_key contains a _PICKLIST_SUBSTRINGS keyword
      and does NOT contain a _NON_PICKLIST_SUBSTRINGS override keyword.
    """
    if friendly_type_val == "picklist":
        return True
    if friendly_type_val in ("date", "time", "float", "integer", "boolean"):
        return False
    if friendly_type_val == "string":
        if any(kw in norm_key for kw in _NON_PICKLIST_SUBSTRINGS):
            return False
        return any(kw in norm_key for kw in _PICKLIST_SUBSTRINGS)
    return False


def _extract_picklist_values(
    column_index: int,
    data_rows: list[list[str]],
    max_values: int = _MAX_PICKLIST_VALUES,
) -> str:
    """
    Return a comma-separated string of unique non-empty values found at
    *column_index* across all *data_rows*, capped at *max_values* items.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in data_rows:
        if column_index < len(row):
            val = str(row[column_index]).strip()
            if val and val not in seen_set:
                seen_set.add(val)
                seen.append(val)
                if len(seen) >= max_values:
                    break
    return ", ".join(seen)


def _get_picklist_candidates(
    templates: list[dict],
    global_lookup: dict,
    entity_lookup: dict,
) -> list[tuple[str, str, str]]:
    """
    Return deduplicated (template_name, col_name, norm_col) for every column
    that is a picklist candidate across the supplied templates.

    Excludes identity columns and the operation column.
    Each unique norm_col appears at most once (attributed to the first template).
    """
    seen_norms: set[str] = set()
    candidates: list[tuple[str, str, str]] = []

    for t in templates:
        best_et = find_best_entity_type(t["property_names"], entity_lookup)
        entity_props = entity_lookup.get(best_et) if best_et else None

        for col_name in t["property_names"]:
            norm_col = _normalise_property_name(col_name)

            if norm_col in seen_norms or norm_col in _IDENTITY_NORMS or norm_col == _OPERATION_NORM:
                continue

            meta = lookup_property(col_name, entity_props, global_lookup)
            typ = friendly_type(meta["type"]) if meta else ""

            if typ == "string" and _is_picklist_column(norm_col, "string"):
                typ = "picklist"

            if _is_picklist_column(norm_col, typ):
                seen_norms.add(norm_col)
                candidates.append((t["name"], col_name, norm_col))

    return candidates


def _gather_template_data_values(
    norm_col: str,
    templates: list[dict],
    max_values: int = 8,
) -> str:
    """
    Collect unique non-empty values for *norm_col* from the data rows (rows 3+)
    across all supplied templates.  Returns a comma-separated string.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for t in templates:
        col_idx = next(
            (i for i, c in enumerate(t["property_names"]) if _normalise_property_name(c) == norm_col),
            None,
        )
        if col_idx is None:
            continue
        for row in t.get("data_rows", []):
            if col_idx < len(row):
                val = str(row[col_idx]).strip()
                if val and val not in seen_set:
                    seen_set.add(val)
                    seen.append(val)
                    if len(seen) >= max_values:
                        break
        if len(seen) >= max_values:
            break
    result = ", ".join(seen)
    if len(seen) >= max_values:
        result += ", ..."
    return result


def transform_template(
    filename: str,
    property_names: list[str],
    descriptions: list[str],
    global_lookup: dict,
    entity_lookup: dict,
    country: str = "",
    skip_operation: bool = False,
    data_rows: list[list[str]] | None = None,
    resolved_picklists: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Build the enriched Import Template DataFrame.

    Output rows (exported with row label in column A, no header row):
      Row 1 — Column Name     : property identifier from the template
      Row 2 — Column Label    : sap:label from XML (falls back to property name)
      Row 3 — Type            : friendly type name
      Row 4 — Mandatory       : true / false
      Row 5 — Max Length      : capped at 10 for date/time fields
      Row 6 — Picklist Values : comma-separated values.  Source priority:
                                1. resolved_picklists[norm_col] if supplied.
                                2. _extract_picklist_values from data_rows.
                                (empty when neither source has values)

    Returns (DataFrame, matched_entity_type_name).
    """
    # Find best EntityType for this template
    best_et = find_best_entity_type(property_names, entity_lookup, country)
    entity_props = entity_lookup.get(best_et) if best_et else None

    column_labels: list[str] = []   # sap:label (Column Label row)
    types: list[str] = []
    mandatories: list[str] = []
    max_lengths: list[str] = []
    picklist_values: list[str] = []

    for i, prop_name in enumerate(property_names):
        norm_key = _normalise_property_name(prop_name)

        # Enforce consistent metadata for identity columns
        if norm_key in _IDENTITY_NORMS:
            column_labels.append(_IDENTITY_LABELS[norm_key])
            types.append("string")
            mandatories.append("true")
            max_lengths.append("100")
            picklist_values.append("")
            continue

        # Operation column — skip metadata if user confirmed
        if norm_key == _OPERATION_NORM and skip_operation:
            column_labels.append("Operation")
            types.append("string")
            mandatories.append("false")
            max_lengths.append("")
            picklist_values.append("")
            continue

        meta = lookup_property(prop_name, entity_props, global_lookup)
        if meta:
            column_labels.append(meta["label"] if meta["label"] else prop_name)
            typ = friendly_type(meta["type"])
            # Picklist keyword upgrade: if the XML says string but the column name
            # matches picklist keywords, upgrade the type so Type and Picklist Values
            # rows are always consistent.
            if typ == "string" and _is_picklist_column(norm_key, "string"):
                typ = "picklist"
            types.append(typ)
            # Duration columns: only mandatory if XML explicitly says so
            if _is_duration_column(norm_key):
                mandatories.append(meta["required"] if meta["required"] == "true" else "false")
            else:
                mandatories.append(meta["required"] if meta["required"] else "false")
            # Date fields: enforce max length of 10
            if typ in ("date", "time"):
                max_lengths.append("10")
            else:
                max_lengths.append(meta["max_length"])
        else:
            column_labels.append(prop_name)
            typ = ""
            types.append(typ)
            mandatories.append("")
            max_lengths.append("")

        # Picklist Values row.
        # Priority: resolved_picklists (from reference file) > data_rows extraction.
        if _is_picklist_column(norm_key, typ):
            if resolved_picklists and norm_key in resolved_picklists:
                picklist_values.append(resolved_picklists[norm_key])
            elif data_rows:
                picklist_values.append(_extract_picklist_values(i, data_rows))
            else:
                picklist_values.append("")
        else:
            picklist_values.append("")

    # Build DataFrame:
    #   columns = property_names (always unique — safe for st.dataframe display)
    #   index   = row descriptors (written as column A in the exported file)
    rows = [
        property_names,  # Column Name
        column_labels,   # Column Label
        types,           # Type
        mandatories,     # Mandatory
        max_lengths,     # Max Length
        picklist_values, # Picklist Values
    ]
    row_index = ["Column Name", "Column Label", "Type", "Mandatory", "Max Length", "Picklist Values"]
    df = pd.DataFrame(rows, index=row_index, columns=property_names)
    df.index.name = "Label"
    return df, best_et


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Export a DataFrame to CSV bytes (UTF-8 with BOM for Excel compat).

    Output: 6 rows, no header row.
    Column A = row label (Column Name / Column Label / Type / …).
    Remaining columns = values for each property.
    """
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return ("\ufeff" + buf.getvalue()).encode("utf-8-sig")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Export a DataFrame to XLSX bytes.

    Output: 6 rows, no header row.
    Column A = row label (Column Name / Column Label / Type / …).
    Remaining columns = values for each property.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Import Template")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="PAY APP SETUP", page_icon="📋", layout="wide")

    # Apply any pending configuration loaded from an uploaded JSON file.
    # Settings are staged into "_pending_config" on upload (sidebar section 4),
    # then applied here at the top of the next rerun so all widgets pick them up.
    _pending = st.session_state.pop("_pending_config", None)
    if _pending:
        if "country" in _pending:
            st.session_state["country_select"] = _pending["country"]
        if "skip_operation" in _pending:
            st.session_state["skip_operation"] = _pending["skip_operation"]
        st.session_state["loaded_config"] = _pending

    st.title("PAY APP SETUP — Template Metadata Enrichment")
    st.markdown(
        "Upload your **Template files** (CSV / Excel) and the **XML metadata dictionary** "
        "to generate enriched Import Templates with column metadata."
    )

    # ---- Sidebar: Country & XML upload ----
    st.sidebar.header("1. Country")
    country = st.sidebar.selectbox(
        "Select country",
        options=["GBR"],
        index=0,
        key="country_select",
        help="Used to prefer country-specific EntityTypes (e.g. EmpJobGBR) during matching.",
    )

    st.sidebar.header("2. XML Metadata Dictionary")
    xml_file = st.sidebar.file_uploader(
        "Upload the metadata XML file",
        type=["xml"],
        help="e.g. veritasp01D-Metadata.xml",
    )

    if xml_file is not None:
        with st.sidebar:
            with st.spinner("Parsing XML metadata..."):
                global_lookup, entity_lookup = parse_xml_metadata(xml_file)
            total_props = sum(len(v) for v in global_lookup.values())
            st.success(f"Loaded **{total_props:,}** property definitions across **{len(entity_lookup):,}** entity types.")
    else:
        st.info("Upload the XML metadata file in the sidebar to get started.")
        return

    # ---- Sidebar: Picklist Reference Files (optional, multiple) ----
    st.sidebar.header("3. Picklist Reference Files")
    picklist_ref_files = st.sidebar.file_uploader(
        "Upload picklist reference workbook(s) or CSV(s) (optional)",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        help=(
            "Excel workbooks with (Data) sheets (e.g. VP_PeelHunt_SF_EC_EmpDataWBProd.xlsx) "
            "or simple 2-column CSV files (Code, Label) — one picklist per CSV. "
            "Values from multiple files are merged (union by code)."
        ),
        key="picklist_ref_uploader",
    )

    picklist_tables: dict[str, list[tuple[str, str]]] = {}
    col_to_picklist: dict[str, str] = {}

    if picklist_ref_files:
        with st.sidebar:
            with st.spinner(f"Parsing {len(picklist_ref_files)} reference file(s)..."):
                for ref_file in picklist_ref_files:
                    tables, mapping = parse_picklist_reference(ref_file)
                    # Merge tables: union values for same-named tables (dedup by code)
                    for pl_name, values in tables.items():
                        if pl_name not in picklist_tables:
                            picklist_tables[pl_name] = list(values)
                        else:
                            existing_codes = {c for c, _ in picklist_tables[pl_name]}
                            for code, label in values:
                                if code not in existing_codes:
                                    picklist_tables[pl_name].append((code, label))
                                    existing_codes.add(code)
                    # Merge column auto-mappings (first file that maps a column wins)
                    for norm_col, pl_name in mapping.items():
                        col_to_picklist.setdefault(norm_col, pl_name)
            if picklist_tables:
                st.success(
                    f"Loaded **{len(picklist_tables):,}** picklist table(s) "
                    f"from **{len(picklist_ref_files):,}** file(s), "
                    f"with **{len(col_to_picklist):,}** auto-mapped column(s)."
                )
            else:
                st.warning("No picklist tables found in the uploaded file(s).")

    # ---- Sidebar: Configuration ----
    st.sidebar.header("4. Configuration")
    config_upload = st.sidebar.file_uploader(
        "Load saved configuration (.json)",
        type=["json"],
        help="Upload a configuration file previously saved from this app to restore picklist assignments and settings.",
        key="config_uploader",
    )
    if config_upload is not None:
        try:
            cfg = json.load(config_upload)
            st.session_state["_pending_config"] = cfg
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Could not read configuration file: {e}")

    # Show info about currently loaded config
    loaded_cfg = st.session_state.get("loaded_config")
    if loaded_cfg:
        saved_at = loaded_cfg.get("saved_at", "unknown")
        n_assignments = len(loaded_cfg.get("picklist_assignments", {}))
        st.sidebar.info(
            f"Config loaded (saved {saved_at}). "
            f"{n_assignments} picklist assignment(s) restored."
        )

    # ---- Main area: Template upload ----
    st.header("3. Upload Template Files")
    uploaded_files = st.file_uploader(
        "Select template files (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Upload one or more template files to continue.")
        return

    # ---- Read templates ----
    templates: list[dict] = []
    flagged: list[str] = []

    for uf in uploaded_files:
        name, row1, row2, data_rows, valid = read_template(uf)
        if valid:
            templates.append({
                "name": name,
                "property_names": row1,
                "descriptions": row2,
                "data_rows": data_rows,
            })
        else:
            flagged.append(name)

    if flagged:
        st.warning(
            f"The following files could not be read and were skipped: "
            f"**{', '.join(flagged)}**"
        )

    if not templates:
        st.error("No valid template files found.")
        return

    # ---- Step 4: Interactive file selection ----
    st.header("4. Select Templates to Process")
    file_names = [t["name"] for t in templates]

    selected = st.multiselect(
        "Deselect any files you do not want to process:",
        options=file_names,
        default=file_names,
    )

    templates = [t for t in templates if t["name"] in selected]

    if not templates:
        st.warning("No templates selected.")
        return

    # ---- Identity column validation ----
    missing_identity: list[str] = []
    for t in templates:
        norm_cols = {_normalise_property_name(c) for c in t["property_names"]}
        if not norm_cols & _IDENTITY_NORMS:
            missing_identity.append(t["name"])
    if missing_identity:
        st.warning(
            "The following templates do not contain a **User ID** or **Person ID External** column: "
            f"**{', '.join(missing_identity)}**"
        )

    # ---- Preview templates ----
    with st.expander("Preview uploaded templates", expanded=False):
        for t in templates:
            st.subheader(t["name"])
            preview_rows = [t["property_names"], t["descriptions"]]
            preview_df = pd.DataFrame(preview_rows, index=["Column Name", "Column Label"])
            st.dataframe(preview_df, use_container_width=True)

    # ---- Operation column check ----
    has_operation: list[str] = []
    for t in templates:
        norm_cols = {_normalise_property_name(c) for c in t["property_names"]}
        if _OPERATION_NORM in norm_cols:
            has_operation.append(t["name"])

    skip_operation = False
    if has_operation:
        st.warning(
            f"An **Operation** column was found in: **{', '.join(has_operation)}**. "
            "This typically contains a database command (e.g. `insert`, `update`, `delete`) "
            "and does not require metadata mapping."
        )
        skip_operation = st.checkbox(
            "Confirm: skip metadata mapping for the Operation column",
            value=True,
            key="skip_operation",
        )

    # ---- Identity mapping note ----
    st.info(
        "**Identity mapping rule:** There must be a 1:1 mapping between each unique "
        "User ID and Person ID External. The master source of this mapping is "
        "**BasicUserInfoImportTemplate**."
    )

    # ---- Step 5: Picklist Assignments ----
    st.header("5. Picklist Assignments")

    resolved_picklists: dict[str, str] = {}

    if picklist_tables:
        candidates = _get_picklist_candidates(templates, global_lookup, entity_lookup)

        if candidates:
            picklist_options = [""] + sorted(picklist_tables.keys())

            # Pre-compute best entity props per template for mandatory lookup
            _tmpl_entity_props: dict[str, dict] = {}
            for _t in templates:
                _best_et = find_best_entity_type(_t["property_names"], entity_lookup)
                _tmpl_entity_props[_t["name"]] = entity_lookup.get(_best_et) if _best_et else {}

            editor_rows = []
            for tmpl_name, col_name, norm_col in candidates:
                # Auto-assigned picklist from reference files
                auto_assigned = col_to_picklist.get(norm_col, "")
                if auto_assigned and auto_assigned in picklist_tables:
                    ref_pairs = picklist_tables[auto_assigned][:5]
                    ref_preview = ", ".join(label for _, label in ref_pairs if label)
                    if len(picklist_tables[auto_assigned]) > 5:
                        ref_preview += ", ..."
                    # Full label list for Final Values pre-population
                    final_vals_default = ", ".join(
                        label for _, label in picklist_tables[auto_assigned] if label
                    )
                else:
                    auto_assigned = ""
                    ref_preview = ""
                    final_vals_default = ""

                tmpl_data_preview = _gather_template_data_values(norm_col, templates)

                # Fall back to template data if no reference table assigned
                if not final_vals_default:
                    final_vals_default = tmpl_data_preview

                # Override with saved assignment from loaded configuration
                _saved = st.session_state.get("loaded_config", {}).get("picklist_assignments", {})
                if norm_col in _saved:
                    final_vals_default = _saved[norm_col]

                # Mandatory flag from XML metadata
                ep = _tmpl_entity_props.get(tmpl_name, {})
                meta = lookup_property(col_name, ep, global_lookup)
                is_mandatory = (meta.get("required", "") == "true") if meta else False

                editor_rows.append({
                    "Mand.": is_mandatory,
                    "Template": tmpl_name,
                    "Column": col_name,
                    "Assigned Picklist": auto_assigned,
                    "Reference Values": ref_preview,
                    "Template Data": tmpl_data_preview,
                    "Final Values": final_vals_default,
                    "_norm": norm_col,
                })

            assignments_df = pd.DataFrame(editor_rows)

            st.markdown(
                "Review or adjust picklist assignments. "
                "**Mand.** — column is mandatory. "
                "**Reference Values** — first 5 labels from the assigned table. "
                "**Template Data** — values found in your uploaded data rows. "
                "**Final Values** is what gets written to the output — edit it freely to add, "
                "remove, or correct values. Changing **Assigned Picklist** loads a different "
                "reference table; update **Final Values** manually if needed."
            )

            edited_df = st.data_editor(
                assignments_df,
                column_config={
                    "Mand.": st.column_config.CheckboxColumn(disabled=True),
                    "Template": st.column_config.TextColumn(disabled=True),
                    "Column": st.column_config.TextColumn(disabled=True),
                    "Assigned Picklist": st.column_config.SelectboxColumn(
                        options=picklist_options,
                        required=False,
                    ),
                    "Reference Values": st.column_config.TextColumn(disabled=True),
                    "Template Data": st.column_config.TextColumn(disabled=True),
                    "Final Values": st.column_config.TextColumn(
                        help="Comma-separated list of valid values. Edit freely before generating.",
                    ),
                    "_norm": None,
                },
                hide_index=True,
                use_container_width=True,
                key="picklist_assignments_editor",
            )

            # --- Validation warnings ---
            mandatory_empty: list[str] = []
            single_value: list[tuple[str, str]] = []
            for _, row in edited_df.iterrows():
                final_vals = str(row.get("Final Values", "") or "").strip()
                col_display = str(row.get("Column", ""))
                if bool(row.get("Mand.", False)) and not final_vals:
                    mandatory_empty.append(col_display)
                if final_vals:
                    items = [v.strip() for v in final_vals.split(",") if v.strip()]
                    if len(items) == 1:
                        single_value.append((col_display, items[0]))

            if mandatory_empty:
                st.error(
                    f"**{len(mandatory_empty)} mandatory picklist column(s) have no values:** "
                    + ", ".join(f"`{c}`" for c in mandatory_empty)
                )
            if single_value:
                st.warning(
                    "**The following picklist column(s) have only one value** — "
                    "check whether more options are expected: "
                    + ", ".join(f"`{c}` ({v})" for c, v in single_value)
                )

            # Build resolved_picklists directly from Final Values column
            for _, row in edited_df.iterrows():
                final_vals = str(row.get("Final Values", "") or "").strip()
                norm_col = str(row.get("_norm", "")).strip()
                if final_vals and norm_col:
                    resolved_picklists[norm_col] = final_vals
        else:
            st.info("No picklist-candidate columns were detected in the selected templates.")
    else:
        st.info(
            "No Picklist Reference File uploaded. "
            "Picklist Values will be extracted from template data rows where available."
        )

    # ---- Save Configuration ----
    with st.expander("Save configuration", expanded=False):
        st.markdown(
            "Download the current settings and picklist assignments as a JSON file. "
            "Upload it via **4. Configuration** in the sidebar to restore this session later."
        )
        _cfg_files = {
            "xml_metadata": xml_file.name,
            "picklist_references": [f.name for f in picklist_ref_files] if picklist_ref_files else [],
            "templates": [t["name"] for t in templates],
        }
        _cfg_to_save = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "country": country,
            "skip_operation": skip_operation,
            "files_used": _cfg_files,
            "picklist_assignments": resolved_picklists,
        }
        _cfg_json = json.dumps(_cfg_to_save, indent=2, ensure_ascii=False)
        st.download_button(
            "Download configuration (.json)",
            data=_cfg_json.encode("utf-8"),
            file_name=f"pay_app_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )
        st.caption(
            f"Captures: country ({country}), skip_operation ({skip_operation}), "
            f"{len(resolved_picklists)} picklist assignment(s), and file names used."
        )

    # ---- Step 6: Transform ----
    st.header("6. Run Transformation")

    if st.button("Generate Import Templates", type="primary"):
        results: list[dict] = []

        progress = st.progress(0, text="Processing templates...")
        for i, t in enumerate(templates):
            result_df, matched_et = transform_template(
                t["name"],
                t["property_names"],
                t["descriptions"],
                global_lookup,
                entity_lookup,
                country,
                skip_operation=skip_operation,
                data_rows=t.get("data_rows", []),
                resolved_picklists=resolved_picklists if resolved_picklists else None,
            )
            results.append({"name": t["name"], "df": result_df, "entity_type": matched_et})
            progress.progress((i + 1) / len(templates), text=f"Processed {t['name']}")

        st.session_state["results"] = results
        st.success(f"Transformed **{len(results)}** template(s).")

    # ---- Step 5: Display results & download ----
    if "results" in st.session_state and st.session_state["results"]:
        results = st.session_state["results"]

        st.header("7. Results")

        # Show unmatched properties summary.
        # A column is unmatched when its Column Label (sap:label) == its property name
        # (meaning the label fell back to the property name — no XML entry found)
        # AND its Type row is empty.
        for r in results:
            df = r["df"]
            col_label_row = df.loc["Column Label"] if "Column Label" in df.index else pd.Series(dtype=str)
            type_row = df.loc["Type"] if "Type" in df.index else pd.Series(dtype=str)
            unmatched = [
                col for col in df.columns
                if str(col_label_row.get(col, "")) == col and str(type_row.get(col, "")) == ""
            ]
            if unmatched:
                st.warning(
                    f"**{r['name']}**: {len(unmatched)} column(s) had no XML match: "
                    f"`{'`, `'.join(unmatched[:10])}`"
                    + (f" ... and {len(unmatched) - 10} more" if len(unmatched) > 10 else "")
                )

        # Display each result
        for r in results:
            et = r.get("entity_type")
            label = f'{r["name"]}  (matched: **{et}**)' if et else r["name"]
            st.subheader(r["name"])
            if et:
                st.caption(f"Best matching EntityType: {et}")
            st.dataframe(r["df"], use_container_width=True)

        # ---- Download options ----
        st.header("8. Download")
        fmt = st.radio("Output format:", ["CSV", "XLSX"], horizontal=True)

        if len(results) == 1:
            # Single file download
            r = results[0]
            base = os.path.splitext(r["name"])[0]
            if fmt == "CSV":
                data = to_csv_bytes(r["df"])
                st.download_button(
                    f"Download {base}_enriched.csv",
                    data=data,
                    file_name=f"{base}_enriched.csv",
                    mime="text/csv",
                )
            else:
                data = to_xlsx_bytes(r["df"])
                st.download_button(
                    f"Download {base}_enriched.xlsx",
                    data=data,
                    file_name=f"{base}_enriched.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            # Multiple files -> zip download
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for r in results:
                    base = os.path.splitext(r["name"])[0]
                    if fmt == "CSV":
                        zf.writestr(f"{base}_enriched.csv", to_csv_bytes(r["df"]))
                    else:
                        zf.writestr(f"{base}_enriched.xlsx", to_xlsx_bytes(r["df"]))
            zip_buf.seek(0)

            ext = "csv" if fmt == "CSV" else "xlsx"
            st.download_button(
                f"Download all enriched templates (.zip)",
                data=zip_buf.getvalue(),
                file_name=f"enriched_templates_{ext}.zip",
                mime="application/zip",
            )

            # Also provide individual downloads
            with st.expander("Or download individually"):
                for r in results:
                    base = os.path.splitext(r["name"])[0]
                    if fmt == "CSV":
                        data = to_csv_bytes(r["df"])
                        st.download_button(
                            f"{base}_enriched.csv",
                            data=data,
                            file_name=f"{base}_enriched.csv",
                            mime="text/csv",
                            key=f"dl_{r['name']}_csv",
                        )
                    else:
                        data = to_xlsx_bytes(r["df"])
                        st.download_button(
                            f"{base}_enriched.xlsx",
                            data=data,
                            file_name=f"{base}_enriched.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{r['name']}_xlsx",
                        )


if __name__ == "__main__":
    main()
