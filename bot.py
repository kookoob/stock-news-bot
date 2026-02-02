import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
import re
import shutil
import json
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from bs4 import BeautifulSoup

# ==========================================
# 1. 환경 변수 로드
# ==========================================
def get_clean_env(name):
    val = os.environ.get(name)
    if val is None: return None
    return val.strip().replace('\n', '').replace('\r', '').replace(' ', '')

GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")
CONSUMER_KEY = get_clean_env("CONSUMER_KEY")
CONSUMER_SECRET = get_clean_env("CONSUMER_SECRET")
ACCESS_TOKEN = get_clean_env("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = get_clean_env("ACCESS_TOKEN_SECRET")

# ==========================================
# 2. 트위터 클라이언트 연결
# ==========================================
client = None
api = None
try:
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    auth = tweepy.OAuth1UserHandler(
        CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET
    )
    api = tweepy.API(auth)
except Exception as e:
    print(f"⚠️ 트위터 클라이언트 연결 실패: {e}")

# ==========================================
# 3. 뉴스 소스 리스트
# ==========================================
RSS_SOURCES = [
    ("Investing.com(News)", "https://kr.investing.com/rss/news.rss", "last_link_inv_news.txt", "Investing.com"),
    ("Investing.com(Market)", "https://kr.investing.com/rss/market_overview.rss", "last_link_inv_market.txt", "Investing.com"),
    ("Investing.com(Forex)", "https://kr.investing.com/rss/forex.rss", "last_link_inv_forex.txt", "Investing.com"),
    ("Investing.com(Crypto)", "https://kr.investing.com/rss/290.rss", "last_link_inv_crypto.txt", "Investing.com"),
    ("Investing.com(Economy)", "https://kr.investing.com/rss/286.rss", "last_link_inv_economy.txt", "Investing.com"),
    ("Investing.com(Stock)", "https://kr.investing.com/rss/stock.rss", "last_link_inv_stock.txt", "Investing.com"),
    ("Investing.com(Commodities)", "https://kr.investing.com/rss/commodities.rss", "last_link_inv_comm.txt", "Investing.com"),
    ("Investing.com(Bonds)", "https://kr.investing.com/rss/bonds.rss", "last_link_inv_bonds.txt", "Investing.com"),
    ("트럼프(TruthSocial)", "https://t.me/s/real_DonaldJTrump", "last_id_trump.txt", "Telegram"),
    ("트럼프(Goddess)", "https://t.me/s/goddessTTF", "last_id_goddess.txt", "Telegram"),
    ("하나차이나(China)", "https://t.me/s/HANAchina", "last_link_hana.txt", "Telegram"),
    ("마이클버리(Burry)", "https://nitter.privacydev.net/michaeljburry/rss", "last_link_burry.txt", "Michael Burry"),
    ("미국주식(블룸버그)", "https://news.google.com/rss/search?q=site:bloomberg.com+when:1d&hl=en-US&gl=US&ceid=US:en", "last_link_bloomberg.txt", "Bloomberg"),
    ("속보(텔레그램)", "https://t.me/s/bornlupin", "last_link_bornlupin.txt", "Telegram"),
    ("연예뉴스(연합)", "https://www.yna.co.kr/rss/entertainment.xml", "last_link_yna_ent.txt", "연합뉴스"),
    ("국제속보(연합)", "https://www.yna.co.kr/rss/international.xml", "last_link_yna_world.txt", "연합뉴스"),
    ("전쟁속보(구글)", "https://news.google.com/rss/search?q=전쟁+속보+미국+이란&hl=ko&gl=KR&ceid=KR:ko", "last_link_google_war.txt", "Google News"),
    ("미국주식(투자)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069", "last_link_us_investing.txt", "CNBC"),
    ("미국주식(금융)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664", "last_link_us_finance.txt", "CNBC"),
    ("미국주식(기술)", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", "last_link_us_tech.txt", "CNBC"),
    ("한국주식(한경)", "https://www.hankyung.com/feed/finance", "last_link_kr.txt", "한국경제"),
    ("미국주식(Yahoo)", "https://finance.yahoo.com/news/rssindex", "last_link_yahoo.txt", "Yahoo Finance"),
    ("미국주식(Tech)", "https://techcrunch.com/feed/", "last_link_techcrunch.txt", "TechCrunch"),
    ("한국주식(매경)", "https://www.mk.co.kr/rss/50200011/", "last_link_mk.txt", "매일경제"),
    ("미국주식(WSJ_Opinion)", "https://feeds.content.dowjones.io/public/rss/RSSOpinion", "last_link_wsj_op.txt", "WSJ"),
    ("미국주식(WSJ_Market)", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", "last_link_wsj_mkt.txt", "WSJ"),
    ("미국주식(WSJ_Economy)", "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed", "last_link_wsj_eco.txt", "WSJ"),
    ("한국주식(연합)", "https://www.yna.co.kr/rss/economy.xml", "last_link_yna.txt", "연합뉴스")
]

MAX_HISTORY = 2000
GLOBAL_TITLE_FILE = "processed_global_titles.txt"
GLOBAL_SUMMARY_FILE = "processed_ai_summaries.txt"

SOURCE_MAP_KR = {
    "Investing.com": "인베스팅닷컴",
    "Bloomberg": "블룸버그",
    "WSJ": "WSJ",
    "CNBC": "CNBC",
    "Yahoo Finance": "야후파이낸스",
    "TechCrunch": "테크크런치",
    "Google News": "구글뉴스",
    "Michael Burry": "마이클버리",
    "연합뉴스": "연합뉴스",
    "한국경제": "한국경제",
    "매일경제": "매일경제"
}

# ==========================================
# 4. 크롤링 및 데이터 수집 함수
# ==========================================
class SimpleNews:
    def __init__(self, title, link, description, source_name, filename, published_parsed=None):
        self.title = title
        self.link = link
        self.description = description
        self.source_name = source_name
        self.filename = filename 
        self.published_parsed = published_parsed

def is_recent_news(entry):
    if not hasattr(entry, 'published_parsed') or not entry.published_parsed: return True
    try:
        published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_diff = current_time - published_time
        if time_diff > timedelta(hours=12): 
            return False
        return True
    except: return True

def fetch_telegram_latest(url, source_name, filename):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        messages = soup.select('.tgme_widget_message_wrap')
        if not messages: return None
        
        last_msg = messages[-1]
        text_elem = last_msg.select_one('.tgme_widget_message_text')
        full_text = ""
        if text_elem: full_text = text_elem.get_text(separator="\n").strip()
        
        link_elem = last_msg.select_one('a.tgme_widget_message_date')
        post_link = link_elem['href'] if link_elem else url
        title = full_text.split('\n')[0] if full_text else "텔레그램 포스트"
        if len(title) > 80: title = title[:80] + "..."
        
        return SimpleNews(title, post_link, full_text, source_name, filename)
    except: return None

def fetch_article_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "header", "footer", "nav", "aside", "form"]):
            script.decompose()
        paragraphs = soup.find_all('p')
        article_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 20])
        if len(article_text) < 100: article_text = soup.get_text(separator=' ', strip=True)
        return article_text[:4000]
    except: return None

