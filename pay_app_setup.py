"""
PAY APP SETUP - Template Metadata Enrichment Tool

Reads a set of CSV/Excel template files and an XML metadata dictionary,
looks up metadata for each column header (Property Name), and produces
enriched Import Template files with additional metadata rows.
"""

import io
import os
import zipfile
import xml.etree.ElementTree as ET

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


def transform_template(
    filename: str,
    property_names: list[str],
    descriptions: list[str],
    global_lookup: dict,
    entity_lookup: dict,
    country: str = "",
    skip_operation: bool = False,
    data_rows: list[list[str]] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Build the enriched Import Template DataFrame.

    Output rows (exported with row label in column A, no header row):
      Row 1 — Column Name     : property identifier from the template
      Row 2 — Column Label    : sap:label from XML (falls back to property name)
      Row 3 — Type            : friendly type name
      Row 4 — Mandatory       : true / false
      Row 5 — Max Length      : capped at 10 for date/time fields
      Row 6 — Picklist Values : comma-separated values from template data rows
                                (only populated for picklist/keyword-matched string columns;
                                 empty when no data rows are present in the template)

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

        # Picklist Values row — populated from template data rows.
        # Extracted only for SFOData.* (picklist) and keyword-matched string columns.
        if _is_picklist_column(norm_key, typ) and data_rows:
            picklist_values.append(_extract_picklist_values(i, data_rows))
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

    # ---- Step 5: Transform ----
    st.header("5. Run Transformation")

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
            )
            results.append({"name": t["name"], "df": result_df, "entity_type": matched_et})
            progress.progress((i + 1) / len(templates), text=f"Processed {t['name']}")

        st.session_state["results"] = results
        st.success(f"Transformed **{len(results)}** template(s).")

    # ---- Step 5: Display results & download ----
    if "results" in st.session_state and st.session_state["results"]:
        results = st.session_state["results"]

        st.header("6. Results")

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
        st.header("7. Download")
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
