"""
Son Dakika Haber Botu
======================
Belirlenen haber sitelerinin RSS beslemelerini kontrol eder,
daha önce görülmemiş ve son 30 dakika içinde yayınlanmış
haberleri Telegram'a bildirir.

Telegram komutları (bot dinleyici ayrı bir workflow ile çalışır):
  /durum   → botun son çalışma bilgisini gösterir
  /başlat  → GitHub Actions workflow'unu manuel tetikler

Gerekli ortam değişkenleri (GitHub Secrets):
  TELEGRAM_TOKEN   : BotFather'dan alınan bot token'ı
  CHAT_ID          : Bildirimlerin gönderileceği sohbet ID'si
  GH_TOKEN_PAT : GitHub Personal Access Token (workflow tetiklemek için)
  GH_REPO      : kullanıcıadı/repo-adi formatında repo adı
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
GH_TOKEN_PAT = os.environ.get("GH_TOKEN_PAT", "")
GH_REPO = os.environ.get("GH_REPO", "")

FEEDS = {
    "NTV": "https://www.ntv.com.tr/gundem.rss",
    "Sözcü": "https://www.sozcu.com.tr/feeds-son-dakika",
    "Habertürk": "https://www.haberturk.com/rss",
    "Hürriyet": "https://www.hurriyet.com.tr/rss/anasayfa",
    "Sporx": "https://www.sporx.com/son-dakika-rss",
    "BBC Türkçe": "https://feeds.bbci.co.uk/turkce/rss.xml",
    "Milliyet": "https://www.milliyet.com.tr/rss/rssNew/gundemRss.xml",
    "Cumhuriyet": "https://www.cumhuriyet.com.tr/rss/son_dakika.xml",
}

STATE_FILE = Path("seen_ids.json")
MAX_STORED_PER_FEED = 300
MAX_HABER_YASI_DAKIKA = 30


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("⚠️ seen_ids.json bozuk, sıfırdan başlanıyor.")
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_entry_time(entry):
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def is_recent(entry) -> bool:
    pub_time = parse_entry_time(entry)
    if pub_time is None:
        return True
    now = datetime.now(timezone.utc)
    return (now - pub_time) <= timedelta(minutes=MAX_HABER_YASI_DAKIKA)


def send_telegram(client: httpx.Client, text: str, chat_id: str = None) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = client.post(
            url,
            json={
                "chat_id": chat_id or CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        time.sleep(0.5)
    except Exception as e:
        print(f"⚠️ Telegram gönderim hatası: {e}")


def trigger_workflow(client: httpx.Client) -> bool:
    """GitHub Actions workflow'unu manuel tetikler."""
    if not GH_TOKEN_PAT or not GH_REPO:
        return False
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/haber-botu.yml/dispatches"
    try:
        r = client.post(
            url,
            headers={
                "Authorization": f"Bearer {GH_TOKEN_PAT}",
                "Accept": "application/vnd.github+json",
            },
            json={"ref": "main"},
            timeout=10.0,
        )
        return r.status_code == 204
    except Exception as e:
        print(f"⚠️ Workflow tetikleme hatası: {e}")
        return False


def get_telegram_updates(client: httpx.Client, offset: int = 0) -> list:
    """Telegram'dan gelen yeni mesajları çeker."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = client.get(url, params={"offset": offset, "timeout": 5}, timeout=10.0)
        data = r.json()
        return data.get("result", [])
    except Exception as e:
        print(f"⚠️ Telegram güncelleme hatası: {e}")
        return []


def handle_telegram_commands(client: httpx.Client, state: dict, yeni_haber_sayisi: int) -> None:
    """
    Telegram'dan gelen komutları işler.
    Offset bilgisi state içinde tutulur, böylece aynı komut iki kez işlenmez.
    """
    offset = state.get("_telegram_offset", 0)
    updates = get_telegram_updates(client, offset)

    for update in updates:
        update_id = update.get("update_id", 0)
        state["_telegram_offset"] = update_id + 1

        message = update.get("message", {})
        text = message.get("text", "").strip().lower()
        from_id = str(message.get("from", {}).get("id", ""))
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Sadece kendi mesajlarımıza cevap ver
        if from_id != str(CHAT_ID) and chat_id != str(CHAT_ID):
            continue

        if text == "/durum":
            son_calisma = state.get("_son_calisma", "Henüz kayıt yok")
            toplam_bildirim = state.get("_toplam_bildirim", 0)
            aktif_kaynaklar = ", ".join(FEEDS.keys())
            mesaj = (
                f"🤖 <b>Bot Durumu</b>\n\n"
                f"✅ Bot aktif ve çalışıyor\n"
                f"🕐 Son çalışma: <b>{son_calisma}</b>\n"
                f"📨 Toplam gönderilen haber: <b>{toplam_bildirim}</b>\n\n"
                f"📡 <b>Aktif kaynaklar:</b>\n{aktif_kaynaklar}"
            )
            send_telegram(client, mesaj, chat_id)

        elif text == "/başlat" or text == "/baslat":
            basarili = trigger_workflow(client)
            if basarili:
                send_telegram(client, "▶️ Bot manuel olarak tetiklendi! Birkaç dakika içinde haberler kontrol edilecek.", chat_id)
            else:
                send_telegram(client, "⚠️ Tetikleme başarısız. GH_TOKEN_PAT ve GH_REPO ayarlarını kontrol et.", chat_id)


def main() -> None:
    state = load_state()
    yeni_haber_sayisi = 0
    eski_haber_sayisi = 0

    with httpx.Client() as client:

        # Önce Telegram komutlarını işle
        handle_telegram_commands(client, state, yeni_haber_sayisi)

        # Sonra haberleri kontrol et
        for kaynak, feed_url in FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                print(f"⚠️ {kaynak} feed okunamadı: {e}")
                continue

            if feed.bozo and not feed.entries:
                print(f"⚠️ {kaynak} feed hatalı, atlanıyor.")
                continue

            seen_ids = set(state.get(kaynak, []))
            ilk_calisma = kaynak not in state
            guncel_id_listesi = list(seen_ids)

            entries = list(reversed(feed.entries))

            for entry in entries:
                entry_id = entry.get("id") or entry.get("link")
                if not entry_id or entry_id in seen_ids:
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()

                seen_ids.add(entry_id)
                guncel_id_listesi.append(entry_id)

                if ilk_calisma:
                    continue

                if not is_recent(entry):
                    eski_haber_sayisi += 1
                    continue

                send_telegram(client, f"📰 <b>{kaynak}</b>\n{title}\n{link}")
                yeni_haber_sayisi += 1

            state[kaynak] = guncel_id_listesi[-MAX_STORED_PER_FEED:]

            if ilk_calisma:
                print(f"ℹ️ {kaynak}: ilk çalıştırma, haberler kaydedildi.")
            else:
                print(f"✔️ {kaynak}: kontrol edildi.")

        # Durum bilgisini güncelle
        state["_son_calisma"] = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        state["_toplam_bildirim"] = state.get("_toplam_bildirim", 0) + yeni_haber_sayisi

    save_state(state)
    if eski_haber_sayisi:
        print(f"⏩ {eski_haber_sayisi} eski haber zaman filtresiyle atlandı.")
    print(f"✅ Tamamlandı. {yeni_haber_sayisi} yeni haber bildirildi.")


if __name__ == "__main__":
    main()
