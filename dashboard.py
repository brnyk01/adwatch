"""
AdWatch Dashboard — Streamlit frontend.
Run: uv run streamlit run dashboard.py
Requires the FastAPI server to be running on API_BASE (default http://127.0.0.1:8000).
"""

import json
import os

import requests
import streamlit as st

API_BASE = os.getenv("ADWATCH_API", "http://127.0.0.1:8000").rstrip("/")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATUS_COLOUR = {
    "ok":               "🟢",
    "no_data":          "🟡",
    "no_official_api":  "⚫",
    "error":            "🔴",
}

STATUS_LABEL = {
    "ok":               "Official data retrieved",
    "no_data":          "No data returned (expected for non-EU)",
    "no_official_api":  "No official API — open UI link",
    "error":            "Error (check credentials)",
}

CONNECTOR_DISPLAY = {
    "meta":       "Meta (Facebook / Instagram)",
    "google_bq":  "Google BigQuery (EEA)",
    "google_ui":  "Google Transparency UI",
    "tiktok":     "TikTok",
    "snapchat":   "Snapchat (political)",
    "linkedin":   "LinkedIn",
    "x":          "X (Twitter)",
    "pinterest":  "Pinterest",
    "reddit":     "Reddit",
    "amazon":     "Amazon",
    "bing":       "Microsoft / Bing",
}


def api(method: str, path: str, **kwargs):
    try:
        r = requests.request(method, f"{API_BASE}{path}", timeout=120, **kwargs)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot reach the AdWatch API. Make sure `uvicorn adwatch.api:app` is running.")
        st.stop()
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
        return None


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AdWatch",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .stButton > button { border-radius: 8px; }
    div[data-testid="metric-container"] { background: #f8f9fb; border-radius: 10px; padding: 0.5rem 1rem; }
    .coverage-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar nav
# ---------------------------------------------------------------------------

st.sidebar.title("📡 AdWatch")
st.sidebar.caption("Ad Transparency Monitor")
page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Clients", "Competitors", "Run History"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption(f"API: `{API_BASE}`")

# ---------------------------------------------------------------------------
# PAGE: Clients
# ---------------------------------------------------------------------------

if page == "Clients":
    st.title("Clients")
    st.caption("Brands you manage. Ads are fetched by landing domain or Meta page ID.")

    with st.expander("➕ Add client", expanded=False):
        with st.form("add_client"):
            name         = st.text_input("Brand name *")
            domain       = st.text_input("Landing domain *", placeholder="example.com")
            page_id      = st.text_input("Meta page ID (optional)", placeholder="123456789")
            goog_id      = st.text_input("Google advertiser ID (optional)")
            notes        = st.text_area("Notes", height=80)
            submitted    = st.form_submit_button("Add client")
        if submitted:
            if not name or not domain:
                st.error("Brand name and domain are required.")
            else:
                result = api("POST", "/clients", json={
                    "name": name, "landing_domain": domain,
                    "meta_page_id": page_id or None,
                    "google_advertiser_id": goog_id or None,
                    "notes": notes or None,
                })
                if result:
                    st.success(f"✅ Added client: {result['name']} (id {result['id']})")
                    st.rerun()

    clients = api("GET", "/clients") or []
    if not clients:
        st.info("No clients yet. Add one above.")
    else:
        for c in clients:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 3, 1])
                col1.markdown(f"**{c['name']}**  \n`{c['landing_domain']}`")
                col2.caption(
                    ("Meta page: `" + c["meta_page_id"] + "`" if c.get("meta_page_id") else "⚠️ No Meta page ID") +
                    ("   |   Google: `" + c["google_advertiser_id"] + "`" if c.get("google_advertiser_id") else "")
                )
                if col3.button("🗑", key=f"del_client_{c['id']}", help="Delete client"):
                    api("DELETE", f"/clients/{c['id']}")
                    st.rerun()

                # Inline ID editor
                with st.expander("✏️ Edit platform IDs", expanded=not c.get("meta_page_id")):
                    ecol1, ecol2, ecol3 = st.columns([3, 3, 2])
                    new_page_id = ecol1.text_input(
                        "Meta page ID",
                        value=c.get("meta_page_id") or "",
                        key=f"mpid_{c['id']}",
                        placeholder="e.g. 123456789",
                    )
                    new_goog_id = ecol2.text_input(
                        "Google advertiser ID",
                        value=c.get("google_advertiser_id") or "",
                        key=f"ggid_c_{c['id']}",
                        placeholder="e.g. AR12345678901234567",
                    )
                    bcol1, bcol2 = ecol3.columns(2)
                    if bcol1.button("💾", key=f"save_cids_{c['id']}", help="Save IDs"):
                        result = api("PATCH", f"/clients/{c['id']}/ids", json={
                            "meta_page_id": new_page_id or None,
                            "google_advertiser_id": new_goog_id or None,
                        })
                        if result:
                            st.success("Saved.")
                            st.rerun()
                    if bcol2.button("🔍", key=f"lookup_c_{c['id']}", help="Lookup Meta page ID from domain"):
                        with st.spinner("Looking up Meta page ID…"):
                            r = api("GET", "/resolve/meta", params={"domain": c["landing_domain"]})
                        if r and r.get("page_id"):
                            api("PATCH", f"/clients/{c['id']}/ids", json={"meta_page_id": r["page_id"]})
                            st.success(f"Found & saved: {r['page_id']}")
                            st.rerun()
                        else:
                            st.warning(r.get("message", "Not found — enter manually."))

