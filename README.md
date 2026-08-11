Son Dakika Haber Botu
NTV, Sözcü, Habertürk, Hürriyet ve Sporx'un RSS beslemelerini 5 dakikada
bir kontrol edip yeni haberleri Telegram'a bildiren bot.
Nasıl çalışır?
`main.py` her kaynağın RSS adresini okur, daha önce görülmemiş haberleri
bulur ve Telegram'a gönderir.
Hangi haberlerin görüldüğü `seen_ids.json` dosyasında tutulur.
`.github/workflows/haber-botu.yml`, GitHub Actions'a botu 5 dakikada bir
otomatik çalıştırmasını, sonra `seen_ids.json`'ı güncelleyip depoya geri
kaydetmesini söyler.
Kurulum
Detaylı adım adım kurulum talimatları Claude ile yapılan sohbette anlatıldı.
Özetle:
`TELEGRAM_TOKEN` ve `CHAT_ID` değerlerini GitHub reponun
Settings → Secrets and variables → Actions bölümüne ekle.
Bu repoyu GitHub'a yükle (bu dosyaların hepsiyle birlikte).
Actions sekmesinden workflow'un etkin olduğundan emin ol.
İlk çalıştırmada bot sadece mevcut haberleri kaydeder, bildirim
göndermez. İkinci çalıştırmadan itibaren yeni haberler Telegram'a düşer.
Yeni bir haber kaynağı eklemek
`main.py` içindeki `FEEDS` sözlüğüne `"Kaynak Adı": "RSS_URL"` şeklinde
yeni bir satır eklemen yeterli.
