import os
import asyncio
import aiohttp
import requests
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from elasticsearch import Elasticsearch, helpers

TEST_MODE = False
THRESHOLD = 34242

INDEX_NAME = "haberler"

# async ayarları
ASYNC_HTTP_CONCURRENCY = 120      
ASYNC_RETRIES = 2                
HTTP_TIMEOUT_TOTAL = 4           

# thread sayısı
THREAD_WORKERS = 40

# buffer limiti
BULK_BATCH_SIZE = 800

# veritabanı bağlantısı ve mapping
es = Elasticsearch(
    ["https://localhost:9200"],
    http_auth=("elastic", "z2TT*I2eBFLh+p-=f3_H"),
    verify_certs=False
)
mapping = {
    "settings": {
        "analysis": {
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase"]
                }
            }
        }
    },
    "mappings": {
        "properties": {
            **{
                alan: {
                    "type": "text",
                    "fields": {
                        "raw": {
                            "type": "keyword",
                            "normalizer": "lowercase_normalizer"
                        }
                    }
                }
                for alan in [
                    "başlık", "açıklama", "resim", "url", "type", "site adı",
                    "twitter:card", "yazar", "içerik türü"
                ]
            },
            "yüklenme tarihi": {
                "type": "date",
                "format": "yyyy-MM-dd'T'HH:mm:ssZ||yyyy-MM-dd"
            },
            "değiştirme tarihi": {
                "type": "date",
                "format": "yyyy-MM-dd'T'HH:mm:ssZ||yyyy-MM-dd"
            },
            "icerik": {"type": "text"}
        }
    }
}

if not es.indices.exists(index=INDEX_NAME):
    es.indices.create(index=INDEX_NAME, body=mapping)
    print("[ Index oluşturuldu.]")
else:
    print("[ Index zaten mevcut. ]")


# datetime çevirme
def parse_dt(s: str):
    if not s:
        return None
    s = s.strip()

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except:
        pass

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None


def makale_id(link):
    try:
        dosya_adi = link.split("/")[-1]  
        temiz = dosya_adi.replace(".html", "")
        rakamlar = ""
        for c in temiz:
            if c.isdigit():
                rakamlar += c
        son5 = rakamlar[-5:]
        return int(son5) if son5.isdigit() else None
    except:
        return None


def kayitli_linkler():
    if not os.path.exists("kayitli_linkler.txt"):
        open("kayitli_linkler.txt", "w", encoding="utf-8").close()
        return set()
    with open("kayitli_linkler.txt", "r", encoding="utf-8") as f:
        return set(x.strip() for x in f if x.strip())


def kayit_ekle(url):
    with open("kayitli_linkler.txt", "a", encoding="utf-8") as f:
        f.write(url + "\n")


def es_mevcut_url_ve_modified():
    
    out = {}
    try:
        res = es.search(
            index=INDEX_NAME,
            scroll="2m",
            size=1000,
            _source=["url", "değiştirme tarihi"],
            body={"query": {"match_all": {}}}
        )
        scroll_id = res.get("_scroll_id")

        while True:
            hits = res.get("hits", {}).get("hits", [])
            if not hits:
                break

            for h in hits:
                src = h.get("_source", {})
                u = src.get("url")
                m = src.get("değiştirme tarihi")
                if u:
                    out[u] = m

            res = es.scroll(scroll_id=scroll_id, scroll="2m")
    except Exception as e:
        print("[UYARI] ES toplu okuma hatası:", e)
    return out


# veri alma
META_KEYS = [
    "og:title", "og:description", "og:image", "og:url", "og:type",
    "og:site_name", "twitter:card", "datePublished", "dateModified",
    "articleAuthor", "articleSection"
]

def verial_from_soup(url, soup):
    data = {k: None for k in META_KEYS}
    data["icerik"] = None

    for tag in soup.find_all("meta"):
        icerik = tag.get("content")
        key = tag.get("name") or tag.get("property") or tag.get("itemprop")
        if icerik and key in META_KEYS and not data[key]:
            data[key] = icerik

    body = soup.find("div", {"property": "articleBody"})
    if body:
        bloklar = []
        for el in body.find_all(["p", "img"]):
            if el.name == "p":
                t = el.get_text(strip=True)
                if t:
                    bloklar.append(t)
            elif el.name == "img":
                src = el.get("src")
                if src:
                    bloklar.append(urljoin(url, src))
        data["icerik"] = "\n".join(bloklar)

    return data

