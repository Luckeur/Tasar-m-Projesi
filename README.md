## Sistem Bileşenleri

Bu repository, tasarım projesi kapsamında geliştirilen sistemin
iki ana bileşenine ait kaynak kodları içermektedir.

### 1. İçerik Tarama ve İndeksleme Sistemi
Bu bileşen, haber sitelerindeki bağlantıların taranması,
sayfa içeriklerinin ayrıştırılması ve elde edilen verilerin
Elasticsearch üzerinde indekslenmesini gerçekleştirmektedir.

Bu modüle ait kaynak kod:
- crawling.py

İlk sürümde senkron ve sıralı çalışan tarama yapısı,
asenkron HTTP istekleri, çoklu iş parçacığı kullanımı
ve Elasticsearch bulk indeksleme yöntemleri ile
optimize edilmiştir. Yapılan iyileştirmeler sonucunda
sistemin toplam çalışma süresi yaklaşık 50 dakikadan
4 dakikaya düşürülmüştür.

### 2. Arayüz ve Sorgu Sistemi
Bu bileşen, indekslenen veriler üzerinde kullanıcı etkileşimli
arama yapılabilmesini sağlayan masaüstü tabanlı bir arayüz ve
sorgu sisteminden oluşmaktadır.

Sistem;
- Doğrudan eşleşmeye dayalı kural tabanlı arama
- Embedding tabanlı anlamsal benzerliklere dayalı
  muhtemel sonuç önerileri

olmak üzere iki aşamalı bir sorgu yapısı sunmaktadır.

Bu modüle ait kaynak kod:
- arayuz_ve_sorgu.py

### Rapordaki Karşılığı
Bu repository’de yer alan tüm kaynak kodlar,
tasarım projesi raporunda açıklanan sistem mimarisi,
sorgu sistemi ve arayüz tasarımı bölümleri ile
birebir uyumludur.

Arayüz, sorgu ve tarama sistemlerinin tam kaynak kodları,
raporun EK-7 bölümünde referans verilen bu GitHub deposu
üzerinden paylaşılmıştır.
