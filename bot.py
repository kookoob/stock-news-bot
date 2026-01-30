import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
import re
import shutil
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

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
    # 국제/전쟁 속보
    ("국제속보(연합)", "https://www.yna.co.kr/rss/international.xml", "last_link_yna_world.txt", "연합뉴스"),
    ("전쟁속보(구글)", "https://news.google.com/rss/search?q=전쟁+속보+미국+이란&hl=ko&gl=KR&ceid=KR:ko", "last_link_google_war.txt", "Google News"),

    # 경제/주식 뉴스
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
    ("속보(텔레그램)", "https://rsshub.app/telegram/channel/bornlupin", "last_link_bornlupin.txt", "Telegram"),
    ("한국주식(연합)", "https://www.yna.co.kr/rss/economy.xml", "last_link_yna.txt", "연합뉴스")
]

# ★ [수정] 기억할 히스토리 개수 (2000개로 상향)
MAX_HISTORY = 2000
GLOBAL_TITLE_FILE = "processed_global_titles.txt"

# ==========================================
# 4. 시간 제어 함수 (6시간 이내 체크)
# ==========================================
def is_recent_news(entry):
    if not hasattr(entry, 'published_parsed') or not entry.published_parsed:
        return True
    try:
        published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_diff = current_time - published_time
        
        # 6시간 경과 체크
        if time_diff > timedelta(hours=6):
            print(f"⏳ [오래된 뉴스] 6시간 경과로 스킵: {time_diff}")
            return False
        return True
    except:
        return True

# ==========================================
# 5. 이미지 및 AI 관련 함수
# ==========================================
def create_info_image(text_lines, source_name):
    try:
        width, height = 1200, 675 
        background_color = (18, 18, 18)
        text_color = (235, 235, 235)
        title_color = (255, 255, 255)
        accent_color = (0, 190, 255)
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        font_path = "font.ttf"
        try:
            title_font = ImageFont.truetype(font_path, 54) 
            body_font = ImageFont.truetype(font_path, 32)
            source_font = ImageFont.truetype(font_path, 24)
        except: return None

        margin_x = 80       
        header_y = 45
        if source_name: header_text = f"Market Radar | {source_name}"
        else: header_text = "Market Radar"
        draw.text((margin_x, header_y), header_text, font=source_font, fill=accent_color)
        draw.text((margin_x, header_y + 30), "@marketradar0", font=source_font, fill=text_color)

        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year % 100}년 {now.month}월 {now.day}일"
        try: date_width = draw.textlength(date_str, font=source_font)
        except AttributeError: date_width = source_font.getsize(date_str)[0]
        draw.text((width - margin_x - date_width, header_y), date_str, font=source_font, fill=text_color)

        current_y = 140     
        for i, line in enumerate(text_lines):
            line = line.strip().replace("**", "").replace("##", "")
            if not line: continue
            if i == 0: 
                wrapped_lines = textwrap.wrap(line, width=18)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=title_font, fill=title_color)
                    current_y += 70
                current_y += 25
                draw.line([(margin_x, current_y), (width-margin_x, current_y)], fill=(80, 80, 80), width=2)
                current_y += 45
            else: 
                bullet_size = 10
                bullet_y = current_y + 12
                draw.rectangle([margin_x - 25, bullet_y, margin_x - 25 + bullet_size, bullet_y + bullet_size], fill=accent_color)
                wrapped_lines = textwrap.wrap(line, width=35)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=body_font, fill=text_color)
                    current_y += 42
                current_y += 10
            if current_y > height - 50: break 
        temp_filename = "temp_card_16_9.png"
        image.save(temp_filename)
        return temp_filename
    except: return None

def extract_image_url(entry):
    if 'media_content' in entry:
        media = entry.media_content[0]
        if 'url' in media: return media['url']
    if 'links' in entry:
        for link in entry.links:
            if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''): return link['href']
    if 'description' in entry:
        urls = re.findall(r'<img[^>]+src="([^">]+)"', entry.description)
        if urls: return urls[0]
    return None

def download_image(url):
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            filename = "temp_downloaded_image.jpg"
            with open(filename, 'wb') as out_file:
                shutil.copyfileobj(response.raw, out_file)
            return filename
    except: pass
    return None

