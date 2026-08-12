"""
Son Dakika Haber Botu
======================
Belirlenen haber sitelerinin RSS beslemelerini kontrol eder,
daha önce görülmemiş ve son 30 dakika içinde yayınlanmış
haberleri Telegram'a bildirir.

Gerekli ortam değişkenleri (GitHub Secrets üzerinden gelir):
- TELEGRAM_TOKEN : BotFather'dan alınan bot token'ı
- CHAT_ID        : Bildirimlerin gönderileceği sohbet/kanal ID'si
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# Takip edilecek kaynaklar.
# Yeni bir kaynak eklemek için "Kaynak Adı": "RSS_URL" satırı eklemen yeterli.
FEEDS = {
    "NTV": "https://www.ntv.com.tr/gundem.rss",
    "Sözcü": "https://www.sozcu.com.tr/feeds-son-dakika",
    "Habertürk": "https://www.haberturk.com/rss",
    "Hürriyet": "https://www.hurriyet.com.tr/rss/anasayfa",
    "Sporx": "https://www.sporx.com/son-dakika-rss",
}

STATE_FILE = Path("seen_ids.json")
MAX_STORED_PER_FEED = 300

# Bu süreden eski haberler bildirilmez.
# GitHub Actions bazen gecikmeli tetiklendiğinden biraz geniş tutuyoruz.
MAX_HABER_YASI_DAKIKA = 30


def load_state() -> dict:
    """Daha önce görülen haber ID'lerini dosyadan okur."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("⚠️ seen_ids.json bozuk görünüyor, sıfırdan başlanıyor.")
            return {}
    return {}


def save_state(state: dict) -> None:
    """Görülen haber ID'lerini dosyaya yazar."""
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_entry_time(entry) -> datetime | None:
    """
    RSS entry'sinin yayınlanma zamanını döner.
    Birden fazla zaman alanını dener; hiçbiri yoksa None döner.
    """
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def is_recent(entry) -> bool:
    """
    Haberin MAX_HABER_YASI_DAKIKA içinde yayınlanıp yayınlanmadığını kontrol eder.
    Zaman bilgisi yoksa haberi yeni kabul eder (kaçırmamak için).
    """
    pub_time = parse_entry_time(entry)
    if pub_time is None:
        return True  # zaman bilinmiyorsa gönder, kaçırma
    now = datetime.now(timezone.utc)
    return (now - pub_time) <= timedelta(minutes=MAX_HABER_YASI_DAKIKA)


def send_telegram(client: httpx.Client, kaynak: str, title: str, link: str) -> None:
    """Tek bir haberi Telegram'a gönderir."""
    text = f"📰 <b>{kaynak}</b>\n{title}\n{link}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = client.post(
            url,
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10.0,
        )
        r.raise_for_status()
        # Telegram API rate limit: saniyede 30 mesaj.
        # Birden fazla haber varsa kısa bekleme ekle.
        time.sleep(0.5)
    except Exception as e:
        print(f"⚠️ Telegram gönderim hatası ({kaynak}): {e}")


def main() -> None:
    state = load_state()
    yeni_haber_sayisi = 0
    eski_haber_sayisi = 0

    with httpx.Client() as client:
        for kaynak, feed_url in FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                print(f"⚠️ {kaynak} feed okunamadı: {e}")
                continue

            if feed.bozo and not feed.entries:
                print(f"⚠️ {kaynak} feed hatalı görünüyor, atlanıyor.")
                continue

            seen_ids = set(state.get(kaynak, []))
            ilk_calisma = kaynak not in state
            guncel_id_listesi = list(seen_ids)

            # RSS'ler genelde en yeni haber en üstte gelir.
            # Ters çevirip eskiden yeniye işleyelim — Telegram'da
            # haberler kronolojik sırayla görünsün.
            entries = list(reversed(feed.entries))

            for entry in entries:
                entry_id = entry.get("id") or entry.get("link")
                if not entry_id or entry_id in seen_ids:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()

                # ID'yi her durumda kaydet — gönderip göndermediğimizden bağımsız.
                seen_ids.add(entry_id)
                guncel_id_listesi.append(entry_id)

                if ilk_calisma:
                    continue  # İlk çalışmada sadece kaydet, gönderme

                if not is_recent(entry):
                    eski_haber_sayisi += 1
                    continue  # Eski haber, atla

                send_telegram(client, kaynak, title, link)
                yeni_haber_sayisi += 1

            state[kaynak] = guncel_id_listesi[-MAX_STORED_PER_FEED:]

            if ilk_calisma:
                print(f"ℹ️ {kaynak}: ilk çalıştırma, mevcut haberler kaydedildi.")
            else:
                print(f"✔️ {kaynak}: kontrol edildi.")

    save_state(state)
    if eski_haber_sayisi:
        print(f"⏩ {eski_haber_sayisi} eski haber zaman filtresiyle atlandı.")
    print(f"✅ Tamamlandı. {yeni_haber_sayisi} yeni haber bildirildi.")


if __name__ == "__main__":
    main()
