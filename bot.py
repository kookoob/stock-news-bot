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
# 4. 카드뉴스 생성 함수 (16:9 와이드 비율)
# ==========================================
def create_info_image(text_lines, source_name):
    try:
        width, height = 1200, 675 
        background_color = (15, 15, 15)
        text_color = (235, 235, 235)
        title_color = (255, 255, 255)
        accent_color = (0, 175, 255)
        
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        
        font_path = "font.ttf"
        try:
            title_font = ImageFont.truetype(font_path, 55) 
            body_font = ImageFont.truetype(font_path, 32)
            source_font = ImageFont.truetype(font_path, 24)
        except:
            return None

        margin_x = 80 
        current_y = 100 
        
        draw.text((margin_x, 45), f"Market Radar | {source_name}", font=source_font, fill=accent_color)

        for i, line in enumerate(text_lines):
            line = line.strip().replace("**", "")
            if not line: continue

            if i == 0: # 제목
                wrapped_lines = textwrap.wrap(line, width=30)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=title_font, fill=title_color)
                    current_y += 70
                current_y += 25
                draw.line([(margin_x, current_y), (width-margin_x, current_y)], fill=(60, 60, 60), width=2)
                current_y += 40
            else: # 본문 요약 (최대 7개 문장)
                # 불렛포인트 사각형 그리기
                bullet_size = 10
                draw.rectangle(
                    [margin_x - 25, current_y + 12, margin_x - 25 + bullet_size, current_y + 12 + bullet_size],
                    fill=accent_color
                )
                
                # 가로폭 넉넉하게 줄바꿈
                wrapped_lines = textwrap.wrap(line, width=50)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=body_font, fill=text_color)
                    current_y += 45
                current_y += 8
            
            if current_y > height - 60: break # 하단 잘림 방지
                
        temp_filename = "temp_card.png"
        image.save(temp_filename)
        return temp_filename
    except Exception as e:
        print(f"❌ 이미지 생성 에러: {e}")
        return None

# ==========================================
# 5. AI 요약 함수 (본문/이미지 텍스트 분리 추출)
# ==========================================
def summarize_news(title, link):
    prompt = f"""
    뉴스 제목: {title}
    뉴스 링크: {link}

    위 뉴스를 바탕으로 트위터 본문용 장문 글과 인포그래픽 이미지용 핵심 요약 글을 각각 작성해줘.

    [작성 규칙 - 공통]
    - 반드시 한국어로 작성할 것. (제목이 영어면 한글로 번역)
    - 존댓말 대신 축약체를 사용할 것 (~함, ~임, ~중, ~발표 등).
    - 마크다운(**)은 절대 사용하지 말 것.

    [작성 규칙 - 트위터 본문]
    - 제목은 한글 번역본 + 이모지 1개를 포함할 것.
    - 내용은 시장 영향, 수치, 데이터를 포함하여 최대한 자세하고 상세하게 작성할 것.
    - 가독성을 위해 문단을 나누고 체크표시(✅)를 사용할 것.
    - 하단에 관련 주식 티커($)와 해시태그(#)를 최대 3개 포함할 것. 티커는 반드시 포함할 것.

    [작성 규칙 - 인포그래픽 이미지]
    - 제목은 잘리지 않게 짧고 강렬한 한글 제목으로 작성.
    - 본문은 가장 핵심적인 문장만 최대 7개 이내로 요약할 것.
    - 이미지 밖으로 나가지 않도록 각 문장은 아주 간결하게 작성할 것.

    응답은 반드시 아래 형식을 지켜줘:
    ---BODY---
    (본문 내용)
    ---IMAGE---
    (이미지용 제목)
    (이미지용 요약 문장 1)
    (이미지용 요약 문장 2)...
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            full_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            body = full_text.split("---BODY---")[1].split("---IMAGE---")[0].strip()
            image_text = full_text.split("---IMAGE---")[1].strip().split('\n')
            return body, image_text
        return None, None
    except: return None, None

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
            body_text, img_lines = summarize_news(news.title, news.link)
            
            if body_text and img_lines:
                image_file = create_info_image(img_lines, source_name)
                
                try:
                    media_id = None
                    if image_file:
                        media = api.media_upload(image_file)
                        media_id = media.media_id
                    
                    final_text = body_text + f"\n\n출처: {source_name}"
                    
                    # 트윗 전송 (이미지 포함)
                    response = client.create_tweet(text=final_text, media_ids=[media_id] if media_id else None)
                    tweet_id = response.data['id']
                    
                    # 답글로 링크 달기
                    client.create_tweet(text=f"🔗 원문 기사:\n{news.link}", in_reply_to_tweet_id=tweet_id)
                    print("✅ 업로드 완료!")

                    save_current_link(filename, news.link)
                    if image_file and os.path.exists(image_file): os.remove(image_file)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
        time.sleep(2)
