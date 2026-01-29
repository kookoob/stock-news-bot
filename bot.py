import feedparser
import tweepy
import requests
import os
import sys
import time
import textwrap
import re  # 정규표현식을 위해 필요
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
# 2. 트위터 클라이언트
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
except:
    print("⚠️ 트위터 클라이언트 생성 오류")

# ==========================================
# 3. 뉴스 소스 설정
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
# 4. 카드뉴스 이미지 생성 함수 (완전 개편)
# ==========================================
def create_info_image(text, source_name):
    try:
        # 디자인 설정
        width, height = 1080, 1080
        background_color = (20, 20, 20) # 다크 그레이 배경
        text_color = (240, 240, 240) # 밝은 회색 (본문)
        title_color = (255, 255, 255) # 흰색 (제목)
        accent_color = (50, 200, 255) # 하늘색 (출처 포인트)
        
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        
        font_path = "font.ttf"
        try:
            # 폰트 크기 조정 (가독성 개선)
            title_font = ImageFont.truetype(font_path, 70) # 제목 더 크게
            body_font = ImageFont.truetype(font_path, 42) # 본문 약간 키움
            source_font = ImageFont.truetype(font_path, 32)
        except:
            print("⚠️ 폰트 파일(font.ttf) 없음! 기본 폰트 사용")
            return None

        margin = 100 # 여백 확보
        current_h = 120
        
        # 상단 출처 표시
        draw.text((margin, 60), f"Market Radar | {source_name}", font=source_font, fill=accent_color)

        lines = text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line: continue

            # ★ 핵심: 마크다운(**) 제거 및 불렛포인트 기호 통일
            # 1. 마크다운 제거 (예: **제목** -> 제목)
            clean_line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            
            # 2. 불렛포인트 처리 (깨진 기호 대신 '✅ '로 통일)
            # 문장 시작이 특수문자거나 비어있으면 '✅ ' 추가
            if i > 0 and not clean_line.startswith(('$', '#', '✅')):
                 # 기존의 이상한 기호 제거 후 '✅ ' 붙이기
                 clean_line = re.sub(r"^[^가-힣a-zA-Z0-9$#\s]+", "", clean_line).strip()
                 clean_line = "✅ " + clean_line

            if i == 0: # 제목줄
                wrapped_lines = textwrap.wrap(clean_line, width=24)
                for wl in wrapped_lines:
                    draw.text((margin, current_h), wl, font=title_font, fill=title_color)
                    current_h += 90 # 제목 줄간격
                current_h += 50 # 제목-본문 사이 간격
                # 구분선
                draw.line([(margin, current_h), (width-margin, current_h)], fill=(80,80,80), width=3)
                current_h += 70
            else: # 본문
                wrapped_lines = textwrap.wrap(clean_line, width=38)
                for wl in wrapped_lines:
                    # 티커/해시태그 줄은 색상 다르게
                    fill_color = accent_color if wl.startswith(('$', '#')) else text_color
                    draw.text((margin, current_h), wl, font=body_font, fill=fill_color)
                    current_h += 60 # 본문 줄간격
            
            if current_h > height - 150: break
                
        temp_filename = "temp_news_card.png"
        image.save(temp_filename)
        return temp_filename
    except Exception as e:
        print(f"❌ 이미지 생성 에러: {e}")
        return None

# ==========================================
# 5. AI 요약 함수 (프롬프트 미세 조정)
# ==========================================
def summarize_news(category, title, link):
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    target_model = "gemini-1.5-flash"

    try:
        list_res = requests.get(list_url)
        if list_res.status_code == 200:
            models = list_res.json().get('models', [])
            for m in models:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    target_model = m['name'].replace('models/', '')
                    break
    except: pass

    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    이 뉴스를 '카드뉴스 이미지'에 넣을 수 있도록 텍스트를 정리해줘.
    
    [작성 규칙]
    1. 첫째 줄: 핵심 제목 (이모지 절대 쓰지 말 것, 한글로만, 마크다운(**) 쓰지 말 것)
    2. 본문:
       - 4~5개의 핵심 문장으로 요약 (개조식)
       - 각 문장 시작에 특수기호나 이모지 쓰지 말 것 (내가 코드에서 넣을 거임)
       - 구체적 수치($) 포함 필수
       - 문장은 너무 길지 않게 간결하게
    3. 맨 아래줄: 관련 티커 ($TSLA 등) 및 해시태그 2개
    4. 링크 절대 포함 금지
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

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"🚨 API 호출 에러 (코드 {response.status_code}): {response.text}")
            return None
            
    except Exception as e:
        print(f"🚨 연결 에러: {e}")
        return None

# ==========================================
# 6. 메인 실행
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
            
            summary = summarize_news(category, news.title, news.link)
            
            if summary:
                image_file = create_info_image(summary, source_name)
                
                try:
                    media_id = None
                    if image_file:
                        print("🖼️ 고품질 카드뉴스 생성 완료, 업로드 중...")
                        media = api.media_upload(image_file)
                        media_id = media.media_id
                    
                    tweet_text = f"[{category}]\n\n{summary}\n\n출처: {source_name}"
                    
                    if len(tweet_text) > 12000:
                        tweet_text = tweet_text[:11995] + "..."

                    if media_id:
                        response = client.create_tweet(text=tweet_text, media_ids=[media_id])
                    else:
                        response = client.create_tweet(text=tweet_text)
                        
                    tweet_id = response.data['id']
                    print("✅ 메인 트윗(이미지 포함) 업로드 성공!")
                    
                    reply_text = f"🔗 원문 기사 보러가기:\n{news.link}"
                    client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
                    print("✅ 링크 댓글 달기 성공!")

                    save_current_link(filename, news.link)
                    
                    if image_file and os.path.exists(image_file):
                        os.remove(image_file)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
            else:
                print("🚨 AI 요약 실패로 건너뜀")
        else:
            print("새 뉴스 없음.")
        time.sleep(2)
