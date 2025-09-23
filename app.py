# -*- coding: utf-8 -*-
import csv
import io
import re
import unicodedata
from difflib import get_close_matches
from typing import List, Tuple

import streamlit as st

# ============================ إعداد الصفحة ============================
st.set_page_config(
    page_title="سعر الصنف",
    page_icon="💸",
    layout="centered",
)

# ============================ تنسيقات CSS (مع موبايل) ============================
CUSTOM_CSS = """
<style>
:root{
  --bg:#0b0f17;
  --card:#111827;
  --muted:#94a3b8;
  --txt:#e5e7eb;
  --accent:#22c55e;
  --danger:#ef4444;
  --shadow: 0 10px 20px rgba(0,0,0,.35);
  --radius:18px;
}

html, body, [class*="css"]  {
  font-family: "Cairo", system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial;
}
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

.block-container{
  padding-top: 1.2rem;
  padding-bottom: 2.2rem;
}

.hero{
  background: radial-gradient(1000px 600px at 85% -10%, rgba(34,197,94,0.15), transparent),
              radial-gradient(1000px 600px at -10% 30%, rgba(59,130,246,0.12), transparent),
              linear-gradient(180deg, #0b0f17 0%, #0b0f17 100%);
  border: 1px solid rgba(255,255,255,.06);
  border-radius: 24px;
  padding: 28px 24px;
  box-shadow: var(--shadow);
}
.hero h1{
  color: var(--txt);
  margin: 0 0 6px 0;
  font-size: 34px;
  line-height: 1.15;
  letter-spacing: .2px;
}
.hero p{ margin: 0; color: var(--muted); }

.card{
  background: var(--card);
  border: 1px solid rgba(255,255,255,.06);
  border-radius: var(--radius);
  padding: 18px 16px;
  box-shadow: var(--shadow);
}

.kpi{
  display:flex; gap:14px; flex-wrap:wrap; margin-top:16px;
}
.kpi .item{
  background: rgba(255,255,255,.03);
  border: 1px solid rgba(255,255,255,.06);
  border-radius:14px;
  padding: 10px 14px;
  min-width: 140px;
}
.kpi .item .label{ color: var(--muted); font-size: 12px; }
.kpi .item .value{ color: var(--txt); font-weight: 700; font-size: 18px; }

.search-box{
  display:flex; gap:10px; align-items:center;
}
.search-box input{
  background:#0d1320 !important;
  border:1px solid rgba(255,255,255,.08) !important;
  color:var(--txt) !important;
  border-radius:12px !important;
  height: 56px !important; /* لمس موبايل */
  font-size: 18px !important;
}

.result{ border-left: 4px solid var(--accent); }

.suggestions-wrap{
  display:flex; flex-wrap:wrap; gap:10px; margin-top: 6px;
}
.suggestion-btn{
  appearance:none; border:none; cursor:pointer;
  padding:10px 14px; border-radius:999px;
  background: rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
  color: var(--txt); font-size:14px;
  transition: transform .05s ease;
}
.suggestion-btn:active{ transform: scale(.98); }

.footer{
  color: var(--muted);
  text-align:center;
  margin-top:28px;
  font-size: 13px;
}
hr.sep{
  border: none; border-top: 1px solid rgba(255,255,255,.08);
  margin: 18px 0;
}

/* ======================= موبايل ======================= */
@media (max-width: 480px){
  .hero{ padding: 18px 14px; border-radius:18px; }
  .hero h1{ font-size: 24px; }
  .kpi .item{ min-width: 120px; padding: 8px 10px; }
  .kpi .item .value{ font-size: 16px; }
  .card{ padding: 14px 12px; border-radius: 14px; }
  .search-box input{ height: 52px !important; font-size: 16px !important; }
  .suggestion-btn{ padding: 9px 12px; font-size: 13px; }
  .stButton>button{ width: 100%; height: 48px; font-size: 16px; }
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================ أدوات عربية ============================
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]")

def normalize_ar(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    return text.strip().lower()

# ============================ تحميل CSV ============================
def load_csv_from_bytes(file_bytes: bytes) -> Tuple[List[str], List[str], List[str]]:
    text = file_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return [], [], []
    start_idx = 0
    if rows and len(rows[0]) >= 2:
        first_a, first_b = rows[0][0].strip(), rows[0][1].strip()
        if first_a in ("اسم الصنف", "المنتج", "product", "name") or first_b in ("السعر", "price"):
            start_idx = 1
    names, names_norm, prices = [], [], []
    for r in rows[start_idx:]:
        name = (r[0].strip() if len(r) > 0 else "")
        price = (r[1].strip() if len(r) > 1 else "")
        if name:
            names.append(name)
            names_norm.append(normalize_ar(name))
            prices.append(price)
    return names, names_norm, prices

def load_csv_from_text(csv_text: str) -> Tuple[List[str], List[str], List[str]]:
    return load_csv_from_bytes(csv_text.encode("utf-8"))

# ============================ بحث الأسعار ============================
def lookup_price(query: str, names, names_norm, prices, cutoff=0.6):
    q_norm = normalize_ar(query)
    if not q_norm:
        return None, [], None
    if q_norm in names_norm:
        idx = names_norm.index(q_norm)
        return prices[idx] if idx < len(prices) else "", [], names[idx]
    matches = get_close_matches(q_norm, names_norm, n=5, cutoff=cutoff)
    if matches:
        idx0 = names_norm.index(matches[0])
        others = [names[names_norm.index(m)] for m in matches[1:]]
        return prices[idx0] if idx0 < len(prices) else "", others, names[idx0]
    for i, n in enumerate(names_norm):
        if q_norm and q_norm in n:
            return prices[i] if i < len(prices) else "", [], names[i]
    return None, [], None

def get_price_by_exact_name(name: str, names, prices):
    """لما يضغط على اقتراح: رجع السعر مباشرة بالاسم الظاهر."""
    try:
        i = names.index(name)
        return prices[i] if i < len(prices) else ""
    except ValueError:
        return ""

# ============================ هيدر ============================
st.markdown(
    """
    <div class="hero">
      <h1>سِعري — محرك سريع لأسعار الأصناف</h1>
      <p>ارفع ملف CSV (اسم، سعر)، واكتب اسم الصنف. لو مش متأكد هنعرض لك اقتراحات قابلة للضغط.</p>
      <div class="kpi">
        <div class="item"><div class="label">الحالة</div><div class="value">جاهز</div></div>
        <div class="item"><div class="label">الوضع</div><div class="value">بدون قواعد بيانات</div></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown("<hr class='sep'/>", unsafe_allow_html=True)

