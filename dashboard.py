"""
AdWatch Dashboard — Streamlit frontend.
Run: uv run streamlit run dashboard.py
Requires the FastAPI server to be running on API_BASE (default http://127.0.0.1:8000).
"""

import json
import os
import re

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
        st.error("⚠️ Cannot reach the AdWatch API. Make sure the API service is running.")
        st.stop()
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:300]}")
        return None


def domain_to_brand(domain: str) -> str:
    """ikea.com.sg → Ikea,  rival-agency.sg → Rival Agency"""
    host = domain.lower().lstrip("www.").split(".")[0]
    return re.sub(r"[-_]", " ", host).title()


def brand_to_domain(brand: str) -> str:
    """IKEA → ikea.com,  Rival Agency → rival-agency.com"""
    slug = re.sub(r"\s+", "-", brand.strip().lower())
    return f"{slug}.com"


def autofill_ids(domain: str | None, name: str | None) -> dict:
    """Call both resolve endpoints, return {meta_page_id, google_advertiser_id}."""
    result = {"meta_page_id": None, "google_advertiser_id": None, "messages": []}

    params = {}
    if domain:
        params["domain"] = domain
    elif name:
        params["name"] = name
    else:
        return result

    meta = api("GET", "/resolve/meta", params=params)
    if meta:
        result["meta_page_id"] = meta.get("platform_id")
        result["messages"].append(f"Meta: {meta.get('message','')}")

    goog = api("GET", "/resolve/google", params=params)
    if goog:
        result["google_advertiser_id"] = goog.get("platform_id")
        result["messages"].append(f"Google: {goog.get('message','')}")

    return result


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

    # ── Session state keys for the add-client form ──
    for k, v in [
        ("nc_name", ""), ("nc_domain", ""),
        ("nc_page_id", ""), ("nc_goog_id", ""), ("nc_notes", ""),
        ("nc_expander_open", False),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    with st.expander("➕ Add client", expanded=st.session_state["nc_expander_open"]):

        acol1, acol2, acol3 = st.columns([3, 3, 2])
        # Use key= matching session_state slot; no value= so Streamlit owns the state
        acol1.text_input("Brand name *", key="nc_name", placeholder="e.g. Ikea")
        acol2.text_input("Landing domain *", key="nc_domain", placeholder="e.g. ikea.com.sg")
        with acol3:
            st.write("")
            st.write("")
            bc1, bc2 = st.columns(2)
            if bc1.button("Name→URL", key="nc_name2url", help="Suggest domain from brand name"):
                if st.session_state["nc_name"]:
                    st.session_state["nc_domain"] = brand_to_domain(st.session_state["nc_name"])
                    st.session_state["nc_expander_open"] = True
                    st.rerun()
            if bc2.button("URL→Name", key="nc_url2name", help="Suggest brand name from domain"):
                if st.session_state["nc_domain"]:
                    st.session_state["nc_name"] = domain_to_brand(st.session_state["nc_domain"])
                    st.session_state["nc_expander_open"] = True
                    st.rerun()

        st.text_input("Meta page ID", key="nc_page_id", placeholder="auto-filled or enter manually")
        st.text_input("Google advertiser ID", key="nc_goog_id", placeholder="auto-filled or enter manually")
        st.text_area("Notes", key="nc_notes", height=60)

        btnA, btnB, btnC = st.columns([2, 2, 2])
        if btnA.button("🔍 Auto-fill IDs", key="nc_autofill", use_container_width=True):
            with st.spinner("Looking up IDs…"):
                filled = autofill_ids(
                    st.session_state["nc_domain"] or None,
                    st.session_state["nc_name"] or None,
                )
            if filled["meta_page_id"]:
                st.session_state["nc_page_id"] = filled["meta_page_id"]
            if filled["google_advertiser_id"]:
                st.session_state["nc_goog_id"] = filled["google_advertiser_id"]
            for msg in filled["messages"]:
                st.caption(msg)
            st.session_state["nc_expander_open"] = True
            st.rerun()

        if btnB.button("✅ Add client", key="nc_submit", type="primary", use_container_width=True):
            if not st.session_state["nc_name"] or not st.session_state["nc_domain"]:
                st.error("Brand name and domain are required.")
            else:
                result = api("POST", "/clients", json={
                    "name": st.session_state["nc_name"],
                    "landing_domain": st.session_state["nc_domain"],
                    "meta_page_id": st.session_state["nc_page_id"] or None,
                    "google_advertiser_id": st.session_state["nc_goog_id"] or None,
                    "notes": st.session_state["nc_notes"] or None,
                })
                if result:
                    st.success(f"✅ Added: {result['name']}")
                    for k in ["nc_name", "nc_domain", "nc_page_id", "nc_goog_id", "nc_notes"]:
                        st.session_state[k] = ""
                    st.session_state["nc_expander_open"] = False
                    st.rerun()

        if btnC.button("🔄 Clear", key="nc_clear", use_container_width=True):
            for k in ["nc_name", "nc_domain", "nc_page_id", "nc_goog_id", "nc_notes"]:
                st.session_state[k] = ""
            st.session_state["nc_expander_open"] = True
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
                    ("Meta: `" + c["meta_page_id"] + "`" if c.get("meta_page_id") else "⚠️ No Meta page ID") +
                    ("   |   Google: `" + c["google_advertiser_id"] + "`" if c.get("google_advertiser_id") else "")
                )
                if col3.button("🗑", key=f"del_client_{c['id']}", help="Delete"):
                    api("DELETE", f"/clients/{c['id']}")
                    st.rerun()

                with st.expander("✏️ Edit platform IDs", expanded=not c.get("meta_page_id")):
                    ecol1, ecol2, ecol3 = st.columns([3, 3, 2])
                    new_page_id = ecol1.text_input(
                        "Meta page ID", value=c.get("meta_page_id") or "",
                        key=f"mpid_{c['id']}", placeholder="e.g. 123456789",
                    )
                    new_goog_id = ecol2.text_input(
                        "Google advertiser ID", value=c.get("google_advertiser_id") or "",
                        key=f"ggid_c_{c['id']}", placeholder="e.g. AR12345678901234567",
                    )
                    bcol1, bcol2 = ecol3.columns(2)
                    if bcol1.button("💾 Save", key=f"save_cids_{c['id']}"):
                        r = api("PATCH", f"/clients/{c['id']}/ids", json={
                            "meta_page_id": new_page_id or None,
                            "google_advertiser_id": new_goog_id or None,
                        })
                        if r:
                            st.success("Saved.")
                            st.rerun()
                    if bcol2.button("🔍 Auto-fill", key=f"lookup_c_{c['id']}"):
                        with st.spinner("Looking up…"):
                            filled = autofill_ids(c["landing_domain"], c["name"])
                        patch = {}
                        if filled["meta_page_id"]:
                            patch["meta_page_id"] = filled["meta_page_id"]
                        if filled["google_advertiser_id"]:
                            patch["google_advertiser_id"] = filled["google_advertiser_id"]
                        if patch:
                            api("PATCH", f"/clients/{c['id']}/ids", json=patch)
                            st.success(f"Auto-filled: {patch}")
                            st.rerun()
                        else:
                            for msg in filled["messages"]:
                                st.warning(msg)

