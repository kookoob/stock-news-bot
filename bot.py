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
    # 하나차이나 (텔레그램)
    ("하나차이나(China)", "https://t.me/s/HANAchina", "last_link_hana.txt", "Telegram"),
    
    # 마이클 버리 (Nitter 우회)
    ("마이클버리(Burry)", "https://nitter.privacydev.net/michaeljburry/rss", "last_link_burry.txt", "Michael Burry"),

    # 트럼프 트루스소셜 (API)
    ("트럼프(TruthSocial)", "https://truthsocial.com/@realDonaldTrump", "last_id_trump.txt", "Truth Social"),
    
    # 블룸버그 (구글뉴스 필터링)
    ("미국주식(블룸버그)", "https://news.google.com/rss/search?q=site:bloomberg.com+when:1d&hl=en-US&gl=US&ceid=US:en", "last_link_bloomberg.txt", "Bloomberg"),

    # 텔레그램 (속보)
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
GLOBAL_TITLE_FILE = "processed_global_titles.txt" # 제목/원문 해시 저장
GLOBAL_SUMMARY_FILE = "processed_ai_summaries.txt" # ★ AI 요약본 저장 (새로 추가)

# ==========================================
# 4. 크롤링 및 데이터 수집 함수
# ==========================================
class SimpleNews:
    def __init__(self, title, link, description, published_parsed=None, image_url=None):
        self.title = title
        self.link = link
        self.description = description
        self.published_parsed = published_parsed
        self.image_url = image_url

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

def download_image_from_url(url, save_path="temp_origin.jpg"):
    try:
        if "google" in url or "gstatic" in url:
            print("🚫 구글 기본 이미지는 다운로드하지 않음")
            return None
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)
            return save_path
    except Exception as e:
        print(f"⚠️ 이미지 다운로드 실패: {e}")
    return None

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
        image_url = None
        media_attachments = latest_post.get('media_attachments', [])
        if media_attachments: image_url = media_attachments[0].get('url')
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
        return SimpleNews(title, post_link, full_text, image_url=image_url)
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
        full_text = ""
        if text_elem: full_text = text_elem.get_text(separator="\n").strip()
        image_url = None
        photo_div = last_msg.select_one('.tgme_widget_message_photo_wrap')
        if photo_div:
            style = photo_div.get('style', '')
            match = re.search(r"url\('?(.*?)'?\)", style)
            if match: image_url = match.group(1)
        link_elem = last_msg.select_one('a.tgme_widget_message_date')
        post_link = link_elem['href'] if link_elem else url
        title = full_text.split('\n')[0] if full_text else "텔레그램 이미지 포스트"
        if len(title) > 50: title = title[:50] + "..."
        return SimpleNews(title, post_link, full_text, image_url=image_url)
    except Exception as e:
        print(f"⚠️ 텔레그램 에러: {e}")
        return None

def fetch_article_content_and_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        image_url = None
        og_image = soup.find('meta', property='og:image')
        if og_image: 
            found_url = og_image.get('content')
            if found_url and ("google" not in found_url and "gstatic" not in found_url):
                image_url = found_url
            else:
                print("🚫 구글/기본 로고 감지되어 이미지 스킵함")

        for script in soup(["script", "style", "header", "footer", "nav", "aside", "form"]):
            script.decompose()
        paragraphs = soup.find_all('p')
        article_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 20])
        if len(article_text) < 100: article_text = soup.get_text(separator=' ', strip=True)
        return article_text[:4000], image_url
    except: return None, None

