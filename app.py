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

def search_products(query: str, names, names_norm, prices, cutoff=0.6):
    """يبحث عن كل المنتجات المشابهة ويرجعها مرتبة حسب الأولوية."""
    q = normalize_ar(query)
    if not q:
        return []

    results = []
    
    # 1. تطابق مباشر أولاً
    for i, n in enumerate(names_norm):
        if q == n:
            results.append({
                'name': names[i],
                'price': prices[i] if i < len(prices) else "",
                'match_type': 'exact',
                'priority': 1
            })
    
    # 2. يحتوي على الكلمة كاملة
    for i, n in enumerate(names_norm):
        if q != n and q in n:
            # تأكد إن الكلمة مش جزء من كلمة أكبر
            if re.search(r'\b' + re.escape(q) + r'\b', n):
                results.append({
                    'name': names[i],
                    'price': prices[i] if i < len(prices) else "",
                    'match_type': 'word_match',
                    'priority': 2
                })
    
    # 3. يحتوي على الكلمة كجزء من كلمة
    for i, n in enumerate(names_norm):
        if q != n and q in n:
            # تجنب التكرار مع النتائج اللي قبل كده
            already_added = any(r['name'] == names[i] for r in results)
            if not already_added:
                results.append({
                    'name': names[i],
                    'price': prices[i] if i < len(prices) else "",
                    'match_type': 'partial_match',
                    'priority': 3
                })
    
    # 4. تطابق تقريبي
    matches = get_close_matches(q, names_norm, n=10, cutoff=cutoff)
    for match in matches:
        i = names_norm.index(match)
        # تجنب التكرار
        already_added = any(r['name'] == names[i] for r in results)
        if not already_added:
            results.append({
                'name': names[i],
                'price': prices[i] if i < len(prices) else "",
                'match_type': 'fuzzy_match',
                'priority': 4
            })
    
    # ترتيب النتائج حسب الأولوية
    results.sort(key=lambda x: x['priority'])
    
    return results

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
cutoff = st.slider("درجة المطابقة التقريبية", 0.1, 1.0, 0.5, 0.05)

def _on_query_change():
    st.session_state["trigger_search"] = True

col_q, col_btn = st.columns([3, 1])
with col_q:
    st.text_input(
        "اكتب اسم الصنف أو جزء منه",
        placeholder="مثال: مشترك، لمبة، كابل",
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
        st.info("اكتب اسم الصنف أو جزء منه ثم اضغط ابحث.")
    elif not names:
        st.error("الشيت لا يحتوي بيانات.")
    else:
        results = search_products(q_val, names, names_norm, prices, cutoff=cutoff)

        if not results:
            st.error("لم يتم العثور على أي منتجات تحتوي على هذا النص.")
        else:
            st.success(f"تم العثور على {len(results)} منتج:")
            
            # عرض النتائج في مجموعات حسب نوع التطابق
            current_priority = None
            
            for i, result in enumerate(results):
                # عرض عنوان المجموعة
                if result['priority'] != current_priority:
                    current_priority = result['priority']
                    if result['match_type'] == 'exact':
                        st.subheader("🎯 تطابق مباشر:")
                    elif result['match_type'] == 'word_match':
                        st.subheader("✅:")
                    elif result['match_type'] == 'partial_match':
                        st.subheader("📝 يحتوي على جزء من الكلمة:")
                    elif result['match_type'] == 'fuzzy_match':
                        st.subheader("🔍:")
                
                # عرض المنتج
                price_text = result['price'] if result['price'] else "غير مسجل"
                
                # استخدام أعمدة لعرض أفضل
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{result['name']}**")
                with col2:
                    st.write(f"💰 {price_text}")
                
                # خط فاصل بين المنتجات
                if i < len(results) - 1:
                    st.divider()

# # =================== إحصائيات ===================
# if names:
#     with st.expander(f"📊 إحصائيات الشيت ({len(names)} منتج)"):
#         st.write(f"إجمالي المنتجات: {len(names)}")
#         priced_count = sum(1 for p in prices if p.strip())
#         st.write(f"المنتجات بأسعار: {priced_count}")
#         st.write(f"المنتجات بدون أسعار: {len(names) - priced_count}")
