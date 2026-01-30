import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
import re
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
    # 마이클 버리 (Nitter 우회)
    ("마이클버리(Burry)", "https://nitter.privacydev.net/michaeljburry/rss", "last_link_burry.txt", "Michael Burry"),

    # 트럼프 트루스소셜 (API)
    ("트럼프(TruthSocial)", "https://truthsocial.com/@realDonaldTrump", "last_id_trump.txt", "Truth Social"),
    
    # 블룸버그 (구글뉴스 필터링)
    ("미국주식(블룸버그)", "https://news.google.com/rss/search?q=site:bloomberg.com+when:1d&hl=en-US&gl=US&ceid=US:en", "last_link_bloomberg.txt", "Bloomberg"),

    # 텔레그램
    ("속보(텔레그램)", "https://t.me/s/bornlupin", "last_link_bornlupin.txt", "Telegram"),

    # 연예뉴스
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

# ==========================================
# 4. 크롤링 및 데이터 수집 함수
# ==========================================
class SimpleNews:
    def __init__(self, title, link, description, published_parsed=None):
        self.title = title
        self.link = link
        self.description = description
        self.published_parsed = published_parsed

def is_recent_news(entry):
    if not hasattr(entry, 'published_parsed') or not entry.published_parsed: return True
    try:
        published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_diff = current_time - published_time
        if time_diff > timedelta(hours=6):
            print(f"⏳ [오래된 뉴스] 6시간 경과로 스킵: {time_diff}")
            return False
        return True
    except: return True

def fetch_truth_social_latest(url):
    try:
        TRUMP_ACCOUNT_ID = "107780213600000000"
        api_url = f"https://truthsocial.com/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses?exclude_replies=true&only_media=false"
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code != 200: return None
        posts = response.json()
        if not posts: return None
        latest_post = posts[0]
        post_id = latest_post.get('id')
        content_html = latest_post.get('content', '')
        created_at_str = latest_post.get('created_at')
        soup = BeautifulSoup(content_html, 'html.parser')
        full_text = soup.get_text(separator="\n").strip()
        post_link = f"https://truthsocial.com/@realDonaldTrump/posts/{post_id}"
        title = full_text.split('\n')[0]
        if len(title) > 50: title = title[:50] + "..."
        if not title: title = "트럼프 트루스소셜 최신 포스팅"
        try:
            post_time = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            if (datetime.now(timezone.utc) - post_time) > timedelta(hours=6): return None
        except: pass
        return SimpleNews(title, post_link, full_text)
    except Exception as e:
        print(f"⚠️ 트루스소셜 에러: {e}")
        return None