def turkce_alana_cevir(d):
    return {
        "başlık": d.get("og:title"),
        "açıklama": d.get("og:description"),
        "resim": d.get("og:image"),
        "url": d.get("og:url"),
        "type": d.get("og:type"),
        "site adı": d.get("og:site_name"),
        "twitter:card": d.get("twitter:card"),
        "yüklenme tarihi": d.get("datePublished"),
        "değiştirme tarihi": d.get("dateModified"),
        "yazar": d.get("articleAuthor"),
        "içerik türü": d.get("articleSection"),
        "icerik": d.get("icerik")
    }

# haber linkleri
def make_fast_requests_session():
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def son_1_ay():
    bugun = datetime.today().replace(day=1)
    return [(bugun.year, bugun.month)]

def dinamik_haber_sitemap():
    base = "https://www.bursadabugun.com/sitemap/haberleraylik_{y}-{m}.xml"
    return [base.format(y=y, m=m) for y, m in son_1_ay()]

def haber_linkleri_al():
    session = make_fast_requests_session()
    urller = []

    for sm in dinamik_haber_sitemap():
        try:
            r = session.get(sm, timeout=10)
            r.raise_for_status()
            root = ElementTree.fromstring(r.content)
            for tag in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                if tag.text:
                    urller.append(tag.text)
        except:
            pass

    if TEST_MODE:
        urller = urller[:10]

    print("Haber linkleri:", len(urller))
    return urller


# temel async url çekme fonksiyonu
async def fetch_text(aio_sess: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore):
    async with sem:
        last_exc = None
        for _ in range(ASYNC_RETRIES + 1):
            try:
                async with aio_sess.get(url) as r:
                    if r.status != 200:
                        return url, None
                    text = await r.text(errors="ignore")
                    return url, text
            except Exception as e:
                last_exc = e
        return url, None


# yazar ve makale bilgileri çekme fonksiyonu
def parse_yazar_linkleri_from_html(html: str):
    soup = BeautifulSoup(html, "lxml")
    yazarlar = set()
    for a in soup.select("a[href^='/yazarlar/']"):
        tam = "https://www.bursadabugun.com" + a.get("href")
        if tam.endswith("/"):
            yazarlar.add(tam)
    return list(yazarlar)

def parse_makale_linkleri_from_yazar_sayfasi(html: str):
    soup = BeautifulSoup(html, "lxml")
    makaleler = set()
    for a in soup.select("a[href^='/yazarlar/']"):
        h = a.get("href")
        if h and h.endswith(".html"):
            makaleler.add("https://www.bursadabugun.com" + h)
    return list(makaleler)

def extract_date_modified_only(html: str):
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", {"name": "dateModified"})
    return meta.get("content") if meta else None

async def yazar_makaleleri_son_1_ay(aio_sess, sem):
    base = "https://www.bursadabugun.com/yazarlar/"
    _, html = await fetch_text(aio_sess, base, sem)
    if not html:
        print("[UYARI] Yazarlar sayfası alınamadı.")
        return [], {}  

    yazarlar = parse_yazar_linkleri_from_html(html)
    if TEST_MODE:
        yazarlar = yazarlar[:10]

    # yazar sayfalarını paralel çek
    tasks = [fetch_text(aio_sess, yz, sem) for yz in yazarlar]
    makale_set = set()

    for coro in asyncio.as_completed(tasks):
        _, yz_html = await coro
        if not yz_html:
            continue
        for m in parse_makale_linkleri_from_yazar_sayfasi(yz_html):
            makale_set.add(m)

    makale_list = list(makale_set)
    if TEST_MODE:
        makale_list = makale_list[:10]

    print("Toplam makale linki:", len(makale_list))

    id_gecen = []
    for link in makale_list:
        mid = makale_id(link)
        if mid and mid > THRESHOLD:
            id_gecen.append(link)

    print("ID filtresine uyanlar:", len(id_gecen))

    LIMIT = datetime.now(timezone.utc) - timedelta(days=30)
    html_cache = {}

    tasks2 = [fetch_text(aio_sess, link, sem) for link in id_gecen]
    son_ay = []

    for coro in asyncio.as_completed(tasks2):
        link, m_html = await coro
        if not m_html:
            continue

        dm = extract_date_modified_only(m_html)
        dt = parse_dt(dm)
        if dt and dt >= LIMIT:
            son_ay.append(link)
            html_cache[link] = m_html  

    print("Son 1 ay toplam:", len(son_ay))
    return son_ay, html_cache