# ==========================================
# 5. 이미지 생성 (디자인)
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
            try:
                font_title_main = ImageFont.truetype("font.ttf", 60)
                font_body = ImageFont.truetype("font.ttf", 34)
                font_header = ImageFont.truetype("font.ttf", 26)
                font_date = ImageFont.truetype("font.ttf", 26)
            except: return None
        margin_x = 60; current_y = 40
        header_text = "MARKET RADAR"; 
        
        if source_name and source_name != "Telegram": 
            header_text += f" | {source_name}"
            
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
    except: return None

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

    [필수 규칙]
    1. 감정 배제, 건조한 뉴스 톤 유지.
    2. 말투는 '~함', '~음' 등 명사형 종결. (존댓말 금지)
    3. 느낌표(!) 사용 금지.
    4. 무조건 한국어 작성.
    5. 트위터 본문은 ✅ 리스트 형식.
    6. **티커와 해시태그에 괄호() 사용 금지. 공백으로 구분.** (예: $TSLA #전기차)
    7. 이미지는 제목 제외 최대 7줄.

    [출력 포맷]
    ---BODY---
    (이모지) (한국어 제목)
    
    ✅ (내용 1)
    ✅ (내용 2)
    ✅ (내용 3)
    
    $AAA #BBB #CCC

    ---IMAGE---
    (한국어 제목)
    (요약 1)
    (요약 2)

    ---SOURCE---
    (언론사)
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    safety_settings = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": safety_settings}
    
    for _ in range(2): 
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=data)
            if response.status_code != 200: continue
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
# 7. 메인 실행 로직 (★3단계 중복 필터링★)
# ==========================================
def get_file_lines(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f: return [line.strip() for line in f.readlines()]

def save_file_line(filename, line):
    lines = get_file_lines(filename)
    # 줄바꿈 및 공백 제거된 상태로 저장
    clean_line = re.sub(r'\s+', ' ', line).strip()
    if clean_line not in lines:
        lines.append(clean_link if 'http' in line else clean_line)
        if len(lines) > MAX_HISTORY: lines = lines[-MAX_HISTORY:]
        with open(filename, 'w', encoding='utf-8') as f: f.write("\n".join(lines))

def normalize_text(text):
    # 특수문자 제거, 소문자 변환, 단어 세트 반환 (비교용)
    text = re.sub(r'[^\w\s]', '', text.lower())
    return set(text.split())

def is_duplicate_content(new_text, history_lines, threshold=0.6):
    """
    텍스트 내용 기반 중복 검사 (Jaccard & SequenceMatcher)
    new_text: 비교할 새 텍스트 (본문 또는 AI 요약본)
    history_lines: 기존 저장된 텍스트 리스트
    threshold: 중복으로 간주할 유사도 기준 (0.6 = 60%)
    """
    if not new_text or len(new_text) < 10: return False
    
    new_words = normalize_text(new_text)
    if len(new_words) < 3: return False 

    # 최신 기록부터 역순 비교 (속도 향상)
    for old_text in reversed(history_lines):
        # 1. 단어 교집합 검사 (빠름)
        old_words = normalize_text(old_text)
        if len(old_words) == 0: continue
        
        intersection = len(new_words & old_words)
        union = len(new_words | old_words)
        jaccard_sim = intersection / union if union > 0 else 0
        
        if jaccard_sim > 0.4: # 단어가 40% 이상 겹치면 의심
            # 2. 정밀 문자열 비교 (느림, 정확)
            seq_sim = SequenceMatcher(None, new_text, old_text).ratio()
            if seq_sim > threshold:
                print(f"🚫 [중복 감지] 유사도 {seq_sim:.2f} | '{new_text[:30]}...'")
                return True
    return False

if __name__ == "__main__":
    current_model = get_working_model()
    
    # 전역 기록 로드
    global_titles = get_file_lines(GLOBAL_TITLE_FILE)
    global_summaries = get_file_lines(GLOBAL_SUMMARY_FILE) # AI 요약본 기록
    
    for category, rss_url, filename, default_source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        
        news = None
        is_telegram = "t.me" in rss_url

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

        # [필터 1] 링크 검사 (정확히 같은 URL)
        processed_links = get_file_lines(filename)
        if news.link.strip() in processed_links: 
            print("💰 이미 처리된 링크 (Link match)"); continue

        # [필터 2] 원문/제목 내용 검사 (유사한 제목/본문)
        # 텔레그램은 제목이 본문과 같으므로 본문 비교 효과
        check_content = news.title if news.title else (news.description[:100] if hasattr(news, 'description') else "")
        if is_duplicate_content(check_content, global_titles, threshold=0.55):
            # 링크만 다르고 내용이 같으면, 링크도 처리된 걸로 저장해버림
            save_file_line(filename, news.link)
            continue

        print(f"✨ 새 뉴스 발견: {news.title[:30]}...")
        
        real_link = news.link
        original_image_url = None
        
        if "truthsocial.com" in rss_url:
            scraped_content = news.description
            original_image_url = news.image_url
        elif "t.me/s/" in rss_url:
            scraped_content = news.description
            original_image_url = news.image_url
        elif "nitter" in rss_url:
            scraped_content = news.description 
        else:
            print("🌍 크롤링 중...")
            rss_summary = news.description if hasattr(news, 'description') else ""
            scraped_text, found_img_url = fetch_article_content_and_image(real_link)
            scraped_content = scraped_text if (scraped_text and len(scraped_text) > 50) else rss_summary
            original_image_url = found_img_url

        print("🤖 AI 분석 시작...")
        body_text, img_lines, detected_source = summarize_news(current_model, news.title, real_link, scraped_content)
        
        if body_text and img_lines:
            # [필터 3] AI 요약본 검사 (핵심 내용 중복 확인)
            # AI가 요약한 내용이 기존 요약들과 비슷하면 여기서 최종 스킵
            if is_duplicate_content(body_text, global_summaries, threshold=0.6):
                print("🚨 [AI 요약 중복] 내용이 기존 트윗과 동일하여 스킵합니다.")
                # 이것도 처리된 걸로 저장하여 다시 시도 안 하게 함
                save_file_line(filename, news.link)
                continue

            final_source_name = detected_source if is_telegram else default_source_name
            if "TruthSocial" in category: final_source_name = "Truth Social (Donald Trump)"
            if "Burry" in category: final_source_name = "Michael Burry (Twitter)"
            if is_telegram: final_source_name = "Telegram"
                
            summary_card_file = create_info_image(img_lines, final_source_name)
            
            original_image_file = None
            if original_image_url:
                print("🖼️ 원본 이미지 다운로드 중...")
                original_image_file = download_image_from_url(original_image_url)

            try:
                media_ids = []
                if summary_card_file: 
                    media1 = api.media_upload(summary_card_file)
                    media_ids.append(media1.media_id)
                if original_image_file:
                    try:
                        media2 = api.media_upload(original_image_file)
                        media_ids.append(media2.media_id)
                    except: pass
                
                final_tweet = body_text
                
                if final_source_name and not is_telegram:
                    final_tweet += f"\n\n출처: {final_source_name}"
                
                final_tweet += " #마켓레이더"
                if len(final_tweet) > 12000: final_tweet = final_tweet[:11995] + "..."

                if media_ids: response = client.create_tweet(text=final_tweet, media_ids=media_ids)
                else: response = client.create_tweet(text=final_tweet)
                
                print("✅ 메인 트윗 성공")

                # 성공 후 데이터 저장
                save_file_line(filename, news.link) # 링크 저장
                save_file_line(GLOBAL_TITLE_FILE, check_content) # 제목/원문 앞부분 저장
                
                # ★ AI 요약본도 저장 (다음 중복 검사 때 사용)
                # 줄바꿈을 공백으로 바꿔서 한 줄로 저장
                clean_summary = re.sub(r'\s+', ' ', body_text).strip()
                with open(GLOBAL_SUMMARY_FILE, 'a', encoding='utf-8') as f:
                    f.write(clean_summary + "\n")
                
                print("⏳ 도배 방지: 3분 대기...")
                time.sleep(180)

            except Exception as e: print(f"❌ 전송 실패: {e}")
            
            if summary_card_file and os.path.exists(summary_card_file): os.remove(summary_card_file)
            if original_image_file and os.path.exists(original_image_file): os.remove(original_image_file)
        else: print("🚨 요약 실패")
        time.sleep(2)
