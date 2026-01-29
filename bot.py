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
    ("속보(텔레그램)", "https://rsshub.app/telegram/channel/bornlupin", "last_link_bornlupin.txt", "Telegram")
]

# ★ [수정] 기억할 히스토리 개수 (300개로 상향)
MAX_HISTORY = 300
GLOBAL_TITLE_FILE = "processed_global_titles.txt"

# ==========================================
# 4. 카드뉴스 생성 함수
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
        except:
            print("⚠️ 폰트 파일 오류")
            return None

        margin_x = 80       
        header_y = 45
        
        if source_name:
            header_text = f"Market Radar | {source_name}"
        else:
            header_text = "Market Radar"
        draw.text((margin_x, header_y), header_text, font=source_font, fill=accent_color)
        draw.text((margin_x, header_y + 30), "@marketradar0", font=source_font, fill=text_color)

        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        date_str = f"{now.year % 100}년 {now.month}월 {now.day}일"

        try:
            date_width = draw.textlength(date_str, font=source_font)
        except AttributeError:
            date_width = source_font.getsize(date_str)[0]
            
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
                draw.rectangle(
                    [margin_x - 25, bullet_y, margin_x - 25 + bullet_size, bullet_y + bullet_size],
                    fill=accent_color
                )
                wrapped_lines = textwrap.wrap(line, width=35)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=body_font, fill=text_color)
                    current_y += 42
                current_y += 10
            
            if current_y > height - 50: break 
        
        temp_filename = "temp_card_16_9.png"
        image.save(temp_filename)
        return temp_filename
    except Exception as e:
        print(f"❌ 이미지 생성 에러: {e}")
        return None

# ==========================================
# 5. AI 모델 찾기
# ==========================================
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

# ==========================================
# 6. AI 요약 함수
# ==========================================
def summarize_news(target_model, title, link, content_text=""):
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}
    뉴스 내용(Raw): {content_text}

    위 내용을 분석해서 트위터 본문, 인포그래픽 텍스트, 그리고 '원천 소스 출처'를 찾아줘.

    [작성 규칙 1: 트위터 본문]
    - 구분자: ---BODY--- 아래에 작성
    - 형식: X 프리미엄용 장문 상세 요약.
    - 스타일: 한국어 번역 필수. 명사형 종결이나 음슴체(~함, ~임). 존댓말 금지.
    - 구성: 제목(이모지+한글), 상세 내용(✅ 체크포인트), 하단 티커($)+해시태그(#)

    [작성 규칙 2: 인포그래픽 이미지]
    - 구분자: ---IMAGE--- 아래에 작성
    - 구성:
      1. 첫 줄: 강렬한 한글 제목. (이모지 X). **기사 핵심 수치(1400조, 2025년 등)는 제목에 반드시 포함.**
      2. 나머지: 핵심 요약 문장 최대 7개 이내. **문장 시작에 오는 숫자(연도, 금액)는 절대 삭제하지 말 것.**

    [작성 규칙 3: 원천 소스 찾기]
    - 구분자: ---SOURCE--- 아래에 작성
    - 규칙 A: 링크가 있다면 해당 언론사 이름(Bloomberg, WSJ 등).
    - 규칙 B: 링크가 없다면 본문에서 'Source:', '출처:', 'via' 뒤에 나오는 기관명.
    - 규칙 C: 링크도 없고 텍스트 언급도 없으면 'Unknown'이라고 적어. 텔레그램 채널명은 적지 마.

    [금지사항]
    - 마크다운(**, ##) 사용 금지.
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }
    headers = {'Content-Type': 'application/json'}

    max_retries = 3
    for attempt in range(max_retries):
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
                    else:
                        image_raw = remaining.strip()
                        source_raw = "Unknown" 

                    body_part = body_raw.replace("**", "").replace("##", "")
                    image_lines = []
                    for line in image_raw.split('\n'):
                        clean_line = line.strip().replace("**", "").replace("##", "")
                        clean_line = re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►]+\s*", "", clean_line)
                        clean_line = re.sub(r"^\d+\.\s+", "", clean_line)
                        if clean_line: image_lines.append(clean_line)
                    
                    source_name = source_raw.split('\n')[0].strip()
                    if "Unknown" in source_name or len(source_name) > 20: source_name = None 
                    
                    return body_part, image_lines, source_name
                else: return None, None, None
            elif response.status_code == 429:
                print(f"⏳ API 한도 초과! 60초 대기... ({attempt+1}/{max_retries})")
                time.sleep(60)
                continue
            else:
                print(f"🚨 API 에러: {response.text}")
                return None, None, None
        except Exception as e:
            print(f"🚨 연결 에러: {e}")
            return None, None, None
    return None, None, None

