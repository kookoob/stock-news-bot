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

# 기억 용량 2000개 (중복 방지 강화)
MAX_HISTORY = 2000
GLOBAL_TITLE_FILE = "processed_global_titles.txt"

# ==========================================
# 4. 시간 제어 함수 (6시간 이내)
# ==========================================
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
    except:
        return True

# ==========================================
# 5. 이미지 및 AI 관련 함수 (디자인 업그레이드 버전)
# ==========================================
def create_gradient_background(width, height, start_color, end_color):
    """세련된 수직 그라데이션 배경 생성 함수"""
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
        
        # --- 🎨 디자인 색상 팔레트 ---
        bg_start = (10, 25, 45)   # 깊은 네이비 (상단)
        bg_end = (20, 40, 70)     # 밝은 네이비 (하단)
        text_white = (245, 245, 250) # 부드러운 흰색
        text_gray = (180, 190, 210)  # 밝은 회색 (보조 텍스트)
        accent_cyan = (0, 220, 255)  # 형광 하늘색 (강조)
        title_box_bg = (0, 0, 0, 80) # 제목 배경 반투명 박스 (RGBA)

        # 1. 그라데이션 배경 생성
        image = create_gradient_background(width, height, bg_start, bg_end)
        draw = ImageDraw.Draw(image, 'RGBA') # RGBA 모드로 그리기

        # 2. 폰트 로드 (준비물에서 준비한 두꺼운/일반 폰트)
        try:
            # 제목용 두꺼운 폰트
            font_title_main = ImageFont.truetype("font_bold.ttf", 60) 
            # 본문용 일반 폰트
            font_body = ImageFont.truetype("font_reg.ttf", 34)
            # 상단 헤더용 작은 폰트
            font_header = ImageFont.truetype("font_bold.ttf", 26)
             # 날짜용 작은 폰트
            font_date = ImageFont.truetype("font_reg.ttf", 26)
        except:
            print("⚠️ 새 폰트 파일(font_bold.ttf, font_reg.ttf)을 찾을 수 없습니다. 기존 font.ttf로 시도합니다.")
            try:
                font_title_main = ImageFont.truetype("font.ttf", 60)
                font_body = ImageFont.truetype("font.ttf", 34)
                font_header = ImageFont.truetype("font.ttf", 26)
                font_date = ImageFont.truetype("font.ttf", 26)
            except: return None

        margin_x = 60
        current_y = 40

        # --- 상단 헤더 (Market Radar | 날짜) ---
        header_text = "MARKET RADAR"
        if source_name:
            header_text += f" | {source_name}"
        
        # 헤더에 작은 포인트 아이콘 그리기 (파란 점)
        draw.ellipse([(margin_x, current_y+8), (margin_x+12, current_y+20)], fill=accent_cyan)
        draw.text((margin_x + 25, current_y), header_text, font=font_header, fill=accent_cyan)

        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year}.{now.month:02d}.{now.day:02d} | @marketradar0"
        
        # 날짜 오른쪽 정렬 계산
        date_bbox = draw.textbbox((0, 0), date_str, font=font_date)
        date_width = date_bbox[2] - date_bbox[0]
        draw.text((width - margin_x - date_width, current_y), date_str, font=font_date, fill=text_gray)
        
        current_y += 70 # 헤더 아래 여백

        # --- 메인 콘텐츠 영역 ---
        for i, line in enumerate(text_lines):
            line = line.strip().replace("**", "").replace("##", "")
            if not line: continue

            if i == 0: 
                # ★ 첫 줄: 메인 제목 (강조 박스 + 큰 폰트)
                wrapped_title = textwrap.wrap(line, width=20) # 제목 줄바꿈 폭 조절
                
                # 제목 박스 높이 계산
                title_box_height = len(wrapped_title) * 85 + 30
                # 반투명 제목 배경 박스 그리기
                draw.rectangle([(margin_x - 20, current_y), (width - margin_x + 20, current_y + title_box_height)], fill=title_box_bg)
                
                current_y += 20 # 박스 내부 패딩
                for wl in wrapped_title:
                    draw.text((margin_x, current_y), wl, font=font_title_main, fill=text_white)
                    current_y += 85
                current_y += 40 # 제목 아래 여백
                
            else: 
                # ★ 나머지 줄: 본문 요약 (세련된 불릿 포인트)
                # 세련된 화살표 모양 불릿 (►)
                bullet_text = "►"
                draw.text((margin_x, current_y + 2), bullet_text, font=font_header, fill=accent_cyan)
                
                wrapped_body = textwrap.wrap(line, width=40) # 본문 줄바꿈 폭 조절
                for wl in wrapped_body:
                    draw.text((margin_x + 35, current_y), wl, font=font_body, fill=text_white)
                    current_y += 48 # 줄간격
                current_y += 15 # 문단 간격

            if current_y > height - 60: break # 높이 초과 시 중단

        # 하단에 얇은 강조선 하나 추가
        draw.rectangle([(margin_x, height - 20), (width - margin_x, height - 18)], fill=accent_cyan)

        temp_filename = "temp_card_16_9.png"
        image.convert("RGB").save(temp_filename) # 저장할 때는 RGB로 변환
        return temp_filename
    except Exception as e:
        print(f"❌ 이미지 생성 에러: {e}")
        return None

# ★ [비용 절감 핵심] 가장 저렴한 모델(Flash) 강제 고정
def get_working_model():
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
    - ★ 중요: 주식 관련 뉴스라면 해시태그에 #주식 반드시 포함.
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
    for _ in range(2): # 재시도 횟수도 2회로 줄여 비용 방어
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
# 6. 기록 관리 (최대 2000개)
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
# 7. 메인 실행 로직 (★ 비용 절감 로직 적용)
# ==========================================
if __name__ == "__main__":
    # ★ 모델 고정 (Flash)
    current_model = "gemini-1.5-flash"
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

        # ★ [비용 절감 1] 링크 중복 시 API 호출 없이 즉시 종료
        processed_links = get_processed_links(filename)
        if news.link.strip() in processed_links: 
            print("💰 [비용 절감] 이미 처리된 링크. API 호출 생략."); continue

        check_title = news.title if news.title else (news.description[:50] if hasattr(news, 'description') else "")
        
        # ★ [비용 절감 2] 제목 중복 시 API 호출 없이 즉시 종료
        if is_similar_title(check_title, global_titles):
            print("💰 [비용 절감] 중복 내용 감지. API 호출 생략."); 
            save_processed_link(filename, news.link); # 링크만 저장해둠
            continue

        print(f"✨ 새 뉴스 발견 (AI 분석 시작): {news.title}")
        
        # --- 여기서부터 돈이 나가는 구간 ---
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
                
                # #주식 해시태그 추가
                if "주식" in category and "#주식" not in final_tweet:
                    final_tweet += " #주식"
                
                if len(final_tweet) > 12000: final_tweet = final_tweet[:11995] + "..."
                if media_id: response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                else: response = client.create_tweet(text=final_tweet)
                tweet_id = response.data['id']
                print("✅ 업로드 성공")
                client.create_tweet(text=f"🔗 원문 기사:\n{real_link}", in_reply_to_tweet_id=tweet_id)
                
                # 성공 후 기록 저장
                save_processed_link(filename, news.link)
                save_global_title(check_title)
                global_titles.append(re.sub(r'\s+', ' ', check_title).strip())
            except Exception as e: print(f"❌ 전송 실패: {e}")
            if image_file and os.path.exists(image_file): os.remove(image_file)
        else: print("🚨 요약 실패")
        time.sleep(2)

