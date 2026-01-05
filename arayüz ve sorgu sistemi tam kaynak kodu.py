import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import json
import requests
from elasticsearch import Elasticsearch
import fasttext

#fasttextin kullandığı model
FASTTEXT_MODEL_PATH = "Downloads/wiki.tr/wiki.tr.bin"
print("[fastText] model yükleniyor...")
ft_model = fasttext.load_model(FASTTEXT_MODEL_PATH)
print("[fastText] model hazır.")

AI_CACHE = {}

def ai_generate_related_terms(keyword, top_k=10):
    if not keyword:
        return []

    keyword = keyword.strip().lower()

    if keyword in AI_CACHE:
        return AI_CACHE[keyword]

    neighbors = ft_model.get_nearest_neighbors(keyword, k=top_k + 10)

    terms = []
    for score, word in neighbors:
        
        if word.startswith(keyword):
            continue
        if len(word) < 4:
            continue
        terms.append(word)
        if len(terms) >= top_k:
            break

    AI_CACHE[keyword] = terms

   #eşleşen kelimelerin terminalde gösterimi
    for t in terms:
        print(f"[fastText] {keyword} → {t}")

    return terms


# veritabanı bağlantısı
ES_HOST = "https://localhost:9200"
ES_USER = "elastic"
ES_PASS = "z2TT*I2eBFLh+p-=f3_H"
INDEX_NAME = "haberler"

def create_es_client():
    try:
        es8 = Elasticsearch(
            [ES_HOST],
            basic_auth=(ES_USER, ES_PASS),
            verify_certs=False
        )
        es8.info()
        return es8
    except:
        es7 = Elasticsearch(
            [ES_HOST],
            http_auth=(ES_USER, ES_PASS),
            verify_certs=False
        )
        es7.info()
        return es7

es = create_es_client()

# tanımlamalar
searchable_fields = ["başlık", "açıklama", "icerik", "yazar", "site adı"]
search_results = []
ai_results = []
listbox_map = []

#yazar listesi için
def load_authors():
    try:
        res = es.search(
            index=INDEX_NAME,
            body={
                "size": 0,
                "aggs": {
                    "yazarlar": {
                        "terms": {"field": "yazar.raw", "size": 500}
                    }
                }
            }
        )
        return [b["key"] for b in res["aggregations"]["yazarlar"]["buckets"]]
    except:
        return []

# öneri araması
def run_ai_search(ai_terms, filtr):
    results = []
    seen_titles = set()

    for term in ai_terms:
        body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "icerik": {
                                    "query": term,
                                    "operator": "or"
                                }
                            }
                        }
                    ],
                    "filter": filtr
                }
            }
        }

        try:
            res = es.search(index=INDEX_NAME, body=body, size=50)
            hits = res["hits"]["hits"]

            print(f"[AI] '{term}' → {len(hits)} kayıt bulundu")

            for h in hits:
                src = h["_source"]
                title = src.get("başlık")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    results.append(src)
        except:
            pass

    return results

# eşleşenler
def run_query():
    global search_results, ai_results

    keyword = entry_keyword.get().strip()
    selected_field = combo_field.get()
    match_type = match_type_var.get()
    content_type = combo_type.get()
    use_date = date_enable_var.get()
    date_field = date_field_var.get()

    must = []
    filtr = []

    if selected_field == "yazar":
        author = combo_author.get()
        if author:
            must.append({"term": {"yazar.raw": author}})

    elif keyword:
        if selected_field == "Tüm Alanlar":
            if match_type == "exact":
                must.append({
                    "multi_match": {
                        "query": keyword.lower(),
                        "fields": [f + ".raw" for f in searchable_fields],
                        "type": "phrase"
                    }
                })
            else:
                must.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": searchable_fields,
                        "operator": "and"
                    }
                })
        else:
            if match_type == "exact":
                must.append({"term": {selected_field + ".raw": keyword.lower()}})
            else:
                must.append({
                    "match": {
                        selected_field: {
                            "query": keyword,
                            "operator": "and"
                        }
                    }
                })

    if content_type == "Haber":
        filtr.append({"term": {"içerik türü.raw": "news"}})
    elif content_type == "Makale":
        filtr.append({"term": {"içerik türü.raw": "columnist"}})

    if use_date:
        filtr.append({
            "range": {
                date_field: {
                    "gte": date_start.get_date().strftime("%Y-%m-%d"),
                    "lte": date_end.get_date().strftime("%Y-%m-%d")
                }
            }
        })

    if not must and not filtr:
        messagebox.showwarning("Uyarı", "Arama kriteri girmediniz.")
        return

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filtr
            }
        }
    }

    # eşleşen sonuçlar
    res = es.search(index=INDEX_NAME, body=body, size=1000)
    search_results = [h["_source"] for h in res["hits"]["hits"]]
    print(f"\n[ES] Normal sorgu → {len(search_results)} kayıt bulundu")

    existing_titles = {item.get("başlık") for item in search_results}

    # embedding tarafı
    ai_results = []
    if keyword:
        ai_terms = ai_generate_related_terms(keyword)
        raw_ai_results = run_ai_search(ai_terms, filtr)
        ai_results = [
            r for r in raw_ai_results
            if r.get("başlık") not in existing_titles
        ]

    print(f"[AI] Toplam öneri sonucu → {len(ai_results)} kayıt\n")
    label_status.config(
    text=f"Eşleşen: {len(search_results)} | AI Öneri: {len(ai_results)}"
    )

    show_results()

