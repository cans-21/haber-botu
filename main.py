"""
Son Dakika Haber Botu
======================
Belirlenen haber sitelerinin RSS beslemelerini kontrol eder,
daha önce görülmemiş haberleri Telegram'a bildirir.

Gerekli ortam değişkenleri (GitHub Secrets üzerinden gelir):
- TELEGRAM_TOKEN : BotFather'dan alınan bot token'ı
- CHAT_ID        : Bildirimlerin gönderileceği sohbet/kanal ID'si
"""

import json
import os
from pathlib import Path

import feedparser
import httpx

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# Takip edilecek kaynaklar. Yeni bir kaynak eklemek için buraya
# "Kaynak Adı": "RSS_URL" şeklinde yeni bir satır eklemen yeterli.
FEEDS = {
    "NTV": "https://www.ntv.com.tr/gundem.rss",
    "Sözcü": "https://www.sozcu.com.tr/feeds-son-dakika",
    "Habertürk": "https://www.haberturk.com/rss",
    "Hürriyet": "https://www.hurriyet.com.tr/rss/anasayfa",
    "Sporx": "https://www.sporx.com/son-dakika-rss",
}

STATE_FILE = Path("seen_ids.json")
# Her kaynak için hafızada tutulacak maksimum haber ID sayısı.
# Dosyanın sınırsız büyümesini engeller.
MAX_STORED_PER_FEED = 300


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
    except Exception as e:
        print(f"⚠️ Telegram gönderim hatası ({kaynak}): {e}")


def main() -> None:
    state = load_state()
    yeni_haber_sayisi = 0

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

            # RSS'ler genelde en yeni haber en üstte sıralanır.
            # Ters çevirip eskiden yeniye işleyelim ki Telegram'da
            # haberler kronolojik sırayla gelsin.
            entries = list(reversed(feed.entries))

            for entry in entries:
                entry_id = entry.get("id") or entry.get("link")
                if not entry_id or entry_id in seen_ids:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()

                if not ilk_calisma:
                    send_telegram(client, kaynak, title, link)
                    yeni_haber_sayisi += 1

                seen_ids.add(entry_id)
                guncel_id_listesi.append(entry_id)

            state[kaynak] = guncel_id_listesi[-MAX_STORED_PER_FEED:]

            if ilk_calisma:
                print(f"ℹ️ {kaynak}: ilk çalıştırma, mevcut haberler bildirilmeden kaydedildi.")
            else:
                print(f"✔️ {kaynak}: kontrol edildi.")

    save_state(state)
    print(f"✅ Tamamlandı. {yeni_haber_sayisi} yeni haber bildirildi.")


if __name__ == "__main__":
    main()