# ============================ إدخال البيانات ============================
tab1, tab2, tab3 = st.tabs(["📤 رفع ملف", "📝 لصق CSV", "ℹ️ مساعدة"])

with tab1:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    uploaded = st.file_uploader("ارفع CSV (عمود 1: اسم الصنف، عمود 2: السعر)", type=["csv"])
    st.caption("من Google Sheets: File → Download → CSV. تأكد من الترميز UTF-8.")
    st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    csv_text = st.text_area(
        "الصق محتوى CSV هنا",
        placeholder="مثال:\nاسم الصنف,السعر\nتفاحة,5\nموبايل سامسونج A14,4500",
        height=160
    )
    st.markdown("</div>", unsafe_allow_html=True)

with tab3:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.write(
        "- الملف: عمود أول للاسم، عمود ثاني للسعر.\n"
        "- يدعم هيدر اختياري: `اسم الصنف,السعر`.\n"
        "- المطابقة تقريبية قابلة للضبط من الشريط الجانبي.\n"
    )
    sample = "اسم الصنف,السعر\nتفاحة,5\nموبايل سامسونج A14,4500\nلبن كامل الدسم,25"
    st.download_button("تنزيل ملف نموذج CSV", data=sample, file_name="sample_products.csv", mime="text/csv")
    st.markdown("</div>", unsafe_allow_html=True)