def fetch_telegram_latest(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        messages = soup.select('.tgme_widget_message_wrap')
        if not messages: return None
        last_msg = messages[-1]
        text_elem = last_msg.select_one('.tgme_widget_message_text')
        if not text_elem: return None
        full_text = text_elem.get_text(separator="\n").strip()
        link_elem = last_msg.select_one('a.tgme_widget_message_date')
        post_link = link_elem['href'] if link_elem else url
        title = full_text.split('\n')[0]
        if len(title) > 50: title = title[:50] + "..."
        return SimpleNews(title, post_link, full_text)
    except Exception as e:
        print(f"⚠️ 텔레그램 에러: {e}")
        return None

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
# 5. 이미지 생성 (깨짐 방지 + 디자인 고정)
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
            clean_line = re.sub(r"^[\W_]+", "", line.strip()) 
            clean_line = clean_line.replace("**", "").replace("##", "")
            if not clean_line: continue
            
            if i == 0: 
                wrapped_title = textwrap.wrap(clean_line, width=20)
                title_box_height = len(wrapped_title) * 85 + 30
                draw.rectangle([(margin_x - 20, current_y), (width - margin_x + 20, current_y + title_box_height)], fill=title_box_bg)
                current_y += 20
                for wl in wrapped_title:
                    draw.text((margin_x, current_y), wl, font=font_title_main, fill=text_white)
                    current_y += 85
                current_y += 40
            else: 
                bullet_y = current_y + 12
                draw.rectangle([margin_x, bullet_y, margin_x + 10, bullet_y + 10], fill=accent_cyan)
                wrapped_body = textwrap.wrap(clean_line, width=40)
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

# ==========================================
# 6. AI 모델 및 프롬프트
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
            for m in data.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    return m['name'].replace('models/', '')
    except: pass
    return "gemini-pro"

def summarize_news(target_model, title, link, content_text=""):
    prompt = f"""
    [지시사항]
    제공된 뉴스 기사를 바탕으로 트위터 게시글과 이미지 텍스트를 작성하라.
    
    [입력 데이터]
    제목: {title}
    링크: {link}
    내용: {content_text}

    [필수 규칙 - 위반 시 실패]
    1. **감정을 완전히 배제할 것.** (건조하고 객관적인 뉴스 톤 유지)
    2. **말투는 무조건 '~함', '~음', '~임', '~개최', '~돌파' 등 명사형으로 끝낼 것.** (존댓말 금지)
    3. **느낌표(!) 절대 사용 금지.**
    4. **무조건 한국어로 번역해서 작성할 것.**
    5. 내용이 없거나 짧으면 제목을 풀어서 설명해라.
    6. 트위터 본문은 ✅ 이모지를 사용한 리스트 형식.
    7. **기사와 관련된 '주식 티커(예: $TSLA)'와 '관련 해시태그(예: #전기차)'를 본문 하단에 반드시 포함할 것.**
    8. 이미지는 제목 제외 최대 7줄.

    [출력 포맷]
    ---BODY---
    (이모지) (한국어 제목 - 명사형 종결, 느낌표 금지)
    
    ✅ (상세 내용 1 - 명사형 종결)
    ✅ (상세 내용 2 - 명사형 종결)
    ✅ (상세 내용 3 - 명사형 종결)
    ...
    
    (관련 티커 $AAA) (관련 해시태그 #BBB #CCC)

    ---IMAGE---
    (한국어 제목 - 명사형 종결, 느낌표 금지)
    (핵심 요약 1 - 명사형 종결)
    (핵심 요약 2 - 명사형 종결)
    ...

    ---SOURCE---
    (언론사)
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": safety_settings}
    headers = {'Content-Type': 'application/json'}
    
    for _ in range(2): 
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code != 200: continue
            
            try:
                full_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            except: continue

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
                image_lines = [l.strip() for l in image_raw.split('\n') if l.strip()]
                source_name = source_raw.split('\n')[0].strip()
                return body_part, image_lines, source_name
            else:
                body_part = full_text.strip()[:500]
                image_lines = [title] + [body_part[:50] + "..."]
                return body_part, image_lines, "Unknown"
        except: continue
    return None, None, None

# ==========================================
# 7. 메인 실행 로직
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
            print(f"🚫 중복 감지: {clean_new}"); return True
    return False

if __name__ == "__main__":
    current_model = get_working_model()
    global_titles = get_global_titles()
    
    for category, rss_url, filename, default_source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        
        news = None
        if "truthsocial.com" in rss_url: 
             news = fetch_truth_social_latest(rss_url)
             if not news: print("트루스소셜 새 글 없음"); continue
        elif "t.me/s/" in rss_url: 
             news = fetch_telegram_latest(rss_url)
             if not news: print("텔레그램 없음"); continue
        else:
            try:
                feed = feedparser.parse(rss_url)
                if not feed.entries: print("뉴스 없음"); continue
                news = feed.entries[0]
                if not is_recent_news(news): continue 
            except: print("RSS 실패"); continue

        processed_links = get_processed_links(filename)
        if news.link.strip() in processed_links: 
            print("💰 이미 처리된 링크"); continue

        check_title = news.title if news.title else (news.description[:50] if hasattr(news, 'description') else "")
        if is_similar_title(check_title, global_titles):
            save_processed_link(filename, news.link); continue

        print(f"✨ 새 뉴스: {news.title}")
        
        real_link = news.link
        if "truthsocial.com" in rss_url or "t.me/s/" in rss_url or "nitter" in rss_url:
            scraped_content = news.description 
        else:
            print("🌍 크롤링 중...")
            rss_summary = news.description if hasattr(news, 'description') else ""
            scraped_text = fetch_article_content(real_link)
            scraped_content = scraped_text if (scraped_text and len(scraped_text) > 50) else rss_summary

        print("🤖 AI 분석 시작...")
        body_text, img_lines, detected_source = summarize_news(current_model, news.title, real_link, scraped_content)
        
        if body_text and img_lines:
            final_source_name = detected_source if "텔레그램" in category else default_source_name
            if "TruthSocial" in category: final_source_name = "Truth Social (Donald Trump)"
            if "Burry" in category: final_source_name = "Michael Burry (Twitter)"
            if "텔레그램" in category: final_source_name = None 
                
            image_file = create_info_image(img_lines, final_source_name)
            
            try:
                media_id = None
                if image_file: 
                    print("📤 미디어 업로드...")
                    media = api.media_upload(image_file)
                    media_id = media.media_id
                
                final_tweet = body_text
                if final_source_name and "텔레그램" not in category:
                    final_tweet += f"\n\n출처: {final_source_name}"
                
                final_tweet += " #마켓레이더"
                
                if len(final_tweet) > 12000: final_tweet = final_tweet[:11995] + "..."

                if media_id: response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                else: response = client.create_tweet(text=final_tweet)
                
                print("✅ 메인 트윗 성공")
                # 댓글 링크 기능 완전히 삭제함

                save_processed_link(filename, news.link)
                save_global_title(check_title)
                global_titles.append(re.sub(r'\s+', ' ', check_title).strip())
            except Exception as e: print(f"❌ 전송 실패: {e}")
            if image_file and os.path.exists(image_file): os.remove(image_file)
        else: print("🚨 요약 실패")
        time.sleep(2)