# ---------------------------------------------------------------------------
# PAGE: Competitors
# ---------------------------------------------------------------------------

elif page == "Competitors":
    st.title("Competitors")
    st.caption("Agencies and brands to monitor. Queried by registration name or brand domain.")

    for k, v in [
        ("nc_disp", ""), ("nc_reg", ""), ("nc_type", "brand"),
        ("nc_bdomain", ""), ("nc_cpid", ""), ("nc_cgid", ""),
        ("cc_expander_open", False),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    with st.expander("➕ Add competitor", expanded=st.session_state["cc_expander_open"]):

        ccol1, ccol2, ccol3 = st.columns([3, 3, 2])
        ccol1.text_input("Display name *", key="nc_disp", placeholder="Rival Agency")
        ccol2.text_input("Brand domain", key="nc_bdomain", placeholder="rival.sg")
        with ccol3:
            st.write("")
            st.write("")
            bc1, bc2 = st.columns(2)
            if bc1.button("Name→URL", key="cc_name2url"):
                if st.session_state["nc_disp"]:
                    st.session_state["nc_bdomain"] = brand_to_domain(st.session_state["nc_disp"])
                    st.session_state["cc_expander_open"] = True
                    st.rerun()
            if bc2.button("URL→Name", key="cc_url2name"):
                if st.session_state["nc_bdomain"]:
                    st.session_state["nc_disp"] = domain_to_brand(st.session_state["nc_bdomain"])
                    st.session_state["cc_expander_open"] = True
                    st.rerun()

        st.text_input("Registration / advertiser name *", key="nc_reg", placeholder="Rival Pte Ltd")
        st.selectbox("Type", ["brand", "agency"], key="nc_type")
        st.text_input("Meta page ID", key="nc_cpid", placeholder="auto-filled or enter manually")
        st.text_input("Google advertiser ID", key="nc_cgid", placeholder="auto-filled or enter manually")

        cb1, cb2, cb3 = st.columns([2, 2, 2])
        if cb1.button("🔍 Auto-fill IDs", key="cc_autofill", use_container_width=True):
            with st.spinner("Looking up…"):
                filled = autofill_ids(
                    st.session_state["nc_bdomain"] or None,
                    st.session_state["nc_disp"] or None,
                )
            if filled["meta_page_id"]:
                st.session_state["nc_cpid"] = filled["meta_page_id"]
            if filled["google_advertiser_id"]:
                st.session_state["nc_cgid"] = filled["google_advertiser_id"]
            for msg in filled["messages"]:
                st.caption(msg)
            st.session_state["cc_expander_open"] = True
            st.rerun()

        if cb2.button("✅ Add competitor", key="cc_submit", type="primary", use_container_width=True):
            if not st.session_state["nc_disp"] or not st.session_state["nc_reg"]:
                st.error("Display name and registration name are required.")
            else:
                result = api("POST", "/competitors", json={
                    "display_name": st.session_state["nc_disp"],
                    "registration_name": st.session_state["nc_reg"],
                    "type": st.session_state["nc_type"],
                    "brand_domain": st.session_state["nc_bdomain"] or None,
                    "meta_page_id": st.session_state["nc_cpid"] or None,
                    "google_advertiser_id": st.session_state["nc_cgid"] or None,
                })
                if result:
                    st.success(f"✅ Added: {result['display_name']}")
                    for k in ["nc_disp", "nc_reg", "nc_bdomain", "nc_cpid", "nc_cgid"]:
                        st.session_state[k] = ""
                    st.session_state["cc_expander_open"] = False
                    st.rerun()

        if cb3.button("🔄 Clear", key="cc_clear", use_container_width=True):
            for k in ["nc_disp", "nc_reg", "nc_bdomain", "nc_cpid", "nc_cgid"]:
                st.session_state[k] = ""
            st.session_state["cc_expander_open"] = True
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
                    (c.get("brand_domain") or "No domain") +
                    ("  |  Meta: `" + c["meta_page_id"] + "`" if c.get("meta_page_id") else "  |  ⚠️ No Meta ID")
                )
                if col3.button("🗑", key=f"del_comp_{c['id']}", help="Delete"):
                    api("DELETE", f"/competitors/{c['id']}")
                    st.rerun()

                with st.expander("✏️ Edit platform IDs", expanded=not c.get("meta_page_id")):
                    ecol1, ecol2, ecol3 = st.columns([3, 3, 2])
                    new_page_id = ecol1.text_input(
                        "Meta page ID", value=c.get("meta_page_id") or "",
                        key=f"mpid_comp_{c['id']}", placeholder="e.g. 123456789",
                    )
                    new_goog_id = ecol2.text_input(
                        "Google advertiser ID", value=c.get("google_advertiser_id") or "",
                        key=f"ggid_comp_{c['id']}",
                    )
                    bcol1, bcol2 = ecol3.columns(2)
                    if bcol1.button("💾 Save", key=f"save_compids_{c['id']}"):
                        r = api("PATCH", f"/competitors/{c['id']}/ids", json={
                            "meta_page_id": new_page_id or None,
                            "google_advertiser_id": new_goog_id or None,
                        })
                        if r:
                            st.success("Saved.")
                            st.rerun()
                    lookup_domain = c.get("brand_domain")
                    lookup_name = c.get("display_name")
                    if bcol2.button("🔍 Auto-fill", key=f"lookup_comp_{c['id']}"):
                        with st.spinner("Looking up…"):
                            filled = autofill_ids(lookup_domain, lookup_name)
                        patch = {}
                        if filled["meta_page_id"]:
                            patch["meta_page_id"] = filled["meta_page_id"]
                        if filled["google_advertiser_id"]:
                            patch["google_advertiser_id"] = filled["google_advertiser_id"]
                        if patch:
                            api("PATCH", f"/competitors/{c['id']}/ids", json=patch)
                            st.success(f"Auto-filled: {patch}")
                            st.rerun()
                        else:
                            for msg in filled["messages"]:
                                st.warning(msg)

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

    runs = api("GET", "/runs", params=params) or []
    if filter_status != "(all)":
        runs = [r for r in runs if r["status"] == filter_status]

    if not runs:
        st.info("No runs yet. Trigger a refresh from the Dashboard.")
    else:
        rows = []
        for r in runs:
            rows.append({
                "When":      r["ran_at"][:19].replace("T", " "),
                "Connector": CONNECTOR_DISPLAY.get(r["connector"], r["connector"]),
                "Subject":   f"{r['subject_type']} #{r['subject_id']}",
                "Dimension": r["query_dimension"],
                "Value":     r["query_value"],
                "Status":    STATUS_COLOUR.get(r["status"], "❓") + " " + r["status"],
                "Count":     r["result_count"],
                "Message":   r["message"][:120],
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# PAGE: Dashboard (default)
# ---------------------------------------------------------------------------

else:
    st.title("Dashboard")

    clients     = api("GET", "/clients") or []
    competitors = api("GET", "/competitors") or []

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
        date_min = rcol3.text_input(
            "From date", value="",
            placeholder="YYYY-MM-DD — leave blank for all time",
        )
        date_max = rcol4.text_input(
            "To date", value="",
            placeholder="YYYY-MM-DD — leave blank for all time",
        )
        run_refresh = st.form_submit_button("▶ Refresh now", type="primary", use_container_width=True)

    if run_refresh:
        payload: dict = {
            "country": country,
            "date_min": date_min.strip() or None,
            "date_max": date_max.strip() or None,
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
            if isinstance(data.get("results"), list):
                all_results = data["results"]
            else:
                all_results = []
                for v in data.get("results", {}).values():
                    all_results.extend(v)

            st.markdown("**Coverage summary**")
            for r in all_results:
                icon  = STATUS_COLOUR.get(r["status"], "❓")
                label = CONNECTOR_DISPLAY.get(r["connector"], r["connector"])
                manual = r.get("manual_url")
                link  = f" [→ open UI]({manual})" if manual else ""
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
