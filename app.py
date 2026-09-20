import sys
import json
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

import streamlit as st
import base64

ROOT = Path(__file__).parent
DATA = ROOT / "advisor" / "data"
CHAT_FILE = DATA / "private" / "chats.json"

CREATOR_URL = "https://faizackhan.github.io"
REPO_URL = "https://github.com/faizackhan/VisionLLM"

st.set_page_config(page_title="Vision", page_icon="💎", initial_sidebar_state="expanded")


def svg_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.strip().encode()).decode()


GEM_AVATAR = svg_uri("""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-12 -2 84 84">
  <polygon points="28,2 10,20 26,30" fill="#F0C43C"/>
  <polygon points="28,2 48,14 26,30" fill="#F9DF75"/>
  <polygon points="10,20 8,52 26,30" fill="#E0AE22"/>
  <polygon points="48,14 52,44 26,30" fill="#EDBB2E"/>
  <polygon points="8,52 30,78 26,30" fill="#D19A17"/>
  <polygon points="52,44 30,78 26,30" fill="#E3A91F"/>
</svg>
""")

USER_AVATAR = svg_uri("""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <circle cx="32" cy="32" r="28" fill="#C4AE84" stroke="#A89878" stroke-width="3"/>
</svg>
""")


def avatar_for(role):
    return GEM_AVATAR if role == "assistant" else USER_AVATAR

GEM = """
<svg width="58" height="78" viewBox="0 0 60 80" xmlns="http://www.w3.org/2000/svg">
  <polygon points="28,2 10,20 26,30" fill="#D8A83C"/>
  <polygon points="28,2 48,14 26,30" fill="#E8C15E"/>
  <polygon points="10,20 8,52 26,30" fill="#C4922E"/>
  <polygon points="48,14 52,44 26,30" fill="#D2A03A"/>
  <polygon points="8,52 30,78 26,30" fill="#B98527"/>
  <polygon points="52,44 30,78 26,30" fill="#C99630"/>
</svg>
"""

