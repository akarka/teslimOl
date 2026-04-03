# Pafta Algılama ve Eşleştirme Prensipleri (Regex Logic)

Bu proje, mimari pafta numaralarını karmaşık dosya isimleri içerisinden ayıklamak için iki aşamalı bir regex (düzenli ifade) stratejisi kullanır. Temel amaç, "A-1" gibi bir paftanın "A-10" içinde yanlışlıkla bulunmasını engellemek ve "01-02-03" gibi liste halindeki dosyalarda doğru paftayı yakalamaktır.

## 1. Aşama: Tam ve Sınır-Duyarlı Eşleşme (Exact & Boundary Match)

Sistem ilk olarak referans listesindeki pafta numarasını (örn: `A-SD-WA-002`) dosya isminde tam olarak arar.

*   **Regex Yapısı:** `re.finditer(sheet_esc, filename, re.I)`
*   **Sınır Kontrolü (Boundary Check):** 
    *   Eşleşmenin öncesinde ve sonrasında alfanümerik (`a-z`, `A-Z`, `0-9`) bir karakter olup olmadığı kontrol edilir.
    *   **Kural:** Eğer eşleşen kısmın hemen önünde veya arkasında başka bir harf veya rakam varsa, bu "kısmi bir eşleşmedir" ve reddedilir.
    *   **Örnek:** `A-101`, `251231_A-101_R1.pdf` içinde bulunur; ancak `A-1011` veya `PA-101` içinde bulunmaz.

## 2. Aşama: Liste ve Aralıklı Fallback (List/Range Fallback)

Eğer tam eşleşme bulunamazsa (pafta numarası dosya isminde parçalanmış veya liste halinde sunulmuşsa), sistem ikinci aşamaya geçer.

*   **Ayrıştırma:** Pafta numarası "Ön ek" (Prefix) ve "Sayısal Sonek" (Numeric Suffix) olarak ikiye bölünür.
    *   *Örnek:* `A-SD-WA-003` -> Prefix: `A-SD-WA-`, Suffix: `003`
*   **Ön Koşul:** Dosya isminde paftanın "Ön ek"i mutlaka bulunmalıdır (Case-insensitive).
*   **Sayısal Arama:** Eğer ön ek varsa, dosya isminde paftanın sayısal karşılığı bağımsız bir "token" olarak aranır.
    *   **Esneklik:** Rakamın farklı formatları (`003`, `03` veya `3`) otomatik olarak taranır.
    *   **Bağımsızlık Kontrolü:** `(?<!\d)(...)(?!\d)` regex'i ile rakamın başka bir sayının parçası olmadığı (sağında veya solunda rakam olmadığı) doğrulanır.
*   **Örnek Senaryo:**
    *   **Pafta:** `A-SD-WA-003`
    *   **Dosya:** `...A-SD-WA-002_169-7-T1_01-02-03_Details.pdf`
    *   **Sonuç:** Dosyada `A-SD-WA-` ön eki bulunduğu ve listenin sonunda bağımsız bir `03` rakamı olduğu için eşleşme başarılı kabul edilir.

## Teknik Notlar

1.  **Performans:** Algoritma önce tam eşleşmeyi kontrol ettiği için, standart isimli dosyalar O(n) hızında işlenir. Sadece eşleşmeyenler için ağır analiz yapılır.
2.  **Case-Insensitivity:** Tüm aramalar `re.I` bayrağı ile büyük/küçük harf duyarsız yapılır.
3.  **Güvenlik:** Regex girişleri `re.escape()` ile sterilize edilerek, pafta numarasındaki noktaların (`.`) veya diğer özel karakterlerin regex operatörü olarak yorumlanması engellenir.