# ==========================================
# 5. 이미지 생성 (요약 카드)
# ==========================================
def create_gradient_background(width, height, start_color, end_color):
    base = Image.new('RGB', (width, height), start_color)
    top = Image.new('RGB', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height): mask_data.extend([int(255 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def create_info_image(text_lines, source_name, index):
    try:
        width, height = 1200, 675
        bg_start = (10, 25, 45); bg_end = (20, 40, 70)
        text_white = (245, 245, 250); text_gray = (180, 190, 210)
        accent_cyan = (0, 220, 255); title_box_bg = (0, 0, 0, 80)
        image = create_gradient_background(width, height, bg_start, bg_end)
        draw = ImageDraw.Draw(image, 'RGBA')
        try:
            font_title_main = ImageFont.truetype("font_bold.ttf", 55)
            font_body = ImageFont.truetype("font_reg.ttf", 32)
            font_header = ImageFont.truetype("font_bold.ttf", 26)
            font_date = ImageFont.truetype("font_reg.ttf", 26)
        except:
            try:
                font_title_main = ImageFont.truetype("font.ttf", 55)
                font_body = ImageFont.truetype("font.ttf", 32)
                font_header = ImageFont.truetype("font.ttf", 26)
                font_date = ImageFont.truetype("font.ttf", 26)
            except: return None
            
        margin_x = 60; current_y = 40
        
        header_text = f"Koob | News {index}"; 
        if source_name and source_name != "Telegram": header_text += f" | {source_name}"
            
        draw.ellipse([(margin_x, current_y+8), (margin_x+12, current_y+20)], fill=accent_cyan)
        draw.text((margin_x + 25, current_y), header_text, font=font_header, fill=accent_cyan)
        
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year}.{now.month:02d}.{now.day:02d} | @kimyg002"
        date_bbox = draw.textbbox((0, 0), date_str, font=font_date)
        date_width = date_bbox[2] - date_bbox[0]
        draw.text((width - margin_x - date_width, current_y), date_str, font=font_date, fill=text_gray)
        current_y += 70
        
        for i, line in enumerate(text_lines):
            clean_line = re.sub(r"^[\W_]+", "", line.strip()) 
            clean_line = clean_line.replace("**", "").replace("##", "")
            if not clean_line: continue
            
            if i == 0: 
                wrapped_title = textwrap.wrap(clean_line, width=22)
                title_box_height = len(wrapped_title) * 80 + 30
                draw.rectangle([(margin_x - 20, current_y), (width - margin_x + 20, current_y + title_box_height)], fill=title_box_bg)
                current_y += 20
                for wl in wrapped_title:
                    draw.text((margin_x, current_y), wl, font=font_title_main, fill=text_white)
                    current_y += 80
                current_y += 40
            else: 
                bullet_y = current_y + 12
                draw.rectangle([margin_x, bullet_y, margin_x + 10, bullet_y + 10], fill=accent_cyan)
                wrapped_body = textwrap.wrap(clean_line, width=42)
                for wl in wrapped_body:
                    draw.text((margin_x + 35, current_y), wl, font=font_body, fill=text_white)
                    current_y += 45
                current_y += 15
            if current_y > height - 60: break 
            
        draw.rectangle([(margin_x, height - 20), (width - margin_x, height - 18)], fill=accent_cyan)
        temp_filename = f"temp_card_{index}.png"
        image.convert("RGB").save(temp_filename)
        return temp_filename
    except Exception as e: 
        print(f"이미지 생성 에러: {e}")
        return None

# ==========================================
# 6. AI 모델 및 처리
# ==========================================
def get_working_model():
    print("🤖 AI 모델 조회 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            models = [m['name'].replace('models/', '') for m in data.get('models', [])]
            priorities = ["gemini-1.5-pro", "gemini-1.5-pro-latest", "gemini-1.5-pro-001", "gemini-pro"]
            for p in priorities:
                if p in models: return p
            return models[0]
    except: pass
    return "gemini-pro"

def select_top_news(news_list, model_name):
    if len(news_list) <= 4: return news_list
    print(f"📊 {len(news_list)}개의 뉴스 중 Top 4 선별 중...")
    titles = [f"{i}. {n.title} (Source: {n.source_name})" for i, n in enumerate(news_list)]
    titles_text = "\n".join(titles)
    
    prompt = f"""
    You are a professional financial editor.
    Select the **Top 4 most important news items** impacting the global market.
    [News List]
    {titles_text}
    [Output]
    JSON array of indices (e.g. [0, 2, 5, 8])
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, headers={'Content-Type': 'application/json'}, json=data)
        text = response.json()['candidates'][0]['content']['parts'][0]['text']
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            indices = json.loads(match.group())
            selected = [news_list[i] for i in indices if i < len(news_list)]
            return selected[:4]
    except: pass
    return news_list[:4]

def summarize_news_item(target_model, news_item):
    content_text = news_item.description
    if not content_text or len(content_text) < 50:
         fetched = fetch_article_content(news_item.link)
         if fetched: content_text = fetched

    # ★ [핵심 수정] 프롬프트: 자세한 본문 내용 생성 요청
    prompt = f"""
    [Task]
    Analyze the provided news and generate outputs.
    
    [Input]
    Title: {news_item.title}
    Source: {news_item.source_name}
    Content: {content_text[:4000]}
    
    [Rules]
    1. Language: **Korean ONLY** for summary.
    2. Terminology: Never use '전기동', always use '구리'.
    3. Tone: **Abbreviated style (e.g., ~함, ~음, ~전망)**. 
    4. **Detail Level for TEXT:**
       - **Do NOT summarize in 1 line.** - Explain the 'Background/Context', 'Key Facts/Numbers', and 'Market Impact' in depth.
       - Each bullet point in the TEXT section must contain **2-3 detailed sentences**.
       - Make it look like a professional analyst's briefing.
    5. **Forbidden:**
       - Do NOT use labels like 'Detailed Point', 'Background:', etc. Just output the content.
       - Do NOT use markdown bold syntax (**text**) in the TEXT section.
    6. **Ticker Extraction:**
       - Identify specific companies or assets mentioned.
       - Convert to Stock Ticker format (e.g., Apple -> $AAPL, Bitcoin -> $BTC).
    
    [Output Format]
    ---IMAGE---
    (Title for Image - 1 line)
    (Short Summary 1 - 1 line)
    (Short Summary 2 - 1 line)
    (Short Summary 3 - 1 line)
    
    ---TEXT---
    (Title for Text - 1 line)
    (Deep Analysis 1: Context/Background - 2~3 sentences ending in noun form)
    (Deep Analysis 2: Key Facts/Numbers - 2~3 sentences ending in noun form)
    (Deep Analysis 3: Market Impact/Outlook - 2~3 sentences ending in noun form)
    (Related Sectors/Assets - 1 line)

    ---TICKERS---
    (Space-separated tickers starting with $, e.g. $AAPL $TSLA $005930. If none, leave empty)
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers={'Content-Type': 'application/json'}, json=data)
        text = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        result_data = {"image": [], "text": [], "tickers": []}
        
        if "---IMAGE---" in text:
            parts_img = text.split("---IMAGE---")[1].split("---TEXT---")
            image_str = parts_img[0].strip()
            remaining = parts_img[1].strip() if len(parts_img) > 1 else ""
            
            if "---TICKERS---" in remaining:
                parts_ticker = remaining.split("---TICKERS---")
                text_str = parts_ticker[0].strip()
                ticker_str = parts_ticker[1].strip()
                
                found_tickers = [t.strip() for t in ticker_str.split() if t.startswith('$')]
                result_data["tickers"] = found_tickers
            else:
                text_str = remaining
            
            result_data["image"] = [l.strip() for l in image_str.split('\n') if l.strip()]
            result_data["text"] = [l.strip() for l in text_str.split('\n') if l.strip()]
            return result_data
        else:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            return {"image": lines[:4], "text": lines, "tickers": []}
            
    except: return None

# ==========================================
# 7. 메인 실행 로직 (일괄 처리 모드)
# ==========================================
def get_file_lines(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f: return [line.strip() for line in f.readlines()]

def save_file_line(filename, line):
    lines = get_file_lines(filename)
    clean_line = re.sub(r'\s+', ' ', line).strip()
    if clean_line not in lines:
        lines.append(clean_line)
        if len(lines) > MAX_HISTORY: lines = lines[-MAX_HISTORY:]
        with open(filename, 'w', encoding='utf-8') as f: f.write("\n".join(lines))

def normalize_text(text):
    text = re.sub(r'[^\w\s]', '', text.lower())
    return set(text.split())

def is_duplicate(new_text, history_lines):
    if not new_text or len(new_text) < 5: return False
    new_words = normalize_text(new_text)
    if len(new_words) < 2: return False
    for old_text in reversed(history_lines):
        old_words = normalize_text(old_text)
        if not old_words: continue
        intersection = len(new_words & old_words)
        union = len(new_words | old_words)
        if union > 0 and (intersection / union) > 0.4: return True
        if SequenceMatcher(None, new_text, old_text).ratio() > 0.55: return True
    return False

if __name__ == "__main__":
    current_model = get_working_model()
    global_titles = get_file_lines(GLOBAL_TITLE_FILE)
    global_summaries = get_file_lines(GLOBAL_SUMMARY_FILE) 
    
    candidates = []
    print("🌍 전체 뉴스 소스 스캔 시작...")
    
    for category, rss_url, filename, source_name in RSS_SOURCES:
        news = None
        if "t.me/s/" in rss_url:
            news = fetch_telegram_latest(rss_url, source_name, filename)
        else:
            try:
                feed = feedparser.parse(rss_url)
                if feed.entries:
                    entry = feed.entries[0]
                    if is_recent_news(entry):
                        news = SimpleNews(entry.title, entry.link, getattr(entry, 'description', ''), source_name, filename)
            except: pass

        if not news: continue
        processed_links = get_file_lines(filename)
        if news.link.strip() in processed_links: continue
        check_content = news.title if news.title else news.description[:100]
        if is_duplicate(check_content, global_titles): continue
        candidates.append(news)

    print(f"✅ 수집된 후보 뉴스: {len(candidates)}개")
    if not candidates:
        print("📭 새로운 뉴스가 없습니다.")
        sys.exit(0)

    selected_news = select_top_news(candidates, current_model)
    print(f"🎯 최종 선별된 뉴스: {len(selected_news)}개")

    media_ids = []
    
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    weekday_kor = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    time_str = now.strftime(f"%m월 %d일 ({weekday_kor}) %H:%M")
    
    tweet_text_body = f"📅 {time_str} 기준 | 주요 소식 정리\n\n"
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    
    collected_tickers = set()
    collected_sources = set()

    processed_count = 0
    for i, news in enumerate(selected_news):
        print(f"Processing {i+1}/{len(selected_news)}: {news.title[:20]}...")
        
        if news.source_name != "Telegram":
            safe_source_name = SOURCE_MAP_KR.get(news.source_name, news.source_name)
            collected_sources.add(safe_source_name)

        result = summarize_news_item(current_model, news)
        if not result or not result.get("image"): continue
        
        image_lines = result["image"]
        text_lines = result["text"]
        
        if result.get("tickers"):
            for t in result["tickers"]:
                collected_tickers.add(t)

        image_lines = [l.replace("전기동", "구리") for l in image_lines]
        text_lines = [l.replace("전기동", "구리") for l in text_lines]
        
        # 볼드체 제거 등 청소
        text_lines = [l.replace("**", "").replace("##", "") for l in text_lines]

        joined_summary = " ".join(text_lines)
        if is_duplicate(joined_summary, global_summaries):
            print("  🚫 요약 내용 중복으로 스킵")
            save_file_line(news.filename, news.link)
            continue
            
        img_path = create_info_image(image_lines, news.source_name, i+1)
        if img_path:
            try:
                media = api.media_upload(img_path)
                media_ids.append(media.media_id)
                
                tweet_text_body += f"{emojis[i]} {text_lines[0]}\n" # 제목
                for line in text_lines[1:]:
                    tweet_text_body += f"  • {line}\n" # 내용 (이제 길게 나옴)
                tweet_text_body += "\n" 
                
                save_file_line(news.filename, news.link)
                save_file_line(GLOBAL_TITLE_FILE, news.title if news.title else news.description[:50])
                with open(GLOBAL_SUMMARY_FILE, 'a', encoding='utf-8') as f: f.write(joined_summary + "\n")
                
                processed_count += 1
                if os.path.exists(img_path): os.remove(img_path)
            except Exception as e:
                print(f"  ❌ 업로드 실패: {e}")

    if media_ids:
        if collected_sources:
            source_str = ", ".join(sorted(list(collected_sources)))
            tweet_text_body += f"출처 : {source_str}\n"

        base_tags = "#미국주식 #속보 #경제"
        ticker_tags = " ".join(list(collected_tickers)) 
        
        tweet_text_body += f"\n{base_tags} {ticker_tags}"
        
        if len(tweet_text_body) > 24000: tweet_text_body = tweet_text_body[:23995] + "..."
        
        try:
            response = client.create_tweet(text=tweet_text_body, media_ids=media_ids)
            print("🚀 [성공] 뉴스 리포트 전송 완료!")
            
        except Exception as e:
            print(f"❌ [실패] 트윗 전송 에러: {e}")
    else:
        print("🤷 게시할 유효한 뉴스가 없습니다.")