# ekrana bastırım
def show_results():
    listbox_results.delete(0, tk.END)
    listbox_map.clear()
    text_detail.delete("1.0", tk.END)

    listbox_results.insert(tk.END, "=== EŞLEŞEN SONUÇLAR ===")
    listbox_map.append(None)

    if not search_results:
        listbox_results.insert(tk.END, "Sonuç bulunamadı.")
        listbox_map.append(None)
    else:
        for item in search_results:
            listbox_results.insert(tk.END, item.get("başlık", "(başlık yok)"))
            listbox_map.append(item)

    if ai_results:
        listbox_results.insert(tk.END, "")
        listbox_map.append(None)
        listbox_results.insert(tk.END, "=== BUNLAR DA OLABİLİR (AI) ===")
        listbox_map.append(None)

        for item in ai_results:
            listbox_results.insert(tk.END, item.get("başlık", "(başlık yok)"))
            listbox_map.append(item)

def show_detail(event):
    sel = listbox_results.curselection()
    if not sel:
        return
    item = listbox_map[sel[0]]
    if not item:
        return
    text_detail.delete("1.0", tk.END)
    text_detail.insert(tk.END, json.dumps(item, indent=2, ensure_ascii=False))

# arayüz başlangıç
root = tk.Tk()
root.title("Elasticsearch Arama Ekranı")
root.geometry("1100x700")

frame_kw = tk.Frame(root)
frame_kw.pack(pady=10)

tk.Label(frame_kw, text="Kelime:", font=("Arial", 12)).pack(side="left")

keyword_container = tk.Frame(frame_kw)
keyword_container.pack(side="left", padx=5)

entry_keyword = tk.Entry(keyword_container, width=40, font=("Arial", 12))
entry_keyword.pack()

combo_author = ttk.Combobox(keyword_container, state="readonly", width=38)
combo_author["values"] = load_authors()

tk.Label(root, text="Arama Alanı:", font=("Arial", 12)).pack()

combo_field = ttk.Combobox(
    root,
    state="readonly",
    width=40,
    values=["Tüm Alanlar"] + searchable_fields
)
combo_field.current(0)
combo_field.pack(pady=5)

def on_field_change(event):
    if combo_field.get() == "yazar":
        entry_keyword.pack_forget()
        combo_author.pack()
    else:
        combo_author.pack_forget()
        entry_keyword.pack()

combo_field.bind("<<ComboboxSelected>>", on_field_change)

match_type_var = tk.StringVar(value="partial")
tk.Radiobutton(root, text="Kısmi", variable=match_type_var, value="partial").pack()
tk.Radiobutton(root, text="Tam", variable=match_type_var, value="exact").pack()

tk.Label(root, text="İçerik Türü:", font=("Arial", 12)).pack()
combo_type = ttk.Combobox(root, state="readonly", width=20, values=["", "Haber", "Makale"])
combo_type.current(0)
combo_type.pack(pady=5)

date_enable_var = tk.BooleanVar()
tk.Checkbutton(root, text="Tarih filtresi kullan", variable=date_enable_var).pack()

frame_date = tk.Frame(root)
frame_date.pack(pady=5)

date_field_var = tk.StringVar(value="yüklenme tarihi")
ttk.Combobox(
    frame_date,
    state="readonly",
    textvariable=date_field_var,
    values=["yüklenme tarihi", "değiştirme tarihi"],
    width=25
).grid(row=0, column=1)

date_start = DateEntry(frame_date, date_pattern="yyyy-mm-dd")
date_start.grid(row=1, column=1)

date_end = DateEntry(frame_date, date_pattern="yyyy-mm-dd")
date_end.grid(row=1, column=3)

tk.Button(
    root,
    text="ARA",
    command=run_query,
    font=("Arial", 14),
    bg="blue",
    fg="white"
).pack(pady=10)

label_status = tk.Label(
    root,
    text="",
    font=("Arial", 11, "bold"),
    fg="darkgreen"
)
label_status.pack(pady=5)


frame_results = tk.Frame(root)
frame_results.pack(expand=True, fill="both")

listbox_results = tk.Listbox(frame_results, width=40, font=("Arial", 12))
listbox_results.pack(side="left", fill="y")
listbox_results.bind("<<ListboxSelect>>", show_detail)

text_detail = tk.Text(frame_results, wrap="word", font=("Consolas", 11))
text_detail.pack(side="right", expand=True, fill="both")

root.mainloop()
