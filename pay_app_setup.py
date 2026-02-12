"""
PAY APP SETUP - Template Metadata Enrichment Tool

Reads a set of CSV/Excel template files and an XML metadata dictionary,
looks up metadata for each column header (Property Name), and produces
enriched Import Template files with additional metadata rows.
"""

import io
import os
import re
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
    Handles UPPERCASE, kebab-case, dotted navigation paths, and underscores.
    """
    if "." in col:
        col = col.rsplit(".", 1)[-1]
    return col.replace("-", "").replace("_", "").lower()


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

# Regex to detect pipe-delimited country-specific descriptions,
# e.g. "GBR: County | JPN: State | USA: State/Province"
_COUNTRY_DESC_RE = re.compile(
    r"^[A-Z]{3}\s*:\s*.+\|", re.DOTALL
)


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
def read_template(uploaded_file) -> tuple[str, list[str], list[str], bool]:
    """
    Read a template file (CSV or Excel).
    Returns (filename, row1_values, row2_values, is_valid).
    A valid template has exactly 2 rows (header + description).
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
        return name, [], [], False

    if len(df) < 2:
        return name, list(df.iloc[0].fillna("")) if len(df) >= 1 else [], [], False

    row1 = list(df.iloc[0].fillna(""))  # Property Names
    row2 = list(df.iloc[1].fillna(""))  # Descriptions
    return name, row1, row2, True


# ---------------------------------------------------------------------------
# Description helpers
# ---------------------------------------------------------------------------
def _filter_country_description(description: str, country: str) -> str:
    """
    If *description* is a pipe-delimited set of country-specific values
    like ``"GBR: County | JPN: State | USA: State/Province"``, return only
    the segment for *country*.  Otherwise return the original string.
    """
    if not country or "|" not in description:
        return description
    # Quick check: does it look like "XXX: value | YYY: value" ?
    if not _COUNTRY_DESC_RE.match(description.strip()):
        return description

    segments = [s.strip() for s in description.split("|")]
    for seg in segments:
        if seg.upper().startswith(country + ":"):
            return seg[len(country) + 1:].strip()
    # Country not listed — return full string so nothing is lost
    return description


# ---------------------------------------------------------------------------
# Transformation
# ---------------------------------------------------------------------------
def transform_template(
    filename: str,
    property_names: list[str],
    descriptions: list[str],
    global_lookup: dict,
    entity_lookup: dict,
    country: str = "",
) -> tuple[pd.DataFrame, str | None]:
    """
    Build the enriched Import Template DataFrame.

    Output rows (under original column headers):
      Row 1: Column Name  (sap:label from XML, falls back to property name)
      Row 2: Description  (original row 2 from template)
      Row 3: Type         (friendly type name)
      Row 4: Mandatory    (true/false from sap:required)
      Row 5: Max Length

    Returns (DataFrame, matched_entity_type_name).
    """
    # Find best EntityType for this template
    best_et = find_best_entity_type(property_names, entity_lookup, country)
    entity_props = entity_lookup.get(best_et) if best_et else None

    column_names = []
    types = []
    mandatories = []
    max_lengths = []

    for prop_name in property_names:
        meta = lookup_property(prop_name, entity_props, global_lookup)
        if meta:
            column_names.append(meta["label"] if meta["label"] else prop_name)
            types.append(friendly_type(meta["type"]))
            mandatories.append(meta["required"] if meta["required"] else "false")
            max_lengths.append(meta["max_length"])
        else:
            column_names.append(prop_name)
            types.append("")
            mandatories.append("")
            max_lengths.append("")

    # Pad / trim descriptions to match column count
    desc = descriptions + [""] * (len(property_names) - len(descriptions))
    desc = desc[: len(property_names)]

    # Filter country-specific descriptions
    if country:
        desc = [_filter_country_description(d, country) for d in desc]

    data = {
        prop_name: [col_name, desc[i], typ, mand, maxl]
        for i, (prop_name, col_name, typ, mand, maxl) in enumerate(
            zip(property_names, column_names, types, mandatories, max_lengths)
        )
    }

    df = pd.DataFrame(data, index=["Column Name", "Description", "Type", "Mandatory", "Max Length"])
    return df, best_et


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Export a DataFrame to CSV bytes (UTF-8 with BOM for Excel compat)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return ("\ufeff" + buf.getvalue()).encode("utf-8-sig")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Export a DataFrame to XLSX bytes."""
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
        help="Used to prefer country-specific EntityTypes and filter descriptions.",
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
        name, row1, row2, valid = read_template(uf)
        if valid:
            templates.append({"name": name, "property_names": row1, "descriptions": row2})
        else:
            flagged.append(name)

    if flagged:
        st.warning(
            f"The following files do not contain exactly 2 rows and were flagged: "
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

    # ---- Preview templates ----
    with st.expander("Preview uploaded templates", expanded=False):
        for t in templates:
            st.subheader(t["name"])
            preview_df = pd.DataFrame(
                [t["property_names"], t["descriptions"]],
                index=["Property Names", "Descriptions"],
            )
            st.dataframe(preview_df, use_container_width=True)

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
            )
            results.append({"name": t["name"], "df": result_df, "entity_type": matched_et})
            progress.progress((i + 1) / len(templates), text=f"Processed {t['name']}")

        st.session_state["results"] = results
        st.success(f"Transformed **{len(results)}** template(s).")

    # ---- Step 5: Display results & download ----
    if "results" in st.session_state and st.session_state["results"]:
        results = st.session_state["results"]

        st.header("6. Results")

        # Show unmatched properties summary
        for r in results:
            df = r["df"]
            unmatched = [col for col in df.columns if df[col].iloc[0] == col and df[col].iloc[2] == ""]
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