# parse
def parse_and_prepare_doc(url: str, html: str, es_mod_map: dict):
   
    try:
        soup = BeautifulSoup(html, "lxml")

        meta = soup.find("meta", {"name": "dateModified"})
        yeni_mod_str = meta.get("content") if meta else None

        eski_mod_str = es_mod_map.get(url)
        eski_dt = parse_dt(eski_mod_str) if eski_mod_str else None
        yeni_dt = parse_dt(yeni_mod_str) if yeni_mod_str else None

        if eski_dt and yeni_dt and eski_dt >= yeni_dt:
            return ("skip", url)

        ham = verial_from_soup(url, soup)
        tr = turkce_alana_cevir(ham)
        tr["url"] = url  # senin kodundaki gibi

        return ("ok", tr, url)
    except Exception:
        return ("err", url)


# 
def bulk_flush(actions):
    if not actions:
        return 0
    helpers.bulk(es, actions, raise_on_error=False, request_timeout=60)
    return len(actions)


# ana fonksiyon
async def async_guncelle():
    print("\n güncelleme başladı (ASYNC) \n")

    # haber linkleri 
    haberler = haber_linkleri_al()

    # 2) veritabanı kayıt kontrolü
    es_mod_map = es_mevcut_url_ve_modified()
    print("ES mevcut kayıt sayısı:", len(es_mod_map))

    kayitlar = kayitli_linkler()

    # 4) aiohttp oturumu
    sem = asyncio.Semaphore(ASYNC_HTTP_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_TOTAL)
    connector = aiohttp.TCPConnector(limit=ASYNC_HTTP_CONCURRENCY)

    bulk_actions = []
    indexed = 0
    skipped = 0
    errors = 0

    loop = asyncio.get_running_loop()
    pool = ThreadPoolExecutor(max_workers=THREAD_WORKERS)

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0"}
    ) as aio_sess:

        # makale linklerini alma
        makaleler, html_cache = await yazar_makaleleri_son_1_ay(aio_sess, sem)

        # bütün linkleri birleştirme
        tum = list(set(haberler + makaleler))
        if TEST_MODE:
            tum = tum[:10]

        print("Toplam benzersiz link:", len(tum))

        # 7) fetch + parse
        tasks = [fetch_text(aio_sess, url, sem) for url in tum]

        for coro in asyncio.as_completed(tasks):
            url, html = await coro

            if not html and url in html_cache:
                html = html_cache[url]
            elif html and url in html_cache:
                pass
            elif not html:
                errors += 1
                continue

            result = await loop.run_in_executor(pool, parse_and_prepare_doc, url, html, es_mod_map)

            if result[0] == "skip":
                skipped += 1
                continue
            if result[0] == "err":
                errors += 1
                continue

            _, doc, link = result

            bulk_actions.append({
                "_op_type": "index",
                "_index": INDEX_NAME,
                "_source": doc
            })

            if link not in kayitlar:
                kayit_ekle(link)
                kayitlar.add(link)

            # buffer dolunca yaz 
            if len(bulk_actions) >= BULK_BATCH_SIZE:
                wrote = await loop.run_in_executor(pool, bulk_flush, bulk_actions)
                indexed += wrote
                bulk_actions.clear()

        # kalanları yaz
        if bulk_actions:
            wrote = await loop.run_in_executor(pool, bulk_flush, bulk_actions)
            indexed += wrote
            bulk_actions.clear()

    pool.shutdown(wait=True)

    print("\n--- ÖZET (ASYNC) ---")
    print("Indexlenen (bulk):", indexed)
    print("Skip (güncellenmemiş):", skipped)
    print("Hata/Alınamayan:", errors)


def guncelle_async_main():
    asyncio.run(async_guncelle())


# run
if __name__ == "__main__":
    guncelle_async_main()