# ---------------------------------------------------------------------------
# PAGE: Competitors
# ---------------------------------------------------------------------------

elif page == "Competitors":
    st.title("Competitors")
    st.caption("Agencies and brands to monitor. Queried by registration name or brand domain.")

    with st.expander("➕ Add competitor", expanded=False):
        with st.form("add_competitor"):
            display_name = st.text_input("Display name *", placeholder="Rival Agency")
            reg_name     = st.text_input("Registration / advertiser name *", placeholder="Rival Pte Ltd")
            ctype        = st.selectbox("Type", ["agency", "brand"])
            brand_domain = st.text_input("Brand domain (optional)", placeholder="rival.sg")
            page_id      = st.text_input("Meta page ID (optional)")
            goog_id      = st.text_input("Google advertiser ID (optional)")
            submitted    = st.form_submit_button("Add competitor")
        if submitted:
            if not display_name or not reg_name:
                st.error("Display name and registration name are required.")
            else:
                result = api("POST", "/competitors", json={
                    "display_name": display_name,
                    "registration_name": reg_name,
                    "type": ctype,
                    "brand_domain": brand_domain or None,
                    "meta_page_id": page_id or None,
                    "google_advertiser_id": goog_id or None,
                })
                if result:
                    st.success(f"✅ Added competitor: {result['display_name']} (id {result['id']})")
                    st.rerun()

    competitors = api("GET", "/competitors") or []
    if not competitors:
        st.info("No competitors yet. Add one above.")
    else:
        for c in competitors:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 3, 1])
                col1.markdown(f"**{c['display_name']}**  \n`{c['registration_name']}` · {c['type']}")
                col2.caption(
                    (c.get("brand_domain") or "No domain set") +
                    ("  |  Meta: `" + c["meta_page_id"] + "`" if c.get("meta_page_id") else "  |  ⚠️ No Meta page ID")
                )
                if col3.button("🗑", key=f"del_comp_{c['id']}", help="Delete competitor"):
                    api("DELETE", f"/competitors/{c['id']}")
                    st.rerun()

                with st.expander("✏️ Edit platform IDs", expanded=not c.get("meta_page_id")):
                    ecol1, ecol2, ecol3 = st.columns([3, 3, 2])
                    new_page_id = ecol1.text_input(
                        "Meta page ID",
                        value=c.get("meta_page_id") or "",
                        key=f"mpid_comp_{c['id']}",
                        placeholder="e.g. 123456789",
                    )
                    new_goog_id = ecol2.text_input(
                        "Google advertiser ID",
                        value=c.get("google_advertiser_id") or "",
                        key=f"ggid_comp_{c['id']}",
                    )
                    bcol1, bcol2 = ecol3.columns(2)
                    if bcol1.button("💾", key=f"save_compids_{c['id']}", help="Save IDs"):
                        result = api("PATCH", f"/competitors/{c['id']}/ids", json={
                            "meta_page_id": new_page_id or None,
                            "google_advertiser_id": new_goog_id or None,
                        })
                        if result:
                            st.success("Saved.")
                            st.rerun()
                    lookup_domain = c.get("brand_domain") or c.get("registration_name")
                    if bcol2.button("🔍", key=f"lookup_comp_{c['id']}", help="Lookup Meta page ID"):
                        with st.spinner("Looking up…"):
                            param = "domain" if c.get("brand_domain") else "name"
                            r = api("GET", "/resolve/meta", params={param: lookup_domain})
                        if r and r.get("page_id"):
                            api("PATCH", f"/competitors/{c['id']}/ids", json={"meta_page_id": r["page_id"]})
                            st.success(f"Found & saved: {r['page_id']}")
                            st.rerun()
                        else:
                            st.warning(r.get("message", "Not found — enter manually."))