HERO = f"""
<div class="hero">
  <div class="brand">{GEM}<span class="name">Vision</span></div>
  <div class="tag">Ask me about your courses!</div>
</div>
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Alegreya+Sans:wght@400;500&family=Cormorant+Garamond:wght@400;500&display=swap');

.stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp label, .stApp textarea, .stApp button {
  font-family: 'Alegreya Sans', sans-serif;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], .stAppDeployButton, [data-testid="stDecoration"], footer { display: none; }
[data-testid="stExpandSidebarButton"], [data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }
[data-testid="stExpandSidebarButton"] *, [data-testid="collapsedControl"] * { color: #B5772E !important; }

/* sidebar */
[data-testid="stSidebar"] { background: #CBB99B; }
[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapseButton"] span { color: #B5772E !important; }
[data-testid="stSidebarUserContent"] > div { min-height: calc(100vh - 7rem); display: flex; flex-direction: column; }
.st-key-sidebar_footer, div:has(> .st-key-sidebar_footer) { margin-top: auto; }
.side-title { font-size: 1.5rem; margin: 3rem 0 .6rem 0; }
.made-by { font-size: .8rem; margin-top: .8rem; }
.side-link { display: block; color: #141414 !important; text-decoration: none; font-size: 1.2rem; padding: .25rem 0; }
.side-link:hover { text-decoration: underline; }
[data-testid="stSidebar"] button {
  background: transparent; border: none; box-shadow: none; color: #141414;
  justify-content: flex-start; padding: .2rem 0; font-size: 1.2rem;
}
[data-testid="stSidebar"] button:hover { background: rgba(0,0,0,.06); }
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] { background: rgba(255,255,255,.35); color: #141414; }

/* hero */
.hero { text-align: center; margin-top: 22vh; }
.hero .brand { display: flex; align-items: center; justify-content: center; gap: 1.2rem; }
.hero .name { font-family: 'Cormorant Garamond', serif; font-size: 3.4rem; letter-spacing: .35em; }
.hero .tag { font-size: 1.25rem; letter-spacing: .12em; margin-top: .5rem; }

/* chat input */
[data-testid="stBottom"], [data-testid="stBottom"] > div { background: transparent; }
[data-testid="stChatInput"] { background: #DDCDAF; border: 1px solid #A89878; border-radius: 22px; }
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] textarea { background: transparent !important; }
[data-testid="stChatInputSubmitButton"] { background: #C4AE84; color: #fff; border-radius: 8px; }

/* messages */
[data-testid="stChatMessage"] { background: rgba(203,185,155,.22); border-radius: 16px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

if not (DATA / "courses.json").exists() or not (ROOT / "chroma_courses").exists():
    st.markdown(HERO, unsafe_allow_html=True)
    st.info(
        "No course data yet. In a terminal, run `python -m advisor.scrape` and then "
        "`python -m advisor.build`, then reload this page."
    )
    st.stop()

from advisor.rag import answer  # imported after the check on purpose

UNGROUNDED_MSG = "Parts of this answer may not be fully supported by the catalog data. Please verify it."


# ---------- chat history ----------
def load_chats():
    try:
        return json.loads(CHAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_chats():
    CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHAT_FILE.write_text(json.dumps(st.session_state.chats), encoding="utf-8")


if "chats" not in st.session_state:
    st.session_state.chats = load_chats()
    st.session_state.current = None


def new_chat():
    st.session_state.current = None


def open_chat(cid):
    st.session_state.current = cid


def delete_chat(cid):
    st.session_state.chats.pop(cid, None)
    if st.session_state.current == cid:
        st.session_state.current = None
    save_chats()


# ---------- rendering ----------
def show_calendar(r):
    for c in r.get("calendar", []):
        with st.container(border=True):
            st.markdown(f"**{c['code']}: {c['title']}**")
            st.markdown(f"**Prerequisite (exact calendar wording):** {c['prereq_text']}")
            if c["exclusions"]:
                st.markdown(f"**Exclusions:** {', '.join(c['exclusions'])}")
            st.caption(f"[Source: UTSC calendar]({c['source']})")


def show_details(r):
    if not (r["rewritten_query"] or r["facts"] or r["sources"]):
        return
    with st.expander("How I got this"):
        if r["rewritten_query"]:
            st.caption(f"Rewrote the search to: {r['rewritten_query']}")
        for f in r["facts"]:
            st.write("• " + f)
        for s in r["sources"]:
            label = s["meta"].get("code") or s["meta"].get("source")
            url = s["meta"].get("url")
            head = f"[{label}]({url})" if url else label
            st.write(f"**{head}**: {s['text'][:200]}…")


def show_result(r):
    show_calendar(r)
    if not r["grounded"]:
        st.warning(UNGROUNDED_MSG)
    show_details(r)


def data_date():
    f = DATA / "courses.json"
    return datetime.fromtimestamp(f.stat().st_mtime).strftime("%B %d, %Y") if f.exists() else "unknown"


@st.dialog("About Vision")
def about():
    st.write(
        "Vision answers questions about UTSC courses, prerequisites and programs using the public "
        "UTSC Academic Calendar. It runs on your own computer with Ollama and Chroma, so your "
        "questions are not sent to an outside AI service."
    )
    st.write(
        "Answers are written by a small language model from the calendar data, so check anything "
        "important against the official calendar or an academic advisor. The exact calendar wording "
        "is shown under each answer."
    )
    st.caption(f"Calendar data last refreshed: {data_date()}")


# ---------- sidebar ----------
with st.sidebar:
    st.markdown('<div class="side-title">My chats</div>', unsafe_allow_html=True)
    st.button("＋ New chat", key="new_chat", on_click=new_chat)
    for cid, chat in reversed(list(st.session_state.chats.items())):
        c1, c2 = st.columns([6, 1])
        c1.button(
            chat["title"], key=f"open_{cid}", on_click=open_chat, args=(cid,),
            type="primary" if cid == st.session_state.current else "secondary",
            use_container_width=True,
        )
        c2.button("✕", key=f"del_{cid}", on_click=delete_chat, args=(cid,))

    with st.expander("Settings"):
        use_grader = st.toggle(
            "Check sources before answering", value=True,
            help="Slower, but filters out irrelevant results and flags unsupported answers.",
        )

    with st.container(key="sidebar_footer"):
        if st.button("Refresh", key="refresh"):
            with st.spinner("Re-downloading the calendar and rebuilding the index. This takes several minutes..."):
                try:
                    subprocess.run([sys.executable, "-m", "advisor.scrape", "--fresh"], check=True, cwd=ROOT)
                    subprocess.run([sys.executable, "-m", "advisor.build"], check=True, cwd=ROOT)
                except subprocess.CalledProcessError:
                    st.error("Refresh failed. Check the terminal for details.")
                else:
                    st.success("Calendar data refreshed. Restart the app to load it.")
        st.markdown(f'<a class="side-link" href="{CREATOR_URL}" target="_blank">Visit Creator!</a>', unsafe_allow_html=True)
        st.markdown(f'<a class="side-link" href="{REPO_URL}" target="_blank">Visit Repo</a>', unsafe_allow_html=True)
        if st.button("About", key="about"):
            st.session_state.show_about = True
        st.markdown('<div class="made-by">made by faiza khan</div>', unsafe_allow_html=True)

if st.session_state.pop("show_about", False):
    about()

# ---------- main area ----------
q = st.chat_input("Ask about any UTSC course or program")

if q and st.session_state.current is None:
    cid = uuid.uuid4().hex[:8]
    st.session_state.chats[cid] = {"title": q[:38] + ("…" if len(q) > 38 else ""), "messages": []}
    st.session_state.current = cid

messages = st.session_state.chats[st.session_state.current]["messages"] if st.session_state.current else []
if q:
    messages.append({"role": "user", "content": q})

if not messages:
    st.markdown(HERO, unsafe_allow_html=True)

for m in messages:
    with st.chat_message(m["role"], avatar=avatar_for(m["role"])):
        st.markdown(m["content"])
        if m.get("result"):
            show_result(m["result"])

if q:
    with st.chat_message("assistant", avatar=GEM_AVATAR):
        try:
            with st.spinner("Searching and checking sources..."):
                r = answer(q, use_grader=use_grader)
        except Exception as e:
            st.error(f"Something went wrong. Is Ollama running? ({str(e)[:200]})")
            st.stop()
        st.markdown(r["answer"])
        show_result(r)
    messages.append({"role": "assistant", "content": r["answer"], "result": r})
    save_chats()
    st.rerun()  # refresh the sidebar so a new chat shows up in "My chats"