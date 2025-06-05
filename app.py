import io
import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

# ─── CONFIG ──────────────────────────────────────────────────────────────────
LOGIN_URL = 'http://webpage.boledragon.com:8080/accounts/login/'
QUERY_URL = 'http://webpage.boledragon.com:8080/forever_new/query/'

# Pull credentials from Streamlit secrets (we’ll configure these later)
USER = st.secrets["credentials"]["username"]
PASS = st.secrets["credentials"]["password"]

# ─── HELPER: fetch a single user’s details (same as your earlier code) ─────────
def fetch_user(session, uid):
    # 1) GET the query page to refresh CSRF token
    qpg = session.get(QUERY_URL)
    soup_q = BeautifulSoup(qpg.text, 'html.parser')
    csrf_q = soup_q.find('input', {'name':'csrfmiddlewaretoken'})['value']

    # 2) POST the user_id
    resp = session.post(
        QUERY_URL,
        data={'csrfmiddlewaretoken': csrf_q, 'user_id': uid},
        headers={'Referer': QUERY_URL}
    )
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 3) Find the “User properties” table and extract rows
    tbl = soup.find('p', string=lambda t: 'User properties' in t) \
              .find_next_sibling('table')
    rows = tbl.find_all('tr')

    out = {'queried_user_id': uid}

    # First header/data (rows 0 & 1)
    if len(rows) >= 2:
        keys  = [th.get_text(strip=True) for th in rows[0].find_all('th')]
        vals  = [td.get_text(strip=True) for td in rows[1].find_all('td')]
        out.update(zip(keys, vals))

    # Second header/data (rows 2 & 3)
    if len(rows) >= 4:
        keys2 = [th.get_text(strip=True) for th in rows[2].find_all('th')]
        vals2 = [td.get_text(strip=True) for td in rows[3].find_all('td')]
        out.update(zip(keys2, vals2))

    return out


# ─── STREAMLIT UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Survey Logic Helper", layout="wide")
st.title("Survey Logic Helper")

# 1) File Uploader: let user import their survey‐logic Excel
uploaded = st.file_uploader("Upload your survey‐structure Excel (.xlsx)", type="xlsx")

if uploaded:
    # ─── 2) Parse Excel into question/answer structure ───────────────────────
    df = pd.read_excel(uploaded, dtype={"contents": str, "qa_mark": int})

    questions = []
    q_counter = 0
    a_counter = 0
    current_q = None

    for _, row in df.iterrows():
        text = str(row["contents"]).strip()
        mark = int(row["qa_mark"])

        if mark == 1:
            # This is a Question
            q_counter += 1
            a_counter = 0
            qid = f"Q{q_counter}"
            current_q = {"qid": qid, "text": text, "answers": []}
            questions.append(current_q)
        else:
            # This is an Answer to the most recent question
            if current_q is None:
                continue  # safety check, but normally every A follows a Q
            a_counter += 1
            aid = f"{current_q['qid']}A{a_counter}"
            current_q["answers"].append({"aid": aid, "text": text})

    # Build a lookup of question display strings for the dropdown
    # e.g. "Q2: What's your favorite animal?"
    question_display_map = {
        q["qid"]: f"{q['qid']}: {q['text']}" for q in questions
    }

    # Prepare a list of dropdown‐options for every answer
    # First option is "" (no jump), second is "End", then each question string
    dropdown_items = ["", "End"] + list(question_display_map.values())

    # ─── 3) Render UI for each question & its answers ─────────────────────────
    st.markdown("## Define your conditional‐logic rules")
    st.markdown(
        "For each **Answer** (A), choose what **Question** (Q) comes next. "
        "Leave blank → no jump. Select **End** → survey terminates."
    )
    st.write("---")

    logic_map = {}  # will store mapping: { "Q2A1": "Q3" or "END" }

    for q in questions:
        st.markdown(f"### {q['qid']}: {q['text']}")
        if not q["answers"]:
            st.markdown("_This question has no answer options._")
        else:
            for ans in q["answers"]:
                aid = ans["aid"]
                label = f"• {aid} → \"{ans['text']}\""
                # Use a unique Streamlit key so dropdowns don’t clash
                sel = st.selectbox(
                    label,
                    options=dropdown_items,
                    key=aid,  # ensures each dropdown is tracked separately
                    help="(default: blank = no jump, 'End' = terminate survey)"
                )
                if sel == "":
                    logic_map[aid] = None
                elif sel == "End":
                    logic_map[aid] = "END"
                else:
                    # sel is something like "Q3: Do you like Subaru or Volvo?"
                    target_qid = sel.split(":")[0]
                    logic_map[aid] = target_qid

        st.write("")  # a tiny spacer

    st.write("---")

    # ─── 4) Export or Edit buttons ────────────────────────────────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Export Logic as .txt"):
            # Build the lines of logic
            lines = []
            for aid, tgt in logic_map.items():
                if tgt == "END":
                    lines.append(f"if {aid} then end")
                elif tgt:  # not None and not "END"
                    lines.append(f"if {aid} then show {tgt}")
            export_text = "\n".join(lines)

            # Show a text area with the result
            st.text_area("Exported Logic", value=export_text, height=200)

            # Provide a download button
            st.download_button(
                label="Download logic (.txt)",
                data=export_text,
                file_name="survey_logic.txt",
                mime="text/plain"
            )

    with col2:
        if st.button("Re-import Another Excel"):
            st.experimental_rerun()

    # ─── 5) (Optional) Bulk User-ID Fetch Section ────────────────────────────
    # If you also want the old “bulk user-ID detail fetch” feature in the same app,
    # uncomment the following block and place it where it belongs. Otherwise, omit.
    #
    # st.write("---")
    # st.markdown("## (Optional) Bulk User-ID Detail Fetcher")
    # 
    # #—- same login/widgets/fetch logic from your previous Streamlit tool —-
    # 
    # uploaded_ids = st.file_uploader("Upload input_ids.xlsx", type="xlsx", key="ids")
    # if uploaded_ids:
    #     df_ids = pd.read_excel(uploaded_ids, dtype=str).iloc[:, 0].tolist()
    #     session = requests.Session()
    #     # … do the login, ThreadPoolExecutor(fetch_user, ...) and then
    #     # out_df = pd.DataFrame(results)
    #     # buffer = io.BytesIO()
    #     # out_df.to_excel(buffer, index=False, engine="openpyxl")
    #     # buffer.seek(0)
    #     # st.download_button("Download results.xlsx", buffer.getvalue(), "results.xlsx",
    #     #                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    #