# ---------------------------------------------------------------------------
# PAGE: Run History
# ---------------------------------------------------------------------------

elif page == "Run History":
    st.title("Run History")
    st.caption("Every connector call logged here — status, result count, message.")

    col1, col2 = st.columns(2)
    filter_connector = col1.selectbox("Filter by connector", ["(all)"] + list(CONNECTOR_DISPLAY.keys()))
    filter_status    = col2.selectbox("Filter by status", ["(all)", "ok", "no_data", "no_official_api", "error"])

    params: dict = {"limit": 100}
    if filter_connector != "(all)":
        params["connector"] = filter_connector
    if filter_status != "(all)":
        params["status"] = filter_status

    runs = api("GET", "/runs", params=params) or []
    if not runs:
        st.info("No runs yet. Trigger a refresh from the Dashboard.")
    else:
        rows = []
        for r in runs:
            rows.append({
                "When":        r["ran_at"][:19].replace("T", " "),
                "Connector":   CONNECTOR_DISPLAY.get(r["connector"], r["connector"]),
                "Subject":     f"{r['subject_type']} #{r['subject_id']}",
                "Dimension":   r["query_dimension"],
                "Value":       r["query_value"],
                "Status":      STATUS_COLOUR.get(r["status"], "❓") + " " + r["status"],
                "Count":       r["result_count"],
                "Message":     r["message"][:120],
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# PAGE: Dashboard (default)
# ---------------------------------------------------------------------------

else:
    st.title("Dashboard")

    clients     = api("GET", "/clients") or []
    competitors = api("GET", "/competitors") or []

    # ── Metrics row ──────────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Clients", len(clients))
    m2.metric("Competitors", len(competitors))
    total_ads = len(api("GET", "/ads", params={"limit": 500}) or [])
    m3.metric("Ads in DB", total_ads)

    st.divider()

    # ── Refresh controls ──────────────────────────────────────────────────────
    st.subheader("🔄 Refresh")

    with st.form("refresh_form"):
        rcol1, rcol2, rcol3, rcol4 = st.columns([2, 2, 2, 2])

        subject_opts = ["All"] + \
            [f"Client: {c['name']} (#{c['id']})" for c in clients] + \
            [f"Competitor: {c['display_name']} (#{c['id']})" for c in competitors]
        subject_sel = rcol1.selectbox("Subject", subject_opts)

        country = rcol2.text_input("Country", value="SG").upper()
        date_min = rcol3.text_input("From date (YYYY-MM-DD)", value="")
        date_max = rcol4.text_input("To date (YYYY-MM-DD)", value="")

        run_refresh = st.form_submit_button("▶ Refresh now", type="primary", use_container_width=True)

    if run_refresh:
        payload: dict = {
            "country": country,
            "date_min": date_min or None,
            "date_max": date_max or None,
        }
        if subject_sel != "All":
            kind, rest = subject_sel.split(": ", 1)
            sid = int(rest.split("(#")[1].rstrip(")"))
            payload["subject_type"] = kind.lower()
            payload["subject_id"] = sid

        with st.spinner("Running connectors…"):
            data = api("POST", "/refresh", json=payload)

        if data:
            st.success("Refresh complete.")
            # Flatten results for display
            if "results" in data and isinstance(data["results"], list):
                all_results = data["results"]
            else:
                all_results = []
                for v in data.get("results", {}).values():
                    all_results.extend(v)

            st.markdown("**Coverage summary**")
            for r in all_results:
                icon = STATUS_COLOUR.get(r["status"], "❓")
                label = CONNECTOR_DISPLAY.get(r["connector"], r["connector"])
                manual = r.get("manual_url")
                link = f" [→ open UI]({manual})" if manual else ""
                st.markdown(f"{icon} **{label}** — {r['message'][:100]}{link}")

    st.divider()

    # ── Ads by subject ────────────────────────────────────────────────────────
    st.subheader("📋 Ads")

    tab_clients, tab_competitors = st.tabs([
        f"Clients ({len(clients)})",
        f"Competitors ({len(competitors)})",
    ])

    def render_ads(subject_type: str, subjects: list):
        if not subjects:
            st.info(f"No {subject_type}s yet.")
            return
        sel = st.selectbox(
            f"Select {subject_type}",
            subjects,
            format_func=lambda x: x.get("name") or x.get("display_name"),
            key=f"sel_{subject_type}",
        )
        if not sel:
            return

        filter_platform = st.selectbox(
            "Filter by platform",
            ["(all)"] + list(CONNECTOR_DISPLAY.keys()),
            key=f"plat_{subject_type}",
        )

        params: dict = {"subject_type": subject_type, "subject_id": sel["id"], "limit": 200}
        if filter_platform != "(all)":
            params["platform"] = filter_platform

        ads = api("GET", "/ads", params=params) or []
        st.caption(f"{len(ads)} ad(s) stored for **{sel.get('name') or sel.get('display_name')}**")

        if not ads:
            st.info("No ads stored yet. Hit **Refresh now** above to pull data.")
            return

        for ad in ads:
            with st.container(border=True):
                acol1, acol2 = st.columns([3, 1])
                with acol1:
                    plat_label = CONNECTOR_DISPLAY.get(ad["platform"], ad["platform"])
                    st.markdown(f"**{plat_label}** · `{ad['external_ad_id']}`")
                    if ad.get("creative_text"):
                        st.markdown(f"> {ad['creative_text'][:200]}")
                    meta_parts = []
                    if ad.get("advertiser_name"):
                        meta_parts.append(f"📢 {ad['advertiser_name']}")
                    if ad.get("landing_domain"):
                        meta_parts.append(f"🔗 {ad['landing_domain']}")
                    if ad.get("first_shown"):
                        meta_parts.append(f"📅 {ad['first_shown'][:10]} → {(ad.get('last_shown') or '')[:10] or 'active'}")
                    if ad.get("spend_range"):
                        try:
                            s = json.loads(ad["spend_range"])
                            meta_parts.append(f"💰 {s.get('lower_bound','?')}–{s.get('upper_bound','?')} {s.get('currency','')}")
                        except Exception:
                            pass
                    st.caption("  ·  ".join(meta_parts))
                with acol2:
                    if ad.get("snapshot_url"):
                        st.markdown(f"[🖼 View creative]({ad['snapshot_url']})")
                    st.caption(f"Fetched: {ad['fetched_at'][:10]}")

    with tab_clients:
        render_ads("client", clients)

    with tab_competitors:
        render_ads("competitor", competitors)
