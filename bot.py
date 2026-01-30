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
from bs4 import BeautifulSoup  # 웹/텔레그램 크롤링 필수

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
# 3. 뉴스 소스 리스트 (텔레그램 링크 수정됨)
# ==========================================
RSS_SOURCES = [
    # ★ [수정됨] RSS 대신 공식 웹 프리뷰 주소 사용
    ("속보(텔레그램)", "https://t.me/s/bornlupin", "last_link_bornlupin.txt", "Telegram"),

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

# ==========================================
# 4. 크롤링 및 데이터 수집 함수
# ==========================================
class SimpleNews:
    """RSS와 텔레그램 데이터를 통일된 형태로 다루기 위한 객체"""
    def __init__(self, title, link, description, published_parsed=None):
        self.title = title
        self.link = link
        self.description = description
        self.published_parsed = published_parsed

def is_recent_news(entry):
    if not hasattr(entry, 'published_parsed') or not entry.published_parsed:
        return True
    try:
        published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_diff = current_time - published_time
        if time_diff > timedelta(hours=6):
            print(f"⏳ [오래된 뉴스] 6시간 경과로 스킵: {time_diff}")
            return False
        return True
    except: return True

def fetch_telegram_latest(url):
    """텔레그램 t.me/s/ 주소에서 최신 메시지 직접 크롤링"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 메시지 래퍼들 찾기
        messages = soup.select('.tgme_widget_message_wrap')
        if not messages: return None
        
        # 가장 마지막 메시지(최신)
        last_msg = messages[-1]
        
        # 텍스트 추출
        text_elem = last_msg.select_one('.tgme_widget_message_text')
        if not text_elem: return None # 텍스트 없는 사진/스티커는 패스
        
        full_text = text_elem.get_text(separator="\n").strip()
        
        # 링크 추출 (메시지 시간 클릭 시 이동하는 고유 링크)
        link_elem = last_msg.select_one('a.tgme_widget_message_date')
        if link_elem:
            post_link = link_elem['href']
        else:
            post_link = url # 링크 못 찾으면 채널 주소로
            
        # 제목 생성 (첫 줄 혹은 앞부분)
        title = full_text.split('\n')[0]
        if len(title) > 50: title = title[:50] + "..."
        
        return SimpleNews(title, post_link, full_text)
        
    except Exception as e:
        print(f"⚠️ 텔레그램 크롤링 에러: {e}")
        return None

def fetch_article_content(url):
    """일반 뉴스 기사 본문 크롤링"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup(["script", "style", "header", "footer", "nav", "aside", "form"]):
            script.decompose()
        
        paragraphs = soup.find_all('p')
        article_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 20])
        
        if len(article_text) < 50:
             article_text = soup.get_text(separator=' ', strip=True)
             
        return article_text[:4000]
    except: return None

