# -*- coding: utf-8 -*-

import os
os.environ["PYTHONIOENCODING"] = "utf-8"
import feedparser
import time
import requests
from datetime import datetime, timezone, timedelta
import openai
import difflib
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# === НАСТРОЙКИ ===
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# === RSS ИСТОЧНИКИ ===
rss_feeds = [
    "https://www.tagesschau.de/xml/rss2",
    "https://www.zdf.de/rss/zdfheutea.xml",
    "https://www.spiegel.de/international/index.rss",
    "https://www.sueddeutsche.de/news/rss"
]

# === ОБРАБОТКА ТЕКСТА ПЕРЕД ОТПРАВКОЙ ===
def fix_formatting(text):
    lines = text.strip().split("\n")
    clean_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Удаляем жирность внутри абзацев
        line = re.sub(r"\*{2,}|_{2,}", "", line)
        line = re.sub(r"<[^>]+>", "", line)  # убираем html-теги

        clean_lines.append(line)

    if not clean_lines:
        return text

    # Первый заголовок — жирный
    clean_lines[0] = f"*{clean_lines[0].strip('*').strip()}*"

    # Форматируем цитаты (оставляем только блоки начинающиеся с > или в кавычках)
    for i in range(1, len(clean_lines)):
        if clean_lines[i].startswith('"') or clean_lines[i].startswith("“"):
            clean_lines[i] = clean_lines[i].strip('\'"')
        if clean_lines[i].startswith(">") and not clean_lines[i].startswith("> "):
            clean_lines[i] = clean_lines[i].replace(">", "> ", 1)

    return "\n\n".join(clean_lines)

# === ФУНКЦИЯ: форматирование новости ===
def format_news(raw_news):
    response = client.chat.completions.create(
        model="mistralai/mistral-7b-instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein erfahrener Redakteur für einen deutschen Telegram-Nachrichtenkanal. "
                    "Erstelle Beiträge im gültigen Telegram-Markdown-Stil. "
                    "Verwende ausschließlich folgende Formatierungen:\n"
                    "- *fett* mit `*text*`\n"
                    "- _kursiv_ mit `_text_`\n"
                    "- Zitate mit `> text`\n"
                    "- Keine Hashtags, keine `**` oder `__`, keine Links, keine Emojis.\n\n"
                    "Struktur:\n"
                    "1. *Fette Überschrift ganz oben*\n"
                    "2. Kurzer Einstiegssatz\n"
                    "3. Ein oder zwei Absätze mit Fakten\n"
                    "4. Optional ein Zitatblock (`> Zitat`)\n\n"
                    "Nutze `\\n\\n` für Absatztrennung. Der Text soll klar, sachlich und professionell wirken."
                )
            },
            {
                "role": "user",
                "content": f"Formuliere aus dieser Nachricht einen hochwertigen Beitrag:\n\n{raw_news}"
            }
        ],
        temperature=0.7,
        max_tokens=600
    )
    content = response.choices[0].message.content
    return fix_formatting(content)

# === ФУНКЦИЯ: отправка в Telegram ===
def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"❌ Ошибка отправки: {response.text}")
    else:
        print("✅ Сообщение отправлено")

# === ФУНКЦИЯ: проверка на дублирование по заголовку ===
def is_similar(title, processed_titles):
    for prev_title in processed_titles:
        similarity = difflib.SequenceMatcher(None, title.lower(), prev_title.lower()).ratio()
        if similarity > 0.75:
            return True
    return False

# === ОСНОВНАЯ ЛОГИКА ===
fresh_time = datetime.now(timezone.utc) - timedelta(hours=2)
processed_titles = []

for feed_url in rss_feeds:
    print(f"\n🔗 Читаем ленту: {feed_url}")
    feed = feedparser.parse(feed_url)

    for entry in feed.entries:
        try:
            published = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
            if published < fresh_time:
                continue

            title = entry.title
            if is_similar(title, processed_titles):
                print(f"⏩ Пропущено (дубликат): {title}")
                continue

            summary = entry.summary if hasattr(entry, "summary") else ""
            raw_text = f"{title}\n{summary}"

            print(f"\n🟡 Обрабатываем: {title}")
            formatted_post = format_news(raw_text)
            send_to_telegram(formatted_post)
            print(f"✅ Отправлено: {title}")
            processed_titles.append(title)

        except Exception as e:
            print(f"⚠️ Ошибка: {e}")