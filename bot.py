import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
import re
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
    ("미국주식(WSJ_Economy)", "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed", "last_link_wsj_eco.txt", "WSJ")
]

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
        current_y = 100     
        
        draw.text((margin_x, 45), f"Market Radar | {source_name}", font=source_font, fill=accent_color)

        for i, line in enumerate(text_lines):
            line = line.strip().replace("**", "").replace("##", "")
            if not line: continue

            if i == 0: 
                wrapped_lines = textwrap.wrap(line, width=32)
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
                wrapped_lines = textwrap.wrap(line, width=54)
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
# 5. AI 요약 함수 (★ 재시도 기능 추가됨)
# ==========================================
def summarize_news(title, link):
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    target_model = "gemini-1.5-flash" 

    # 모델 자동 선택 (Pro 우선)
    try:
        list_res = requests.get(list_url)
        if list_res.status_code == 200:
            models = list_res.json().get('models', [])
            for m in models:
                name = m['name'].replace('models/', '')
                if 'gemini-1.5-pro' in name:
                    target_model = name
                    break
    except: pass
    
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    이 뉴스를 분석해서 '트위터 본문용'과 '인포그래픽 이미지용' 텍스트를 각각 작성해줘.

    [작성 규칙 1: 트위터 본문]
    - 구분자: ---BODY--- 아래에 작성
    - 형식: X 프리미엄용 장문. 기사의 육하원칙, 구체적 수치, 데이터, 시장 영향을 포함해 '최대한 상세하게' 작성.
    - 스타일: 한국어 번역 필수. 명사형 종결이나 음슴체(~함, ~임, ~발표 등) 사용. 존댓말 금지.
    - 구성:
      1. 제목 (이모지 포함 + 한글 번역)
      2. 상세 내용 (단락 구분 및 ✅ 체크포인트 활용)
      3. 하단에 티커($) 및 해시태그(#) 3개 포함

    [작성 규칙 2: 인포그래픽 이미지]
    - 구분자: ---IMAGE--- 아래에 작성
    - 형식: 이미지 안에 들어갈 아주 짧고 간결한 요약.
    - 구성:
      1. 첫 줄: 강렬한 한글 제목 (이모지 X)
      2. 나머지: 핵심 요약 문장 최대 7개 (문장부호 절제, 아주 짧게)

    [공통 금지사항]
    - ** (볼드체), ## (헤딩) 등 마크다운 문법 절대 사용 금지.
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": safety_settings
    }
    headers = {'Content-Type': 'application/json'}

    # ★ 3번까지 재시도하는 로직 추가
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=data)
            
            # 성공 (200 OK)
            if response.status_code == 200:
                full_text = response.json()['candidates'][0]['content']['parts'][0]['text']
                if "---BODY---" in full_text and "---IMAGE---" in full_text:
                    parts = full_text.split("---IMAGE---")
                    body_raw = parts[0].replace("---BODY---", "").strip()
                    image_raw = parts[1].strip()
                    
                    body_part = body_raw.replace("**", "").replace("##", "")
                    image_lines = []
                    for line in image_raw.split('\n'):
                        clean_line = line.strip().replace("**", "").replace("##", "")
                        clean_line = re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►\d\.]+\s*", "", clean_line)
                        if clean_line:
                            image_lines.append(clean_line)
                    return body_part, image_lines
                else:
                    return None, None
            
            # 429 에러 (한도 초과) 발생 시 대기
            elif response.status_code == 429:
                print(f"⏳ API 한도 초과! 60초 대기 후 재시도 ({attempt+1}/{max_retries})...")
                time.sleep(60) # 1분 대기
                continue # 다시 시도
                
            else:
                print(f"🚨 API 에러: {response.text}")
                return None, None
                
        except Exception as e:
            print(f"🚨 연결 에러: {e}")
            return None, None
    
    print("❌ 3회 재시도 실패. 건너뜁니다.")
    return None, None

# ==========================================
# 6. 메인 실행 로직
# ==========================================
def get_latest_news(rss_url):
    try:
        feed = feedparser.parse(rss_url)
        return feed.entries[0] if feed.entries else None
    except: return None

def check_if_new(last_link_file, current_link):
    if not os.path.exists(last_link_file): return True
    with open(last_link_file, 'r', encoding='utf-8') as f:
        return f.read().strip() != current_link

def save_current_link(last_link_file, current_link):
    with open(last_link_file, 'w', encoding='utf-8') as f:
        f.write(current_link)

if __name__ == "__main__":
    for category, rss_url, filename, source_name in RSS_SOURCES:
        print(f"\n--- [{category}] ---")
        news = get_latest_news(rss_url)
        
        if news and check_if_new(filename, news.link):
            print(f"✨ 뉴스 발견: {news.title}")
            
            # AI 요약 (재시도 로직 포함)
            body_text, img_lines = summarize_news(news.title, news.link)
            
            if body_text and img_lines:
                image_file = create_info_image(img_lines, source_name)
                
                try:
                    media_id = None
                    if image_file:
                        print("🖼️ 16:9 카드뉴스 생성 완료, 업로드 중...")
                        media = api.media_upload(image_file)
                        media_id = media.media_id
                    
                    final_tweet = f"{body_text}\n\n출처: {source_name}"
                    
                    if len(final_tweet) > 12000:
                        final_tweet = final_tweet[:11995] + "..."

                    if media_id:
                        response = client.create_tweet(text=final_tweet, media_ids=[media_id])
                    else:
                        response = client.create_tweet(text=final_tweet)
                        
                    tweet_id = response.data['id']
                    print("✅ 메인 트윗 업로드 성공!")
                    
                    reply_text = f"🔗 원문 기사:\n{news.link}"
                    client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                    print("✅ 링크 댓글 완료!")

                    save_current_link(filename, news.link)
                    
                except Exception as e:
                    print(f"❌ 트윗 전송 실패: {e}")
                
                if image_file and os.path.exists(image_file):
                    os.remove(image_file)
            else:
                print("🚨 AI 요약 실패 (한도 초과 등)")
        else:
            print("새 뉴스 없음.")
        
        # 뉴스 하나 처리 후 대기 시간 늘림 (2초 -> 10초)
        time.sleep(10)
