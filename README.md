
İlk sürümde sistem, bağlantıları **senkron ve sıralı** biçimde işlemekteydi.
Bu yapı, çok sayıda URL içeren durumlarda yüksek gecikmelere neden olmaktaydı.

Bu repository’de yer alan sürümde aşağıdaki iyileştirmeler uygulanmıştır:

### 🔹 Asenkron HTTP İstekleri
- Çok sayıda URL’ye eş zamanlı erişim sağlanmıştır
- Ağ gecikmeleri toplam çalışma süresinden ayrıştırılmıştır

### 🔹 Çoklu İş Parçacığı (Thread)
- HTML ayrıştırma ve veri hazırlama işlemleri paralel hâle getirilmiştir
- CPU yoğun işlemler ana akıştan ayrılmıştır

### 🔹 Toplu (Bulk) Elasticsearch Kayıtları
- Her kayıt için ayrı veritabanı isteği yerine
- Veriler tampon bellekte biriktirilerek toplu biçimde indekslenmiştir

Bu iyileştirmeler sonucunda sistemin toplam çalışma süresi
yaklaşık **50 dakikadan 4 dakikaya** düşürülmüştür.