def get_working_model():
    print("🤖 사용 가능한 AI 모델 검색 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    preferred_order = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    try:
        response = requests.get(url)
        if response.status_code == 200:
            models = [m['name'].replace('models/', '') for m in response.json().get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
            for pref in preferred_order:
                for model in models:
                    if pref in model: 
                        print(f"✅ 모델 찾음: {model}")
                        return model
            if models: return models[0]
    except: pass
    return "gemini-1.5-flash"

def summarize_news(target_model, title, link, content_text=""):
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}
    뉴스 내용(Raw): {content_text}
    분석 후 트위터 본문, 인포그래픽 텍스트, 원천 소스를 찾아줘.
    [작성 규칙 1: 트위터 본문]
    - ---BODY--- 아래 작성. X 프리미엄용 장문 상세 요약. 한국어 번역 필수. 명사형 종결/음슴체.
    - 구성: 제목(이모지+한글), 상세 내용(✅ 체크포인트), 하단 티커($)+해시태그(#)
    [작성 규칙 2: 인포그래픽 이미지]
    - ---IMAGE--- 아래 작성.
    - 구성: 첫 줄 강렬한 한글 제목(핵심 수치 포함, 이모지X). 나머지 핵심 요약 7문장 이내.
    [작성 규칙 3: 원천 소스]
    - ---SOURCE--- 아래 작성. 언론사 이름만. 없으면 Unknown.
    [금지사항] 마크다운(**, ##) 금지.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]}
    headers = {'Content-Type': 'application/json'}
    for _ in range(3):
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                full_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                if "---BODY---" in full_text and "---IMAGE---" in full_text:
                    parts = full_text.split("---IMAGE---")
                    body_raw = parts[0].replace("---BODY---", "").strip()
                    remaining = parts[1]
                    if "---SOURCE---" in remaining:
                        img_parts = remaining.split("---SOURCE---")
                        image_raw = img_parts[0].strip()
                        source_raw = img_parts[1].strip()
                    else: image_raw = remaining.strip(); source_raw = "Unknown"
                    body_part = body_raw.replace("**", "").replace("##", "")
                    image_lines = [re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►]+\s*", "", re.sub(r"^\d+\.\s+", "", l.strip().replace("**", "").replace("##", ""))) for l in image_raw.split('\n') if l.strip()]
                    source_name = source_raw.split('\n')[0].strip()
                    if "Unknown" in source_name or len(source_name) > 20: source_name = None
                    return body_part, image_lines, source_name
                return None, None, None
            elif response.status_code == 429: time.sleep(60); continue
            else: return None, None, None
        except: return None, None, None
    return None, None, None

# ==========================================
# 6. 기록 관리 (최대 2000개 유지 & 중복 검사)
# ==========================================
def get_processed_links(filename):
    if not os.path.exists(filename): return []
    # 읽어올 때 공백 제거
    with open(filename, 'r', encoding='utf-8') as f: return [line.strip() for line in f.readlines()]

def save_processed_link(filename, link):
    links = get_processed_links(filename)
    clean_link = link.strip() # ★ 저장할 때도 공백 제거
    if clean_link not in links:
        links.append(clean_link)
        if len(links) > MAX_HISTORY: links = links[-MAX_HISTORY:]
        with open(filename, 'w', encoding='utf-8') as f: f.write("\n".join(links))

def get_global_titles():
    if not os.path.exists(GLOBAL_TITLE_FILE): return []
    with open(GLOBAL_TITLE_FILE, 'r', encoding='utf-8') as f: return [line.strip() for line in f.readlines()]

def save_global_title(title):
    titles = get_global_titles()
    clean_title = re.sub(r'\s+', ' ', title).strip()
    if clean_title not in titles:
        titles.append(clean_title)
        if len(titles) > MAX_HISTORY: titles = titles[-MAX_HISTORY:]
        with open(GLOBAL_TITLE_FILE, 'w', encoding='utf-8') as f: f.write("\n".join(titles))

def is_similar_title(new_title, existing_titles):
    clean_new = re.sub(r'\s+', ' ', new_title).strip()
    for old_title in existing_titles:
        if SequenceMatcher(None, clean_new, old_title).ratio() > 0.6: 
            print(f"🚫 중복 감지 (유사도): {clean_new} <-> {old_title}")
            return True
    return False

# ==========================================
# 7. 메인 실행 로직
# ==========================================
if __name__ == "__main__":
    current_model = get_working_model()
    global_titles = get_global_titles()
    
    for category, rss_url, filename, default_source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries: print("뉴스 없음"); continue
            news = feed.entries[0]
        except: print("RSS 파싱 실패"); continue
        
        # 6시간 이내 체크
        if not is_recent_news(news):
            continue

        processed_links = get_processed_links(filename)
        # ★ 링크 비교 시 공백 제거 후 비교 (안전장치)
        if news.link.strip() in processed_links: 
            print("이미 처리된 링크 (동일 URL)"); continue

        check_title = news.title if news.title else (news.description[:50] if hasattr(news, 'description') else "")
        
        # 중복 체크
        if is_similar_title(check_title, global_titles):
            print("패스: 다른 소스에서 이미 다룬 내용."); save_processed_link(filename, news.link); continue

        print(f"✨ 새 뉴스 발견: {news.title}")
        real_link = news.link
        content_for_ai = ""
        if hasattr(news, 'description'):
            content_for_ai = news.description
            if "텔레그램" in category:
                urls = re.findall(r'(https?://\S+)', content_for_ai)
                if urls: real_link = urls[0]

        body_text, img_lines, detected_source = summarize_news(current_model, news.title, real_link, content_for_ai)
        
        if body_text and img_lines:
            final_source_name = detected_source if "텔레그램" in category else default_source_name
            image_file = create_info_image(img_lines, final_source_name)
            
            try:
                media_id = None
                if image_file: media = api.media_upload(image_file); media_id = media.media_id
                final_tweet = body_text if not final_source_name else f"{body_text}\n\n출처: {final_source_name}"
                if len(final_tweet) > 12000: final_tweet = final_tweet[:11995] + "..."
                if media_id: response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                else: response = client.create_tweet(text=final_tweet)
                tweet_id = response.data['id']
                print("✅ 업로드 성공")
                client.create_tweet(text=f"🔗 원문 기사:\n{real_link}", in_reply_to_tweet_id=tweet_id)
                
                # ★ 성공 시 링크 저장 (공백 제거)
                save_processed_link(filename, news.link)
                save_global_title(check_title)
                global_titles.append(re.sub(r'\s+', ' ', check_title).strip())
            except Exception as e: print(f"❌ 전송 실패: {e}")
            if image_file and os.path.exists(image_file): os.remove(image_file)
        else: print("🚨 요약 실패")
        time.sleep(2)