# ============================ الشريط الجانبي ============================
with st.sidebar:
    st.header("الإعدادات")
    cutoff = st.slider("درجة المطابقة التقريبية", 0.0, 1.0, 0.6, 0.05)
    show_preview = st.checkbox("عرض معاينة سريعة", value=True)
    st.caption("لو الأسماء متقاربة، عليّ المطابقة. للدقة العالية، نزّلها.")

# ============================ تحميل البيانات ============================
names: List[str] = []
names_norm: List[str] = []
prices: List[str] = []

if uploaded is not None:
    names, names_norm, prices = load_csv_from_bytes(uploaded.getvalue())
elif 'csv_text' in locals() and csv_text.strip():
    names, names_norm, prices = load_csv_from_text(csv_text)

# عدّاد أصناف
if names:
    st.markdown(
        f"""
        <div class="kpi" style="margin-top:8px;">
          <div class="item">
            <div class="label">عدد الأصناف</div>
            <div class="value">{len(names)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================ صندوق البحث ============================
st.markdown("<div class='card'>", unsafe_allow_html=True)
with st.form(key="search_form", clear_on_submit=False):
    st.markdown("<div class='search-box'>", unsafe_allow_html=True)
    query = st.text_input("ابحث عن السعر", placeholder="مثال: موبايل سامسونج A14")
    st.markdown("</div>", unsafe_allow_html=True)
    submitted = st.form_submit_button("ابحث ✅")

# ============================ عرض النتيجة + اقتراحات قابلة للضغط ============================
def show_result_card(title_name: str | None, price_value: str | None):
    st.markdown("<div class='card result'>", unsafe_allow_html=True)
    st.subheader("النتيجة")
    if title_name:
        st.markdown(f"**{title_name}**")
    st.markdown(f"### السعر: **{price_value if price_value else 'غير مسجل'}**")
    st.markdown("</div>", unsafe_allow_html=True)

if submitted:
    if not names:
        st.error("ارفع ملف أو الصق CSV أولًا.")
    elif not query.strip():
        st.info("اكتب اسم الصنف ثم اضغط ابحث.")
    else:
        with st.spinner("جاري البحث ..."):
            price, suggestions, matched_name = lookup_price(query, names, names_norm, prices, cutoff=cutoff)

        if price is None:
            st.error("الصنف غير موجود. جرّب تعديل الاسم أو زوّد درجة المطابقة.")
        else:
            show_result_card(matched_name, price)

        # اقتراحات كأزرار قابلة للضغط
        # اقتراحات كأزرار قابلة للضغط
        if suggestions:
            st.caption("يمكن قصدت:")
            st.markdown('<div class="suggestions-wrap">', unsafe_allow_html=True)

            for i, s in enumerate(suggestions):
                # كل اقتراح = زر. عند الضغط: يجيب السعر ويعرضه، ويحدّث حقل البحث كمان.
                if st.button(s, key=f"sugg_{i}", help="اضغط لعرض السعر"):
                    p = get_price_by_exact_name(s, names, prices)
                    # حدّث صندوق البحث (لو بتحب يرجّع يظهر فوق)
                    if "search_form-query" in st.session_state:
                        st.session_state["search_form-query"] = s
                    # اعرض نتيجة فورية
                    show_result_card(s, p)

            st.markdown('</div>', unsafe_allow_html=True)


st.markdown("</div>", unsafe_allow_html=True)

# ============================ معاينة (اختيارية) ============================
if show_preview and names:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("معاينة سريعة")
    preview_count = min(50, len(names))
    data = [{"اسم الصنف": names[i], "السعر": prices[i] if i < len(prices) else ""} for i in range(preview_count)]
    st.table(data)
    st.markdown("</div>", unsafe_allow_html=True)

# ============================ فوتر ============================
st.markdown("<hr class='sep'/>", unsafe_allow_html=True)
st.markdown("<div class='footer'>© سِعري — أداة خفيفة لعرض أسعار الأصناف من CSV • جاهزة للموبايل</div>", unsafe_allow_html=True)