# ==========================================
# 5. 이미지 및 AI 관련 함수
# ==========================================
def create_gradient_background(width, height, start_color, end_color):
    base = Image.new('RGB', (width, height), start_color)
    top = Image.new('RGB', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        mask_data.extend([int(255 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def create_info_image(text_lines, source_name):
    try:
        width, height = 1200, 675
        bg_start = (10, 25, 45); bg_end = (20, 40, 70)
        text_white = (245, 245, 250); text_gray = (180, 190, 210)
        accent_cyan = (0, 220, 255); title_box_bg = (0, 0, 0, 80)

        image = create_gradient_background(width, height, bg_start, bg_end)
        draw = ImageDraw.Draw(image, 'RGBA')

        try:
            font_title_main = ImageFont.truetype("font_bold.ttf", 60) 
            font_body = ImageFont.truetype("font_reg.ttf", 34)
            font_header = ImageFont.truetype("font_bold.ttf", 26)
            font_date = ImageFont.truetype("font_reg.ttf", 26)
        except:
            print("⚠️ 폰트 로드 실패, 기본 폰트 사용")
            try:
                font_title_main = ImageFont.truetype("font.ttf", 60)
                font_body = ImageFont.truetype("font.ttf", 34)
                font_header = ImageFont.truetype("font.ttf", 26)
                font_date = ImageFont.truetype("font.ttf", 26)
            except: return None

        margin_x = 60; current_y = 40
        header_text = "MARKET RADAR"; 
        if source_name: header_text += f" | {source_name}"
        
        draw.ellipse([(margin_x, current_y+8), (margin_x+12, current_y+20)], fill=accent_cyan)
        draw.text((margin_x + 25, current_y), header_text, font=font_header, fill=accent_cyan)

        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year}.{now.month:02d}.{now.day:02d} | @marketradar0"
        
        date_bbox = draw.textbbox((0, 0), date_str, font=font_date)
        date_width = date_bbox[2] - date_bbox[0]
        draw.text((width - margin_x - date_width, current_y), date_str, font=font_date, fill=text_gray)
        current_y += 70

        for i, line in enumerate(text_lines):
            line = line.strip().replace("**", "").replace("##", "")
            if not line: continue
            if i == 0: 
                wrapped_title = textwrap.wrap(line, width=20)
                title_box_height = len(wrapped_title) * 85 + 30
                draw.rectangle([(margin_x - 20, current_y), (width - margin_x + 20, current_y + title_box_height)], fill=title_box_bg)
                current_y += 20
                for wl in wrapped_title:
                    draw.text((margin_x, current_y), wl, font=font_title_main, fill=text_white)
                    current_y += 85
                current_y += 40
            else: 
                bullet_text = "►"
                draw.text((margin_x, current_y + 2), bullet_text, font=font_header, fill=accent_cyan)
                wrapped_body = textwrap.wrap(line, width=40)
                for wl in wrapped_body:
                    draw.text((margin_x + 35, current_y), wl, font=font_body, fill=text_white)
                    current_y += 48
                current_y += 15
            if current_y > height - 60: break 
        draw.rectangle([(margin_x, height - 20), (width - margin_x, height - 18)], fill=accent_cyan)
        temp_filename = "temp_card_16_9.png"
        image.convert("RGB").save(temp_filename)
        return temp_filename
    except Exception as e: print(f"❌ 이미지 생성 에러: {e}"); return None

def get_working_model():
    return "gemini-1.5-flash"

def summarize_news(target_model, title, link, content_text=""):
    prompt = f"""
    [역할] 금융 뉴스 요약 전문가.
    [입력 뉴스]
    제목: {title}
    내용: {content_text}
    [필수 규칙]
    1. 서론(예: "네, 요약해드릴게요") 절대 금지. 바로 결과만 출력.
    2. 본문에 없는 숫자는 지어내지 말 것.
    [출력 형식 - 반드시 이 틀을 지킬 것]
    ---BODY---
    (여기에 트윗 본문 작성. 한국어. 이모지 사용. 해시태그 포함)
    ---IMAGE---
    (여기에 이미지에 들어갈 텍스트 작성. 첫 줄은 제목, 나머지는 요약 3줄)
    ---SOURCE---
    (언론사 이름. 모르면 Unknown)
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]}
    headers = {'Content-Type': 'application/json'}
    for _ in range(2): 
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                full_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                # ★ [수정] Flash 모델 형식 오류 방어 로직 포함
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
                    image_lines = [re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►]+\s*", "", l.strip()) for l in image_raw.split('\n') if l.strip()]
                    source_name = source_raw.split('\n')[0].strip()
                    return body_part, image_lines, source_name
                else: # 형식이 깨졌을 때 구제
                    print("⚠️ 형식 오류 감지 -> 강제 변환 시도")
                    body_part = full_text.replace("---BODY---", "").replace("---IMAGE---", "").strip()[:500]
                    image_lines = [title] + [body_part[:50] + "..."]
                    return body_part, image_lines, "Unknown"
            elif response.status_code == 429: time.sleep(60); continue
            else: return None, None, None
        except: return None, None, None
    return None, None, None

# ==========================================
# 6. 기록 관리
# ==========================================
def get_processed_links(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f: return [line.strip() for line in f.readlines()]

def save_processed_link(filename, link):
    links = get_processed_links(filename)
    clean_link = link.strip()
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
    current_model = "gemini-1.5-flash"
    global_titles = get_global_titles()
    
    for category, rss_url, filename, default_source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        
        news = None
        # ★ [핵심] 텔레그램은 별도 크롤러 사용, 나머지는 RSS 사용
        if "t.me/s/" in rss_url:
             news = fetch_telegram_latest(rss_url)
             if not news: print("텔레그램 새 메시지 없음"); continue
        else:
            try:
                feed = feedparser.parse(rss_url)
                if not feed.entries: print("뉴스 없음"); continue
                news = feed.entries[0]
                if not is_recent_news(news): continue # 시간 체크(RSS만)
            except: print("RSS 파싱 실패"); continue

        processed_links = get_processed_links(filename)
        if news.link.strip() in processed_links: 
            print("💰 [비용 절감] 이미 처리된 링크. API 호출 생략."); continue

        check_title = news.title if news.title else (news.description[:50] if hasattr(news, 'description') else "")
        if is_similar_title(check_title, global_titles):
            print("💰 [비용 절감] 중복 내용 감지. API 호출 생략."); 
            save_processed_link(filename, news.link); continue

        print(f"✨ 새 뉴스 발견: {news.title}")
        
        # 본문 가져오기 (텔레그램은 이미 본문이 description에 있음)
        real_link = news.link
        if "t.me/s/" in rss_url:
            scraped_content = news.description # 텔레그램은 이게 본문
        else:
            print("🌍 기사 본문 크롤링 중...")
            rss_summary = news.description if hasattr(news, 'description') else ""
            scraped_text = fetch_article_content(real_link)
            scraped_content = scraped_text if scraped_text else rss_summary

        print("🤖 AI 분석 시작...")
        body_text, img_lines, detected_source = summarize_news(current_model, news.title, real_link, scraped_content)
        
        if body_text and img_lines:
            final_source_name = detected_source if "텔레그램" in category else default_source_name
            image_file = create_info_image(img_lines, final_source_name)
            
            try:
                media_id = None
                if image_file: 
                    print("📤 미디어 업로드 중...")
                    media = api.media_upload(image_file)
                    media_id = media.media_id
                
                final_tweet = body_text
                if final_source_name: final_tweet += f"\n\n출처: {final_source_name}"
                if "주식" in category and "#주식" not in final_tweet: final_tweet += " #주식"
                final_tweet += f"\n\n🔗 원문: {real_link}"

                if len(final_tweet) > 11500: final_tweet = final_tweet[:11495] + "..."

                if media_id: response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                else: response = client.create_tweet(text=final_tweet)
                
                print("✅ 업로드 성공")
                
                save_processed_link(filename, news.link)
                save_global_title(check_title)
                global_titles.append(re.sub(r'\s+', ' ', check_title).strip())
            except Exception as e: print(f"❌ 전송 실패: {e}")
            if image_file and os.path.exists(image_file): os.remove(image_file)
        else: print("🚨 요약 실패")
        time.sleep(2)
