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
def create_info_image(text, source_name):
    try:
        # 16:9 와이드 비율 설정 (HD 표준)
        width, height = 1200, 675 
        background_color = (15, 15, 15) # 더 깊은 블랙 배경
        text_color = (235, 235, 235)
        title_color = (255, 255, 255)
        accent_color = (0, 175, 255) # 브랜드 컬러 (딥 시안)
        
        image = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(image)
        
        font_path = "font.ttf"
        try:
            # 와이드 비율에 맞춘 폰트 크기 조정
            title_font = ImageFont.truetype(font_path, 58) 
            body_font = ImageFont.truetype(font_path, 34)
            source_font = ImageFont.truetype(font_path, 26)
        except:
            print("⚠️ 폰트 파일 오류")
            return None

        margin_x = 80 
        current_y = 100 
        
        # 1. 상단 워터마크
        draw.text((margin_x, 45), f"Market Radar | {source_name}", font=source_font, fill=accent_color)

        lines = text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if not line: continue

            # 텍스트 클리닝 (마크다운 및 지저분한 기호 제거)
            line = line.replace("**", "").replace("##", "")
            if i > 0 and not line.startswith(('$', '#')):
                 line = re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►\d\.]+\s*", "", line)

            # --- [그리기 로직] ---
            if i == 0: # 제목
                # 가로가 길어져서 width를 32까지 늘림 (한글 잘림 방지)
                wrapped_lines = textwrap.wrap(line, width=32)
                for wl in wrapped_lines:
                    draw.text((margin_x, current_y), wl, font=title_font, fill=title_color)
                    current_y += 75
                
                current_y += 30
                # 얇고 세련된 구분선
                draw.line([(margin_x, current_y), (width-margin_x, current_y)], fill=(60, 60, 60), width=2)
                current_y += 45
                
            else: # 본문
                is_tag = line.startswith(('$', '#'))
                # 본문 가로폭도 48로 넉넉하게 설정
                wrap_width = 48 
                wrapped_lines = textwrap.wrap(line, width=wrap_width)
                
                for wl in wrapped_lines:
                    if not is_tag:
                        # 세련된 사각형 불렛 (글자 높이에 맞춰 정렬)
                        bullet_size = 10
                        draw.rectangle(
                            [margin_x - 25, current_y + 14, margin_x - 25 + bullet_size, current_y + 14 + bullet_size],
                            fill=accent_color
                        )
                        fill_color = text_color
                    else:
                        fill_color = accent_color # 하단 태그 포인트 컬러

                    draw.text((margin_x, current_y), wl, font=body_font, fill=fill_color)
                    current_y += 48
                
                current_y += 10 # 줄간 여백
            
            if current_y > height - 80: break
                
        temp_filename = "temp_news_card.png"
        image.save(temp_filename)
        return temp_filename
    except Exception as e:
        print(f"❌ 이미지 생성 에러: {e}")
        return None

# ==========================================
# 5. AI 요약 함수 (본문 clean text 처리)
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

    이 뉴스를 '카드뉴스'와 '트윗 본문'에 쓸 수 있도록 텍스트를 정리해줘.
    
    [작성 규칙]
    1. 첫째 줄: 핵심 제목 (이모지/마크다운 금지)
    2. 본문:
       - 4~5개의 핵심 문장 요약
       - 문장 앞 기호 금지 (코드에서 처리함)
       - 구체적 수치($) 포함 필수
    3. 맨 아래줄: 관련 티커 ($TSLA 등) 및 해시태그 2개
    4. 마크다운(**) 절대 사용 금지.
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={GEMINI_API_KEY}"
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                          {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                          {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                          {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}]
    }
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            return text.replace("**", "").replace("##", "").strip()
        return None
    except: return None

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
                        media = api.media_upload(image_file)
                        media_id = media.media_id
                    
                    # 텍스트 본문 포맷팅 (카테고리 삭제, 제목부터 시작)
                    formatted_lines = []
                    for i, line in enumerate(summary.split('\n')):
                        line = line.strip()
                        if not line: continue
                        if i > 0 and not line.startswith(('$', '#')):
                             clean = re.sub(r"^[\-\*\•\·\✅\✔\▪\▫\►\d\.]+\s*", "", line)
                             formatted_lines.append(f"✅ {clean}")
                        else:
                             formatted_lines.append(line)
                    
                    final_text = "\n".join(formatted_lines) + f"\n\n출처: {source_name}"
                    
                    # 트윗 전송
                    response = client.create_tweet(text=final_text, media_ids=[media_id] if media_id else None)
                    tweet_id = response.data['id']
                    
                    # 댓글 링크
                    client.create_tweet(text=f"🔗 원문 기사:\n{news.link}", in_reply_to_tweet_id=tweet_id)
                    print("✅ 업로드 완료!")

                    save_current_link(filename, news.link)
                    if image_file and os.path.exists(image_file): os.remove(image_file)
                    
                except Exception as e:
                    print(f"❌ 트윗 실패: {e}")
        time.sleep(2)
