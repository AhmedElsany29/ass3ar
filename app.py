# -*- coding: utf-8 -*-
import csv
import io
import re
import unicodedata
from difflib import get_close_matches
from typing import List, Tuple

import requests
import streamlit as st

# =================== إعدادات الشيت ===================
SHEET_ID = "1A1VgWuHyHR-EhuAObTHbQgtXM6JxWDMT"   # ← ID الشيت
WORKSHEET_NAME = "المحل"                         # ← اسم الورقة (التبويب)
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={WORKSHEET_NAME}"

# =================== إعداد الصفحة ===================
st.set_page_config(page_title="ابو احمد - للادوات الكهربائية", page_icon="🥷", layout="centered")
st.title("🥷 ابو احمد - للادوات الكهربائية")

# =================== أدوات عربية ===================
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]")
def normalize_ar(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    return text.strip().lower()

# =================== تحميل البيانات من CSV ===================
@st.cache_data(ttl=60)
def load_products_from_csv(url: str) -> Tuple[List[str], List[str], List[str]]:
    """يسحب الورقة كـ CSV ويطلع (أسماء، أسماء مطبّعة، أسعار). يحدث كل دقيقة."""
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    text = r.text
    rows = [row for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row)]
    if not rows:
        return [], [], []

    # تخطي الهيدر لو موجود
    start = 1 if (len(rows[0]) >= 2 and (
        rows[0][0].strip() in ("اسم الصنف", "المنتج", "product", "name")
        or rows[0][1].strip() in ("السعر", "price")
    )) else 0

    names, names_norm, prices = [], [], []
    for r0 in rows[start:]:
        name = (r0[0].strip() if len(r0) > 0 else "")
        price = (r0[1].strip() if len(r0) > 1 else "")
        if name:
            names.append(name)
            names_norm.append(normalize_ar(name))
            prices.append(price)
    return names, names_norm, prices

def lookup_price(query: str, names, names_norm, prices, cutoff=0.6):
    """يرجع (أفضل_تطابق_بالاسم_الأصلي, السعر) + قائمة اقتراحات أخرى."""
    q = normalize_ar(query)
    if not q:
        return None, []

    # تطابق مباشر
    if q in names_norm:
        i = names_norm.index(q)
        return (names[i], prices[i] if i < len(prices) else ""), []

    # أقرب تقريبي
    matches = get_close_matches(q, names_norm, n=5, cutoff=cutoff)
    if matches:
        i0 = names_norm.index(matches[0])
        sugg = [names[names_norm.index(m)] for m in matches[1:]]
        return (names[i0], prices[i0] if i0 < len(prices) else ""), sugg

    # contains
    for i, n in enumerate(names_norm):
        if q and q in n:
            return (names[i], prices[i] if i < len(prices) else ""), []

    return None, []

def get_price_by_exact_name(name: str, names, prices) -> str:
    try:
        i = names.index(name)
        return prices[i] if i < len(prices) else ""
    except ValueError:
        return ""

# =================== تحميل البيانات ===================
try:
    names, names_norm, prices = load_products_from_csv(CSV_URL)
except Exception as e:
    st.error("تعذر قراءة الشيت عبر CSV.\nتأكد من:")
    st.write("- اسم الورقة صحيح (WORKSHEET_NAME).")
    st.write("- مشاركة/نشر الورقة (Anyone with the link أو Publish to web).")
    st.code(str(e))
    st.stop()

# =================== حالة افتراضية ===================
if "q" not in st.session_state:
    st.session_state["q"] = ""
if "trigger_search" not in st.session_state:
    st.session_state["trigger_search"] = False

# =================== UI: مدخلات ===================
cutoff = st.slider("درجة المطابقة التقريبية", 0.0, 1.0, 0.3, 0.05)

def _on_query_change():
    st.session_state["trigger_search"] = True

col_q, col_btn = st.columns([3, 1])
with col_q:
    st.text_input(
        "اكتب اسم الصنف",
        placeholder="مثال: لمبة 100",
        key="q",
        on_change=_on_query_change,
    )
with col_btn:
    clicked_search = st.button("ابحث")

do_search = clicked_search or st.session_state.get("trigger_search", False)

# =================== تنفيذ البحث ===================
if do_search:
    st.session_state["trigger_search"] = False

    q_val = st.session_state.get("q", "")
    if not q_val.strip():
        st.info("اكتب اسم الصنف ثم اضغط ابحث.")
    elif not names:
        st.error("الشيت لا يحتوي بيانات.")
    else:
        best, suggestions = lookup_price(q_val, names, names_norm, prices, cutoff=cutoff)

        # نتيجة أفضل تطابق
        if best is None:
            st.error("الصنف غير موجود.")
        else:
            pname, price = best
            st.success(f"**{pname}** — السعر: **{price or 'غير مسجل'}**")

        # -------- اقتراحات + أسعارها (تظهر فورًا) --------
        if suggestions:
            st.caption("يمكن قصدت (مع السعر):")
            cols = st.columns(min(3, len(suggestions)))
            for i, s in enumerate(suggestions):
                sp = get_price_by_exact_name(s, names, prices)
                label = f"{s} — السعر: {sp or 'غير مسجل'}"
                # زر اختياري: يملّي البحث ويعيد النتيجة الأساسية
                if cols[i % len(cols)].button(label, key=f"sugg_{i}"):
                    st.session_state["q"] = s
                    st.session_state["trigger_search"] = True
                    try:
                        st.experimental_rerun()
                    except Exception:
                        st.rerun()