# ==========================================
# 7. 기록 관리 함수 (최대 300개 유지)
# ==========================================

def get_processed_links(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines()]

def save_processed_link(filename, link):
    links = get_processed_links(filename)
    if link not in links:
        links.append(link)
        if len(links) > MAX_HISTORY: # 300개 유지
            links = links[-MAX_HISTORY:]
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(links))

def get_global_titles():
    if not os.path.exists(GLOBAL_TITLE_FILE):
        return []
    with open(GLOBAL_TITLE_FILE, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines()]

def save_global_title(title):
    titles = get_global_titles()
    clean_title = re.sub(r'\s+', ' ', title).strip()
    
    if clean_title not in titles:
        titles.append(clean_title)
        if len(titles) > MAX_HISTORY: # 300개 유지
            titles = titles[-MAX_HISTORY:]
        with open(GLOBAL_TITLE_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(titles))

def is_similar_title(new_title, existing_titles):
    clean_new = re.sub(r'\s+', ' ', new_title).strip()
    
    for old_title in existing_titles:
        ratio = SequenceMatcher(None, clean_new, old_title).ratio()
        if ratio > 0.6: 
            print(f"🚫 중복 감지 (유사도 {ratio:.2f}): {clean_new} <-> {old_title}")
            return True
    return False

# ==========================================
# 8. 메인 실행 로직
# ==========================================
if __name__ == "__main__":
    current_model = get_working_model()
    global_titles = get_global_titles()
    
    for category, rss_url, filename, default_source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                print("뉴스 없음 (RSS 비어있음)")
                continue
            news = feed.entries[0]
        except:
            print("RSS 파싱 실패")
            continue
        
        # 1. 링크 중복 체크
        processed_links = get_processed_links(filename)
        if news.link in processed_links:
            print("이미 처리된 링크입니다.")
            continue

        # 2. 제목 유사도 체크
        check_title = news.title if news.title else (news.description[:50] if hasattr(news, 'description') else "")
        if is_similar_title(check_title, global_titles):
            print("패스: 다른 소스에서 이미 다룬 내용입니다.")
            save_processed_link(filename, news.link)
            continue

        print(f"✨ 새 뉴스 발견: {news.title}")
        
        real_link = news.link
        content_for_ai = ""
        if hasattr(news, 'description'):
            content_for_ai = news.description
            if "텔레그램" in category:
                urls = re.findall(r'(https?://\S+)', content_for_ai)
                if urls:
                    real_link = urls[0]
                    print(f"🔗 텔레그램 원문 링크 추출됨: {real_link}")

        body_text, img_lines, detected_source = summarize_news(current_model, news.title, real_link, content_for_ai)
        
        if body_text and img_lines:
            if "텔레그램" in category:
                final_source_name = detected_source 
            else:
                final_source_name = default_source_name
            
            image_file = create_info_image(img_lines, final_source_name)
            
            try:
                media_id = None
                if image_file:
                    print(f"🖼️ 카드뉴스 생성 완료 (출처: {final_source_name if final_source_name else '없음'})")
                    media = api.media_upload(image_file)
                    media_id = media.media_id
                
                if final_source_name:
                    final_tweet = f"{body_text}\n\n출처: {final_source_name}"
                else:
                    final_tweet = body_text 
                
                if len(final_tweet) > 12000:
                    final_tweet = final_tweet[:11995] + "..."

                if media_id:
                    response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                else:
                    response = client.create_tweet(text=final_tweet)
                    
                tweet_id = response.data['id']
                print("✅ 메인 트윗 업로드 성공!")
                
                reply_text = f"🔗 원문 기사:\n{real_link}"
                client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                print("✅ 링크 댓글 완료!")

                save_processed_link(filename, news.link)
                save_global_title(check_title)
                global_titles.append(re.sub(r'\s+', ' ', check_title).strip())
                
            except Exception as e:
                print(f"❌ 트윗 전송 실패: {e}")
            
            if image_file and os.path.exists(image_file):
                os.remove(image_file)
        else:
            print("🚨 AI 요약 실패")
    
        time.sleep(2)
